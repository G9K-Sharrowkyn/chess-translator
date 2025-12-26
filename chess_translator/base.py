# -*- coding: utf-8 -*-
"""Base abstract class for chess translators."""

from abc import ABC, abstractmethod
from typing import List


class Translator(ABC):
    """Abstract base class defining the translator interface."""

    @abstractmethod
    def translate_chunks(self, texts: List[str], source_lang: str = "EN", target_lang: str = "PL") -> List[str]:
        """Translate a list of texts, preserving order. Empty texts returned unchanged."""
        raise NotImplementedError
