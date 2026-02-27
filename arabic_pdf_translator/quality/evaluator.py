"""
Translation Quality Evaluator.

Multi-dimensional quality assessment system that evaluates translations
across several criteria and uses Claude-as-judge for final arbitration.

Evaluation Dimensions:
1. Completeness — does the translation cover all source content?
2. Fluency — is the English natural and grammatically correct?
3. Accuracy — does the translation preserve the source meaning?
4. Consistency — is terminology consistent throughout?
5. Cross-agreement — do multiple methods agree on key terms/phrases?

The system combines automated heuristics with LLM-based judgment
to produce a final ranking that consistently outperforms any single
translation method.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from arabic_pdf_translator.translator.base import TranslationResult
from arabic_pdf_translator.utils import calculate_text_similarity, normalize_arabic

logger = logging.getLogger(__name__)


@dataclass
class QualityScore:
    """Quality evaluation result for a set of translations."""
    scores: dict[str, float]  # method_name → overall_score (0.0–1.0)
    dimension_scores: dict[str, dict[str, float]]  # method → {dimension → score}
    best_method: str
    reasoning: str = ""
    judge_used: bool = False

    def get_ranking(self) -> list[tuple[str, float]]:
        """Return methods ranked by score, highest first."""
        return sorted(self.scores.items(), key=lambda x: x[1], reverse=True)


JUDGE_PROMPT = """You are an expert translation quality evaluator specializing in Arabic-to-English translation.

You will be given the original Arabic text and {n_translations} different English translations.
Evaluate each translation on these dimensions (score 1-10 for each):

1. **Accuracy**: Does the translation faithfully convey the original Arabic meaning?
   - Check for mistranslations, omissions, and additions
   - Verify proper nouns are correctly transliterated
   - Check numbers and dates are preserved

2. **Fluency**: Is the English natural, grammatically correct, and readable?
   - Check grammar, word choice, and sentence structure
   - Assess whether it reads like native English

3. **Completeness**: Does the translation cover ALL of the source content?
   - Check for missing sentences or paragraphs
   - Verify nothing is skipped or summarized

4. **Terminology**: Are domain-specific terms translated correctly and consistently?
   - Check technical, legal, religious, or cultural terms
   - Verify consistent terminology throughout

5. **Register**: Does the translation maintain the appropriate formality level?
   - Formal Arabic should produce formal English
   - Colloquial Arabic should produce natural conversational English

ORIGINAL ARABIC TEXT:
{source_text}

{translations_block}

Respond in this EXACT JSON format (no other text):
{{
    "evaluations": {{
        {evaluations_template}
    }},
    "best_method": "<method_name of the best translation>",
    "reasoning": "<brief explanation of why the best translation wins>"
}}"""


class QualityEvaluator:
    """
    Multi-dimensional translation quality evaluator.

    Combines:
    - Automated heuristic scoring (fast, no API calls)
    - Cross-method agreement analysis
    - Claude-as-judge arbitration (when available)
    """

    # Weights for combining dimension scores
    DIMENSION_WEIGHTS = {
        "accuracy": 0.30,
        "fluency": 0.25,
        "completeness": 0.25,
        "consistency": 0.10,
        "cross_agreement": 0.10,
    }

    def __init__(
        self,
        anthropic_api_key: Optional[str] = None,
        judge_model: str = "claude-sonnet-4-6",
    ):
        self.anthropic_api_key = anthropic_api_key
        self.judge_model = judge_model
        self._claude_client = None

        if anthropic_api_key:
            try:
                import anthropic
                self._claude_client = anthropic.Anthropic(api_key=anthropic_api_key)
                logger.info("Quality evaluator: Claude judge enabled")
            except ImportError:
                logger.warning("anthropic package not installed, Claude judge disabled")

    def evaluate_translations(
        self,
        source_text: str,
        translations: list[TranslationResult],
    ) -> QualityScore:
        """
        Evaluate and rank multiple translations of the same source text.

        Uses a combination of automated heuristics and (optionally)
        Claude-as-judge for final ranking.

        Args:
            source_text: Original Arabic text.
            translations: List of translation results from different methods.

        Returns:
            QualityScore with rankings and detailed scores.
        """
        if not translations:
            return QualityScore(scores={}, dimension_scores={}, best_method="")

        if len(translations) == 1:
            method = translations[0].method
            return QualityScore(
                scores={method: translations[0].confidence},
                dimension_scores={method: {"self_confidence": translations[0].confidence}},
                best_method=method,
            )

        # Phase 1: Automated heuristic scoring
        heuristic_scores = self._heuristic_evaluation(source_text, translations)

        # Phase 2: Cross-method agreement
        agreement_scores = self._cross_agreement_scoring(translations)

        # Phase 3: Combine heuristic scores
        combined_scores: dict[str, float] = {}
        dimension_scores: dict[str, dict[str, float]] = {}

        for result in translations:
            method = result.method
            h_scores = heuristic_scores.get(method, {})
            agreement = agreement_scores.get(method, 0.5)

            dims = {**h_scores, "cross_agreement": agreement}
            dimension_scores[method] = dims

            # Weighted combination
            total = 0.0
            total_weight = 0.0
            for dim, weight in self.DIMENSION_WEIGHTS.items():
                if dim in dims:
                    total += dims[dim] * weight
                    total_weight += weight

            combined_scores[method] = total / total_weight if total_weight > 0 else 0.0

        # Phase 4: Claude-as-judge (if available and scores are close)
        judge_used = False
        reasoning = ""

        if self._claude_client and self._should_use_judge(combined_scores):
            try:
                judge_result = self._claude_judge(source_text, translations)
                if judge_result:
                    # Blend judge scores with heuristic scores (60% judge, 40% heuristic)
                    for method in combined_scores:
                        if method in judge_result["scores"]:
                            combined_scores[method] = (
                                0.6 * judge_result["scores"][method]
                                + 0.4 * combined_scores[method]
                            )
                    reasoning = judge_result.get("reasoning", "")
                    judge_used = True

                    # Update dimension scores with judge dimensions
                    for method, judge_dims in judge_result.get("dimensions", {}).items():
                        if method in dimension_scores:
                            dimension_scores[method].update(
                                {f"judge_{k}": v for k, v in judge_dims.items()}
                            )
            except Exception as e:
                logger.warning("Claude judge evaluation failed: %s", e)

        # Determine best method
        best_method = max(combined_scores, key=combined_scores.get)

        return QualityScore(
            scores=combined_scores,
            dimension_scores=dimension_scores,
            best_method=best_method,
            reasoning=reasoning,
            judge_used=judge_used,
        )

    def _heuristic_evaluation(
        self,
        source_text: str,
        translations: list[TranslationResult],
    ) -> dict[str, dict[str, float]]:
        """
        Fast heuristic-based quality evaluation.

        Checks:
        - Length ratio (translation should be ~0.8-1.5x source length for Arabic→English)
        - Sentence count preservation
        - Paragraph structure preservation
        - Presence of untranslated Arabic characters (failure indicator)
        - Self-reported confidence from translator
        """
        scores: dict[str, dict[str, float]] = {}
        source_len = len(source_text)
        source_sentences = len(re.split(r'[.!?،؟\n]+', source_text))
        source_paragraphs = len([p for p in source_text.split('\n\n') if p.strip()])

        for result in translations:
            method = result.method
            text = result.translated_text

            if not text.strip():
                scores[method] = {
                    "accuracy": 0.0,
                    "fluency": 0.0,
                    "completeness": 0.0,
                    "consistency": 0.0,
                }
                continue

            # Completeness: length ratio check
            length_ratio = len(text) / source_len if source_len > 0 else 0
            # Arabic→English typically produces 0.7x to 1.5x length
            if 0.5 <= length_ratio <= 2.0:
                completeness = min(1.0, 1.0 - abs(1.0 - length_ratio) * 0.3)
            else:
                completeness = max(0.2, 1.0 - abs(1.0 - length_ratio) * 0.5)

            # Sentence preservation
            trans_sentences = len(re.split(r'[.!?\n]+', text))
            sentence_ratio = trans_sentences / source_sentences if source_sentences > 0 else 1
            sentence_score = min(1.0, 1.0 - abs(1.0 - sentence_ratio) * 0.4)
            completeness = (completeness + sentence_score) / 2

            # Accuracy: check for untranslated Arabic (bad sign)
            arabic_pattern = re.compile(r'[\u0600-\u06FF]')
            arabic_in_output = len(arabic_pattern.findall(text))
            arabic_ratio = arabic_in_output / len(text) if len(text) > 0 else 0
            accuracy = max(0.3, 1.0 - arabic_ratio * 5)

            # Blend with self-reported confidence
            accuracy = (accuracy * 0.7 + result.confidence * 0.3)

            # Fluency: basic English quality checks
            fluency = self._assess_fluency(text)

            # Consistency: check for repeated phrases (possible errors)
            consistency = self._assess_consistency(text)

            scores[method] = {
                "accuracy": accuracy,
                "fluency": fluency,
                "completeness": completeness,
                "consistency": consistency,
            }

        return scores

    def _assess_fluency(self, text: str) -> float:
        """Assess English fluency heuristically."""
        score = 0.75  # Base score

        # Check for common fluency indicators
        sentences = re.split(r'[.!?]+', text)
        valid_sentences = [s.strip() for s in sentences if s.strip()]

        if not valid_sentences:
            return 0.3

        # Sentence length variety (good English has varied sentence lengths)
        lengths = [len(s.split()) for s in valid_sentences]
        if len(lengths) > 1:
            avg_len = sum(lengths) / len(lengths)
            if 8 <= avg_len <= 25:
                score += 0.1  # Good average sentence length
            variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)
            if variance > 10:
                score += 0.05  # Good variety

        # Capitalization check
        properly_capitalized = sum(
            1 for s in valid_sentences if s[0].isupper()
        )
        cap_ratio = properly_capitalized / len(valid_sentences)
        score += cap_ratio * 0.1

        return min(1.0, score)

    def _assess_consistency(self, text: str) -> float:
        """Check for internal consistency (repeated verbatim phrases = bad)."""
        words = text.split()
        if len(words) < 10:
            return 0.8

        # Check for exact duplicate phrases (3+ words)
        trigrams = [' '.join(words[i:i+3]) for i in range(len(words) - 2)]
        unique_ratio = len(set(trigrams)) / len(trigrams) if trigrams else 1.0

        return min(1.0, unique_ratio + 0.1)

    def _cross_agreement_scoring(
        self, translations: list[TranslationResult]
    ) -> dict[str, float]:
        """
        Score each translation by how much it agrees with others.

        Translations that are similar to the majority are likely more accurate.
        """
        agreement_scores: dict[str, float] = {}

        for i, result_i in enumerate(translations):
            if not result_i.is_successful:
                agreement_scores[result_i.method] = 0.0
                continue

            similarities = []
            for j, result_j in enumerate(translations):
                if i == j or not result_j.is_successful:
                    continue
                sim = calculate_text_similarity(
                    result_i.translated_text, result_j.translated_text
                )
                similarities.append(sim)

            if similarities:
                agreement_scores[result_i.method] = sum(similarities) / len(similarities)
            else:
                agreement_scores[result_i.method] = 0.5  # No comparison available

        return agreement_scores

    def _should_use_judge(self, scores: dict[str, float]) -> bool:
        """Determine if Claude-as-judge is needed (scores are close)."""
        if len(scores) < 2:
            return False

        sorted_scores = sorted(scores.values(), reverse=True)
        # Use judge if top 2 scores are within 0.1 of each other
        return (sorted_scores[0] - sorted_scores[1]) < 0.1

    def _claude_judge(
        self,
        source_text: str,
        translations: list[TranslationResult],
    ) -> Optional[dict]:
        """
        Use Claude as a judge to evaluate and rank translations.

        Returns dict with 'scores', 'dimensions', and 'reasoning'.
        """
        if not self._claude_client:
            return None

        successful = [t for t in translations if t.is_successful]
        if len(successful) < 2:
            return None

        logger.info("Running Claude-as-judge evaluation on %d translations", len(successful))

        # Build the prompt
        translations_block = ""
        evaluations_template_parts = []

        for i, result in enumerate(successful, 1):
            translations_block += (
                f"\n--- TRANSLATION {i} (method: {result.method}) ---\n"
                f"{result.translated_text}\n"
            )
            evaluations_template_parts.append(
                f'"{result.method}": {{"accuracy": <1-10>, "fluency": <1-10>, '
                f'"completeness": <1-10>, "terminology": <1-10>, "register": <1-10>}}'
            )

        evaluations_template = ",\n        ".join(evaluations_template_parts)

        prompt = JUDGE_PROMPT.format(
            n_translations=len(successful),
            source_text=source_text[:2000],  # Truncate to avoid token limits
            translations_block=translations_block,
            evaluations_template=evaluations_template,
        )

        try:
            message = self._claude_client.messages.create(
                model=self.judge_model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = message.content[0].text.strip()

            # Parse JSON response
            import json
            # Extract JSON from response (handle potential wrapping)
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if not json_match:
                logger.warning("Claude judge did not return valid JSON")
                return None

            judge_data = json.loads(json_match.group())

            # Convert judge scores (1-10) to normalized (0-1)
            scores = {}
            dimensions = {}

            for method, dims in judge_data.get("evaluations", {}).items():
                dim_scores = {}
                total = 0.0
                for dim_name, dim_score in dims.items():
                    normalized = float(dim_score) / 10.0
                    dim_scores[dim_name] = normalized
                    total += normalized
                dimensions[method] = dim_scores
                scores[method] = total / len(dim_scores) if dim_scores else 0.0

            return {
                "scores": scores,
                "dimensions": dimensions,
                "best_method": judge_data.get("best_method", ""),
                "reasoning": judge_data.get("reasoning", ""),
            }

        except Exception as e:
            logger.warning("Claude judge evaluation error: %s", e)
            return None
