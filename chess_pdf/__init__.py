# -*- coding: utf-8 -*-
"""Chess PDF Processing Module"""

from .config import (
    REGULAR_FONT_CANDIDATES, BOLD_FONT_CANDIDATES, TARGET_BOLD_FONT,
    AXIS_LETTERS, AXIS_DIGITS, B_START, B_END
)
from .fonts import get_fonts_with_polish_chars, ensure_font_embedded
from .decoding import decode_chess_text, clean_chess_notation
from .geometry import (
    _rect_overlap_ratio, _cluster_sorted, find_board_axis_regions, _avoid_regions
)
from .extraction import extract_text_blocks
from .san import postprocess_translated_marked
from .translation_core import (
    build_marked_text_for_translation, translate_blocks_intelligent
)
from .rendering import (
    render_translated_page, parse_marked_segments, render_text_in_rect,
    render_wrapped_text_in_rect
)
from .metrics import (
    get_safe_text_width, will_text_fit, find_optimal_fontsize,
    find_optimal_fontsize_mixed
)
from .pipeline import translate_pdf

__all__ = [
    "REGULAR_FONT_CANDIDATES", "BOLD_FONT_CANDIDATES", "TARGET_BOLD_FONT",
    "AXIS_LETTERS", "AXIS_DIGITS", "B_START", "B_END",
    "translate_pdf",
    "get_fonts_with_polish_chars", "ensure_font_embedded",
    "decode_chess_text", "clean_chess_notation",
    "_rect_overlap_ratio", "_cluster_sorted", "find_board_axis_regions", "_avoid_regions",
    "extract_text_blocks",
    "postprocess_translated_marked",
    "build_marked_text_for_translation", "translate_blocks_intelligent",
    "render_translated_page", "parse_marked_segments", "render_text_in_rect",
    "render_wrapped_text_in_rect",
    "get_safe_text_width", "will_text_fit", "find_optimal_fontsize",
    "find_optimal_fontsize_mixed",
]
