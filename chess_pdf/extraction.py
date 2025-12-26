# -*- coding: utf-8 -*-
"""Text block extraction from PDF pages."""

from typing import List, Dict, Optional
import fitz

from .config import TARGET_BOLD_FONT
from .decoding import decode_chess_text, clean_chess_notation
from .geometry import _rect_overlap_ratio
from .config import AXIS_LETTERS, AXIS_DIGITS


def _is_bold_span(s: Dict) -> bool:
    """Check if span is bold based on font name or flags."""
    if s.get("is_bold", False):
        return True

    fname = (s.get("font", "") or s.get("fontname", "")).lower()
    fname_normalized = fname.replace(" ", "").replace("-", "").replace("_", "")
    target_normalized = TARGET_BOLD_FONT.lower().replace(" ", "").replace("-", "").replace("_", "")

    if target_normalized in fname_normalized:
        return True

    return any(k in fname for k in ("bold", "semibold", "demi", "black"))


def extract_text_blocks(page: fitz.Page, skip_regions: Optional[List[fitz.Rect]] = None) -> List[Dict]:
    """Extract text blocks from PDF page with bold detection and skip regions."""
    skip_regions = skip_regions or []
    blocks: List[Dict] = []
    text_dict = page.get_text("dict")

    for block in text_dict.get("blocks", []):
        if "lines" not in block:
            continue

        block_text_parts: List[str] = []
        block_rect = fitz.Rect(block["bbox"])
        spans_in_block: List[Dict] = []

        for li, line in enumerate(block["lines"]):
            line_parts: List[str] = []
            for span in line.get("spans", []):
                txt = span.get("text", "")
                if not txt:
                    continue
                bbox = span.get("bbox")
                span_rect = fitz.Rect(bbox) if bbox else None

                trimmed = txt.strip()
                if len(trimmed) == 1 and (trimmed in AXIS_LETTERS or trimmed in AXIS_DIGITS):
                    continue

                if span_rect and any(_rect_overlap_ratio(span_rect, r) > 0.5 for r in skip_regions):
                    continue

                is_bold = _is_bold_span(span)
                decoded = decode_chess_text(txt)

                spans_in_block.append({
                    "text": decoded,
                    "is_bold": is_bold,
                    "rect": span_rect,
                    "font_size": span.get("size", 11),
                    "font": span.get("font", "")
                })

                line_parts.append(decoded)

            if line_parts:
                block_text_parts.append(" ".join(line_parts))
                if li < len(block["lines"]) - 1:
                    block_text_parts.append("\n")
                    spans_in_block.append({"text": "\n", "is_bold": False})

        if block_text_parts:
            full_text = "".join(block_text_parts)
            full_text = clean_chess_notation(full_text)
            blocks.append({
                "text": full_text,
                "spans": spans_in_block,
                "rect": block_rect,
                "bbox": block["bbox"]
            })

    return blocks
