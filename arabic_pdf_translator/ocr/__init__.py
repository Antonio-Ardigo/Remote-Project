"""
OCR subsystem for Arabic text extraction from PDF images.

Supports multiple OCR engines with image preprocessing optimized
for Arabic script (RTL, connected letters, diacritics).
"""

from arabic_pdf_translator.ocr.postprocessor import ArabicPostProcessor


def __getattr__(name: str):
    if name == "ImagePreprocessor":
        from arabic_pdf_translator.ocr.preprocessor import ImagePreprocessor
        return ImagePreprocessor
    if name == "OCREngineManager":
        from arabic_pdf_translator.ocr.engine import OCREngineManager
        return OCREngineManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ImagePreprocessor", "OCREngineManager", "ArabicPostProcessor"]
