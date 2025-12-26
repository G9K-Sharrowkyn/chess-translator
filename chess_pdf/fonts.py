# -*- coding: utf-8 -*-
"""Font management for Polish text and chess symbols."""

import os
import fitz
import logging
from typing import Optional, Tuple

from .config import log, REGULAR_FONT_CANDIDATES, BOLD_FONT_CANDIDATES


def get_fonts_with_polish_chars() -> Tuple[Optional[str], Optional[str]]:
    """Find fonts with Polish character support. Returns (regular_path, bold_path)."""
    regular = None
    for font_path in REGULAR_FONT_CANDIDATES:
        if os.path.exists(font_path):
            log.info(f"Using regular font: {font_path}")
            regular = font_path
            break

    bold = None
    for font_path in BOLD_FONT_CANDIDATES:
        if os.path.exists(font_path):
            log.info(f"Using bold font: {font_path}")
            bold = font_path
            break

    if not regular:
        log.warning("No regular font with Polish characters found!")
    if not bold:
        log.warning("No bold font with Polish characters found!")

    return regular, bold


def ensure_font_embedded(page: fitz.Page, font_path: Optional[str], font_name: str) -> str:
    """Embed TTF font in PDF page. Returns font name for insert_text()."""
    if not font_path or not os.path.exists(font_path):
        log.warning(f"Font file not found: {font_path}, using default 'helv'")
        return "helv"

    try:
        page.insert_font(fontname=font_name, fontfile=font_path)
        log.debug(f"Font embedded successfully: {font_name} from {font_path}")
        return font_name
    except Exception as e:
        log.error(f"Font embedding failed for {font_path}: {e}")
        return "helv"


def _draw_wrapped_text(page, text, x, y, right_limit, base_fontsize, fontname, line_height=1.2):
    """Legacy wrapper for backward compatibility."""
    try:
        from .rendering import render_wrapped_text_in_rect
        rect = fitz.Rect(x, y - base_fontsize, right_limit, y + base_fontsize * 10)
        render_wrapped_text_in_rect(page, text, rect, base_fontsize, fontname)
        log.debug(f"Text rendered via _draw_wrapped_text: {text[:50]}...")
    except ImportError:
        log.warning("rendering.render_wrapped_text_in_rect not available yet - text not rendered")
    except Exception as e:
        log.error(f"Error in _draw_wrapped_text: {e}")
    return x, y
