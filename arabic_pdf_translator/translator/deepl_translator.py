"""
Method 3: DeepL translator.

DeepL's neural MT is known for:
- Exceptional fluency in target language (English)
- Natural-sounding translations
- Strong handling of complex sentence structures
- Good preservation of formatting
"""

import logging
from typing import Optional

from arabic_pdf_translator.translator.base import BaseTranslator, TranslationResult
from arabic_pdf_translator.utils import retry_with_backoff

logger = logging.getLogger(__name__)

# DeepL language code mapping
DEEPL_LANG_MAP = {
    "ar": "AR",
    "en": "EN-US",
    "en-gb": "EN-GB",
    "en-us": "EN-US",
    "fr": "FR",
    "de": "DE",
    "es": "ES",
    "it": "IT",
    "pt": "PT-BR",
}


class DeepLTranslator(BaseTranslator):
    """Translation using DeepL API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        """Initialize DeepL client."""
        # Try official deepl library
        try:
            import deepl
            self._client = deepl.Translator(self.api_key)
            self._backend = "deepl_official"
            logger.info("Using official DeepL Python library")
            return
        except ImportError:
            pass

        # Fallback to direct HTTP
        self._backend = "http_direct"
        logger.info("Using DeepL REST API directly")

    @property
    def method_name(self) -> str:
        return "deepl"

    @retry_with_backoff(max_retries=3, base_delay=1.5, exceptions=(Exception,))
    def translate(
        self,
        text: str,
        source_lang: str = "ar",
        target_lang: str = "en",
        context: Optional[str] = None,
    ) -> TranslationResult:
        """Translate using DeepL."""
        logger.info("DeepL translation: sending %d chars", len(text))

        deepl_source = DEEPL_LANG_MAP.get(source_lang, source_lang.upper())
        deepl_target = DEEPL_LANG_MAP.get(target_lang, "EN-US")

        if self._backend == "deepl_official":
            return self._translate_official(text, deepl_source, deepl_target, context)
        else:
            return self._translate_http(text, deepl_source, deepl_target, context)

    def _translate_official(
        self, text: str, source_lang: str, target_lang: str, context: Optional[str]
    ) -> TranslationResult:
        """Use official DeepL Python library."""
        kwargs = {
            "text": text,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "preserve_formatting": True,
        }
        if context:
            kwargs["context"] = context

        result = self._client.translate_text(**kwargs)

        translated = result.text
        # DeepL reports detected language — use for confidence
        confidence = 0.85
        if result.detected_source_lang.upper() == source_lang.upper():
            confidence = 0.88

        logger.info("DeepL official: received %d chars", len(translated))

        return TranslationResult(
            method=self.method_name,
            source_text=text,
            translated_text=translated,
            confidence=confidence,
            metadata={
                "backend": "deepl_official",
                "detected_lang": result.detected_source_lang,
            },
        )

    def _translate_http(
        self, text: str, source_lang: str, target_lang: str, context: Optional[str]
    ) -> TranslationResult:
        """Use DeepL REST API directly."""
        try:
            import httpx
            use_httpx = True
        except ImportError:
            import requests
            use_httpx = False

        # Determine API endpoint (free vs pro key)
        if self.api_key.endswith(":fx"):
            base_url = "https://api-free.deepl.com/v2/translate"
        else:
            base_url = "https://api.deepl.com/v2/translate"

        data = {
            "text": [text],
            "source_lang": source_lang,
            "target_lang": target_lang,
            "preserve_formatting": "1",
        }
        if context:
            data["context"] = context

        headers = {
            "Authorization": f"DeepL-Auth-Key {self.api_key}",
            "Content-Type": "application/json",
        }

        if use_httpx:
            response = httpx.post(base_url, json=data, headers=headers, timeout=30.0)
            response.raise_for_status()
            result = response.json()
        else:
            response = requests.post(base_url, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()

        translations = result.get("translations", [])
        if not translations:
            return TranslationResult(
                method=self.method_name,
                source_text=text,
                translated_text="",
                confidence=0.0,
                error="No translations returned from DeepL",
            )

        translated = translations[0].get("text", "")
        detected = translations[0].get("detected_source_language", "")
        confidence = 0.85 if detected.upper() == source_lang.upper() else 0.80

        logger.info("DeepL HTTP: received %d chars", len(translated))

        return TranslationResult(
            method=self.method_name,
            source_text=text,
            translated_text=translated,
            confidence=confidence,
            metadata={"backend": "http_direct", "detected_lang": detected},
        )
