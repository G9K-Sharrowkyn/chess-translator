# -*- coding: utf-8 -*-
"""Chess notation protection - replaces notation with placeholders before translation."""

import re
from typing import List, Tuple


def extract_chess_elements(text: str) -> Tuple[str, List[Tuple[int, int, str]]]:
    """Extract all chess notation fragments from text."""
    elements: List[Tuple[int, int, str]] = []

    # Move numbers (1., 15..., 42.)
    for m in re.finditer(r'\b(\d+)\s*\.\s*(?:\.\.)?', text):
        elements.append((m.start(), m.end(), m.group()))

    # Piece/pawn moves (Nf3, e4, exd5, Bxc6+, Qh7#)
    for m in re.finditer(r'\b([KQRBN]?[a-h]?[1-8]?x?[a-h][1-8][+#!?]*)', text):
        mv = m.group()
        if (re.match(r'^[a-h][1-8]$', mv) or
            'x' in mv or
            any(c in mv for c in 'KQRBN') or
            any(c in mv for c in '+#!?')):
            elements.append((m.start(), m.end(), mv))

    # Castling (O-O, O-O-O)
    for m in re.finditer(r'\bO-O(?:-O)?\b', text):
        elements.append((m.start(), m.end(), m.group()))

    # Game results (1-0, 0-1, 1/2-1/2)
    for m in re.finditer(r'\b(?:1-0|0-1|1/2-1/2)\b', text):
        elements.append((m.start(), m.end(), m.group()))

    # Sort and filter overlapping
    elements.sort(key=lambda x: x[0])
    filtered: List[Tuple[int, int, str]] = []
    last_end = -1
    for start, end, notat in elements:
        if start >= last_end:
            filtered.append((start, end, notat))
            last_end = end

    return text, filtered


def protect_chess_notation(text: str) -> Tuple[str, List[str]]:
    """Replace chess notation with placeholders before sending to translator."""
    text, elements = extract_chess_elements(text)
    protected = text
    placeholders: List[str] = []

    for i, (start, end, notation) in enumerate(reversed(elements)):
        placeholder_id = len(elements) - i - 1
        placeholder = f" <<<CHESS_{placeholder_id}>>> "

        left_has_space = start > 0 and protected[start - 1].isspace()
        right_has_space = end < len(protected) and protected[end].isspace()

        if left_has_space and right_has_space:
            placeholder = placeholder.strip()
        elif left_has_space:
            placeholder = placeholder.lstrip()
        elif right_has_space:
            placeholder = placeholder.rstrip()

        protected = protected[:start] + placeholder + protected[end:]
        placeholders.append(notation)

    placeholders.reverse()
    return protected, placeholders


def restore_chess_notation(translated: str, placeholders: List[str]) -> str:
    """Restore original notation after translation."""
    result = translated

    for i, notation in enumerate(placeholders):
        result = result.replace(f"<<<CHESS_{i}>>>", notation)
        result = result.replace(f"§CHESS{i}§", notation)
        result = result.replace(f"[CHESS_{i}_PROTECT]", notation)

    return result
