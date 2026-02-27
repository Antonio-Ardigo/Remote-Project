"""
Method 4: OpenAI GPT translator.

Uses GPT-4o for contextual Arabic translation. Strengths:
- Good at handling colloquial/dialectal Arabic
- Strong contextual understanding
- Flexible instruction-following for specialized domains
- Good at maintaining tone and style
"""

import logging
from typing import Optional

from arabic_pdf_translator.translator.base import BaseTranslator, TranslationResult
from arabic_pdf_translator.utils import retry_with_backoff

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a professional Arabic-to-English translator. You specialize in:
- Modern Standard Arabic (MSA / الفصحى)
- Classical Arabic texts
- Technical, legal, and literary Arabic
- Common dialectal expressions

Rules:
1. Output ONLY the English translation — no notes, no transliterations, no explanations
2. Preserve the original meaning, tone, and register
3. Translate idiomatic expressions to natural English equivalents
4. Keep proper nouns in standard English transliteration
5. Maintain paragraph structure and formatting
6. For Quranic or Hadith text, use established English translations when possible"""


class OpenAITranslator(BaseTranslator):
    """Translation using OpenAI's GPT API."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key)
        except ImportError:
            raise ImportError(
                "openai package required. Install with: pip install openai"
            )
        self.model = model

    @property
    def method_name(self) -> str:
        return "openai"

    @retry_with_backoff(max_retries=3, base_delay=2.0, exceptions=(Exception,))
    def translate(
        self,
        text: str,
        source_lang: str = "ar",
        target_lang: str = "en",
        context: Optional[str] = None,
    ) -> TranslationResult:
        """Translate Arabic text using OpenAI GPT."""
        logger.info("OpenAI translation: sending %d chars", len(text))

        user_message = f"Translate the following Arabic text to English:\n\n{text}"
        if context:
            user_message = (
                f"Context (for reference only, do NOT translate):\n{context}\n\n---\n\n"
                f"Translate the following Arabic text to English:\n\n{text}"
            )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,  # Lower temperature for more consistent translation
            max_tokens=4096,
        )

        translated = response.choices[0].message.content.strip()

        # Estimate confidence
        confidence = 0.87
        finish_reason = response.choices[0].finish_reason
        if finish_reason == "stop":
            confidence = 0.89
        if len(translated) < len(text) * 0.2:
            confidence *= 0.7  # Suspiciously short

        logger.info(
            "OpenAI translation: received %d chars, confidence %.2f",
            len(translated),
            confidence,
        )

        return TranslationResult(
            method=self.method_name,
            source_text=text,
            translated_text=translated,
            confidence=confidence,
            metadata={
                "model": self.model,
                "finish_reason": finish_reason,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
            },
        )
