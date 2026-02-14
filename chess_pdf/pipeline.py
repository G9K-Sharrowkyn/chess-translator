# -*- coding: utf-8 -*-
"""Main translation pipeline for chess PDF books."""

from typing import Optional
import fitz
import os
import re

from .config import log, VISION_USE_CLAUDE
from .fonts import get_fonts_with_polish_chars
from .geometry import find_board_axis_regions
from .extraction import extract_text_blocks
from .san import postprocess_translated_marked
from .translation_core import translate_blocks_intelligent, _build_runs_from_block
from .rendering import render_translated_page, parse_marked_segments
from .vision_corrections import VisionCorrectionService, ClaudeVisionService
from .diagnostics import run_diagnostics_on_translation

_ENGLISH_HINT_RE = re.compile(
    r"\b(the|and|with|for|this|that|was|were|would|should|could|"
    r"black|white|move|correct|analysis|leading|clear|advantage|cannot|"
    r"game|position|next|take|pain|follows)\b",
    flags=re.IGNORECASE,
)
_POLISH_HINT_RE = re.compile(
    r"[ąćęłńóśźż]|"
    r"\b(i|oraz|że|się|jest|był|była|białe|czarne|ruch|przewag|wkrótce|pozycj)\b",
    flags=re.IGNORECASE,
)


def _looks_like_english_prose(text: str) -> bool:
    plain = (text or "").replace("[[B]]", "").replace("[[/B]]", "").strip()
    if not plain:
        return False
    if len(plain) < 18:
        return False
    english_hits = len(_ENGLISH_HINT_RE.findall(plain))
    polish_hits = len(_POLISH_HINT_RE.findall(plain))
    return english_hits >= 2 and polish_hits == 0


def _rebuild_block_text_from_spans(block: dict) -> str:
    """Rebuild block text from spans after Vision corrections."""
    spans = block.get("spans", [])
    if not spans:
        return block.get("text", "")

    parts = []
    for span in spans:
        text = span.get("text", "")
        if text:
            parts.append(text)

    return "".join(parts)


def _save_simple_debug_comparison(debug_dir: str, page_number: int, blocks: list) -> None:
    """Save OCR -> Vision -> Translation comparison for debugging."""
    import json

    os.makedirs(debug_dir, exist_ok=True)

    debug_blocks = []
    for b_idx, block in enumerate(blocks):
        ocr_text = block.get("ocr_text", "")
        vision_text = block.get("vision_text", "")
        final_text = block.get("translated_marked", "")

        source_runs = _build_runs_from_block(block) if block else []
        source_bold = [r.get("text", "") for r in source_runs if r.get("bold")]

        translated_segments = parse_marked_segments(final_text) if final_text else []
        translated_bold = [s.get("text", "") for s in translated_segments if s.get("bold")]

        if ocr_text or vision_text or final_text:
            debug_blocks.append({
                "block_index": b_idx,
                "ocr_text": ocr_text,
                "vision_text": vision_text,
                "final_text": final_text,
                "source_bold_runs": source_bold,
                "translated_bold_segments": translated_bold,
                "ocr_spans": block.get("_ocr_spans_backup")
            })

    output = {
        "page_number": page_number,
        "total_blocks": len(debug_blocks),
        "blocks": debug_blocks
    }

    json_path = os.path.join(debug_dir, f"page_{page_number}.json")
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        log.info(f"Debug comparison saved to: {json_path}")
    except Exception as e:
        log.error(f"Failed to save debug comparison JSON: {e}")


def translate_pdf(
    input_path: str,
    output_path: str,
    translator,
    mode: str = "word",
    glossary_path: Optional[str] = None,
    run_fixpass: bool = True,
    fix_rules_path: Optional[str] = None,
    fix_in_place: bool = False,
    vision_debug_dir: Optional[str] = None,
    diagnostics_dir: Optional[str] = None,
) -> str:
    """Translate a chess PDF book from English to Polish."""
    if not output_path.lower().endswith(".pdf"):
        output_path = output_path + ".pdf"

    import time as time_module
    start_time = time_module.time()

    log.info(f"Opening PDF: {input_path}")
    log.info("Using INTELLIGENT block translation with bold markers")

    doc = fitz.open(input_path)
    total_pages = len(doc)

    log.info(f"Document has {total_pages} pages - this may take a while for large books")
    log.info(f"Estimated time: ~{total_pages * 5} seconds minimum (with rate limiting)")

    if VISION_USE_CLAUDE:
        log.info("Using Claude Vision API for chess notation corrections")
        vision_service = ClaudeVisionService(debug_output_dir=vision_debug_dir)
    else:
        log.info("Using OpenAI Vision API for chess notation corrections")
        vision_service = VisionCorrectionService(debug_output_dir=vision_debug_dir)

    if vision_debug_dir:
        log.info(f"Vision debug mode enabled - JSON files will be saved to: {vision_debug_dir}")

    if diagnostics_dir:
        log.info(f"Diagnostics enabled - reports will be saved to: {diagnostics_dir}")

    font_path_regular, font_path_bold = get_fonts_with_polish_chars()
    if not font_path_regular:
        log.error("No suitable regular font found for Polish characters!")
    if not font_path_bold:
        log.warning("No suitable bold font found - using regular for all text")

    for page_num, page in enumerate(doc):
        log.info(f"Processing page {page_num + 1}/{total_pages} ({int((page_num + 1) / total_pages * 100)}%)...")

        skip_regions = find_board_axis_regions(page)
        log.debug(f"Axis markers to skip: {len(skip_regions)}")

        blocks = extract_text_blocks(page, skip_regions=skip_regions)
        log.info(f"Extracted {len(blocks)} text blocks")

        if vision_debug_dir:
            for block in blocks:
                block["ocr_text"] = block.get("text", "")

        claude_direct_mode = bool(
            getattr(vision_service, "direct_translation", False) and vision_service.is_enabled
        )

        if vision_service.is_enabled:
            log.info(f"Running Vision on page {page_num + 1}")
            if claude_direct_mode:
                log.info("  Mode: Claude direct translation (read + translate)")
            else:
                log.info("  Mode: Vision correction only (transcribe)")

            vision_service.correct_page(page, blocks, page_number=page_num)
            log.info(f"Vision complete on page {page_num + 1}")

            if vision_debug_dir:
                for block in blocks:
                    block["vision_text"] = _rebuild_block_text_from_spans(block)
        else:
            log.warning(f"Vision DISABLED on page {page_num + 1}")
            if vision_debug_dir:
                for block in blocks:
                    block["vision_text"] = block.get("ocr_text", "")

        if claude_direct_mode:
            log.info(f"Skipping GPT translation (Claude already translated)")
            fallback_blocks = []
            for block in blocks:
                direct_text = _rebuild_block_text_from_spans(block)
                block["translated_marked"] = postprocess_translated_marked(direct_text)
                if translator is not None and _looks_like_english_prose(block["translated_marked"]):
                    fallback_blocks.append(block)

            if fallback_blocks and translator is not None:
                log.warning(
                    "Direct Vision left %d English-looking blocks; retrying via GPT translator fallback",
                    len(fallback_blocks),
                )
                translate_blocks_intelligent(fallback_blocks, translator)
        else:
            log.info(f"Translating blocks on page {page_num + 1}")
            blocks = translate_blocks_intelligent(blocks, translator)
            log.info(f"Translation complete on page {page_num + 1}")

        if vision_debug_dir:
            _save_simple_debug_comparison(vision_debug_dir, page_num, blocks)

        if diagnostics_dir:
            translated_texts = [b.get("translated_marked", "") for b in blocks]
            page_diag = run_diagnostics_on_translation(
                original_blocks=blocks,
                translated_texts=translated_texts,
                page_num=page_num,
                output_dir=diagnostics_dir
            )
            if page_diag.has_issues:
                log.warning(
                    f"Page {page_num + 1}: {page_diag.total_bold_issues} bold issues, "
                    f"{page_diag.total_language_issues} language issues"
                )

        render_translated_page(
            page, blocks, font_path_regular, font_path_bold, skip_regions=skip_regions
        )

    log.info(f"Saving translated PDF to: {output_path}")
    doc.save(output_path)
    doc.close()

    elapsed_time = time_module.time() - start_time
    minutes = int(elapsed_time // 60)
    seconds = int(elapsed_time % 60)
    log.info(f"Translation complete in {minutes}m {seconds}s ({total_pages} pages)")
    log.info(f"Average: {elapsed_time / total_pages:.1f}s per page")

    return output_path
