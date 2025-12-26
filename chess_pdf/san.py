# -*- coding: utf-8 -*-
"""Chess SAN (Standard Algebraic Notation) postprocessing."""

import regex as re
from .config import B_START, B_END

MOVE_NO_RE = re.compile(r'^\d{1,3}\.{1,3}$')
CASTLE_RE = re.compile(r'^(?:O-?O(?:-?O)?|0-0(?:-0)?)$')
SQUARE_LIKE = re.compile(r'^[a-h][1-8]$')

SAN_TOKEN_RE = re.compile(r"""
    (?:(?<=^)|(?<=\s)|(?<=\()|(?<=\.))
    (?P<tok>
        (?:O-?O(?:-?O)? | 0-0(?:-0)?)
        |
        (?:
            (?: (?:[KQRBN]|[iI]|J)(?:[""'!]+)? | (?:[""]!|![""]) )?
            (?:[a-h]|[1-8])?
            (?:[a-h]|[1-8])?
            (?:[""'!]+)?
            x?
            [a-h][1-8]
            (?:=[QRBN])?
            (?:[+#])?
            (?:[!?]{1,2})?
        )
    )
""", re.X)


def _fix_spaced_punctuation(s: str) -> str:
    s = re.sub(r'!\s*!', '!!', s)
    s = re.sub(r'\?\s*\?', '??', s)
    s = re.sub(r'!\s*\?', '!?', s)
    s = re.sub(r'\?\s*!', '?!', s)
    s = re.sub(r'\s+([!?.,;:])', r'\1', s)
    s = re.sub(r'([(\[]) +', r'\1', s)
    s = re.sub(r' +([)\]])', r'\1', s)
    return s


def _insert_missing_dot_after_move_number(s: str) -> str:
    pat = r'(?<!\.)\b(\d{1,3})(?=\s*(?:[KQRBNO]|[a-h]|[iI]|J|[""]!|![""]))'
    return re.sub(pat, r'\1.', s)


def _normalize_move_numbers(s: str) -> str:
    trans = str.maketrans({'l': '1', 'I': '1', '|': '1'})

    def repl(m):
        raw = m.group('num')
        dots = m.group('dots')
        digits = re.sub(r'\s+', '', raw.translate(trans))
        ndots = dots.count('.')
        dots_norm = '...' if ndots >= 2 else '.'
        return f"{digits}{dots_norm}"

    pattern = r'\b(?P<num>[Il|\d][Il|\s\d]{0,4})\s*(?P<dots>(?:\.\s*){1,6})'
    return re.sub(pattern, repl, s)


def _normalize_move_dots(s: str) -> str:
    s = re.sub(r'\b(\d{1,3})\s*(?:\.\s*){2,}', r'\1...', s)
    s = re.sub(r'\b(\d{1,3})\s*\.(?!\.)', r'\1.', s)
    return s


def _normalize_castling_and_times(s: str) -> str:
    s = s.replace('×', 'x')
    s = (s.replace('0-0-0', 'O-O-O')
         .replace('0-0', 'O-O')
         .replace('O-0-0', 'O-O-O')
         .replace('O-0', 'O-O')
         .replace('0-O', 'O-O'))
    return s


def _normalize_piece_glyphs_in_context(s: str) -> str:
    return s


def _repair_san_token(tok: str) -> str:
    t = tok
    t = t.replace('×', 'x')
    t = (t.replace('0-0-0', 'O-O-O')
         .replace('0-0', 'O-O')
         .replace('O-0-0', 'O-O-O')
         .replace('O-0', 'O-O')
         .replace('0-O', 'O-O'))

    ornaments = ""
    if t and t[0] in ("i", "I", "J"):
        k = 1
        while k < len(t) and t[k] in '""\'!':
            ornaments += t[k]
            k += 1
        if t[0] in ("i", "I"):
            if k < len(t) and (t[k] == 'x' or t[k] in 'abcdefghKQRBNO'):
                t = 'B' + t[k:]
        elif t[0] == "J":
            if k < len(t) and (t[k] == 'x' or t[k] in 'abcdefghKQBNRO'):
                t = 'R' + t[k:]
    elif t.startswith(('"!', '!"', '"!', '!"')) and len(t) > 2:
        t = 'N' + t[2:]

    t = re.sub(r'^([KQRBN]|[a-h])[""\'!]+x([a-h][1-8])', r'\1x\2!', t)
    t = re.sub(r'^([KQRBN])[""\'!]+([a-h][1-8])', r'\1\2!', t)

    if '!' in ornaments and not re.search(r'[!?](?=$|[+#])', t):
        m = re.search(r'([+#]+)$', t)
        t = (t[:m.start()] + '!' + t[m.start():]) if m else (t + '!')

    t = re.sub(
        r'^((?:[KQRBN])?(?:[a-h]|[1-8])?(?:[a-h]|[1-8])?x?[a-h][1-8](?:=[QRBN])?(?:[+#])?(?:[!?]{0,2}))(?:[a-z]{1,3})\b',
        r'\1',
        t
    )
    return t


def _repair_san_tokens_in_text(s: str) -> str:
    return s


def _strip_garbage_suffixes_after_square(s: str) -> str:
    token = r'(?:[KQRBN])?(?:[a-h])?x?(?:[a-h][1-8])(?:=[QRBN])?(?:[+#])?(?:[!?]{1,2})?'
    return re.sub(rf'(\b{token})([a-z]{{1,3}})\b', r'\1', s)


def _newline_after_bold_move(marked: str) -> str:
    move_token = r'(?:\d{1,3}\s*\.\.\.|\\?\d{1,3}\s*\.)\s*[A-Za-z0-9O\-=+#]*[a-h]?[1-8]?[=QNRB]?[+#]?[\!\?]*'
    pat = rf'(\[\[B\]\]\s*{move_token}\s*\[\[\/B\]\])\s*'
    return re.sub(pat, r'\1\n', marked)


def _fix_remaining_ocr_artifacts(text: str) -> str:
    text = re.sub(r'\b(\d)l(\.{1,3})', r'\1\1\2', text)
    text = re.sub(r'(\d+)\s*\.\s*\.(?=[KQRBN]?[a-h][1-8])', r'\1.', text)
    text = re.sub(r'(\d+)\.{4,}(?=[KQRBN]?[a-h][1-8])', r'\1...', text)
    text = text.replace('0-0-0', 'O-O-O')
    text = text.replace('0-0', 'O-O')
    text = text.replace('O-0-0', 'O-O-O')
    text = text.replace('O-0', 'O-O')
    text = text.replace('0-O', 'O-O')
    text = re.sub(r'\b([a-h])\s+([1-8])\b', r'\1\2', text)
    text = re.sub(r'\b([KQRBN])\s+([a-h][1-8])', r'\1\2', text)
    text = re.sub(r'([KQRBN]|[a-h][1-8]|[a-h])\s+x\s*', r'\1x', text)
    text = re.sub(r'x\s+([a-h][1-8])', r'x\1', text)
    text = re.sub(r'(\d+\.)\s+([a-hKQRBN])', r'\1\2', text)
    text = re.sub(r'\b[Hh]etman\s*([xa-h])', r'Q\1', text, flags=re.IGNORECASE)
    text = re.sub(r'\b[Gg]oniec\s*([xa-h])', r'B\1', text, flags=re.IGNORECASE)
    text = re.sub(r'\b[Ss]koczek\s*([xa-h])', r'N\1', text, flags=re.IGNORECASE)
    text = re.sub(r'\b[Ww]ie(?:za|za)\s*([xa-h])', r'R\1', text, flags=re.IGNORECASE)
    text = re.sub(r'\b[Kk]r(?:ol|ol)\s*([xa-h])', r'K\1', text, flags=re.IGNORECASE)
    text = re.sub(r'\b[Ww]ie[zz]a\s*([xa-h])', r'R\1', text, flags=re.IGNORECASE)
    text = re.sub(r'\b[Kk]r[oo]l\s*([xa-h])', r'K\1', text, flags=re.IGNORECASE)
    text = re.sub(r'\bone\s*([1-8])\b', r'on e\1', text)
    text = re.sub(r'\bind\s*([1-8])\b', r'on d\1', text)
    text = re.sub(r'\binc\s*([1-8])\b', r'on c\1', text)
    text = re.sub(r'\binf\s*([1-8])\b', r'on f\1', text)
    text = re.sub(r'\bing\s*([1-8])\b', r'on g\1', text)
    text = re.sub(r'(\d+\.{2,})\s+([KQRBN][a-h]?[1-8]?x?[a-h][1-8])', r'\1\2', text)
    text = re.sub(r'([KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?[!?]{0,2})(?:ao|±)\b', r'\1', text)
    return text


def _fix_misplaced_bold_markers(marked: str) -> str:
    def fix_marker(match):
        content = match.group(1)
        content = re.sub(r'\s*\n\s*', ' ', content)
        content = content.strip()
        polish_word_pattern = r'\b(?![KQRBNO]\b)(?![A-Z]x)\p{Lu}[\p{Ll}]{2,}\b'
        polish_match = re.search(polish_word_pattern, content)
        if polish_match:
            split_pos = polish_match.start()
            notation = content[:split_pos].rstrip()
            prose = content[split_pos:]
            return f"[[B]]{notation}[[/B]] {prose}"
        return f"[[B]]{content}[[/B]]"

    pattern = r'\[\[B\]\](.*?)\[\[/B\]\]'
    return re.sub(pattern, fix_marker, marked, flags=re.DOTALL)


def postprocess_translated_marked(marked: str) -> str:
    """Main postprocessing function for translated text with markers."""
    if not marked:
        return marked

    import logging
    log = logging.getLogger("chess_pdf.san")
    log.debug(f"[SAN postprocess] BEFORE: {marked[:100]}...")

    s = marked
    s = _fix_misplaced_bold_markers(s)
    s = _insert_missing_dot_after_move_number(s)
    s = _normalize_move_numbers(s)
    s = _normalize_move_dots(s)
    s = _normalize_castling_and_times(s)
    s = _normalize_piece_glyphs_in_context(s)
    s = _repair_san_tokens_in_text(s)
    s = _fix_spaced_punctuation(s)
    s = _strip_garbage_suffixes_after_square(s)
    s = _fix_remaining_ocr_artifacts(s)
    s = _newline_after_bold_move(s)
    s = re.sub(r'(\b\d{1,3})\s*,\s*', r'\1. ', s)
    s = re.sub(r'\n{3,}', '\n\n', s)

    log.debug(f"[SAN postprocess] AFTER ALL: {s[:100]}...")
    return s
