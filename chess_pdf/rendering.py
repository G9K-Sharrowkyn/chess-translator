# -*- coding: utf-8 -*-
"""Rendering translated text to PDF pages."""

from typing import List, Dict, Optional
import fitz
import re

from .config import B_START, B_END, log
from .fonts import ensure_font_embedded
from .geometry import _avoid_regions
from .metrics import text_width_fitz, get_safe_text_width, find_optimal_fontsize

BOLD_SCALE_DEFAULT = 1.06
BASE_SIZE_CLAMP = (9.0, 15.75)


def _collect_page_baseline_sizes(blocks: List[Dict]) -> float:
    """Collect font sizes from spans and return baseline size for page."""
    regular_sizes = []
    bold_sizes = []
    for b in blocks:
        for s in b.get("spans", []) or []:
            fs = s.get("font_size")
            if fs:
                if s.get("is_bold"):
                    bold_sizes.append(float(fs))
                else:
                    regular_sizes.append(float(fs))

    if regular_sizes:
        regular_sizes.sort()
        median = regular_sizes[len(regular_sizes)//2] * 0.95
    elif bold_sizes:
        bold_sizes.sort()
        median = (bold_sizes[len(bold_sizes)//2] / BOLD_SCALE_DEFAULT) * 0.95
    else:
        return 10.0

    return max(BASE_SIZE_CLAMP[0], min(BASE_SIZE_CLAMP[1], median))


def _measure_height_dual(segments: List[Dict], rect_w: float,
                         regular_size: float, bold_size: float,
                         font_regular: str, font_bold: str) -> float:
    """Estimate height needed for segments at given font sizes."""
    if rect_w <= 0:
        return 1e9
    line_h = max(regular_size, bold_size) * 1.18
    curw = 0.0
    lines = 1

    def wlen(t: str, is_bold: bool) -> float:
        size = bold_size if is_bold else regular_size
        fontn = font_bold if is_bold else font_regular
        return text_width_fitz(t, size, fontn)

    for seg in segments:
        is_bold = bool(seg.get("bold"))
        parts = (seg.get("text") or "").split("\n")
        for pi, part in enumerate(parts):
            for word in part.split():
                ww = wlen(word, is_bold)
                sp = wlen(" ", is_bold) if curw > 0 else 0.0
                if curw + sp + ww <= rect_w:
                    curw += sp + ww
                else:
                    lines += 1
                    curw = ww
            if pi < len(parts) - 1:
                lines += 1
                curw = 0.0
    return lines * line_h


def choose_sizes_that_fit(segments: List[Dict], rect: fitz.Rect,
                          base_regular: float, bold_scale: float,
                          font_regular: str, font_bold: str) -> tuple[float, float]:
    """Try base sizes; if they don't fit, scale down together."""
    reg = base_regular
    bold = base_regular * bold_scale
    H = _measure_height_dual(segments, rect.width, reg, bold, font_regular, font_bold)
    if H <= rect.height:
        return reg, bold

    lo, hi = 0.6, 1.0
    for _ in range(14):
        mid = (lo + hi) / 2.0
        r = base_regular * mid
        b = r * bold_scale
        Hm = _measure_height_dual(segments, rect.width, r, b, font_regular, font_bold)
        if Hm <= rect.height:
            lo = mid
        else:
            hi = mid
        if hi - lo < 0.02:
            break
    reg = base_regular * lo
    bold = reg * bold_scale
    return reg, bold


def parse_marked_segments(marked_text: str) -> List[Dict]:
    """Parse [[B]]...[[/B]] markers into segments."""
    if not marked_text:
        return []
    segs = []
    i = 0
    N = len(marked_text)
    while i < N:
        if marked_text.startswith(B_START, i):
            i += len(B_START)
            j = marked_text.find(B_END, i)
            if j == -1:
                segs.append({"text": marked_text[i:], "bold": True})
                break
            segs.append({"text": marked_text[i:j], "bold": True})
            i = j + len(B_END)
        else:
            j = marked_text.find(B_START, i)
            if j == -1:
                segs.append({"text": marked_text[i:], "bold": False})
                break
            segs.append({"text": marked_text[i:j], "bold": False})
            i = j
    merged = []
    for s in segs:
        if not s["text"]:
            continue
        if merged and merged[-1]["bold"] == s["bold"]:
            merged[-1]["text"] += s["text"]
        else:
            merged.append(s)
    return merged


def render_marked_segments(
    page: fitz.Page,
    segments: List[Dict],
    rect: fitz.Rect,
    regular_size: float,
    bold_size: float,
    font_regular: str,
    font_bold: str,
):
    """Render mixed-style segments word by word."""
    if not segments:
        return

    def w(text: str, is_bold: bool) -> float:
        size = bold_size if is_bold else regular_size
        return text_width_fitz(text, size, font_bold if is_bold else font_regular)

    line_height = max(regular_size, bold_size) * 1.18
    y = rect.y0 + max(regular_size, bold_size)
    x0 = rect.x0

    line_runs: List[Dict] = []
    curw = 0.0

    def flush_line():
        nonlocal line_runs, curw, y
        if not line_runs:
            return
        x = x0
        for run in line_runs:
            txt = run["text"]
            if not txt:
                continue
            is_b = bool(run["bold"])
            size = bold_size if is_b else regular_size
            fontn = font_bold if is_b else font_regular
            page.insert_text((x, y), txt, fontsize=size, fontname=fontn, color=(0, 0, 0))
            x += w(txt, is_b)
        y += line_height
        line_runs = []
        curw = 0.0

    def append_token(tok: str, is_bold: bool):
        nonlocal curw, y
        if not tok:
            return
        leading_space = (" " if line_runs and not line_runs[-1]["text"].endswith("\n") else "")
        candidate = leading_space + tok
        add_w = w(candidate, is_bold)

        if curw > 0 and curw + add_w > rect.width:
            if y + line_height > rect.y1 + line_height * 2.0:
                log.warning(f"[RENDERING] Text truncated - ran out of vertical space. Last word: '{tok[:30]}'")
                return
            flush_line()
            candidate = tok
            add_w = w(candidate, is_bold)

        if line_runs and line_runs[-1]["bold"] == is_bold:
            line_runs[-1]["text"] += candidate
        else:
            line_runs.append({"bold": is_bold, "text": candidate})
        curw += add_w

    for seg in segments:
        is_bold = bool(seg.get("bold"))
        txt = (seg.get("text") or "")
        parts = txt.split("\n")
        for i, part in enumerate(parts):
            for word in part.split():
                append_token(word, is_bold)
            if i < len(parts) - 1:
                if y + line_height > rect.y1 + line_height * 2.0:
                    log.warning(f"[RENDERING] Text truncated - newline forced overflow")
                    return
                flush_line()

    if line_runs and y <= rect.y1 + line_height * 2.0:
        flush_line()
    elif line_runs:
        log.warning(f"[RENDERING] Final line not rendered - exceeded bbox by too much")


def render_wrapped_text_in_rect(
    page: fitz.Page, text: str, rect: fitz.Rect, fontsize: float, fontname: str
):
    """Render plain text with word wrapping."""
    if not text.split():
        return
    line_height = fontsize * 1.2
    current_y = rect.y0 + fontsize
    space_width = get_safe_text_width(" ", fontsize)
    current_line = []
    current_line_width = 0.0
    for word in text.split():
        word_width = get_safe_text_width(word, fontsize)
        space_needed = space_width if current_line else 0
        if current_line_width + space_needed + word_width <= rect.width or not current_line:
            current_line.append(word)
            current_line_width += space_needed + word_width
        else:
            if current_line:
                line_text = " ".join(current_line)
                try:
                    page.insert_text((rect.x0, current_y), line_text, fontsize=fontsize, fontname=fontname, color=(0, 0, 0))
                except Exception as e:
                    log.error(f"Text insertion failed: {e}")
                    page.insert_text((rect.x0, current_y), line_text, fontsize=fontsize, fontname="helv", color=(0, 0, 0))
            current_y += line_height
            if current_y > rect.y1:
                break
            current_line = [word]
            current_line_width = word_width
    if current_line and current_y <= rect.y1:
        line_text = " ".join(current_line)
        try:
            page.insert_text((rect.x0, current_y), line_text, fontsize=fontsize, fontname=fontname, color=(0, 0, 0))
        except Exception as e:
            log.error(f"Text insertion failed: {e}")
            page.insert_text((rect.x0, current_y), line_text, fontsize=fontsize, fontname="helv", color=(0, 0, 0))


def render_text_in_rect(
    page: fitz.Page, text: str, rect: fitz.Rect, fontname: str,
    original_spans: Optional[List[Dict]] = None
):
    """Render text in rectangle with optimal font size."""
    if not text.strip():
        return
    MARGIN = 2.0
    work_rect = fitz.Rect(rect.x0 + MARGIN, rect.y0 + MARGIN, rect.x1 - MARGIN, rect.y1 - MARGIN)
    if work_rect.width <= 0 or work_rect.height <= 0:
        return
    if original_spans:
        sizes = [s.get("font_size", 11) for s in original_spans if s.get("font_size")]
        start_fontsize = max(6.0, min(14.0, (sum(sizes)/len(sizes)) * 0.9)) if sizes else 10.0
    else:
        start_fontsize = 10.0
    fontsize = find_optimal_fontsize(text, work_rect.width, work_rect.height, start_fontsize)
    if fontsize < 4.0:
        log.warning(f"Font size too small ({fontsize:.1f}) for text: {text[:30]}...")
        fontsize = 6.0
    render_wrapped_text_in_rect(page, text, work_rect, fontsize, fontname)


def render_translated_page(
    page: fitz.Page,
    blocks: List[Dict],
    font_path_regular: Optional[str],
    font_path_bold: Optional[str],
    skip_regions: Optional[List[fitz.Rect]] = None,
):
    """Render translated blocks on PDF page with consistent font sizes."""
    skip_regions = skip_regions or []

    regular_font = ensure_font_embedded(page, font_path_regular, "polish_regular")
    bold_font = ensure_font_embedded(page, font_path_bold, "polish_bold") if font_path_bold else regular_font

    base_regular_size = _collect_page_baseline_sizes(blocks)
    bold_scale = BOLD_SCALE_DEFAULT

    min_scale = 1.0
    valid_blocks = []

    for block in blocks:
        marked = (block.get("translated_marked") or "").strip()
        if (not marked) or (not block.get("rect")):
            continue

        original_rect = fitz.Rect(block["rect"])
        safe_rect = _avoid_regions(original_rect, skip_regions, pad=1.0)
        if safe_rect is None:
            continue

        MARGIN = 2.0
        work_rect = fitz.Rect(
            safe_rect.x0 + MARGIN, safe_rect.y0 + MARGIN,
            safe_rect.x1 - MARGIN + 20, safe_rect.y1 - MARGIN + 10
        )
        if work_rect.width <= 0 or work_rect.height <= 0:
            continue

        segments = parse_marked_segments(marked)
        valid_blocks.append((block, segments, work_rect, safe_rect))

        reg = base_regular_size
        bold = base_regular_size * bold_scale
        H = _measure_height_dual(segments, work_rect.width, reg, bold, regular_font, bold_font)
        if H > work_rect.height:
            lo, hi = 0.6, 1.0
            for _ in range(14):
                mid = (lo + hi) / 2.0
                r = base_regular_size * mid
                b = r * bold_scale
                Hm = _measure_height_dual(segments, work_rect.width, r, b, regular_font, bold_font)
                if Hm <= work_rect.height:
                    lo = mid
                else:
                    hi = mid
                if hi - lo < 0.02:
                    break
            min_scale = min(min_scale, lo)

    final_regular_size = base_regular_size * min_scale
    final_bold_size = final_regular_size * bold_scale

    move_head_re = re.compile(r'^\s*\d{1,3}\s*(?:\.\.\.|\.)(?:\s|$)')

    for block, segments, work_rect, safe_rect in valid_blocks:
        page.draw_rect(safe_rect, color=None, fill=(1, 1, 1))

        for i in range(len(segments) - 1):
            if segments[i].get("bold") and move_head_re.match(segments[i].get("text", "")):
                if not segments[i]["text"].endswith("\n") and not segments[i + 1].get("bold"):
                    segments[i]["text"] += "\n"

        render_marked_segments(
            page, segments, work_rect,
            regular_size=final_regular_size, bold_size=final_bold_size,
            font_regular=regular_font, font_bold=bold_font
        )
