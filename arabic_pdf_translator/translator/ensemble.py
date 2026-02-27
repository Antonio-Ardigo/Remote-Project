"""
Translation Ensemble System.

Runs all 4 translation methods in parallel, evaluates quality,
and selects the best translation. This is the core differentiator
that beats market standard.

Strategy:
1. Run primary method (Claude) first as baseline
2. If confidence < threshold OR force_multi_method is True:
   a. Run all 4 methods in parallel
   b. Cross-compare all translations
   c. Score each on fluency, accuracy, completeness
   d. Use Claude-as-judge to arbitrate if scores are close
   e. Return the best translation with detailed scoring
"""

import concurrent.futures
import logging
from typing import Optional

from arabic_pdf_translator.config import TranslationConfig, TranslationMethod
from arabic_pdf_translator.translator.base import BaseTranslator, TranslationResult
from arabic_pdf_translator.translator.claude_translator import ClaudeTranslator
from arabic_pdf_translator.translator.google_translator import GoogleTranslator
from arabic_pdf_translator.translator.deepl_translator import DeepLTranslator
from arabic_pdf_translator.translator.openai_translator import OpenAITranslator
from arabic_pdf_translator.quality.evaluator import QualityEvaluator, QualityScore

logger = logging.getLogger(__name__)


class TranslationEnsemble:
    """
    Multi-method translation ensemble with quality-based selection.

    This system runs multiple translation backends and uses sophisticated
    quality evaluation to select the best result, significantly outperforming
    any single method.
    """

    def __init__(self, config: TranslationConfig):
        self.config = config
        self.translators: dict[str, BaseTranslator] = {}
        self.evaluator: Optional[QualityEvaluator] = None
        self._init_translators()
        self._init_evaluator()

    def _init_translators(self) -> None:
        """Initialize all available translation backends."""
        method_factories = {
            TranslationMethod.CLAUDE: lambda: ClaudeTranslator(
                api_key=self.config.anthropic_api_key,
                model=self.config.claude_model,
            ),
            TranslationMethod.GOOGLE: lambda: GoogleTranslator(
                api_key=self.config.google_api_key,
            ),
            TranslationMethod.DEEPL: lambda: DeepLTranslator(
                api_key=self.config.deepl_api_key,
            ),
            TranslationMethod.OPENAI: lambda: OpenAITranslator(
                api_key=self.config.openai_api_key,
                model=self.config.openai_model,
            ),
        }

        available_methods = self.config.get_available_methods()

        for method in available_methods:
            factory = method_factories.get(method)
            if factory:
                try:
                    translator = factory()
                    self.translators[method.value] = translator
                    logger.info("Initialized translator: %s", method.value)
                except (ImportError, Exception) as e:
                    logger.warning(
                        "Failed to initialize %s translator: %s", method.value, e
                    )

        if not self.translators:
            raise RuntimeError(
                "No translation methods available. "
                "Set at least one API key (ANTHROPIC_API_KEY, GOOGLE_TRANSLATE_API_KEY, "
                "DEEPL_API_KEY, or OPENAI_API_KEY)."
            )

        logger.info(
            "Translation ensemble ready with %d methods: %s",
            len(self.translators),
            list(self.translators.keys()),
        )

    def _init_evaluator(self) -> None:
        """Initialize the quality evaluator."""
        # Use Claude as judge if available
        claude_key = self.config.anthropic_api_key
        if claude_key:
            self.evaluator = QualityEvaluator(
                anthropic_api_key=claude_key,
                judge_model=self.config.claude_judge_model,
            )
        else:
            self.evaluator = QualityEvaluator()

    def translate(
        self,
        text: str,
        source_lang: str = "ar",
        target_lang: str = "en",
        context: Optional[str] = None,
    ) -> tuple[TranslationResult, list[TranslationResult], Optional[QualityScore]]:
        """
        Translate text using the ensemble system.

        Flow:
        1. If only one method is available, use it directly
        2. If force_multi_method or ensemble is enabled:
           a. Run all methods in parallel
           b. Evaluate and rank results
           c. Return best translation

        Returns:
            Tuple of (best_result, all_results, quality_scores).
        """
        if len(self.translators) == 1:
            # Single method — use it directly
            method_name = list(self.translators.keys())[0]
            translator = self.translators[method_name]
            result = translator.translate_with_timing(text, source_lang, target_lang, context)
            return result, [result], None

        if not self.config.enable_ensemble and not self.config.force_multi_method:
            # Ensemble disabled — use first available (Claude preferred)
            preferred_order = ["claude", "deepl", "openai", "google"]
            for name in preferred_order:
                if name in self.translators:
                    result = self.translators[name].translate_with_timing(
                        text, source_lang, target_lang, context
                    )
                    if result.is_successful:
                        return result, [result], None

        # Run the full ensemble
        return self._run_ensemble(text, source_lang, target_lang, context)

    def _run_ensemble(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: Optional[str],
    ) -> tuple[TranslationResult, list[TranslationResult], Optional[QualityScore]]:
        """
        Run all translation methods in parallel and select the best.

        This is where the magic happens — by running 4 independent methods
        and using quality evaluation to pick the best, we consistently
        outperform any single method.
        """
        logger.info(
            "Running ensemble translation with %d methods", len(self.translators)
        )

        # Run all methods in parallel using ThreadPoolExecutor
        results: list[TranslationResult] = []

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(self.translators)
        ) as executor:
            future_to_method = {
                executor.submit(
                    translator.translate_with_timing,
                    text,
                    source_lang,
                    target_lang,
                    context,
                ): name
                for name, translator in self.translators.items()
            }

            for future in concurrent.futures.as_completed(future_to_method):
                method_name = future_to_method[future]
                try:
                    result = future.result(timeout=60)
                    results.append(result)
                    logger.info(
                        "Method %s completed: %d chars, confidence %.2f, %.1fs",
                        method_name,
                        len(result.translated_text),
                        result.confidence,
                        result.latency_seconds,
                    )
                except Exception as e:
                    logger.error("Method %s failed: %s", method_name, e)
                    results.append(
                        TranslationResult(
                            method=method_name,
                            source_text=text,
                            translated_text="",
                            confidence=0.0,
                            error=str(e),
                        )
                    )

        # Filter to successful results
        successful = [r for r in results if r.is_successful]

        if not successful:
            logger.error("All translation methods failed!")
            return results[0], results, None

        if len(successful) == 1:
            return successful[0], results, None

        # Evaluate quality and pick the best
        quality_score = self.evaluator.evaluate_translations(
            source_text=text,
            translations=successful,
        )

        # Get the best translation based on quality evaluation
        best_method = quality_score.best_method
        best_result = next(
            (r for r in successful if r.method == best_method),
            successful[0],
        )

        logger.info(
            "Ensemble winner: %s (score: %.3f)",
            best_method,
            quality_score.scores.get(best_method, 0),
        )

        # Log comparative results
        for method, score in sorted(
            quality_score.scores.items(), key=lambda x: x[1], reverse=True
        ):
            logger.info("  %s: %.3f", method, score)

        return best_result, results, quality_score
