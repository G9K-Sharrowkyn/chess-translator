# -*- coding: utf-8 -*-
"""Core translation logic - prepares text for translation and processes results."""

from typing import List, Dict
import re
import logging

from .san import postprocess_translated_marked
from .config import B_START, B_END

log = logging.getLogger("chess_pdf.translation_core")

token_logger = logging.getLogger("non_polish_tokens")
token_logger.setLevel(logging.INFO)
if not token_logger.handlers:
    token_handler = logging.FileHandler("non_polish_tokens.log", mode='w', encoding='utf-8')
    token_handler.setFormatter(logging.Formatter("%(message)s"))
    token_logger.addHandler(token_handler)
    token_logger.info("=== LOGGER INITIALIZED ===")

_MOVE_START_RE = re.compile(r'^\s*\d{1,3}\s*(?:\.\.\.|\.)')
_MOVE_PREFIX_RE = re.compile(r'^\d{1,3}\.{1,3}')
_RESULT_TOKEN_RE = re.compile(r'^(?:1-0|0-1|1/2-1/2|\*)$')
_EVAL_TOKEN_RE = re.compile(r'^(?:\+/-|-/\+|±|∓|\+=|=\+|=|∞)$')

_SAN_SUFFIX = r'(?:=[QRBN])?(?:[+#t])?(?:[!?]{1,2})?(?:N)?'
_SAN_TOKEN_RE = re.compile(
    r'^(?:'
    rf'(?:O-?O(?:-?O)?|0-0(?:-0)?){_SAN_SUFFIX}'
    r'|'
    rf'(?:[KQRBN])(?:[a-h1-8]{{0,2}})x?[a-h][1-8]{_SAN_SUFFIX}'
    r'|'
    rf'(?:[a-h])x[a-h][1-8]{_SAN_SUFFIX}'
    r'|'
    rf'(?:[a-h][1-8]){_SAN_SUFFIX}'
    r')$',
    flags=re.IGNORECASE,
)


def _strip_token_wrappers(token: str) -> str:
    if not token:
        return ""
    t = token.strip()
    t = t.strip("()[]{}")
    t = t.strip(",;:")
    return t


def _is_chess_notation_token(token: str) -> bool:
    """Check if token is chess notation (SAN)."""
    t = _strip_token_wrappers(token)
    if not t:
        return False

    if t == "N":
        return True
    if t in ("+", "#", "t"):
        return True
    if re.fullmatch(r'[.]{1,3}', t):
        return True
    if re.fullmatch(r'[-–—]+', t):
        return True
    if re.fullmatch(r'[!?]+', t):
        return True
    if _RESULT_TOKEN_RE.fullmatch(t):
        return True
    if _EVAL_TOKEN_RE.fullmatch(t):
        return True
    if re.fullmatch(r'\d{1,3}', t):
        return True
    if re.fullmatch(r'\d{1,3}\.{1,3}', t):
        return True

    m = _MOVE_PREFIX_RE.match(t)
    if m:
        rest = t[m.end():]
        if not rest:
            return True
        t = rest.lstrip(".")

    for suffix in ("+/-", "-/+"):
        if t.endswith(suffix) and len(t) > len(suffix):
            core = t[: -len(suffix)]
            if _SAN_TOKEN_RE.fullmatch(core):
                return True

    return _SAN_TOKEN_RE.fullmatch(t) is not None


def _find_notation_prefix_end(text: str) -> int | None:
    """Return char index after last notation token at start."""
    last_end: int | None = None

    for m in re.finditer(r'\S+', text or ""):
        token = m.group(0)
        token_start = m.start()

        if last_end is not None:
            between = text[last_end:token_start]
            if '\n' in between:
                # Keep scanning across wrapped notation lines.
                if _is_chess_notation_token(token) or token in ("N", "t", "+", "#"):
                    last_end = m.end()
                    continue
                break

        if _is_chess_notation_token(token):
            last_end = m.end()
        else:
            break

    return last_end


def _split_bold_at_move_boundary(runs: List[Dict]) -> List[Dict]:
    """Split bold runs containing notation + prose text."""
    result: List[Dict] = []

    for run in runs:
        if not run.get("bold"):
            result.append(run)
            continue

        text = run.get("text", "") or ""
        if not _MOVE_START_RE.match(text):
            result.append(run)
            continue

        end = _find_notation_prefix_end(text)
        if not end or end >= len(text):
            result.append(run)
            continue

        bold_part = text[:end].rstrip()
        regular_part = text[end:]

        if bold_part:
            result.append({"text": bold_part, "bold": True})
        if regular_part:
            if bold_part and not bold_part[-1].isspace() and not regular_part[0].isspace():
                regular_part = " " + regular_part
            result.append({"text": regular_part, "bold": False})

    return result


def _coalesce_style_runs(spans: List[Dict]) -> List[Dict]:
    """Merge adjacent spans of same style into runs."""
    runs = []
    for sp in spans or []:
        txt = sp.get("text") or ""
        if not txt:
            continue
        bold = bool(sp.get("is_bold", False))

        if txt == " " and runs and runs[-1]["bold"] == bold:
            runs[-1]["text"] += " "
            continue

        if runs and runs[-1]["bold"] == bold:
            prev_text = runs[-1]["text"]
            if prev_text and txt:
                needs_space = (not prev_text[-1].isspace() and not txt[0].isspace())
                if needs_space:
                    runs[-1]["text"] += " " + txt
                else:
                    runs[-1]["text"] += txt
            else:
                runs[-1]["text"] += txt
        else:
            runs.append({"text": txt, "bold": bold})

    for r in runs:
        r["text"] = r["text"].replace("\u00ad", "")

    merged = []
    i = 0
    while i < len(runs):
        current = runs[i]
        if (current.get("bold")
            and i + 2 < len(runs)
            and runs[i + 1].get("text", "").strip() == ""
            and not runs[i + 1].get("bold")
            and runs[i + 2].get("bold")):
            merged_text = current["text"] + runs[i + 1]["text"] + runs[i + 2]["text"]
            merged.append({"text": merged_text, "bold": True})
            i += 3
        else:
            merged.append(current)
            i += 1

    return merged


def _snap_cut_to_boundary(text: str, cut: int, lo: int, hi: int, window: int = 24) -> int:
    """Snap a cut index to nearby whitespace to avoid splitting words."""
    cut = max(lo, min(hi, cut))
    if cut <= lo or cut >= hi:
        return cut

    if text[cut - 1].isspace() or (cut < len(text) and text[cut].isspace()):
        return cut

    for delta in range(1, window + 1):
        left = cut - delta
        if left > lo and (text[left - 1].isspace() or (left < len(text) and text[left].isspace())):
            return left
        right = cut + delta
        if right < hi and (text[right - 1].isspace() or (right < len(text) and text[right].isspace())):
            return right

    return cut


def _project_style_runs_onto_text(style_runs: List[Dict], target_text: str) -> List[Dict]:
    """Project bold/non-bold style layout onto newer text of different content."""
    if not target_text:
        return []
    if not style_runs:
        return [{"text": target_text, "bold": False}]
    if len(style_runs) == 1:
        return [{"text": target_text, "bold": bool(style_runs[0].get("bold"))}]

    weights = [max(1, len((run.get("text") or ""))) for run in style_runs]
    total = max(1, sum(weights))
    text_len = len(target_text)

    cuts: List[int] = []
    cumulative = 0
    prev = 0
    for w in weights[:-1]:
        cumulative += w
        raw_cut = int(round(text_len * cumulative / total))
        snapped = _snap_cut_to_boundary(target_text, raw_cut, prev, text_len)
        if snapped < prev:
            snapped = prev
        cuts.append(snapped)
        prev = snapped

    projected: List[Dict] = []
    cursor = 0
    for run, end in zip(style_runs, cuts + [text_len]):
        segment = target_text[cursor:end]
        cursor = end
        if not segment:
            continue
        bold = bool(run.get("bold"))
        if projected and projected[-1]["bold"] == bold:
            projected[-1]["text"] += segment
        else:
            projected.append({"text": segment, "bold": bold})

    return projected or [{"text": target_text, "bold": False}]


def _build_runs_from_block(block: Dict) -> List[Dict]:
    """Build style runs from original font spans and current block text."""
    text = block.get("text", "") or ""
    style_spans = (
        block.get("_style_spans_backup")
        or block.get("_ocr_spans_backup")
        or block.get("spans", [])
    )

    if not style_spans:
        return [{"text": text, "bold": False}] if text else []

    style_runs = _coalesce_style_runs(style_spans)
    if not style_runs:
        return [{"text": text, "bold": False}] if text else []
    if not text:
        return style_runs

    style_text = "".join(run.get("text", "") for run in style_runs)
    if style_text == text:
        return style_runs

    return _project_style_runs_onto_text(style_runs, text)


def _runs_to_marked_text(runs: List[Dict]) -> str:
    """Convert runs to marked text with [[B]]...[[/B]]."""
    parts = []
    for r in runs:
        text_part = r.get("text", "")
        if r.get("bold"):
            parts.append(B_START + text_part + B_END)
        else:
            parts.append(text_part)
    return "".join(parts)


def build_marked_text_for_translation(block: Dict) -> str:
    """Build text with [[B]]...[[/B]] markers for AI translation."""
    runs = _build_runs_from_block(block)
    if not runs:
        return ""
    return _runs_to_marked_text(runs)


_HEADLINE_AFTER_BOLD_RE = re.compile(
    r'(\[\[B\]\]\s*(?:\d{1,3}\s*(?:\.\.\.|\.))[^[]*?\[\[\/B\]\])(?!\s*\n)',
    flags=re.UNICODE
)


def _force_newline_after_bold_headings(marked: str) -> str:
    """Insert newline after [[B]]NN. ...[[/B]] if missing."""
    return _HEADLINE_AFTER_BOLD_RE.sub(r'\1\n', marked)


_BOLD_SPAN_RE = re.compile(r'\[\[B\]\](.*?)\[\[/B\]\]', flags=re.DOTALL)
_CHESS_MOVE_BOLD_RE = re.compile(r'\b\d{1,3}\s*(?:\.\.\.|\.)\s*[A-Za-z0-9][^\s,;:]*')
_HEADING_BOLD_RE = re.compile(r'\b(?:diagram|rysunek|figure|fig\.?|game|partia|chapter|rozdzia[\u0142l]|exercise|\u0107wiczenie)\b[^\n]*', flags=re.IGNORECASE)


def _has_bold_leak(spans: List[str], plain_len: int, expected_count: int) -> bool:
    """Check if bold covers too much text."""
    if plain_len <= 0:
        return False
    coverage = sum(len(s.strip()) for s in spans)
    ratio = coverage / max(1, plain_len)
    count_off = bool(expected_count) and (len(spans) != expected_count)
    return ratio > 0.55 or count_off


def _rebuild_bold_from_patterns(runs: List[Dict], translated_text: str) -> str:
    """Fallback: rebuild bold markers from notation patterns."""
    plain = translated_text.replace(B_START, "").replace(B_END, "")
    expected = [r for r in runs or [] if r.get("bold") and (r.get("text") or "").strip()]
    expected_count = len(expected)
    if expected_count == 0:
        return plain

    if _MOVE_START_RE.match(plain):
        end = _find_notation_prefix_end(plain)
        if end:
            head = plain[:end].rstrip()
            tail = plain[end:]
            if head:
                return f"{B_START}{head}{B_END}{tail}"

    spans = [(m.start(), min(m.end(), m.start() + 140)) for m in _CHESS_MOVE_BOLD_RE.finditer(plain)]
    if not spans:
        spans = [(m.start(), min(m.end(), m.start() + 140)) for m in _HEADING_BOLD_RE.finditer(plain)]
    if not spans:
        if not plain.strip():
            return plain
        lines = plain.split("\n")
        notation_lines = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "N" and notation_lines:
                notation_lines.append(line)
                continue
            if i == 0 and _MOVE_START_RE.match(stripped):
                notation_lines.append(line)
            elif notation_lines and _is_chess_notation_token(stripped):
                notation_lines.append(line)
            else:
                break

        if notation_lines:
            bold_part = "\n".join(notation_lines)
            rest_lines = lines[len(notation_lines):]
            if rest_lines:
                return f"{B_START}{bold_part}{B_END}\n" + "\n".join(rest_lines)
            return f"{B_START}{bold_part}{B_END}"
        else:
            first_line, *rest = plain.split("\n", 1)
            if rest:
                return f"{B_START}{first_line}{B_END}\n{rest[0]}"
            return f"{B_START}{plain}{B_END}"

    use_count = len(spans) if spans else expected_count
    spans = spans[:use_count]

    clean_spans = []
    for start, end in spans:
        newline_pos = plain.find("\n", start)
        if newline_pos != -1:
            end = min(end, newline_pos)
        clean_spans.append((start, end))
    spans = clean_spans

    rebuilt = plain
    for start, end in sorted(spans, reverse=True):
        rebuilt = rebuilt[:end] + B_END + rebuilt[end:]
        rebuilt = rebuilt[:start] + B_START + rebuilt[start:]
    return rebuilt


def _normalize_notation_in_bold(text: str) -> str:
    """Normalize spacing in chess notation inside bold markers."""
    if not text or B_START not in text:
        return text

    def normalize_bold_content(m):
        content = m.group(1)
        content = re.sub(r'(\d+\.)\s+', r'\1', content)
        content = re.sub(r'\s+N$', 'N', content)
        content = re.sub(r'(\.\.\.)\s+', r'\1', content)
        return f'{B_START}{content}{B_END}'

    return re.sub(
        rf'{re.escape(B_START)}(.*?){re.escape(B_END)}',
        normalize_bold_content,
        text,
        flags=re.DOTALL
    )


def _fix_novelty_outside_bold(text: str) -> str:
    """Fix "N" (Novelty) appearing right after bold close."""
    if not text or B_END not in text:
        return text

    pattern = re.compile(
        rf'( ?)({re.escape(B_END)})'
        rf'(\s*)'
        rf'(N)'
        rf'(?=\s|$|\n)'
    )

    def replacer(m):
        ws = m.group(3)
        has_newline = '\n' in ws
        suffix = '\n' if has_newline else ''
        return f'N{B_END}{suffix}'

    result = pattern.sub(replacer, text)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result


def _reapply_bold_markers(runs: List[Dict], translated_text: str) -> str:
    """Preserve GPT bold markers, rebuild if leaked."""
    if not translated_text:
        return translated_text

    translated_text = _fix_novelty_outside_bold(translated_text)
    translated_text = _normalize_notation_in_bold(translated_text)

    expected_count = sum(1 for r in runs or [] if r.get("bold") and (r.get("text") or "").strip())
    spans = list(_BOLD_SPAN_RE.finditer(translated_text))
    plain = translated_text.replace(B_START, "").replace(B_END, "")
    balanced = translated_text.count(B_START) == translated_text.count(B_END)

    if spans and balanced and not _has_bold_leak([m.group(1) for m in spans], len(plain), expected_count):
        return translated_text

    if spans and expected_count == 1:
        if _MOVE_START_RE.match(plain):
            end = _find_notation_prefix_end(plain)
            if end and end < len(plain):
                head = plain[:end].rstrip()
                tail = plain[end:]
                if head and tail.strip():
                    return f"{B_START}{head}{B_END}{tail}"

        total_src = sum(len(r.get("text", "")) for r in runs or [])
        bold_src = sum(len(r.get("text", "")) for r in runs or [] if r.get("bold"))
        if total_src > 0 and bold_src > 0:
            target_len = int(len(plain) * bold_src / total_src)
            target_len = max(1, min(len(plain), target_len))
            newline_pos = plain.find("\n")
            if newline_pos != -1:
                target_len = min(target_len, newline_pos)
            return f"{B_START}{plain[:target_len]}{B_END}{plain[target_len:]}"

    if expected_count > 0 and not spans:
        if expected_count == 1:
            sentence_split = re.split(r'(?<=[\.!?])\s+', plain, maxsplit=1)
            if len(sentence_split) == 2 and sentence_split[0].strip() and sentence_split[1].strip():
                return f"{B_START}{sentence_split[0]}{B_END} {sentence_split[1]}"

        if "\n" in plain:
            lines = plain.split("\n")
            notation_lines = []
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped == "N" and notation_lines:
                    notation_lines.append(line)
                    continue
                if i == 0 and _MOVE_START_RE.match(stripped):
                    notation_lines.append(line)
                elif notation_lines and _is_chess_notation_token(stripped):
                    notation_lines.append(line)
                else:
                    break

            if notation_lines:
                bold_part = "\n".join(notation_lines)
                rest_lines = lines[len(notation_lines):]
                rest_part = "\n".join(rest_lines) if rest_lines else ""
                if rest_part:
                    return f"{B_START}{bold_part}{B_END}\n{rest_part}"
                return f"{B_START}{bold_part}{B_END}"
            else:
                first_line, rest = plain.split("\n", 1)
                return f"{B_START}{first_line}{B_END}\n{rest}"
        return _rebuild_bold_from_patterns(runs, plain)

    return _rebuild_bold_from_patterns(runs, translated_text)


def _log_non_polish_tokens(text: str):
    """Log tokens that aren't standard Polish words."""
    if not text:
        return

    token_logger.info(f"=== ANALYZING TEXT ===")
    token_logger.info(f"Text length: {len(text)}")

    token_pattern = re.compile(r'\S+')
    tokens = token_pattern.findall(text)

    token_logger.info(f"Found {len(tokens)} tokens")

    pure_polish_pattern = re.compile(r'^[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9\.\,\;\:\!\?\(\)\-]+$')

    for i, token in enumerate(tokens):
        is_polish = pure_polish_pattern.match(token)
        status = "POLISH" if is_polish else "NON-POLISH"
        token_logger.info(f"{i+1:3d}. [{status}] {repr(token)}")

        if any(ord(c) > 127 and c not in 'ąćęłńóśźżĄĆĘŁŃÓŚŹŻ' for c in token):
            token_logger.info(f"     ^ SPECIAL CHARS: {[c for c in token if ord(c) > 127 and c not in 'ąćęłńóśźżĄĆĘŁŃÓŚŹŻ']}")

    token_logger.info(f"=== END ANALYSIS ===\n")


def translate_blocks_intelligent(blocks: List[Dict], translator) -> List[Dict]:
    """Translate text blocks preserving formatting."""
    token_logger.info("@@@ TRANSLATE_BLOCKS_INTELLIGENT CALLED @@@")
    token_logger.info(f"@@@ Number of blocks: {len(blocks)} @@@")
    token_logger.info(f"@@@ Translator type: {type(translator)} @@@")

    log.info(f"Translating {len(blocks)} blocks...")

    payloads, idx_map = [], []
    runs_map = {}

    for i, b in enumerate(blocks):
        src = (b.get("text") or "").strip()
        if not src and not b.get("spans"):
            b["translated_marked"] = ""
            continue
        runs = _build_runs_from_block(b)
        marked = _runs_to_marked_text(runs) if runs else ""

        payloads.append(marked)
        idx_map.append(i)
        runs_map[i] = runs

    if payloads:
        log.info(f"Sending {len(payloads)} text chunks to translator (this may take a while)...")
        try:
            translated_list = translator.translate_chunks(payloads)
        except Exception as e:
            import traceback
            log.error(f"Translation failed: {e}")
            log.error(f"Traceback: {traceback.format_exc()}")
            translated_list = payloads

        for j, tr in enumerate(translated_list):
            tr = postprocess_translated_marked(tr)
            tr = _reapply_bold_markers(runs_map.get(idx_map[j], []), tr)
            tr = _force_newline_after_bold_headings(tr)

            token_logger.info(f"=== PROCESSING TRANSLATION {j+1} ===")
            token_logger.info(f"Original text length: {len(tr)}")
            _log_non_polish_tokens(tr)
            token_logger.info(f"=== FINISHED TRANSLATION {j+1} ===\n")

            blocks[idx_map[j]]["translated_marked"] = tr

    for b in blocks:
        tm = b.get("translated_marked", "") or ""
        b["translated"] = tm.replace(B_START, "").replace(B_END, "")

    return blocks
