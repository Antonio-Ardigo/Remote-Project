"""
Base translator interface and common data structures.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TranslationResult:
    """Result from a single translation method."""
    method: str
    source_text: str
    translated_text: str
    confidence: float  # Self-assessed confidence 0.0–1.0
    latency_seconds: float = 0.0
    metadata: dict = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def is_successful(self) -> bool:
        return self.error is None and bool(self.translated_text.strip())


class BaseTranslator(ABC):
    """Abstract base for all translation backends."""

    @property
    @abstractmethod
    def method_name(self) -> str:
        """Human-readable name of this translation method."""
        ...

    @abstractmethod
    def translate(
        self,
        text: str,
        source_lang: str = "ar",
        target_lang: str = "en",
        context: Optional[str] = None,
    ) -> TranslationResult:
        """
        Translate text from source to target language.

        Args:
            text: Source text to translate.
            source_lang: Source language code.
            target_lang: Target language code.
            context: Optional surrounding context for better translation.

        Returns:
            TranslationResult with the translation and metadata.
        """
        ...

    def translate_with_timing(
        self,
        text: str,
        source_lang: str = "ar",
        target_lang: str = "en",
        context: Optional[str] = None,
    ) -> TranslationResult:
        """Translate and record latency."""
        start = time.time()
        try:
            result = self.translate(text, source_lang, target_lang, context)
        except Exception as e:
            result = TranslationResult(
                method=self.method_name,
                source_text=text,
                translated_text="",
                confidence=0.0,
                error=str(e),
            )
        result.latency_seconds = time.time() - start
        return result
