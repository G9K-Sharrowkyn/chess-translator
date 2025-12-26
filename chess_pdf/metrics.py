# -*- coding: utf-8 -*-
"""Text metrics and font sizing utilities."""

from typing import List, Dict, Tuple
import fitz
from .config import log


def text_width_fitz(text: str, fontsize: float, fontname: str) -> float:
    """Calculate text width in points."""
    try:
        return fitz.get_text_length(text, fontname=fontname, fontsize=fontsize)
    except Exception:
        return len(text) * fontsize * 0.6


def get_safe_text_width(text: str, fontsize: float) -> float:
    """Safe text width measurement with fallback to Times."""
    try:
        return fitz.get_text_length(text, fontname="times", fontsize=fontsize)
    except Exception:
        return len(text) * fontsize * 0.6


def will_text_fit(text: str, max_width: float, max_height: float, fontsize: float) -> bool:
    """Check if text will fit in given dimensions with word wrapping."""
    words = text.split()
    if not words:
        return True
    space_width = get_safe_text_width(" ", fontsize)
    line_height = fontsize * 1.2
    lines_needed = 0
    current_line_width = 0.0
    for word in words:
        word_width = get_safe_text_width(word, fontsize)
        space_needed = space_width if current_line_width > 0 else 0
        if current_line_width + space_needed + word_width <= max_width:
            current_line_width += space_needed + word_width
        else:
            lines_needed += 1
            current_line_width = word_width
    if current_line_width > 0:
        lines_needed += 1
    total_height_needed = lines_needed * line_height
    return total_height_needed <= max_height


def find_optimal_fontsize(text: str, max_width: float, max_height: float, start_size: float) -> float:
    """Find largest font size that fits text in rectangle using binary search."""
    min_size = 4.0
    max_size = start_size * 1.5
    for _ in range(10):
        test_size = (min_size + max_size) / 2.0
        if will_text_fit(text, max_width, max_height, test_size):
            min_size = test_size
        else:
            max_size = test_size
        if max_size - min_size < 0.1:
            break
    return min_size


def measure_lines_for_segments(
    segments: List[Dict],
    rect_width: float,
    fontsize: float,
    font_regular: str,
    font_bold: str,
    line_height_factor: float = 1.18,
) -> Tuple[int, float]:
    """Calculate line count and total height for mixed-format segments."""
    if rect_width <= 0:
        return 1, 1e9

    line_height = fontsize * line_height_factor
    lines = 1
    curw = 0.0

    def wlen(t: str, bold: bool) -> float:
        return text_width_fitz(t, fontsize, font_bold if bold else font_regular)

    for seg in segments:
        bold = bool(seg.get("bold"))
        parts = (seg.get("text") or "").split("\n")
        for pi, part in enumerate(parts):
            words = part.split()
            for w in words:
                ww = wlen(w, bold)
                sp = wlen(" ", bold) if curw > 0 else 0.0
                if curw + sp + ww <= rect_width:
                    curw += sp + ww
                else:
                    lines += 1
                    curw = ww
            if pi < len(parts) - 1:
                lines += 1
                curw = 0.0

    total_h = lines * line_height
    return lines, total_h


def find_optimal_fontsize_mixed(
    segments: List[Dict],
    max_w: float,
    max_h: float,
    start_size: float,
    font_regular: str,
    font_bold: str
) -> float:
    """Find optimal font size for mixed-format text using binary search."""
    lo, hi = 4.0, max(6.0, start_size * 1.5)
    for _ in range(12):
        mid = (lo + hi) / 2
        _, h = measure_lines_for_segments(
            segments, max_w, mid, font_regular, font_bold, line_height_factor=1.18
        )
        if h <= max_h:
            lo = mid
        else:
            hi = mid
        if hi - lo < 0.1:
            break
    return lo
