# -*- coding: utf-8 -*-
"""GPT-4o-mini based chess text translator (EN -> PL)."""

import os
import re
import time
import random
import logging
from typing import List
from openai import OpenAI

from .base import Translator
from .prompts import SYSTEM_PROMPT
from .protect import protect_chess_notation, restore_chess_notation
from .postprocess import postprocess_translation, looks_like_refusal

log = logging.getLogger(__name__)


class GPT4MiniTranslator(Translator):
    """Translator using OpenAI GPT-4o-mini with chess notation protection."""

    def __init__(
        self,
        api_key: str | None = None,
        temperature: float = 0.0,
        max_retries: int = 6,
        delay_between_requests: float | None = None
    ):
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set for GPT-4 mini translator.")

        self.client = OpenAI(api_key=api_key)
        self.temperature = float(temperature)
        self.max_retries = int(max_retries)

        if delay_between_requests is None:
            self.delay_between_requests = float(os.getenv("CHESS_TRANSLATION_DELAY", "1.0"))
        else:
            self.delay_between_requests = float(delay_between_requests)

    def translate_chunks(
        self,
        texts: List[str],
        source_lang: str = "EN",
        target_lang: str = "PL"
    ) -> List[str]:
        """Translate list of chess texts with notation protection."""
        results: List[str] = []

        for idx, text in enumerate(texts):
            if not text.strip():
                results.append(text)
                continue

            if idx > 0 and self.delay_between_requests > 0:
                log.debug(f"[GPT4Mini] Sleeping {self.delay_between_requests}s before next translation...")
                time.sleep(self.delay_between_requests)

            protected_text, placeholders = protect_chess_notation(text)

            translated: str | None = None
            for attempt in range(self.max_retries):
                try:
                    log.info(f"[GPT4Mini] Translating chunk {idx+1}/{len(texts)} (attempt {attempt+1}/{self.max_retries})")

                    user_content = f"""Translate to Polish. Keep <<<CHESS_X>>> placeholders EXACTLY as they are.
Keep formatting markers [[B]] and [[/B]] EXACTLY as they are.

{protected_text}"""

                    resp = self.client.chat.completions.create(
                        model="gpt-4o-mini",
                        temperature=self.temperature,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_content},
                        ],
                    )
                    candidate = (resp.choices[0].message.content or "").strip()

                    log.warning(f"[GPT4Mini] PROTECTED TEXT sent to GPT: {protected_text[:200]}")
                    log.warning(f"[GPT4Mini] RAW GPT RESPONSE: {candidate[:200]}")
                    log.warning(f"[GPT4Mini] PLACEHOLDERS: {placeholders}")

                    candidate = restore_chess_notation(candidate, placeholders)
                    log.warning(f"[GPT4Mini] AFTER RESTORE: {candidate[:200]}")

                    log.debug(f"[GPT4Mini] Before postprocess: {candidate[:100]}")
                    candidate = postprocess_translation(candidate, text)
                    log.warning(f"[GPT4Mini] AFTER POSTPROCESS: {candidate[:200]}")
                    log.debug(f"[GPT4Mini] After postprocess: {candidate[:100]}")

                    if candidate and not looks_like_refusal(candidate):
                        translated = candidate
                        log.info("[GPT4Mini] translation ok")
                        break

                except Exception as e:
                    log.warning(f"[GPT4Mini] API call failed (attempt {attempt+1}): {e}")

                    delay = None
                    if _is_rate_limit_error(e):
                        delay = _retry_delay_seconds(e, attempt + 1)

                    if delay is None:
                        delay = (2 ** attempt) + random.uniform(0, 1)

                    if attempt < self.max_retries - 1:
                        time.sleep(delay)

            results.append(translated if translated is not None else text)

        return results


def _is_rate_limit_error(exc: Exception) -> bool:
    """Check if exception is an OpenAI rate limit error."""
    text = str(exc).lower()
    if "rate limit" in text or "limit reached" in text:
        return True
    status = getattr(exc, "status_code", None)
    if status == 429:
        return True
    code = getattr(getattr(exc, "error", None), "code", None)
    return code == "rate_limit_exceeded"


def _retry_delay_seconds(exc: Exception, attempt: int) -> float | None:
    """Extract retry delay from rate limit error message."""
    text = str(exc)
    match = re.search(r"try again in ([0-9.]+)(ms|s)", text, re.IGNORECASE)
    if match:
        value = float(match.group(1))
        if match.group(2).lower() == "ms":
            value /= 1000.0
        return max(value, 0.1)
    return min(0.5 * (2 ** (attempt - 1)), 10.0)
