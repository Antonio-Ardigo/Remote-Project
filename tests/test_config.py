"""Tests for configuration management."""

import os
import pytest
from arabic_pdf_translator.config import (
    TranslationConfig,
    TranslationMethod,
    OCRConfig,
    OCREngine,
    QualityThreshold,
)


class TestTranslationConfig:
    def test_default_config(self):
        config = TranslationConfig()
        assert config.source_lang == "ar"
        assert config.target_lang == "en"
        assert config.enable_ensemble is True

    def test_api_keys_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")
        config = TranslationConfig()
        assert config.anthropic_api_key == "test-key-123"

    def test_explicit_key_overrides_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
        config = TranslationConfig(anthropic_api_key="explicit-key")
        assert config.anthropic_api_key == "explicit-key"

    def test_get_available_methods_none(self):
        config = TranslationConfig(
            anthropic_api_key=None,
            google_api_key=None,
            deepl_api_key=None,
            openai_api_key=None,
        )
        # Clear env vars that might be set
        for var in ["ANTHROPIC_API_KEY", "GOOGLE_TRANSLATE_API_KEY", "DEEPL_API_KEY", "OPENAI_API_KEY"]:
            os.environ.pop(var, None)
        config.__post_init__()  # Re-run env var loading
        assert config.get_available_methods() == []

    def test_get_available_methods_some(self):
        config = TranslationConfig(
            anthropic_api_key="key1",
            deepl_api_key="key2",
        )
        available = config.get_available_methods()
        assert TranslationMethod.CLAUDE in available
        assert TranslationMethod.DEEPL in available
        assert TranslationMethod.GOOGLE not in available

    def test_quality_threshold_values(self):
        assert QualityThreshold.STRICT.value == 0.85
        assert QualityThreshold.ALWAYS.value == 1.0


class TestOCRConfig:
    def test_default_engines(self):
        config = OCRConfig()
        assert OCREngine.TESSERACT in config.engines
        assert OCREngine.EASYOCR in config.engines

    def test_default_dpi(self):
        config = OCRConfig()
        assert config.dpi == 300

    def test_tesseract_arabic_lang(self):
        config = OCRConfig()
        assert config.tesseract_lang == "ara"
