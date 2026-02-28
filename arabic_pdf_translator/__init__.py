"""
Arabic PDF OCR & Translation Plugin
====================================

A production-grade pipeline that extracts Arabic text from scanned PDF documents
using multi-engine OCR, then translates to English using an ensemble of 4 methods
with automatic quality evaluation and best-result selection.

Architecture:
    PDF → Image Rendering → Preprocessing → Multi-Engine OCR → Arabic Post-processing
        → 4-Method Translation → Quality Evaluation → Best Translation Selection

Translation Methods:
    1. Claude (Anthropic) — contextual, culturally-aware translation
    2. Google Cloud Translation — high-volume statistical + neural MT
    3. DeepL — fluency-focused neural machine translation
    4. OpenAI GPT — LLM-based contextual translation

Quality Evaluation:
    - Cross-method agreement scoring
    - Linguistic coherence analysis
    - Arabic-specific fidelity checks (diacritics, proper nouns, idioms)
    - Claude-as-judge arbitration for final ranking
"""

__version__ = "2.0.0"
__author__ = "Arabic PDF Translator Plugin"

from arabic_pdf_translator.config import TranslationConfig


def __getattr__(name: str):
    """Lazy import for heavy modules that require numpy/cv2."""
    if name == "ArabicPDFTranslator":
        from arabic_pdf_translator.pipeline import ArabicPDFTranslator
        return ArabicPDFTranslator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ArabicPDFTranslator", "TranslationConfig"]
