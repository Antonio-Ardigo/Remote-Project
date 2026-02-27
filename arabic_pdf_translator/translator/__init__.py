"""
Translation subsystem with 4 independent methods and ensemble selection.
"""

from arabic_pdf_translator.translator.base import BaseTranslator, TranslationResult

__all__ = [
    "BaseTranslator",
    "TranslationResult",
    "ClaudeTranslator",
    "GoogleTranslator",
    "DeepLTranslator",
    "OpenAITranslator",
    "TranslationEnsemble",
]


def __getattr__(name: str):
    if name == "ClaudeTranslator":
        from arabic_pdf_translator.translator.claude_translator import ClaudeTranslator
        return ClaudeTranslator
    if name == "GoogleTranslator":
        from arabic_pdf_translator.translator.google_translator import GoogleTranslator
        return GoogleTranslator
    if name == "DeepLTranslator":
        from arabic_pdf_translator.translator.deepl_translator import DeepLTranslator
        return DeepLTranslator
    if name == "OpenAITranslator":
        from arabic_pdf_translator.translator.openai_translator import OpenAITranslator
        return OpenAITranslator
    if name == "TranslationEnsemble":
        from arabic_pdf_translator.translator.ensemble import TranslationEnsemble
        return TranslationEnsemble
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
