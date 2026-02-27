"""Tests for utility functions."""

import pytest
from arabic_pdf_translator.utils import (
    chunk_text,
    is_arabic,
    normalize_arabic,
    calculate_text_similarity,
)


class TestIsArabic:
    def test_arabic_text(self):
        assert is_arabic("مرحبا بالعالم") is True

    def test_english_text(self):
        assert is_arabic("Hello World") is False

    def test_mixed_mostly_arabic(self):
        assert is_arabic("مرحبا Hello بالعالم") is True

    def test_mixed_mostly_english(self):
        assert is_arabic("Hello مرحبا World Test Foo Bar") is False

    def test_empty_string(self):
        assert is_arabic("") is False

    def test_numbers_only(self):
        assert is_arabic("12345") is False


class TestNormalizeArabic:
    def test_remove_tashkeel(self):
        # "kitaab" with diacritics → plain
        with_tashkeel = "كِتَابٌ"
        without = normalize_arabic(with_tashkeel)
        assert "ٌ" not in without
        assert "ِ" not in without
        assert "َ" not in without

    def test_normalize_alef(self):
        # All alef variants should become plain alef
        text = "أحمد إبراهيم آل"
        normalized = normalize_arabic(text)
        assert "أ" not in normalized
        assert "إ" not in normalized
        assert "آ" not in normalized

    def test_normalize_taa_marbuta(self):
        text = "مدرسة"
        normalized = normalize_arabic(text)
        assert "ة" not in normalized

    def test_plain_text_unchanged(self):
        text = "كتاب"
        assert normalize_arabic(text) == text


class TestChunkText:
    def test_short_text_single_chunk(self):
        text = "Hello world"
        chunks = chunk_text(text, max_chars=100)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_split(self):
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        chunks = chunk_text(text, max_chars=30, overlap=5)
        assert len(chunks) > 1
        # All content should be represented
        combined = " ".join(chunks)
        assert "First" in combined
        assert "Fourth" in combined

    def test_arabic_text_split(self):
        # Simulate a longer Arabic text
        text = "الجملة الأولى، الجملة الثانية، الجملة الثالثة، الجملة الرابعة."
        chunks = chunk_text(text, max_chars=30, overlap=5)
        assert len(chunks) >= 1

    def test_empty_text(self):
        assert chunk_text("", max_chars=100) == [""]

    def test_exact_max_chars(self):
        text = "a" * 100
        chunks = chunk_text(text, max_chars=100)
        assert len(chunks) == 1


class TestCalculateTextSimilarity:
    def test_identical_texts(self):
        sim = calculate_text_similarity("hello world", "hello world")
        assert sim == 1.0

    def test_completely_different(self):
        sim = calculate_text_similarity("hello world", "foo bar baz")
        assert sim == 0.0

    def test_partial_overlap(self):
        sim = calculate_text_similarity("hello world foo", "hello world bar")
        assert 0.3 < sim < 0.8

    def test_empty_texts(self):
        assert calculate_text_similarity("", "") == 1.0

    def test_one_empty(self):
        assert calculate_text_similarity("hello", "") == 0.0
