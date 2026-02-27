"""
Method 2: Google Cloud Translation translator.

Uses Google's Neural Machine Translation (NMT) system, which excels at:
- High throughput and speed
- Broad vocabulary coverage
- Consistent quality across document types
- Good handling of technical/scientific Arabic
"""

import logging
from typing import Optional

from arabic_pdf_translator.translator.base import BaseTranslator, TranslationResult
from arabic_pdf_translator.utils import retry_with_backoff

logger = logging.getLogger(__name__)


class GoogleTranslator(BaseTranslator):
    """Translation using Google Cloud Translation API v2."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        """Initialize Google Translate client. Supports both official and fallback."""
        # Try official Google Cloud Translation API first
        try:
            from google.cloud import translate_v2 as translate
            self._client = translate.Client()
            self._backend = "google_cloud"
            logger.info("Using Google Cloud Translation API")
            return
        except ImportError:
            pass

        # Fallback: use googletrans (free, unofficial)
        try:
            import httpx
            self._backend = "httpx_direct"
            logger.info("Using direct Google Translate API via httpx")
            return
        except ImportError:
            pass

        # Last resort: requests-based
        try:
            import requests
            self._backend = "requests_direct"
            logger.info("Using direct Google Translate API via requests")
            return
        except ImportError:
            raise ImportError(
                "Install google-cloud-translate or httpx or requests for Google Translation. "
                "pip install google-cloud-translate  OR  pip install httpx"
            )

    @property
    def method_name(self) -> str:
        return "google"

    @retry_with_backoff(max_retries=3, base_delay=1.0, exceptions=(Exception,))
    def translate(
        self,
        text: str,
        source_lang: str = "ar",
        target_lang: str = "en",
        context: Optional[str] = None,
    ) -> TranslationResult:
        """Translate using Google Translate."""
        logger.info("Google translation: sending %d chars", len(text))

        if self._backend == "google_cloud":
            return self._translate_cloud(text, source_lang, target_lang)
        else:
            return self._translate_direct(text, source_lang, target_lang)

    def _translate_cloud(
        self, text: str, source_lang: str, target_lang: str
    ) -> TranslationResult:
        """Use official Google Cloud Translation API."""
        result = self._client.translate(
            text,
            source_language=source_lang,
            target_language=target_lang,
        )

        translated = result["translatedText"]
        # Google doesn't provide confidence; estimate from detection
        confidence = 0.82
        if result.get("detectedSourceLanguage") == source_lang:
            confidence = 0.85

        logger.info("Google Cloud: received %d chars", len(translated))

        return TranslationResult(
            method=self.method_name,
            source_text=text,
            translated_text=translated,
            confidence=confidence,
            metadata={"backend": "google_cloud", "detected_lang": result.get("detectedSourceLanguage")},
        )

    def _translate_direct(
        self, text: str, source_lang: str, target_lang: str
    ) -> TranslationResult:
        """Use Google Translate API directly via HTTP."""
        import json
        url = "https://translation.googleapis.com/language/translate/v2"
        params = {
            "q": text,
            "source": source_lang,
            "target": target_lang,
            "key": self.api_key,
            "format": "text",
        }

        if self._backend == "httpx_direct":
            import httpx
            response = httpx.post(url, data=params, timeout=30.0)
            response.raise_for_status()
            data = response.json()
        else:
            import requests
            response = requests.post(url, data=params, timeout=30)
            response.raise_for_status()
            data = response.json()

        translations = data.get("data", {}).get("translations", [])
        if not translations:
            return TranslationResult(
                method=self.method_name,
                source_text=text,
                translated_text="",
                confidence=0.0,
                error="No translations returned from Google API",
            )

        translated = translations[0].get("translatedText", "")
        confidence = 0.82

        logger.info("Google Direct: received %d chars", len(translated))

        return TranslationResult(
            method=self.method_name,
            source_text=text,
            translated_text=translated,
            confidence=confidence,
            metadata={"backend": self._backend},
        )
