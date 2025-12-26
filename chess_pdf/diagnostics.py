# -*- coding: utf-8 -*-
"""Diagnostic tools for translation quality analysis."""

import re
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from .config import TARGET_BOLD_FONT

log = logging.getLogger(__name__)

POLISH_IDIOM_ERRORS = [
    (r"\bzabr[aą][ćłl]\s+lini[ęe]", "Dosłowne tłumaczenie 'take the line'", "zająć linię"),
    (r"\bzagraża\s+matowi", "Dosłowne tłumaczenie 'threatens mate'", "grozi matem"),
    (r"\bniedoceni[łl]\s+to\s+poświęcenie", "Błąd przypadka - biernik zamiast dopełniacza", "niedocenił tego poświęcenia"),
    (r"\bby\s+tego\s+nie\s+pozwoli[łl]", "Błąd składni - brak przyimka 'na'", "by na to nie pozwoliły"),
    (r"\bnie\s+pozwoli[łl]yby\s+tego", "Błąd składni - brak przyimka 'na'", "nie pozwoliłyby na to"),
    (r"\bpo\s+grze\b", "Błędna terminologia - 'gra' zamiast 'partia'", "po partii"),
    (r"\bkrólowa\b", "Błędna terminologia - 'królowa' zamiast 'hetman'", "hetman"),
    (r"\bdama\b", "Błędna terminologia - 'dama' zamiast 'hetman'", "hetman"),
    (r"\bkoń\s+(?:na\s+)?[a-h][1-8]", "Nieformalna terminologia - 'koń' zamiast 'skoczek'", "skoczek"),
    (r"\bpionki\b", "Nieformalna terminologia - 'pionki' zamiast 'piony'", "piony"),
    (r"\bzagrano\s+\d+\.", "Zbędne 'zagrano' - dosłowne tłumaczenie", "po prostu numer ruchu"),
    (r"\bto\s+poświęcenie\b(?!\s+jest|\s+było)", "Potencjalny błąd przypadka z 'poświęcenie'", "tego poświęcenia (dopełniacz)"),
    (r"\bzabrać\s+pole", "Dosłowne 'take the square'", "zająć pole / opanować pole"),
    (r"\bjest\s+lepsze?\s+dla\s+(?:białych|czarnych)", "Dosłowne 'is better for White/Black'", "białe/czarne stoją lepiej"),
    (r"\bwykonać\s+wymianę", "Zbyt formalne - można uprościć", "wymienić"),
    (r"\bgrozi\s+z\s+matem", "Błąd składni - zbędny przyimek 'z'", "grozi matem"),
    (r"\bzagrożenie\s+mata", "Nienaturalna konstrukcja", "groźba mata"),
]

GRAMMAR_WARNINGS = [
    (r"  +", "Podwójna spacja", None),
    (r"[.,!?][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]", "Brak spacji po interpunkcji", None),
    (r"\s[.,!?]", "Spacja przed interpunkcją", None),
    (r"\.\s+[a-ząćęłńóśźż]", "Mała litera po kropce (sprawdź kontekst)", None),
]


@dataclass
class BoldDiagnostic:
    """Diagnostyka pojedynczego pogrubienia."""
    text: str
    source: str
    font_name: str
    font_size: float
    is_correct: bool
    warning: Optional[str] = None


@dataclass
class LanguageDiagnostic:
    """Diagnostyka błędu językowego."""
    text_fragment: str
    error_type: str
    description: str
    suggestion: Optional[str]
    position: int
    severity: str = "warning"


@dataclass
class BlockDiagnostic:
    """Pełna diagnostyka bloku tekstu."""
    block_index: int
    original_text: str
    translated_text: str
    bold_diagnostics: List[BoldDiagnostic] = field(default_factory=list)
    language_diagnostics: List[LanguageDiagnostic] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.bold_diagnostics) or bool(self.language_diagnostics)

    @property
    def bold_issues(self) -> List[BoldDiagnostic]:
        return [b for b in self.bold_diagnostics if not b.is_correct]

    @property
    def language_errors(self) -> List[LanguageDiagnostic]:
        return [l for l in self.language_diagnostics if l.severity == "error"]


@dataclass
class PageDiagnostic:
    """Diagnostyka całej strony."""
    page_num: int
    blocks: List[BlockDiagnostic] = field(default_factory=list)

    @property
    def total_bold_issues(self) -> int:
        return sum(len(b.bold_issues) for b in self.blocks)

    @property
    def total_language_issues(self) -> int:
        return sum(len(b.language_diagnostics) for b in self.blocks)

    @property
    def has_issues(self) -> bool:
        return any(b.has_issues for b in self.blocks)


def _normalize_font_name(font_name: str) -> str:
    """Normalizuje nazwę czcionki do porównania."""
    return (font_name or "").lower().replace(" ", "").replace("-", "").replace("_", "")


def _get_bold_source(span: Dict) -> tuple[str, bool]:
    """Określa źródło pogrubienia dla spana."""
    font_name = span.get("font", "") or span.get("fontname", "")
    font_normalized = _normalize_font_name(font_name)
    target_normalized = _normalize_font_name(TARGET_BOLD_FONT)

    if target_normalized in font_normalized:
        return (f"TARGET_FONT:{TARGET_BOLD_FONT}", True)

    if span.get("is_bold", False):
        return ("FLAG:is_bold", False)

    font_lower = font_name.lower()
    for keyword in ("bold", "semibold", "demi", "black", "heavy"):
        if keyword in font_lower:
            return (f"KEYWORD:{keyword}", False)

    return ("UNKNOWN", False)


def diagnose_bold_sources(blocks: List[Dict]) -> List[BoldDiagnostic]:
    """Analizuje wszystkie pogrubienia w blokach i ich źródła."""
    diagnostics = []

    for block in blocks:
        spans = block.get("spans", [])
        for span in spans:
            if not span.get("is_bold", False):
                continue

            text = span.get("text", "").strip()
            if not text:
                continue

            font_name = span.get("font", "") or span.get("fontname", "")
            font_size = span.get("font_size", span.get("size", 0))
            source, is_correct = _get_bold_source(span)

            warning = None
            if not is_correct:
                warning = f"Pogrubienie NIE pochodzi z {TARGET_BOLD_FONT}!"

            diagnostics.append(BoldDiagnostic(
                text=text,
                source=source,
                font_name=font_name,
                font_size=font_size,
                is_correct=is_correct,
                warning=warning
            ))

    return diagnostics


def diagnose_polish_quality(text: str) -> List[LanguageDiagnostic]:
    """Analizuje tekst pod kątem typowych błędów w polskim tłumaczeniu."""
    diagnostics = []

    if not text:
        return diagnostics

    for pattern, description, suggestion in POLISH_IDIOM_ERRORS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            diagnostics.append(LanguageDiagnostic(
                text_fragment=match.group(0),
                error_type="IDIOM_ERROR",
                description=description,
                suggestion=suggestion,
                position=match.start(),
                severity="error"
            ))

    for pattern, description, suggestion in GRAMMAR_WARNINGS:
        for match in re.finditer(pattern, text):
            diagnostics.append(LanguageDiagnostic(
                text_fragment=match.group(0),
                error_type="GRAMMAR_WARNING",
                description=description,
                suggestion=suggestion,
                position=match.start(),
                severity="warning"
            ))

    return diagnostics


def generate_block_diagnostic(
    block_index: int,
    original_block: Dict,
    translated_text: str
) -> BlockDiagnostic:
    """Generuje pełną diagnostykę dla pojedynczego bloku."""
    original_text = original_block.get("text", "")
    bold_diags = diagnose_bold_sources([original_block])
    lang_diags = diagnose_polish_quality(translated_text)

    return BlockDiagnostic(
        block_index=block_index,
        original_text=original_text,
        translated_text=translated_text,
        bold_diagnostics=bold_diags,
        language_diagnostics=lang_diags
    )


def generate_page_diagnostic(
    page_num: int,
    original_blocks: List[Dict],
    translated_texts: List[str]
) -> PageDiagnostic:
    """Generuje pełną diagnostykę dla strony."""
    page_diag = PageDiagnostic(page_num=page_num)

    for i, (block, trans_text) in enumerate(zip(original_blocks, translated_texts)):
        block_diag = generate_block_diagnostic(i, block, trans_text)
        if block_diag.has_issues:
            page_diag.blocks.append(block_diag)

    return page_diag


def format_diagnostic_report(page_diag: PageDiagnostic) -> str:
    """Formatuje diagnostykę strony jako raport tekstowy."""
    lines = []
    lines.append("=" * 80)
    lines.append(f"RAPORT DIAGNOSTYCZNY - STRONA {page_diag.page_num}")
    lines.append("=" * 80)

    if not page_diag.has_issues:
        lines.append("\nBrak wykrytych problemów na tej stronie.\n")
        return "\n".join(lines)

    lines.append(f"\nPODSUMOWANIE:")
    lines.append(f"   - Problemy z pogrubieniem: {page_diag.total_bold_issues}")
    lines.append(f"   - Problemy językowe: {page_diag.total_language_issues}")
    lines.append("")

    for block_diag in page_diag.blocks:
        lines.append("-" * 60)
        lines.append(f"BLOK #{block_diag.block_index}")
        lines.append(f"Oryginał: {block_diag.original_text[:100]}...")
        lines.append(f"Tłumaczenie: {block_diag.translated_text[:100]}...")
        lines.append("")

        if block_diag.bold_diagnostics:
            lines.append("  POGRUBIENIA:")
            for bd in block_diag.bold_diagnostics:
                status = "OK" if bd.is_correct else "BŁĄD"
                lines.append(f"    [{status}] \"{bd.text}\"")
                lines.append(f"       Źródło: {bd.source}")
                lines.append(f"       Font: {bd.font_name} ({bd.font_size}pt)")
                if bd.warning:
                    lines.append(f"       {bd.warning}")
            lines.append("")

        if block_diag.language_diagnostics:
            lines.append("  POLSZCZYZNA:")
            for ld in block_diag.language_diagnostics:
                icon = "BŁĄD" if ld.severity == "error" else "UWAGA"
                lines.append(f"    [{icon}] [{ld.error_type}] \"{ld.text_fragment}\"")
                lines.append(f"       {ld.description}")
                if ld.suggestion:
                    lines.append(f"       -> Sugestia: {ld.suggestion}")
            lines.append("")

    lines.append("=" * 80)
    return "\n".join(lines)


def save_diagnostic_report(page_diag: PageDiagnostic, output_path: str) -> None:
    """Zapisuje raport diagnostyczny do pliku."""
    report = format_diagnostic_report(page_diag)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    log.info(f"Raport diagnostyczny zapisany: {output_path}")


def run_diagnostics_on_translation(
    original_blocks: List[Dict],
    translated_texts: List[str],
    page_num: int,
    output_dir: Optional[str] = None
) -> PageDiagnostic:
    """Uruchamia pełną diagnostykę po tłumaczeniu strony."""
    page_diag = generate_page_diagnostic(page_num, original_blocks, translated_texts)

    if output_dir and page_diag.has_issues:
        import os
        os.makedirs(output_dir, exist_ok=True)
        report_path = os.path.join(output_dir, f"diagnostic_page_{page_num:03d}.txt")
        save_diagnostic_report(page_diag, report_path)

    return page_diag
