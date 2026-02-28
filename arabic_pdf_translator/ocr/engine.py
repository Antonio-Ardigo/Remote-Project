"""
Multi-engine OCR system for Arabic text extraction.

Supports Tesseract, EasyOCR, and PaddleOCR with consensus-based
text extraction for maximum accuracy.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from arabic_pdf_translator.config import OCRConfig, OCREngine

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    """Result from a single OCR engine."""
    engine: str
    text: str
    confidence: float  # 0.0 to 1.0
    word_confidences: list[float]
    raw_data: Optional[dict] = None


class TesseractOCR:
    """Tesseract OCR wrapper optimized for Arabic."""

    def __init__(self, config: OCRConfig):
        try:
            import pytesseract
            self.pytesseract = pytesseract
        except ImportError:
            raise ImportError(
                "pytesseract is required. Install with: pip install pytesseract\n"
                "Also install Tesseract binary: sudo apt-get install tesseract-ocr tesseract-ocr-ara"
            )
        self.config = config

    def extract(self, image: np.ndarray) -> OCRResult:
        """Extract Arabic text using Tesseract."""
        custom_config = (
            f"--oem {self.config.tesseract_oem} "
            f"--psm {self.config.tesseract_psm} "
            f"-l {self.config.tesseract_lang}"
        )

        # Get detailed data with confidences
        data = self.pytesseract.image_to_data(
            image, config=custom_config, output_type=self.pytesseract.Output.DICT
        )

        # Extract text and confidence scores
        words = []
        confidences = []
        for i, text in enumerate(data["text"]):
            text = text.strip()
            if text:
                words.append(text)
                conf = float(data["conf"][i])
                # Tesseract reports confidence as 0-100, normalize to 0-1
                confidences.append(max(0.0, conf / 100.0))

        full_text = " ".join(words)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        logger.info(
            "Tesseract OCR: extracted %d words, avg confidence %.2f",
            len(words),
            avg_confidence,
        )

        return OCRResult(
            engine="tesseract",
            text=full_text,
            confidence=avg_confidence,
            word_confidences=confidences,
            raw_data=data,
        )


class EasyOCREngine:
    """EasyOCR wrapper with Arabic language support."""

    def __init__(self, config: OCRConfig):
        try:
            import easyocr
            self.reader = easyocr.Reader(
                config.easyocr_langs,
                gpu=config.easyocr_gpu,
            )
        except ImportError:
            raise ImportError(
                "easyocr is required. Install with: pip install easyocr"
            )
        self.config = config

    def extract(self, image: np.ndarray) -> OCRResult:
        """Extract Arabic text using EasyOCR."""
        # Use detail=1, paragraph=False to get (bbox, text, conf) tuples
        # paragraph=True drops confidence scores in many EasyOCR versions
        results = self.reader.readtext(image, detail=1, paragraph=False)

        texts = []
        confidences = []
        for item in results:
            if len(item) == 3:
                _bbox, text, conf = item
            elif len(item) == 2:
                text, conf = item
                conf = 0.5  # default if no confidence
            else:
                continue
            text = str(text).strip()
            if text:
                texts.append(text)
                try:
                    confidences.append(float(conf))
                except (ValueError, TypeError):
                    confidences.append(0.5)

        # EasyOCR returns text in reading order — for Arabic RTL,
        # paragraphs within each line are already ordered correctly
        full_text = "\n".join(texts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        logger.info(
            "EasyOCR: extracted %d text blocks, avg confidence %.2f",
            len(texts),
            avg_confidence,
        )

        return OCRResult(
            engine="easyocr",
            text=full_text,
            confidence=avg_confidence,
            word_confidences=confidences,
        )


class PaddleOCREngine:
    """PaddleOCR wrapper with Arabic support."""

    def __init__(self, config: OCRConfig):
        try:
            from paddleocr import PaddleOCR
            self.ocr = PaddleOCR(
                lang=config.paddleocr_lang,
                use_angle_cls=True,
                show_log=False,
            )
        except ImportError:
            raise ImportError(
                "paddleocr is required. Install with: pip install paddleocr paddlepaddle"
            )
        self.config = config

    def extract(self, image: np.ndarray) -> OCRResult:
        """Extract Arabic text using PaddleOCR."""
        results = self.ocr.ocr(image, cls=True)

        texts = []
        confidences = []

        if results and results[0]:
            for line in results[0]:
                text = line[1][0].strip()
                conf = float(line[1][1])
                if text:
                    texts.append(text)
                    confidences.append(conf)

        full_text = "\n".join(texts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        logger.info(
            "PaddleOCR: extracted %d text blocks, avg confidence %.2f",
            len(texts),
            avg_confidence,
        )

        return OCRResult(
            engine="paddleocr",
            text=full_text,
            confidence=avg_confidence,
            word_confidences=confidences,
        )


class OCREngineManager:
    """
    Manages multiple OCR engines and combines their results.

    Strategy:
    1. Run all configured engines
    2. Use confidence-weighted voting for final text
    3. Falls back to highest-confidence single engine if voting fails
    """

    ENGINE_MAP = {
        OCREngine.TESSERACT: TesseractOCR,
        OCREngine.EASYOCR: EasyOCREngine,
        OCREngine.PADDLEOCR: PaddleOCREngine,
    }

    def __init__(self, config: OCRConfig):
        self.config = config
        self.engines = {}
        self._init_engines()

    def _init_engines(self) -> None:
        """Initialize all configured OCR engines, skip unavailable ones."""
        for engine_type in self.config.engines:
            engine_cls = self.ENGINE_MAP.get(engine_type)
            if engine_cls is None:
                logger.warning("Unknown OCR engine: %s", engine_type)
                continue
            try:
                self.engines[engine_type] = engine_cls(self.config)
                logger.info("Initialized OCR engine: %s", engine_type.value)
            except ImportError as e:
                logger.warning("OCR engine %s unavailable: %s", engine_type.value, e)

        if not self.engines:
            raise RuntimeError(
                "No OCR engines available. Install at least one of: "
                "pytesseract, easyocr, paddleocr"
            )

    def extract_text(self, image: np.ndarray) -> tuple[str, float, list[OCRResult]]:
        """
        Extract text using all available engines and return the best result.

        Returns:
            Tuple of (best_text, confidence, all_results).
        """
        results: list[OCRResult] = []

        for engine_type, engine in self.engines.items():
            try:
                result = engine.extract(image)
                if result.text.strip():
                    results.append(result)
                    logger.info(
                        "Engine %s: %d chars, confidence %.2f",
                        engine_type.value,
                        len(result.text),
                        result.confidence,
                    )
            except Exception as e:
                logger.error("OCR engine %s failed: %s", engine_type.value, e)

        if not results:
            logger.warning("All OCR engines returned empty results")
            return "", 0.0, results

        # If only one engine, use its result directly
        if len(results) == 1:
            return results[0].text, results[0].confidence, results

        # Multiple engines — pick the one with highest confidence
        # and longest meaningful text (length * confidence as score)
        best = max(results, key=lambda r: len(r.text) * r.confidence)

        # If another engine has significantly higher confidence,
        # prefer it even if shorter
        highest_conf = max(results, key=lambda r: r.confidence)
        if highest_conf.confidence - best.confidence > 0.15:
            best = highest_conf

        logger.info(
            "Selected OCR result from %s (confidence: %.2f, length: %d)",
            best.engine,
            best.confidence,
            len(best.text),
        )

        return best.text, best.confidence, results
