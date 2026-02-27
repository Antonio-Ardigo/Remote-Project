"""Tests for Arabic OCR post-processor."""

import pytest
from arabic_pdf_translator.ocr.postprocessor import ArabicPostProcessor


class TestArabicPostProcessor:
    def setup_method(self):
        self.processor = ArabicPostProcessor()

    def test_empty_text(self):
        assert self.processor.process("") == ""
        assert self.processor.process("   ") == ""

    def test_normalize_whitespace(self):
        text = "مرحبا   بالعالم"
        result = self.processor.process(text)
        assert "   " not in result

    def test_fix_al_prefix(self):
        # "al-" prefix separated from word
        text = "ال كتاب"
        result = self.processor.process(text)
        assert "الكتاب" in result

    def test_remove_noise_characters(self):
        text = "مرحبا ~ ` | بالعالم"
        result = self.processor.process(text)
        assert "~" not in result
        assert "`" not in result
        assert "|" not in result

    def test_preserve_arabic_text(self):
        text = "بسم الله الرحمن الرحيم"
        result = self.processor.process(text)
        # Core Arabic words should be preserved
        assert "الله" in result
        assert "الرحمن" in result

    def test_fix_punctuation(self):
        # Latin comma between Arabic should become Arabic comma
        text = "مرحبا,عالم"
        result = self.processor.process(text)
        assert "،" in result or "," not in result.replace("،", "")

    def test_preserve_waw_conjunction(self):
        # و (waw) is a valid single-character word meaning "and"
        text = "أحمد و علي"
        result = self.processor.process(text)
        assert "و" in result

    def test_merge_ocr_results(self):
        results = [
            "السطر الأول\nالسطر الثاني",
            "السطر الأول\nالسطر الثاني الأطول",
        ]
        merged = self.processor.merge_ocr_results(results)
        # Should pick longer version of line 2
        assert "الأطول" in merged

    def test_merge_single_result(self):
        result = self.processor.merge_ocr_results(["مرحبا"])
        assert result == "مرحبا"

    def test_merge_empty(self):
        assert self.processor.merge_ocr_results([]) == ""
