# -*- coding: utf-8 -*-
"""Chess board geometry detection - identifies board axis markers (a-h, 1-8)."""

from typing import List, Optional
import fitz
from .config import AXIS_LETTERS, AXIS_DIGITS


def _rect_overlap_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    """Calculate overlap ratio between two rectangles."""
    inter = a & b
    if inter.is_empty or a.get_area() == 0:
        return 0.0
    return inter.get_area() / a.get_area()


def _cluster_sorted(values: List[float], tol: float) -> List[List[float]]:
    """Cluster nearby 1D values together."""
    if not values:
        return []
    values = sorted(values)
    clusters: List[List[float]] = [[values[0]]]
    for v in values[1:]:
        if abs(v - clusters[-1][-1]) <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return clusters


def find_board_axis_regions(page: fitz.Page, tol: float = 6.0, pad: float = 1.5) -> List[fitz.Rect]:
    """Find regions containing chess board axis markers (a-h, 1-8) to skip during translation."""
    skip_rects: List[fitz.Rect] = []
    words = page.get_text("words")
    if not words:
        return skip_rects

    letters, digits = [], []
    for w in words:
        x0, y0, x1, y1, txt = w[:5]
        txt = (txt or "").strip()
        if len(txt) != 1:
            continue
        r = fitz.Rect(x0, y0, x1, y1)
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        if txt in AXIS_LETTERS:
            letters.append((txt, cx, cy, r))
        elif txt in AXIS_DIGITS:
            digits.append((txt, cx, cy, r))

    if letters:
        xs = [cx for _, cx, _, _ in letters]
        for cluster_x in _cluster_sorted(xs, tol=tol):
            members = [t for t in letters if any(abs(t[1] - x) <= tol for x in cluster_x)]
            if len(members) < 7:
                continue
            members.sort(key=lambda t: t[2])
            uniq = set(ch.lower() for ch, _, _, _ in members[:8])
            if set("abcdefgh").issubset(uniq) or len(uniq.intersection(set("abcdefgh"))) >= 7:
                for ch, _, _, r in members[:8]:
                    if ch.lower() in "abcdefgh":
                        skip_rects.append(fitz.Rect(r.x0 - pad, r.y0 - pad, r.x1 + pad, r.y1 + pad))

    if digits:
        ys = [cy for _, _, cy, _ in digits]
        for cluster_y in _cluster_sorted(ys, tol=tol):
            members = [t for t in digits if any(abs(t[2] - y) <= tol for y in cluster_y)]
            if len(members) < 7:
                continue
            members.sort(key=lambda t: t[1])
            uniq = set(ch for ch, _, _, _ in members[:8])
            if set("12345678").issubset(uniq) or len(uniq.intersection(set("12345678"))) >= 7:
                for ch, _, _, r in members[:8]:
                    if ch in "12345678":
                        skip_rects.append(fitz.Rect(r.x0 - pad, r.y0 - pad, r.x1 + pad, r.y1 + pad))

    return skip_rects


def _avoid_regions(rect: fitz.Rect, blockers: List[fitz.Rect], pad: float = 1.0) -> Optional[fitz.Rect]:
    """Trim rectangle to avoid overlapping with blocker regions."""
    r = fitz.Rect(rect)
    for b in blockers:
        if not r.intersects(b):
            continue
        overlap = r & b
        if overlap.is_empty:
            continue
        horiz = overlap.width / max(r.width, 1e-6)
        vert = overlap.height / max(r.height, 1e-6)
        if horiz >= vert:
            if b.y0 <= r.y0 < b.y1:
                r.y0 = min(b.y1 + pad, r.y1 - 1)
            else:
                r.y1 = max(b.y0 - pad, r.y0 + 1)
        else:
            if b.x0 <= r.x0 < b.x1:
                r.x0 = min(b.x1 + pad, r.x1 - 1)
            else:
                r.x1 = max(b.x0 - pad, r.x0 + 1)

        if r.width <= 1 or r.height <= 1:
            return None
    return r
