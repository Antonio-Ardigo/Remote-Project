"""
Quality evaluation subsystem for translation comparison and ranking.
"""

__all__ = ["QualityEvaluator", "QualityScore"]


def __getattr__(name: str):
    if name in ("QualityEvaluator", "QualityScore"):
        from arabic_pdf_translator.quality.evaluator import QualityEvaluator, QualityScore
        if name == "QualityEvaluator":
            return QualityEvaluator
        return QualityScore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
