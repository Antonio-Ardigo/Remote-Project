"""
Method 1: Claude (Anthropic) translator.

Uses Claude's deep understanding of Arabic language, culture, and context
for high-quality, nuanced translation. Particularly strong at:
- Idiomatic expressions and proverbs (أمثال)
- Formal/religious Arabic (Modern Standard Arabic, Classical Arabic)
- Context-dependent word sense disambiguation
- Maintaining register (formal/informal) in translation
"""

import logging
from typing import Optional

from arabic_pdf_translator.translator.base import BaseTranslator, TranslationResult
from arabic_pdf_translator.utils import retry_with_backoff

logger = logging.getLogger(__name__)

ARABIC_TRANSLATION_PROMPT = """You are an expert Arabic-to-English translator with deep knowledge of:
- Modern Standard Arabic (الفصحى)
- Classical Arabic (العربية الكلاسيكية)
- Common Arabic dialects
- Islamic and cultural terminology
- Legal and technical Arabic vocabulary

TRANSLATION GUIDELINES:
1. Translate accurately while preserving the original meaning and tone
2. For idiomatic expressions (أمثال), provide both literal and natural English equivalents
3. Preserve proper nouns in their most common English transliteration
4. Maintain paragraph structure and formatting
5. For ambiguous words, use context to determine the best translation
6. Preserve numbers, dates, and references exactly
7. If text contains Quranic verses or Hadith, use established English translations where possible
8. Maintain the formal/informal register of the source text

IMPORTANT:
- Do NOT add explanations or notes — output ONLY the English translation
- Do NOT transliterate Arabic — translate to natural English
- If a word/phrase cannot be translated, provide the closest English equivalent

Translate the following Arabic text to English:

{text}"""

ARABIC_TRANSLATION_WITH_CONTEXT_PROMPT = """You are an expert Arabic-to-English translator.

CONTEXT (preceding text for reference, do NOT translate this):
{context}

---

TRANSLATION GUIDELINES:
1. Translate accurately, using the context above to resolve ambiguities
2. Preserve meaning, tone, and register
3. Output ONLY the English translation — no notes or explanations
4. Maintain paragraph structure

Translate the following Arabic text to English:

{text}"""


class ClaudeTranslator(BaseTranslator):
    """Translation using Anthropic's Claude API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            raise ImportError(
                "anthropic package required. Install with: pip install anthropic"
            )
        self.model = model

    @property
    def method_name(self) -> str:
        return "claude"

    @retry_with_backoff(max_retries=3, base_delay=2.0, exceptions=(Exception,))
    def translate(
        self,
        text: str,
        source_lang: str = "ar",
        target_lang: str = "en",
        context: Optional[str] = None,
    ) -> TranslationResult:
        """Translate Arabic text using Claude."""
        if context:
            prompt = ARABIC_TRANSLATION_WITH_CONTEXT_PROMPT.format(
                text=text, context=context
            )
        else:
            prompt = ARABIC_TRANSLATION_PROMPT.format(text=text)

        logger.info("Claude translation: sending %d chars", len(text))

        message = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        translated = message.content[0].text.strip()

        # Estimate confidence based on stop reason and output quality
        confidence = 0.90  # Claude is generally high quality
        if message.stop_reason == "end_turn":
            confidence = 0.92
        if len(translated) < len(text) * 0.2:
            confidence *= 0.7  # Suspiciously short translation

        logger.info(
            "Claude translation: received %d chars, confidence %.2f",
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
                "stop_reason": message.stop_reason,
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
            },
        )
