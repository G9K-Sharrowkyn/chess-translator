# -*- coding: utf-8 -*-
"""Chess symbol decoding and notation cleanup."""

import regex as re


def decode_chess_text(text: str) -> str:
    """Minimal decoder - artifact correction is handled by Vision API."""
    return text


def clean_chess_notation(text: str) -> str:
    """Clean and standardize chess notation formatting."""
    text = re.sub(r'(\d+)\s*\.\s*\.\s*\.', r'\1...', text)
    text = re.sub(r'(\d+)\s*\.\s+', r'\1. ', text)
    text = re.sub(r'([KQRBN])([a-h][1-8])', r'\1\2', text)
    text = re.sub(r'([a-h][1-8])([KQRBN])', r'\1 \2', text)
    text = re.sub(r'([KQRBN])\1+', r'\1', text)
    return text
