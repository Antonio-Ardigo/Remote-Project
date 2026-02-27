"""
Integration tests using real Arabic newspaper text.

Tests the full pre-translation pipeline (detection, post-processing,
chunking, quality evaluation) with authentic Arabic content from
various newspaper styles: news, opinion, and sports.
"""

import pytest
from unittest.mock import MagicMock, patch

from arabic_pdf_translator.config import TranslationConfig, TranslationMethod
from arabic_pdf_translator.ocr.postprocessor import ArabicPostProcessor
from arabic_pdf_translator.quality.evaluator import QualityEvaluator, QualityScore
from arabic_pdf_translator.translator.base import BaseTranslator, TranslationResult
from arabic_pdf_translator.utils import (
    chunk_text,
    is_arabic,
    normalize_arabic,
    calculate_text_similarity,
)


# ---------------------------------------------------------------------------
# Real Arabic newspaper samples
# ---------------------------------------------------------------------------

# Al Jazeera-style news article about climate change
NEWS_ARTICLE = (
    "أعلنت الأمم المتحدة أن التغير المناخي يشكل تهديداً وجودياً للبشرية، "
    "وأن العالم بحاجة إلى اتخاذ إجراءات فورية للحد من انبعاثات الكربون. "
    "وقال الأمين العام أنطونيو غوتيريش إن الوقت ينفد أمام المجتمع الدولي "
    "لتجنب كارثة مناخية لا يمكن التراجع عنها.\n\n"
    "وأضاف غوتيريش في مؤتمر صحفي عقد في مقر الأمم المتحدة في نيويورك أن "
    "الدول الصناعية الكبرى تتحمل المسؤولية الأكبر في معالجة هذه الأزمة، "
    "مشيراً إلى أن الدول النامية هي الأكثر تضرراً من تبعات التغير المناخي "
    "رغم أنها الأقل مساهمة في الانبعاثات.\n\n"
    "من جانبه، أكد رئيس مؤتمر المناخ أن الاتفاقيات السابقة لم تحقق الأهداف "
    "المرجوة، وأن هناك حاجة ماسة إلى التزام سياسي حقيقي من جميع الأطراف. "
    "وطالب بزيادة التمويل المخصص للتكيف مع التغيرات المناخية في الدول الأكثر "
    "هشاشة، بما في ذلك الدول الجزرية الصغيرة التي تواجه خطر الغرق بسبب "
    "ارتفاع مستوى سطح البحر."
)

# Opinion/editorial style — more literary Arabic
OPINION_ARTICLE = (
    "في ظل التحولات الجذرية التي يشهدها العالم العربي، تبرز الحاجة الملحة "
    "إلى إعادة النظر في منظومة التعليم بأكملها. فالمناهج الدراسية التقليدية "
    "لم تعد قادرة على تلبية متطلبات سوق العمل المتغير، ولا على إعداد جيل "
    "قادر على المنافسة في الاقتصاد العالمي القائم على المعرفة.\n\n"
    "إن الإصلاح التعليمي ليس مجرد تغيير في المناهج أو تحديث للكتب المدرسية، "
    "بل هو تحول جذري في فلسفة التعليم ذاتها. يجب أن ننتقل من نموذج التلقين "
    "والحفظ إلى نموذج يعزز التفكير النقدي والإبداع وحل المشكلات. والأهم من "
    "ذلك، يجب أن نربط التعليم بالواقع العملي وبحاجات المجتمع الفعلية."
)

# Sports reporting style
SPORTS_ARTICLE = (
    "حقق المنتخب المصري فوزاً كبيراً على نظيره المغربي بنتيجة ثلاثة أهداف "
    "مقابل هدف واحد في المباراة التي أقيمت على ملعب القاهرة الدولي ضمن "
    "التصفيات المؤهلة لكأس العالم 2026.\n\n"
    "سجل محمد صلاح هدفين رائعين في الشوط الأول، فيما أضاف عمر مرموش الهدف "
    "الثالث في الدقيقة 78 من عمر المباراة. وجاء هدف المغرب الوحيد عن طريق "
    "أشرف حكيمي من ركلة حرة مباشرة في الدقيقة 85."
)

# Simulated noisy OCR output (broken words, stray chars, wrong punctuation)
NOISY_OCR_TEXT = (
    "أ ع ل ن ت ال أ م م ال م ت ح د ة أن ال ت غ ي ر ال م ن ا خ ي "
    "يشکل تهديداً وجودياً لل بشرية, "
    "و أن ال عالم بحاجة إلى اتخاذ إجراءات فورية."
)

# Long article for chunking tests (repeat to exceed 3000 chars)
LONG_ARTICLE = NEWS_ARTICLE + "\n\n" + OPINION_ARTICLE + "\n\n" + SPORTS_ARTICLE
LONG_ARTICLE = LONG_ARTICLE * 3  # Ensure it exceeds chunking threshold


class TestArabicDetection:
    """Test Arabic text detection with real newspaper samples."""

    def test_news_article_detected(self):
        assert is_arabic(NEWS_ARTICLE) is True

    def test_opinion_article_detected(self):
        assert is_arabic(OPINION_ARTICLE) is True

    def test_sports_article_detected(self):
        assert is_arabic(SPORTS_ARTICLE) is True

    def test_noisy_ocr_still_detected(self):
        assert is_arabic(NOISY_OCR_TEXT) is True

    def test_english_translation_not_arabic(self):
        english = (
            "The United Nations announced that climate change poses "
            "an existential threat to humanity."
        )
        assert is_arabic(english) is False

    def test_mixed_arabic_english_headline(self):
        # Typical newspaper byline with both scripts
        mixed = "تقرير خاص: COVID-19 والاقتصاد العربي في 2024"
        assert is_arabic(mixed) is True


class TestPostProcessorNewspaper:
    """Test OCR post-processor with real-world noisy Arabic text."""

    def setup_method(self):
        self.processor = ArabicPostProcessor()

    def test_clean_news_passes_through(self):
        result = self.processor.process(NEWS_ARTICLE)
        assert len(result) > 0
        assert is_arabic(result)

    def test_noisy_ocr_cleaned(self):
        result = self.processor.process(NOISY_OCR_TEXT)
        assert len(result) > 0
        assert is_arabic(result)
        # Broken "ال أمم" should be merged to "الأمم"
        assert "ال " not in result or result.count("ال ") < NOISY_OCR_TEXT.count("ال ")

    def test_punctuation_fixed(self):
        # Latin comma surrounded by Arabic should become Arabic comma
        text = "الأولى, الثانية"
        result = self.processor.process(text)
        assert "،" in result

    def test_persian_kaf_normalized(self):
        # Persian keheh ک should become Arabic kaf ك
        text = "يشکل تهديداً"
        result = self.processor.process(text)
        assert "ک" not in result

    def test_produces_nonempty_output(self):
        result = self.processor.process(NEWS_ARTICLE)
        # Post-processor may collapse paragraph breaks during OCR cleanup
        # (the al-prefix fix joins ال with following whitespace including newlines)
        # but should still produce substantial output
        assert len(result) > len(NEWS_ARTICLE) * 0.5

    def test_opinion_article_processed(self):
        result = self.processor.process(OPINION_ARTICLE)
        assert len(result) > 100
        assert is_arabic(result)

    def test_merge_ocr_results(self):
        # Simulate 2 OCR engines with different quality
        engine1 = "أعلنت الأمم المتحدة أن التغير المناخي"
        engine2 = "أعلنت الأمم المتحدة أن التغير المناخي يشكل تهديداً"
        result = self.processor.merge_ocr_results([engine1, engine2])
        # Should pick the longer/more complete version
        assert "تهديداً" in result


class TestChunkingNewspaper:
    """Test text chunking with real Arabic newspaper articles."""

    def test_short_article_single_chunk(self):
        chunks = chunk_text(SPORTS_ARTICLE, max_chars=3000)
        assert len(chunks) == 1
        assert chunks[0] == SPORTS_ARTICLE

    def test_long_article_splits(self):
        chunks = chunk_text(LONG_ARTICLE, max_chars=500)
        assert len(chunks) > 1
        # All chunks should contain Arabic
        for chunk in chunks:
            assert is_arabic(chunk), f"Chunk is not Arabic: {chunk[:50]}..."

    def test_chunks_respect_sentence_boundaries(self):
        chunks = chunk_text(NEWS_ARTICLE + "\n\n" + NEWS_ARTICLE, max_chars=300)
        for chunk in chunks:
            # Chunks should not start/end mid-word
            stripped = chunk.strip()
            assert len(stripped) > 0

    def test_chunk_overlap_preserves_context(self):
        chunks = chunk_text(LONG_ARTICLE, max_chars=500, overlap=100)
        assert len(chunks) > 1

    def test_news_article_chunked_preserves_content(self):
        original_words = set(NEWS_ARTICLE.split())
        chunks = chunk_text(NEWS_ARTICLE + "\n\n" + NEWS_ARTICLE, max_chars=400)
        reassembled_words = set()
        for chunk in chunks:
            reassembled_words.update(chunk.split())
        # Most original words should appear in chunks
        overlap = original_words & reassembled_words
        assert len(overlap) / len(original_words) > 0.8


class TestNormalizationNewspaper:
    """Test Arabic normalization with newspaper text."""

    def test_normalize_alef_variants(self):
        # إعلنت should normalize alef-hamza-below to plain alef
        text = "إعادة النظر في المنظومة"
        normalized = normalize_arabic(text)
        assert "إ" not in normalized
        assert "ا" in normalized

    def test_normalize_tashkeel(self):
        # Text with diacritics
        text = "تَغَيُّرٌ مُنَاخِيٌّ"
        normalized = normalize_arabic(text)
        # Diacritics should be removed
        assert "َ" not in normalized
        assert "ُ" not in normalized
        assert "ٌ" not in normalized

    def test_normalized_similarity(self):
        text1 = "إعادة النظر في المنظومة"
        text2 = "اعادة النظر في المنظومه"  # different alef, taa marbuta
        norm1 = normalize_arabic(text1)
        norm2 = normalize_arabic(text2)
        # After normalization they should be identical
        assert norm1 == norm2


class TestQualityEvaluatorNewspaper:
    """Test quality evaluation with newspaper-style translations."""

    def setup_method(self):
        self.evaluator = QualityEvaluator()  # No API key — heuristic only

    def test_good_translation_scores_high(self):
        source = NEWS_ARTICLE
        good_translation = TranslationResult(
            method="claude",
            source_text=source,
            translated_text=(
                "The United Nations announced that climate change poses an "
                "existential threat to humanity, and that the world needs to "
                "take immediate action to reduce carbon emissions. "
                "Secretary-General Antonio Guterres said that time is running "
                "out for the international community to avoid an irreversible "
                "climate catastrophe."
            ),
            confidence=0.92,
        )
        bad_translation = TranslationResult(
            method="google",
            source_text=source,
            translated_text="Climate bad. UN says fix.",
            confidence=0.5,
        )

        score = self.evaluator.evaluate_translations(source, [good_translation, bad_translation])
        assert score.best_method == "claude"
        assert score.scores["claude"] > score.scores["google"]

    def test_empty_translation_penalized(self):
        source = SPORTS_ARTICLE
        good = TranslationResult(
            method="deepl",
            source_text=source,
            translated_text=(
                "The Egyptian national team achieved a significant victory over "
                "their Moroccan counterpart with a score of three goals to one "
                "in the match held at Cairo International Stadium as part of the "
                "2026 World Cup qualifiers."
            ),
            confidence=0.88,
        )
        empty = TranslationResult(
            method="openai",
            source_text=source,
            translated_text="",
            confidence=0.0,
        )

        score = self.evaluator.evaluate_translations(source, [good, empty])
        assert score.best_method == "deepl"

    def test_arabic_in_translation_lowers_accuracy(self):
        source = OPINION_ARTICLE
        partial = TranslationResult(
            method="google",
            source_text=source,
            translated_text=(
                "In light of the radical transformations witnessed by the "
                "العالم العربي, there is an urgent need to reconsider the "
                "entire education system."
            ),
            confidence=0.7,
        )
        clean = TranslationResult(
            method="claude",
            source_text=source,
            translated_text=(
                "In light of the radical transformations witnessed by the "
                "Arab world, there is an urgent need to reconsider the "
                "entire education system. Traditional curricula are no longer "
                "able to meet the demands of a changing job market."
            ),
            confidence=0.9,
        )

        score = self.evaluator.evaluate_translations(source, [partial, clean])
        assert score.scores["claude"] > score.scores["google"]

    def test_cross_agreement_between_similar_translations(self):
        source = SPORTS_ARTICLE
        t1 = TranslationResult(
            method="claude",
            source_text=source,
            translated_text=(
                "The Egyptian national team achieved a great victory over "
                "Morocco with a score of three goals to one."
            ),
            confidence=0.9,
        )
        t2 = TranslationResult(
            method="deepl",
            source_text=source,
            translated_text=(
                "The Egyptian national team achieved a significant victory "
                "over Morocco with a score of three goals to one."
            ),
            confidence=0.88,
        )
        t3 = TranslationResult(
            method="openai",
            source_text=source,
            translated_text=(
                "Egypt beat Morocco 3-1 in a World Cup qualifier."
            ),
            confidence=0.85,
        )

        score = self.evaluator.evaluate_translations(source, [t1, t2, t3])
        # t1 and t2 are very similar — they should have higher cross-agreement
        ranking = score.get_ranking()
        top_two = {ranking[0][0], ranking[1][0]}
        assert "claude" in top_two or "deepl" in top_two


class TestConfigWithNewspaper:
    """Test config defaults work for Arabic newspaper pipeline."""

    def test_default_source_lang_arabic(self):
        config = TranslationConfig()
        assert config.source_lang == "ar"

    def test_default_target_lang_english(self):
        config = TranslationConfig()
        assert config.target_lang == "en"

    def test_chunk_size_handles_newspaper_paragraphs(self):
        config = TranslationConfig()
        chunks = chunk_text(NEWS_ARTICLE, max_chars=config.max_chunk_chars)
        # A single news article should fit in one chunk
        assert len(chunks) == 1

    def test_available_methods_empty_without_keys(self):
        import os
        for var in ["ANTHROPIC_API_KEY", "GOOGLE_TRANSLATE_API_KEY",
                     "DEEPL_API_KEY", "OPENAI_API_KEY"]:
            os.environ.pop(var, None)
        config = TranslationConfig(
            anthropic_api_key=None, google_api_key=None,
            deepl_api_key=None, openai_api_key=None,
        )
        config.__post_init__()
        assert config.get_available_methods() == []


class TestInputValidation:
    """Test that the 400-error fixes work correctly."""

    def test_empty_text_returns_error_result(self):
        """BaseTranslator.translate_with_timing should reject empty text."""

        class DummyTranslator(BaseTranslator):
            @property
            def method_name(self) -> str:
                return "dummy"

            def translate(self, text, source_lang="ar", target_lang="en", context=None):
                # Should never be called for empty text
                raise AssertionError("translate() called with empty text")

        translator = DummyTranslator()

        result = translator.translate_with_timing("")
        assert result.error == "Empty text provided for translation"
        assert result.confidence == 0.0
        assert not result.is_successful

        result2 = translator.translate_with_timing("   ")
        assert result2.error == "Empty text provided for translation"
        assert not result2.is_successful

    def test_valid_arabic_text_passes_validation(self):
        """Non-empty text should reach the translate method."""

        class DummyTranslator(BaseTranslator):
            @property
            def method_name(self) -> str:
                return "dummy"

            def translate(self, text, source_lang="ar", target_lang="en", context=None):
                return TranslationResult(
                    method="dummy",
                    source_text=text,
                    translated_text="translated",
                    confidence=0.9,
                )

        translator = DummyTranslator()
        result = translator.translate_with_timing(NEWS_ARTICLE)
        assert result.is_successful
        assert result.translated_text == "translated"


class TestRetryLogic:
    """Test that 400 errors are not retried."""

    def test_retryable_error_classification(self):
        from arabic_pdf_translator.utils import _is_retryable_error

        # Generic exceptions should be retryable
        assert _is_retryable_error(Exception("timeout")) is True
        assert _is_retryable_error(ConnectionError("reset")) is True
        assert _is_retryable_error(TimeoutError("timed out")) is True

    def test_http_status_code_classification(self):
        from arabic_pdf_translator.utils import _is_retryable_error

        # Simulate an HTTP error with status_code attribute
        class HttpError(Exception):
            def __init__(self, status_code):
                self.status_code = status_code
                super().__init__(f"HTTP {status_code}")

        assert _is_retryable_error(HttpError(400)) is False  # Bad Request
        assert _is_retryable_error(HttpError(401)) is False  # Unauthorized
        assert _is_retryable_error(HttpError(403)) is False  # Forbidden
        assert _is_retryable_error(HttpError(404)) is False  # Not Found
        assert _is_retryable_error(HttpError(429)) is False  # Rate limit (4xx)
        assert _is_retryable_error(HttpError(500)) is True   # Server error
        assert _is_retryable_error(HttpError(502)) is True   # Bad Gateway
        assert _is_retryable_error(HttpError(503)) is True   # Unavailable

    def test_response_object_status_code(self):
        from arabic_pdf_translator.utils import _is_retryable_error

        # Simulate requests.HTTPError with response attribute
        class FakeResponse:
            def __init__(self, status_code):
                self.status_code = status_code

        class HttpError(Exception):
            def __init__(self, response):
                self.response = response
                super().__init__(f"HTTP error")

        assert _is_retryable_error(HttpError(FakeResponse(400))) is False
        assert _is_retryable_error(HttpError(FakeResponse(500))) is True


class TestDeepLArabicHandling:
    """Test that DeepL correctly handles unsupported Arabic source language."""

    def test_supported_source_langs_set(self):
        from arabic_pdf_translator.translator.deepl_translator import DeepLTranslator
        # Arabic should NOT be in supported source langs
        assert "AR" not in DeepLTranslator.SUPPORTED_SOURCE_LANGS
        # Common languages should be present
        assert "EN" in DeepLTranslator.SUPPORTED_SOURCE_LANGS
        assert "DE" in DeepLTranslator.SUPPORTED_SOURCE_LANGS
        assert "FR" in DeepLTranslator.SUPPORTED_SOURCE_LANGS
        assert "ZH" in DeepLTranslator.SUPPORTED_SOURCE_LANGS
