# -*- coding: utf-8 -*-
"""Vision-based chess notation corrections using GPT Vision or Claude."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import string
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import fitz
from openai import OpenAI

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from .config import (
    VISION_MODEL,
    VISION_MAX_BATCH,
    VISION_DPI,
    VISION_ENABLED,
    VISION_DELAY_BETWEEN_BATCHES,
    VISION_USE_CLAUDE,
    ANTHROPIC_API_KEY,
    CLAUDE_VISION_MODEL,
    VISION_USE_BATCH,
    VISION_CLAUDE_DIRECT_TRANSLATION,
    TARGET_BOLD_FONT,
    B_START,
    B_END,
)

logger = logging.getLogger("chess_pdf.vision")


@dataclass
class SpanCandidate:
    candidate_id: str
    block_index: int
    span_index: int
    span: Dict
    block: Dict
    rect: fitz.Rect
    text: str
    cache_key: Optional[str] = None
    image_b64: Optional[str] = None
    clip_rect: Optional[fitz.Rect] = None


_POLISH_LETTERS = set("ĄĆĘŁŃÓŚŹŻąćęłńóśźż")
_ASCII_LETTERS = set(string.ascii_letters)
_DIGITS = set(string.digits)
_ALLOWED_WHITESPACE = {" ", "\n"}
_ALLOWED_PUNCTUATION = set(".,:;!?()[]{}\"'`+-=*/\\#%@&$^_|~<>")
_PIECE_GLYPH_MAP = {
    "\u2654": "K", "\u2655": "Q", "\u2656": "R", "\u2657": "B", "\u2658": "N", "\u2659": "",
    "\u265A": "K", "\u265B": "Q", "\u265C": "R", "\u265D": "B", "\u265E": "N", "\u265F": "",
}
_SPECIAL_SYMBOL_MAP = {
    "\ufeff": "", "\u00a0": " ", "\u00ad": "", "\u00b1": "+/-", "\u00b7": ".",
    "\u00bb": '"', "\u00ab": '"', "\u00d7": "x", "\u00f7": ":",
    "\u2007": " ", "\u2009": " ", "\u200a": " ",
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2015": "-",
    "\u2018": "'", "\u2019": "'", "\u201a": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"',
    "\u2026": "...", "\u202f": " ", "\u2032": "'", "\u2033": '"',
    "\u2020": "+", "\u2021": "+", "\u271d": "+", "\u271e": "+",
    "\u2212": "-", "\u2213": "-/+", "\u221e": "?", "\u2219": ".",
    "\u2190": "<-", "\u2192": "->", "\u2194": "<->", "\u21d2": "->", "\u21d4": "<->",
    "\u2715": "x",
}


def _is_allowed_character(ch: str) -> bool:
    if ch in _ALLOWED_WHITESPACE or ch in _ALLOWED_PUNCTUATION:
        return True
    if ch in _POLISH_LETTERS or ch in _ASCII_LETTERS or ch in _DIGITS:
        return True
    return False


def _sanitize_span_copy(span: Dict) -> Dict:
    """Create a JSON-serializable shallow copy of a span."""
    copy = dict(span)
    rect = copy.get("rect")
    if isinstance(rect, fitz.Rect):
        copy["rect"] = [rect.x0, rect.y0, rect.x1, rect.y1]
    bbox = copy.get("bbox")
    if isinstance(bbox, fitz.Rect):
        copy["bbox"] = [bbox.x0, bbox.y0, bbox.x1, bbox.y1]
    elif isinstance(bbox, tuple):
        copy["bbox"] = list(bbox)
    is_bold = copy.get("is_bold")
    if is_bold is None:
        is_bold = copy.get("bold")
    if is_bold is None:
        is_bold = _is_bold_font(copy.get("font", ""))
    copy["is_bold"] = bool(is_bold)
    return copy


_MOVE_TOKEN_RE = re.compile(r"\d{1,3}\.{1,3}[^\s]+")


def _extract_move_tokens(text: str) -> List[str]:
    """Extract move tokens (e.g., 16.Rac1, 3...Nf6) from text."""
    if not text:
        return []
    return _MOVE_TOKEN_RE.findall(text)


def _normalize_transcribed_text(text: str) -> str:
    if not text:
        return text

    result: List[str] = []
    reported: set[str] = set()

    for ch in text:
        if ch == "\r":
            continue
        if ch == "\t":
            result.append(" ")
            continue
        if ch in _PIECE_GLYPH_MAP:
            mapped = _PIECE_GLYPH_MAP[ch]
            if mapped:
                result.append(mapped)
            continue
        if ch in _SPECIAL_SYMBOL_MAP:
            mapped = _SPECIAL_SYMBOL_MAP[ch]
            if mapped:
                result.append(mapped)
            continue
        if _is_allowed_character(ch):
            result.append(ch)
            continue
        if ch not in reported and ch.strip():
            logger.debug("Dropping unsupported character: %r (U+%04X)", ch, ord(ch))
            reported.add(ch)

    normalized = "".join(result)
    while "  " in normalized:
        normalized = normalized.replace("  ", " ")
    normalized = normalized.replace(" \n", "\n").replace("\n ", "\n")
    normalized = re.sub(r"\+\s*/\s*-", "+/-", normalized)
    normalized = re.sub(r"-\s*/\s*\+", "-/+", normalized)
    normalized = re.sub(r"\b(\d+)\.\.(?=[^\.\s])", r"\1...", normalized)
    return normalized


class VisionCorrectionService:
    """Identify suspicious spans and use GPT Vision to correct them."""

    def __init__(self, model: Optional[str] = None, max_batch: int = None, dpi: int = None, debug_output_dir: Optional[str] = None):
        self.model = model or VISION_MODEL
        self.max_batch = max_batch or VISION_MAX_BATCH
        self.dpi = dpi or VISION_DPI
        self.enabled = bool(VISION_ENABLED and self.model)
        self._client: Optional[OpenAI] = None
        self._cache: Dict[str, str] = {}
        self.debug_output_dir = debug_output_dir
        self._debug_data: List[Dict] = []
        self.direct_translation = False

        logger.info("=" * 60)
        logger.info("VISION API INITIALIZATION")
        logger.info(f"  VISION_ENABLED env: {VISION_ENABLED}")
        logger.info(f"  Model: {self.model}")
        logger.info(f"  Final enabled status: {self.enabled}")
        logger.info("=" * 60)

        if not self.enabled:
            logger.warning("Vision corrections DISABLED (missing model or env toggle)")

    @property
    def is_enabled(self) -> bool:
        return self.enabled

    def _ensure_client(self) -> None:
        if self._client is None:
            try:
                self._client = OpenAI()
            except Exception as exc:
                self.enabled = False
                logger.warning("Cannot initialise OpenAI client: %s", exc)

    def correct_page(self, page: fitz.Page, blocks: List[Dict], page_number: int = 0) -> None:
        if not self.is_enabled:
            logger.warning("Vision corrections DISABLED - check CHESS_VISION_ENABLED env var")
            return

        self._debug_data = []
        candidates = list(_collect_candidates(blocks))
        logger.info(f"Vision API: Found {len(candidates)} suspicious spans to check")
        if not candidates:
            return

        self._ensure_client()
        if not self._client:
            logger.error("Vision API: Failed to initialize OpenAI client!")
            return

        page_rect = page.rect
        to_query: List[SpanCandidate] = []

        for cand in candidates:
            clip = _expanded_rect(cand.rect, page_rect, pad=5.0)
            if clip is None or clip.width <= 0 or clip.height <= 0:
                continue
            image_bytes = _grab_region(page, clip, self.dpi)
            if not image_bytes:
                continue
            digest = hashlib.sha256(image_bytes).hexdigest()
            cand.cache_key = digest

            if digest in self._cache:
                new_text = self._cache[digest]
                _apply_correction(cand, new_text, add_markers=False)
            else:
                cand.image_b64 = base64.b64encode(image_bytes).decode("ascii")
                cand.clip_rect = clip
                to_query.append(cand)

                if self.debug_output_dir:
                    import os
                    img_path = os.path.join(self.debug_output_dir, f"vision_img_{cand.candidate_id}.png")
                    try:
                        with open(img_path, 'wb') as f:
                            f.write(image_bytes)
                    except Exception as e:
                        logger.warning(f"Failed to save Vision image: {e}")

        logger.info(f"Vision API: Sending {len(to_query)} spans (cached: {len(candidates) - len(to_query)})")

        if not to_query:
            return

        remaining: List[SpanCandidate] = list(to_query)
        failed_first_attempt: List[SpanCandidate] = []
        schema = {
            "type": "object",
            "properties": {
                "corrections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "text": {"type": "string"},
                        },
                        "required": ["id", "text"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["corrections"],
            "additionalProperties": False,
        }

        current_batch_size = min(self.max_batch, len(remaining)) or 0
        rate_attempts = 0

        while remaining and current_batch_size > 0:
            batch = remaining[:current_batch_size]
            try:
                system_prompt = self._build_vision_prompt()
                content = [{"type": "text", "text": system_prompt}]

                for cand in batch:
                    visible = cand.text.strip() or "<empty>"
                    content.append({
                        "type": "text",
                        "text": f"\n\n=== BLOCK {cand.candidate_id} ===\nOCR text:\n{visible}\n\nTranscribe this chess notation from the image below:",
                    })
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{cand.image_b64}", "detail": "high"},
                    })

                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": content}],
                    response_format={"type": "json_schema", "json_schema": {"name": "chess_corrections", "schema": schema, "strict": True}},
                    temperature=0,
                )

                payload = _parse_response_json(response)
                processed_ids = set()

                for item in payload.get("corrections", []):
                    cand = _find_candidate(batch, item.get("id"))
                    if not cand:
                        continue
                    processed_ids.add(cand.candidate_id)
                    new_text = (item.get("text") or "").strip()
                    if not new_text:
                        continue
                    old_text = cand.text

                    if not _validate_correction_length(old_text, new_text, cand.candidate_id):
                        logger.warning(f"REJECTED Vision correction for {cand.candidate_id}: Length mismatch!")
                        continue

                    self._cache[cand.cache_key] = new_text
                    _apply_correction(cand, new_text, add_markers=False)

                for cand in batch:
                    if cand.candidate_id not in processed_ids:
                        has_chess_notation = bool(
                            re.search(r'\d+\.', cand.text) or
                            re.search(r'\.\.\.[a-h]|[a-h]\d', cand.text) or
                            re.search(r'[!?+#±∞]', cand.text) or
                            any(ord(ch) > 127 for ch in cand.text)
                        )
                        if has_chess_notation:
                            failed_first_attempt.append(cand)
                        _apply_correction(cand, cand.text, add_markers=False)

                del remaining[:len(batch)]
                current_batch_size = min(self.max_batch, len(remaining)) or 0
                rate_attempts = 0

                if remaining and VISION_DELAY_BETWEEN_BATCHES > 0:
                    time.sleep(VISION_DELAY_BETWEEN_BATCHES)

            except Exception as exc:
                if _is_rate_limit_error(exc):
                    rate_attempts += 1
                    delay = _retry_delay_seconds(exc, rate_attempts)
                    delay = max(delay, 3.0 * rate_attempts)
                    logger.warning("Vision rate limit hit. Sleeping %.2fs", delay)
                    time.sleep(delay)
                    current_batch_size = max(1, current_batch_size // 2)
                    if rate_attempts >= 5:
                        del remaining[:len(batch)]
                        rate_attempts = 0
                        current_batch_size = min(self.max_batch, len(remaining)) or 0
                    continue

                logger.warning("Vision correction batch failed: %s", exc)
                del remaining[:len(batch)]
                rate_attempts = 0
                current_batch_size = min(self.max_batch, len(remaining)) or 0

        if failed_first_attempt:
            logger.info(f"RETRY: Re-processing {len(failed_first_attempt)} blocks")
            for retry_cand in failed_first_attempt:
                try:
                    self._retry_single_candidate(retry_cand, schema)
                except Exception as exc:
                    logger.warning(f"RETRY failed for {retry_cand.candidate_id}: {exc}")

        _verify_chess_piece_consistency(blocks, page_number)

    def _build_vision_prompt(self) -> str:
        return (
            "You are a chess notation transcription expert.\n\n"
            "TASK: Transcribe the ENTIRE text from the image, replacing GRAPHICAL CHESS PIECE ICONS with standard notation letters.\n\n"
            "CRITICAL: The images contain GRAPHICAL ICONS/GLYPHS of chess pieces, NOT text characters!\n\n"
            "Chess piece ICONS:\n"
            "- Crown icons → Q (Queen)\n"
            "- Horse head icons → N (Knight)\n"
            "- Tower/castle icons → R (Rook)\n"
            "- Pointed hat icons → B (Bishop)\n"
            "- King crown icon → K (King)\n\n"
            "OCR garbage patterns:\n"
            "- ² (superscript 2) = Queen → Q\n"
            "- YlY, YIY, Y!f, 'i;Y = Queen → Q\n"
            "- lLl, *, ttl, lil = Knight → N\n"
            "- J\"!, g+letters = Rook → R\n"
            "- .i, ig = Bishop → B\n\n"
            "RULES:\n"
            "1. Look at the IMAGE - identify chess piece ICONS\n"
            "2. Replace ALL OCR garbage with correct letters: Q, N, R, B, K\n"
            "3. BE CONSISTENT - same icon = same letter throughout\n"
            "4. Return COMPLETE TEXT - do NOT abbreviate or summarize\n"
        )

    def _retry_single_candidate(self, cand: SpanCandidate, schema: Dict) -> None:
        content = [
            {"type": "text", "text": self._build_vision_prompt()},
            {"type": "text", "text": f"\n\n=== BLOCK {cand.candidate_id} (RETRY) ===\nOCR text:\n{cand.text}\n\nTranscribe:"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{cand.image_b64}", "detail": "high"}},
        ]

        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_schema", "json_schema": {"name": "chess_corrections", "schema": schema, "strict": True}},
            temperature=0,
        )

        payload = _parse_response_json(response)
        for item in payload.get("corrections", []):
            if item.get("id") == cand.candidate_id:
                new_text = (item.get("text") or "").strip()
                if new_text and new_text != cand.text:
                    if _validate_correction_length(cand.text, new_text, cand.candidate_id):
                        self._cache[cand.cache_key] = new_text
                        _apply_correction(cand, new_text)
                        logger.info(f"RETRY SUCCESS: Block {cand.block_index} fixed")
                break


def _verify_chess_piece_consistency(blocks: List[Dict], page_number: int) -> None:
    """Verify chess piece icons were transcribed consistently."""
    all_text = " ".join(block.get("text", "") for block in blocks)

    remaining_garbage = {
        'Knight (lLl)': all_text.count('lLl'),
        'Knight (ttl)': all_text.count('ttl'),
        'Knight (lil)': all_text.count('lil'),
        'Queen (²)': all_text.count('²'),
        'Queen (YlY)': all_text.count('YlY'),
    }
    remaining_garbage = {k: v for k, v in remaining_garbage.items() if v > 0}

    if remaining_garbage:
        logger.warning(f"PAGE {page_number} - Chess piece OCR garbage still present: {remaining_garbage}")


class ClaudeVisionService:
    """Vision correction service using Claude (Anthropic)."""

    def __init__(self, model: Optional[str] = None, max_batch: int = None, dpi: int = None, debug_output_dir: Optional[str] = None):
        self.model = model or CLAUDE_VISION_MODEL
        self.max_batch = max_batch or VISION_MAX_BATCH
        self.dpi = dpi or VISION_DPI
        self.use_batch = VISION_USE_BATCH
        self.enabled = bool(VISION_ENABLED and self.model and ANTHROPIC_AVAILABLE and ANTHROPIC_API_KEY)
        self._client: Optional[Anthropic] = None
        self._cache: Dict[str, str] = {}
        self.debug_output_dir = debug_output_dir
        self._debug_data: List[Dict] = []
        self.direct_translation = bool(VISION_CLAUDE_DIRECT_TRANSLATION)

        logger.info("=" * 60)
        logger.info("CLAUDE VISION API INITIALIZATION")
        logger.info(f"  Model: {self.model}")
        logger.info(f"  Direct translation: {self.direct_translation}")
        logger.info(f"  Enabled: {self.enabled}")
        logger.info("=" * 60)

        if not self.enabled:
            if not ANTHROPIC_AVAILABLE:
                logger.warning("Claude Vision DISABLED - anthropic package not installed")
            elif not ANTHROPIC_API_KEY:
                logger.warning("Claude Vision DISABLED - ANTHROPIC_API_KEY not set")

    @property
    def is_enabled(self) -> bool:
        return self.enabled

    def _ensure_client(self) -> None:
        if self._client is None:
            try:
                self._client = Anthropic(api_key=ANTHROPIC_API_KEY)
            except Exception as exc:
                self.enabled = False
                logger.warning("Cannot initialise Anthropic client: %s", exc)

    def correct_page(self, page: fitz.Page, blocks: List[Dict], page_number: int = 0) -> None:
        if not self.is_enabled:
            logger.warning("Claude Vision DISABLED")
            return

        self._debug_data = []
        candidates = list(_collect_candidates(blocks, include_all=self.direct_translation))
        logger.info(f"Claude Vision: Found {len(candidates)} suspicious spans")
        if not candidates:
            _verify_chess_piece_consistency(blocks, page_number)
            return

        self._ensure_client()
        if not self._client:
            return

        page_rect = page.rect
        to_query: List[SpanCandidate] = []

        for cand in candidates:
            clip = _expanded_rect(cand.rect, page_rect, pad=5.0)
            if clip is None or clip.width <= 0 or clip.height <= 0:
                continue
            image_bytes = _grab_region(page, clip, self.dpi)
            if not image_bytes:
                continue
            digest = hashlib.sha256(image_bytes).hexdigest()
            cand.cache_key = digest

            if digest in self._cache:
                new_text = self._cache[digest]
                _apply_correction(cand, new_text, add_markers=self.direct_translation)
            else:
                cand.image_b64 = base64.b64encode(image_bytes).decode("ascii")
                cand.clip_rect = clip
                to_query.append(cand)

        logger.info(f"Claude Vision: Sending {len(to_query)} blocks (cached: {len(candidates) - len(to_query)})")

        if not to_query:
            _verify_chess_piece_consistency(blocks, page_number)
            return

        self._process_candidates_sync(to_query)
        _verify_chess_piece_consistency(blocks, page_number)

    def _process_candidates_sync(self, candidates: List[SpanCandidate]) -> None:
        """Process candidates using Claude's synchronous API."""
        remaining = list(candidates)
        current_batch_size = min(self.max_batch, len(remaining)) or 0
        rate_attempts = 0

        while remaining and current_batch_size > 0:
            batch = remaining[:current_batch_size]
            try:
                for cand in batch:
                    self._process_single_candidate(cand)

                del remaining[:len(batch)]
                current_batch_size = min(self.max_batch, len(remaining)) or 0
                rate_attempts = 0

                if remaining and VISION_DELAY_BETWEEN_BATCHES > 0:
                    time.sleep(VISION_DELAY_BETWEEN_BATCHES)

            except Exception as exc:
                if _is_rate_limit_error(exc):
                    rate_attempts += 1
                    delay = max(_retry_delay_seconds(exc, rate_attempts), 3.0 * rate_attempts)
                    logger.warning("Claude Vision rate limit. Sleeping %.2fs", delay)
                    time.sleep(delay)
                    current_batch_size = max(1, current_batch_size // 2)
                    if rate_attempts >= 5:
                        del remaining[:len(batch)]
                        rate_attempts = 0
                        current_batch_size = min(self.max_batch, len(remaining)) or 0
                    continue

                logger.warning("Claude Vision batch failed: %s", exc)
                del remaining[:len(batch)]
                rate_attempts = 0
                current_batch_size = min(self.max_batch, len(remaining)) or 0

    def _process_single_candidate(self, cand: SpanCandidate) -> None:
        if self.direct_translation:
            self._process_single_candidate_direct(cand)
        else:
            self._process_single_candidate_transcribe(cand)

    def _process_single_candidate_transcribe(self, cand: SpanCandidate) -> None:
        """Transcribe the image into clean English text."""
        try:
            system_prompt = (
                "You are a chess notation transcription expert.\n\n"
                "TASK: Read the chess book image and return the exact English text.\n"
                "- Convert graphical chess piece icons to SAN letters: Q, N, R, B, K\n"
                "- Preserve move numbers, punctuation, evaluation symbols\n"
                "- Do NOT translate into Polish\n"
                "- Return only the text"
            )
            instructions = f"=== BLOCK {cand.candidate_id} ===\nOCR preview:\n{cand.text or '<empty>'}\n\nTranscribe:"

            message = self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                temperature=0,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": instructions},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": cand.image_b64}},
                    ],
                }],
            )
            self._finalise_claude_response(cand, message, context="transcribe")
        except Exception as exc:
            logger.warning("Claude Vision transcription failed for %s: %s", cand.candidate_id, exc)

    def _process_single_candidate_direct(self, cand: SpanCandidate) -> None:
        """Translate the image directly into Polish."""
        try:
            system_prompt = (
                "You are a professional chess book translator (English to Polish).\n\n"
                "TASK:\n"
                "1. Read the English text from the image\n"
                "2. Translate commentary into fluent Polish with diacritics\n"
                "3. Keep chess notation unchanged\n"
                "4. Wrap bold fragments with [[B]]...[[/B]]\n"
                "5. Replace chess icons with SAN letters (N, B, R, Q, K)\n\n"
                "Return only the translated text."
            )
            instructions = "Read and translate this chess book text to Polish:"

            message = self._client.messages.create(
                model=self.model,
                max_tokens=2048,
                temperature=0,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": instructions},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": cand.image_b64}},
                    ],
                }],
            )
            self._finalise_claude_response(cand, message, context="direct")
        except Exception as exc:
            logger.warning("Claude Vision direct translation failed for %s: %s", cand.candidate_id, exc)

    def _finalise_claude_response(self, cand: SpanCandidate, message, *, context: str) -> None:
        new_text = ""
        for block in getattr(message, "content", []):
            if getattr(block, "type", None) == "text":
                new_text += block.text
        old_text = cand.text
        new_text = _normalize_transcribed_text(new_text).strip()
        if not new_text:
            return
        if not _validate_correction_length(old_text, new_text, cand.candidate_id):
            return
        if cand.cache_key:
            self._cache[cand.cache_key] = new_text
        _apply_correction(cand, new_text, add_markers=(context == "direct"))


def _collect_candidates(blocks: Iterable[Dict], *, include_all: bool = False) -> Iterable[SpanCandidate]:
    """Collect BLOCKS for Vision API correction."""
    for b_idx, block in enumerate(blocks):
        if "_ocr_spans_backup" not in block:
            spans = block.get("spans")
            if spans is not None:
                block["_ocr_spans_backup"] = [_sanitize_span_copy(s) for s in spans]
        if "_style_spans_backup" not in block:
            spans = block.get("spans")
            if spans is not None:
                block["_style_spans_backup"] = [_sanitize_span_copy(s) for s in spans]

        text = block.get("text", "").strip()
        if not text:
            continue

        bbox = block.get("bbox")
        if not bbox:
            continue

        if (not include_all) and len(text) > 300:
            has_notation = bool(re.search(r'\d|[a-h][1-8]|[KQRBN]|[!?+#]|\.\.\.', text))
            has_special = any(ord(ch) > 127 for ch in text)
            if not has_notation and not has_special:
                continue

        candidate_id = f"b{b_idx}"
        rect = fitz.Rect(bbox)

        yield SpanCandidate(
            candidate_id=candidate_id,
            block_index=b_idx,
            span_index=0,
            span={"text": text},
            block=block,
            rect=rect,
            text=text
        )


def _expanded_rect(rect: fitz.Rect, page_rect: fitz.Rect, pad: float = 1.0) -> Optional[fitz.Rect]:
    if rect is None:
        return None
    expanded = fitz.Rect(rect)
    expanded.x0 = max(page_rect.x0, expanded.x0 - pad)
    expanded.y0 = max(page_rect.y0, expanded.y0 - pad)
    expanded.x1 = min(page_rect.x1, expanded.x1 + pad)
    expanded.y1 = min(page_rect.y1, expanded.y1 + pad)
    if expanded.width <= 0 or expanded.height <= 0:
        return None
    return expanded


def _grab_region(page: fitz.Page, rect: fitz.Rect, dpi: int) -> Optional[bytes]:
    try:
        pix = page.get_pixmap(clip=rect, dpi=dpi, alpha=False)
        return pix.tobytes("png")
    except Exception as exc:
        logger.debug("Pixmap extraction failed: %s", exc)
        return None


def _is_bold_font(font_name: str) -> bool:
    """Check if a font name indicates bold text."""
    if not font_name:
        return False
    fname = font_name.lower()
    fname_normalized = fname.replace(" ", "").replace("-", "").replace("_", "")
    target_normalized = TARGET_BOLD_FONT.lower().replace(" ", "").replace("-", "").replace("_", "")
    if target_normalized in fname_normalized:
        return True
    return any(keyword in fname for keyword in ("bold", "semibold", "demi", "black"))


def _auto_tag_bold_spans(original_spans: List[Dict], old_text: str, new_text: str) -> str:
    """Auto-tag bold text in Vision output based on OCR font info."""
    if not new_text or not original_spans:
        return new_text

    span_infos: List[Dict] = []
    for span in original_spans:
        raw = span.get("text") or ""
        if not raw.strip():
            continue
        normalized = _normalize_transcribed_text(raw).strip()
        if not normalized:
            continue
        is_bold = span.get("is_bold", False) or _is_bold_font(span.get("font", ""))
        span_infos.append({"text": normalized, "is_bold": is_bold})

    if not span_infos:
        return new_text

    merged: List[Dict] = []
    for info in span_infos:
        if merged and merged[-1]["is_bold"] == info["is_bold"]:
            merged[-1]["text"] += info["text"]
        else:
            merged.append({"text": info["text"], "is_bold": info["is_bold"]})

    cursor = 0
    any_tagged = False
    tagged_parts: List[str] = []

    for info in merged:
        fragment = info["text"] or ""
        if not fragment:
            continue

        pattern = re.escape(fragment).replace(r"\ ", r"\s+").replace(r"\n", r"\s*")
        regex = re.compile(pattern, re.IGNORECASE)
        match = regex.search(new_text, cursor) or regex.search(new_text)
        if not match:
            continue

        idx, end = match.span()
        if cursor < idx:
            tagged_parts.append(new_text[cursor:idx])

        selected = new_text[idx:end]
        if info["is_bold"]:
            tagged_parts.append(f"{B_START}{selected}{B_END}")
            any_tagged = True
        else:
            tagged_parts.append(selected)
        cursor = end

    tagged_parts.append(new_text[cursor:])
    result = "".join(tagged_parts)

    if not any_tagged:
        bold_tokens: List[str] = []
        for info in merged:
            if info["is_bold"]:
                bold_tokens.extend(_extract_move_tokens(info["text"]))

        if bold_tokens:
            lowered = new_text.lower()
            result_parts: List[str] = []
            cursor = 0
            for token in bold_tokens:
                token_lower = token.lower()
                idx = lowered.find(token_lower, cursor)
                if idx == -1:
                    idx = lowered.find(token_lower)
                if idx == -1:
                    continue
                if idx < len(B_START) or new_text[idx-len(B_START):idx] != B_START:
                    result_parts.append(new_text[cursor:idx])
                    result_parts.append(f"{B_START}{new_text[idx:idx+len(token)]}{B_END}")
                    cursor = idx + len(token)
            result_parts.append(new_text[cursor:])
            candidate = "".join(result_parts)
            if candidate != new_text:
                return candidate

    return result


def _apply_correction(candidate: SpanCandidate, new_text: str, *, add_markers: bool = True) -> None:
    """Apply Vision correction to a block."""
    block = candidate.block
    old_text = candidate.text

    cleaned_text = _normalize_transcribed_text(new_text).strip()
    if not cleaned_text:
        return

    has_vision_markers = (B_START in cleaned_text) or (B_END in cleaned_text)

    if add_markers:
        if has_vision_markers:
            new_text_with_bold = cleaned_text
        else:
            original_spans = block.get("_ocr_spans_backup") or block.get("spans", [])
            if original_spans:
                new_text_with_bold = _auto_tag_bold_spans(original_spans, block.get("text", ""), cleaned_text)
            else:
                new_text_with_bold = cleaned_text
    else:
        if has_vision_markers:
            cleaned_text = cleaned_text.replace(B_START, "").replace(B_END, "")
        new_text_with_bold = cleaned_text

    block["text"] = new_text_with_bold if add_markers else cleaned_text
    if add_markers:
        block["translated_marked"] = new_text_with_bold
    else:
        block.pop("translated_marked", None)

    spans = block.get("spans") or []
    if not spans:
        backup_spans = block.get("_ocr_spans_backup") or []
        spans = [_sanitize_span_copy(s) for s in backup_spans]
    if spans:
        first = True
        for span in spans:
            span["vision_corrected"] = True
            if first:
                span["text"] = new_text_with_bold if add_markers else cleaned_text
                first = False
            else:
                span["text"] = ""
        block["spans"] = spans

    if cleaned_text.strip() != old_text.strip():
        logger.info(
            "Vision corrected BLOCK %s: '%s' -> '%s'",
            candidate.block_index,
            old_text[:50] + ("..." if len(old_text) > 50 else ""),
            cleaned_text[:50] + ("..." if len(cleaned_text) > 50 else ""),
        )


def _validate_correction_length(ocr_text: str, vision_text: str, candidate_id: str) -> bool:
    """Validate Vision output respects text length constraints."""
    ocr_len = len(ocr_text)
    vision_len = len(vision_text)

    if vision_len <= ocr_len:
        return True

    max_allowed_len = int(ocr_len * 3.0)
    if vision_len <= max_allowed_len:
        return True

    logger.warning(f"[{candidate_id}] Vision added EXCESSIVE text: {ocr_len} -> {vision_len} chars")
    return False


def _parse_response_json(response) -> Dict:
    """Decode JSON payload from chat.completions response."""
    if not response:
        return {}

    try:
        if hasattr(response, 'choices') and len(response.choices) > 0:
            message = response.choices[0].message
            if hasattr(message, 'content') and message.content:
                return json.loads(message.content)
    except (TypeError, json.JSONDecodeError):
        pass
    return {}


def _find_candidate(batch: List[SpanCandidate], candidate_id: str) -> Optional[SpanCandidate]:
    for cand in batch:
        if cand.candidate_id == candidate_id:
            return cand
    return None


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    if "rate limit" in text or "limit reached" in text:
        return True
    status = getattr(exc, "status_code", None)
    if status == 429:
        return True
    code = getattr(getattr(exc, "error", None), "code", None)
    return code == "rate_limit_exceeded"


def _retry_delay_seconds(exc: Exception, attempt: int) -> float:
    text = str(exc)
    match = re.search(r"try again in ([0-9.]+)(ms|s)", text, re.IGNORECASE)
    if match:
        value = float(match.group(1))
        if match.group(2).lower() == "ms":
            value /= 1000.0
        return max(value, 0.1)
    return min(0.5 * (2 ** (attempt - 1)), 10.0)
