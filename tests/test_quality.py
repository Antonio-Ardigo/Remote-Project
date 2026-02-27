"""Tests for translation quality evaluator."""

import pytest
from arabic_pdf_translator.quality.evaluator import QualityEvaluator, QualityScore
from arabic_pdf_translator.translator.base import TranslationResult


class TestQualityEvaluator:
    def setup_method(self):
        self.evaluator = QualityEvaluator()

    def test_single_translation(self):
        results = [
            TranslationResult(
                method="claude",
                source_text="مرحبا",
                translated_text="Hello",
                confidence=0.9,
            )
        ]
        score = self.evaluator.evaluate_translations("مرحبا", results)
        assert score.best_method == "claude"
        assert score.scores["claude"] == 0.9

    def test_multiple_translations_ranking(self):
        source = "بسم الله الرحمن الرحيم"
        results = [
            TranslationResult(
                method="claude",
                source_text=source,
                translated_text="In the name of God, the Most Gracious, the Most Merciful",
                confidence=0.92,
            ),
            TranslationResult(
                method="google",
                source_text=source,
                translated_text="In the name of God the Merciful",
                confidence=0.80,
            ),
            TranslationResult(
                method="deepl",
                source_text=source,
                translated_text="In the name of God, the Most Gracious, the Most Merciful",
                confidence=0.87,
            ),
        ]
        score = self.evaluator.evaluate_translations(source, results)

        # Should have scores for all methods
        assert "claude" in score.scores
        assert "google" in score.scores
        assert "deepl" in score.scores

        # Rankings should be ordered
        ranking = score.get_ranking()
        assert len(ranking) == 3
        assert ranking[0][1] >= ranking[1][1] >= ranking[2][1]

    def test_empty_translation_penalized(self):
        source = "مرحبا بالعالم"
        results = [
            TranslationResult(
                method="good",
                source_text=source,
                translated_text="Hello world",
                confidence=0.85,
            ),
            TranslationResult(
                method="bad",
                source_text=source,
                translated_text="",
                confidence=0.0,
                error="Failed",
            ),
        ]
        score = self.evaluator.evaluate_translations(source, results)
        # Successful method should be best
        assert score.best_method == "good"

    def test_no_translations(self):
        score = self.evaluator.evaluate_translations("مرحبا", [])
        assert score.best_method == ""

    def test_cross_agreement_boosts_consensus(self):
        source = "الكتاب" * 20  # Longer source
        # Two methods agree, one disagrees
        results = [
            TranslationResult(
                method="method_a",
                source_text=source,
                translated_text="The book is on the table in the room",
                confidence=0.85,
            ),
            TranslationResult(
                method="method_b",
                source_text=source,
                translated_text="The book is on the table in the room",
                confidence=0.83,
            ),
            TranslationResult(
                method="method_c",
                source_text=source,
                translated_text="A completely different unrelated translation output",
                confidence=0.84,
            ),
        ]
        score = self.evaluator.evaluate_translations(source, results)
        # Methods a and b should score higher due to cross-agreement
        assert score.scores["method_a"] > score.scores["method_c"] or \
               score.scores["method_b"] > score.scores["method_c"]


class TestQualityScore:
    def test_get_ranking(self):
        score = QualityScore(
            scores={"a": 0.8, "b": 0.9, "c": 0.7},
            dimension_scores={},
            best_method="b",
        )
        ranking = score.get_ranking()
        assert ranking[0] == ("b", 0.9)
        assert ranking[-1] == ("c", 0.7)
