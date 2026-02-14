# -*- coding: utf-8 -*-
"""Post-processing fixes for translated chess text."""

import logging
import re

log = logging.getLogger(__name__)

_REFUSAL_PATTERNS = [
    r"nie mog",
    r"przykro mi",
    r"cannot",
    r"sorry",
    r"i can't",
    r"i'm unable",
]


def looks_like_refusal(text: str) -> bool:
    low = (text or "").lower()
    return any(re.search(p, low) for p in _REFUSAL_PATTERNS)


_PIECE_FIXES = {
    "S": "N", "Sk": "N",
    "G": "B", "Go": "B",
    "W": "R", "Wi": "R",
    "H": "Q", "He": "Q",
    "Kr": "K",
}

_FIGURINE_TRANSLATION = str.maketrans({
    "\u2654": "K",
    "\u2655": "Q",
    "\u2656": "R",
    "\u2657": "B",
    "\u2658": "N",
    "\u2659": "",
    "\u265A": "K",
    "\u265B": "Q",
    "\u265C": "R",
    "\u265D": "B",
    "\u265E": "N",
    "\u265F": "",
    "\u2020": "+",
    "\u2021": "+",
    "\u271d": "+",
    "\u271e": "+",
})


def _normalize_piece_glyphs(text: str) -> str:
    if not text:
        return text
    text = text.translate(_FIGURINE_TRANSLATION)
    text = re.sub(r"\+\s*/\s*-", "+/-", text)
    text = re.sub(r"-\s*/\s*\+", "-/+", text)
    return text


def _fix_piece_letters(translated: str) -> str:
    t = translated
    for wrong, correct in _PIECE_FIXES.items():
        t = re.sub(fr"\b{re.escape(wrong)}([a-h][1-8])", fr"{correct}\1", t)
        t = re.sub(fr"\b{re.escape(wrong)}x([a-h][1-8])", fr"{correct}x\1", t)
    return t


def _fix_queen_D(translated: str) -> str:
    t = translated
    t = re.sub(r"\b(\d+\.)\s*D([a-h][1-8])", r"\1 Q\2", t)
    t = re.sub(r"\bD([a-h][1-8])", r"Q\1", t)
    t = re.sub(r"\bDx([a-h][1-8])", r"Qx\1", t)
    return t


def _sync_move_numbers(translated: str, original: str) -> str:
    orig_nums = re.findall(r"\b(\d+)\s*\.", original or "")
    tr_nums = re.findall(r"\b(\d+)\s*\.", translated or "")
    if orig_nums and tr_nums:
        for num in orig_nums:
            if num not in tr_nums:
                if num != "1" and re.search(r"\b1\s*\.", translated or ""):
                    translated = re.sub(r"\b1\s*\.", f"{num}.", translated, count=1)
    return translated


def _strip_unwanted_zagrano(translated: str, original: str) -> str:
    if not re.search(r"\bplayed\b|\bwas played\b", original or "", re.IGNORECASE):
        translated = re.sub(r"\bzagrano\s+\d+\s*", "", translated, flags=re.IGNORECASE)
        translated = re.sub(r"\bzagrano\b\s*", "", translated, flags=re.IGNORECASE)
    return translated


def _fix_spaced_numbers(text: str) -> str:
    def collapse_digits(match: re.Match) -> str:
        return match.group(0).replace(" ", "")

    before = text
    text = re.sub(r"\b\d+(?:\s+\d+)+\b", collapse_digits, text)
    if before != text:
        log.debug("[postprocess] Fixed spaced numbers")
    return text


def _fix_merged_prepositions(text: str) -> str:
    text = re.sub(r"\bone\s+([1-8])\b", r"na e\1", text)
    text = re.sub(r"\bind\s+([1-8])\b", r"na d\1", text)
    text = re.sub(r"\binc\s+([1-8])\b", r"na c\1", text)
    for letter in "abcdefgh":
        pattern = fr"\bin{letter}\s+([1-8])\b"
        replacement = fr"na {letter}\1"
        text = re.sub(pattern, replacement, text)
    return text


def _fix_square_piece_pattern(text: str) -> str:
    def replace_square_piece(match: re.Match) -> str:
        square = match.group(1)
        piece_word = match.group(2)
        piece_keywords = [
            "pion", "wież", "goniec", "gońc", "skoczek", "skoczk",
            "hetman", "król", "pól", "figur",
        ]
        if any(piece_word.lower().startswith(kw) for kw in piece_keywords):
            return f"{piece_word} na {square}"
        return match.group(0)

    pattern = r"([a-h][1-8])\s*-\s*(\w+)"
    return re.sub(pattern, replace_square_piece, text)


_TERM_REPLACEMENTS = [
    (re.compile(r"\bpionki\b", re.IGNORECASE), "piony"),
    (re.compile(r"\bpionków\b", re.IGNORECASE), "pionów"),
    (re.compile(r"\bpionkami\b", re.IGNORECASE), "pionami"),
    (re.compile(r"\bpionkom\b", re.IGNORECASE), "pionom"),
    (re.compile(r"\bpionkach\b", re.IGNORECASE), "pionach"),
]

_IDIOM_FIXES = [
    (re.compile(r"\bzabrać\s+lini[ęe]", re.IGNORECASE), "zająć linię"),
    (re.compile(r"\bzabiera\s+lini[ęe]", re.IGNORECASE), "zajmuje linię"),
    (re.compile(r"\bzabrał\s+lini[ęe]", re.IGNORECASE), "zajął linię"),
    (re.compile(r"\bzabrała\s+lini[ęe]", re.IGNORECASE), "zajęła linię"),
    (re.compile(r"\bzagraża\s+matowi", re.IGNORECASE), "grozi matem"),
    (re.compile(r"\bzagrażając\s+matowi", re.IGNORECASE), "grożąc matem"),
    (re.compile(r"\bzagrażał\s+matowi", re.IGNORECASE), "groził matem"),
    (re.compile(r"\bgrozi\s+z\s+matem", re.IGNORECASE), "grozi matem"),
    (re.compile(r"\bzagrożenie\s+mata", re.IGNORECASE), "groźba mata"),
    (re.compile(r"\bpo\s+grze\b", re.IGNORECASE), "po partii"),
    (re.compile(r"\bkrólowa\b", re.IGNORECASE), "hetman"),
    (re.compile(r"\bkrólową\b", re.IGNORECASE), "hetmana"),
    (re.compile(r"\bkrólowej\b", re.IGNORECASE), "hetmana"),
    (re.compile(r"\bkrólowe\b", re.IGNORECASE), "hetmany"),
    (re.compile(r"\bdama\b", re.IGNORECASE), "hetman"),
    (re.compile(r"\bdamę\b", re.IGNORECASE), "hetmana"),
    (re.compile(r"\bdamy\b", re.IGNORECASE), "hetmana"),
    (re.compile(r"\bzabrać\s+pole", re.IGNORECASE), "zająć pole"),
    (re.compile(r"\bzabiera\s+pole", re.IGNORECASE), "zajmuje pole"),
    (re.compile(r"\bwykonać\s+wymianę", re.IGNORECASE), "wymienić"),
    (re.compile(r"\bwykonuje\s+wymianę", re.IGNORECASE), "wymienia"),
    (re.compile(r"\bwykonał\s+wymianę", re.IGNORECASE), "wymienił"),
]


def _fix_chess_idioms(text: str) -> str:
    def preserve_case(match: re.Match, replacement: str) -> str:
        original = match.group(0)
        if original[0].isupper():
            return replacement[0].upper() + replacement[1:]
        return replacement

    for pattern, replacement in _IDIOM_FIXES:
        text = pattern.sub(lambda m, rep=replacement: preserve_case(m, rep), text)
    return text


def _fix_genitive_errors(text: str) -> str:
    text = re.sub(
        r"\b(nie)?doceni[łl]\s+to\s+poświęcenie\b",
        lambda m: f"{'nie' if m.group(1) else ''}docenił tego poświęcenia",
        text,
        flags=re.IGNORECASE
    )
    text = re.sub(
        r"\bby\s+tego\s+nie\s+pozwoli[łl]",
        "by na to nie pozwoliły",
        text,
        flags=re.IGNORECASE
    )
    text = re.sub(
        r"\bnie\s+pozwoli[łl]yby\s+tego\b",
        "nie pozwoliłyby na to",
        text,
        flags=re.IGNORECASE
    )
    return text


def _fix_move_phrase_artifacts(text: str) -> str:
    text = re.sub(
        r"\bmog[ęe]\s+wygra[cć]\s+z\s+(\d+\.\.\.[A-Za-z0-9O\-+=#/]+)",
        r"mogę wygrać po \1",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bz ruchu tekstowego\b",
        "z ruchu z partii",
        text,
        flags=re.IGNORECASE,
    )
    return text


def _normalize_soft_prose_linebreaks(text: str) -> str:
    if not text or "\n" not in text:
        return text

    marker = "__PARA_BREAK__"
    text = text.replace("\r", "")
    text = text.replace("\n\n", marker)
    text = re.sub(r"([,;:])\n(?=[a-z])", r"\1 ", text, flags=re.IGNORECASE)
    text = re.sub(r"(\b\w{1,14})\n(?=[a-z])", r"\1 ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<=\w)\n(?=[a-z])", " ", text, flags=re.IGNORECASE)
    text = text.replace(marker, "\n\n")
    text = re.sub(r" {2,}", " ", text)
    return text


def _normalize_chess_terms(text: str) -> str:
    def _preserve_case(match: re.Match, replacement: str) -> str:
        token = match.group(0)
        return replacement.capitalize() if token[:1].isupper() else replacement

    for pattern, replacement in _TERM_REPLACEMENTS:
        text = pattern.sub(lambda m, rep=replacement: _preserve_case(m, rep), text)
    return text


def _cleanup_spacing(translated: str) -> str:
    lines = (translated or "").split("\n")
    cleaned_lines: list[str] = []

    for line in lines:
        t = re.sub(r"[ \t\r\f\v]+", " ", line)
        t = _fix_spaced_numbers(t)
        t = re.sub(r"(\d+)\s*\.\s*\.+\s*", r"\1...", t)
        t = re.sub(r"(\d+)\s*\.\s+", r"\1. ", t)
        t = t.strip()
        t = re.sub(r"(?<=[^\s\d])(?=\d+\.)", " ", t)
        t = re.sub(r"([.!?])(?!\s|$)(?=[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż])", r"\1 ", t)
        t = re.sub(r" {2,}", " ", t)
        cleaned_lines.append(t)

    return "\n".join(cleaned_lines).strip()


def postprocess_translation(translated: str, original: str) -> str:
    """Main postprocessing function - fixes common translation errors."""
    t = translated or ""

    t = _normalize_piece_glyphs(t)
    t = _fix_queen_D(t)
    t = _fix_piece_letters(t)
    t = _fix_merged_prepositions(t)
    t = _fix_square_piece_pattern(t)
    t = _sync_move_numbers(t, original or "")
    t = _strip_unwanted_zagrano(t, original or "")
    t = _normalize_chess_terms(t)
    t = _fix_chess_idioms(t)
    t = _fix_genitive_errors(t)
    t = _fix_move_phrase_artifacts(t)
    t = _normalize_soft_prose_linebreaks(t)
    t = _cleanup_spacing(t)

    return t
