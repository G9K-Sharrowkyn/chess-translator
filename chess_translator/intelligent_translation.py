# -*- coding: utf-8 -*-
"""
Simplified intelligent translation helpers.

This module now delegates chess-notation correction to the GPT Vision stage.
The helpers here keep backwards compatibility for public functions that other
modules import, but they intentionally avoid hard-coded glyph replacement rules.
"""

from __future__ import annotations

import logging
import re
from typing import List, Tuple

log = logging.getLogger(__name__)

_SAN_TOKEN_RE = re.compile(r"^(?:O-?O(?:-?O)?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#!?]{0,2}|\d+\.{1,3})$")


def is_word(token: str) -> bool:
    """Heuristic to decide whether a token is a natural-language word."""
    if not token or token.isspace():
        return False
    stripped = token.strip()
    if _SAN_TOKEN_RE.match(stripped):
        return False
    if any(ch.isdigit() for ch in stripped):
        return False
    if re.search(r"[+#=]", stripped):
        return False
    if re.match(r"^[\W_]+$", stripped):
        return False
    return True


def apply_chess_notation_rules(text: str) -> str:
    """Legacy hook retained for compatibility.

    Chess-notation cleanup is now handled by the GPT Vision correction pass,
    so this function simply returns the text unchanged.
    """
    return text


def process_text_intelligently(text: str, translator) -> str:
    """Placeholder implementation that keeps formatting intact.

    The previous version tried to translate only word-like tokens while leaving
    chess notation untouched. With the new vision-based fixer we simply return
    the original text so the downstream translator receives the exact input.
    """
    return text


def split_text_for_intelligent_processing(text: str) -> List[Tuple[str, bool]]:
    """Split text into tokens and flag which ones look like words."""
    if not text:
        return []
    tokens = re.findall(r"\S+|\s+", text)
    return [(tok, not tok.isspace() and is_word(tok)) for tok in tokens]
