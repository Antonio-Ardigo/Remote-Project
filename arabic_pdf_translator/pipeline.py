"""
Main pipeline orchestrator for Arabic PDF OCR & Translation.

This is the primary entry point that ties together:
1. PDF rendering → Image preprocessing → OCR extraction
2. Arabic text post-processing
3. Multi-method translation with ensemble selection
4. Output formatting and reporting
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import numpy as np

from arabic_pdf_translator.config import TranslationConfig
from arabic_pdf_translator.ocr.preprocessor import ImagePreprocessor
from arabic_pdf_translator.ocr.engine import OCREngineManager, OCRResult
from arabic_pdf_translator.ocr.postprocessor import ArabicPostProcessor
from arabic_pdf_translator.translator.ensemble import TranslationEnsemble
from arabic_pdf_translator.translator.base import TranslationResult
from arabic_pdf_translator.quality.evaluator import QualityScore
from arabic_pdf_translator.utils import chunk_text, is_arabic, setup_logging

logger = logging.getLogger(__name__)


@dataclass
class PageResult:
    """Result for a single PDF page."""
    page_number: int
    ocr_text: str
    ocr_confidence: float
    best_translation: str
    translation_method: str
    all_translations: list[dict] = field(default_factory=list)
    quality_scores: Optional[dict] = None
    processing_time_seconds: float = 0.0


@dataclass
class DocumentResult:
    """Complete result for an entire PDF document."""
    source_file: str
    total_pages: int
    pages: list[PageResult] = field(default_factory=list)
    full_translation: str = ""
    total_processing_time: float = 0.0
    summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to a serializable dictionary."""
        return {
            "source_file": self.source_file,
            "total_pages": self.total_pages,
            "pages": [
                {
                    "page_number": p.page_number,
                    "ocr_text": p.ocr_text,
                    "ocr_confidence": p.ocr_confidence,
                    "best_translation": p.best_translation,
                    "translation_method": p.translation_method,
                    "all_translations": p.all_translations,
                    "quality_scores": p.quality_scores,
                    "processing_time_seconds": p.processing_time_seconds,
                }
                for p in self.pages
            ],
            "full_translation": self.full_translation,
            "total_processing_time": self.total_processing_time,
            "summary": self.summary,
        }


class ArabicPDFTranslator:
    """
    Complete Arabic PDF OCR & Translation pipeline.

    Usage:
        config = TranslationConfig(
            anthropic_api_key="sk-...",
            force_multi_method=True,
        )
        translator = ArabicPDFTranslator(config)
        result = translator.translate_pdf("document.pdf")
        print(result.full_translation)
    """

    def __init__(self, config: Optional[TranslationConfig] = None):
        self.config = config or TranslationConfig()
        setup_logging()

        # Initialize components
        self.preprocessor = ImagePreprocessor(
            deskew=self.config.ocr.deskew,
            denoise=self.config.ocr.denoise,
            binarize=self.config.ocr.binarize,
            contrast_enhance=self.config.ocr.contrast_enhance,
            target_dpi=self.config.ocr.dpi,
        )
        self.ocr_manager = OCREngineManager(self.config.ocr)
        self.postprocessor = ArabicPostProcessor()
        self.ensemble = TranslationEnsemble(self.config)

        logger.info("ArabicPDFTranslator initialized")
        logger.info("OCR engines: %s", list(self.ocr_manager.engines.keys()))
        logger.info("Translation methods: %s", list(self.ensemble.translators.keys()))

    def translate_pdf(
        self,
        pdf_path: str,
        pages: Optional[list[int]] = None,
        output_path: Optional[str] = None,
    ) -> DocumentResult:
        """
        Translate an entire Arabic PDF document.

        Args:
            pdf_path: Path to the PDF file.
            pages: Optional list of page numbers to translate (0-indexed).
                   If None, translates all pages.
            output_path: Optional path to save the result.

        Returns:
            DocumentResult with complete translation and metadata.
        """
        start_time = time.time()
        pdf_path = str(Path(pdf_path).resolve())

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        logger.info("Starting translation of: %s", pdf_path)

        # Get page count
        try:
            import fitz
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            doc.close()
        except ImportError:
            raise ImportError("PyMuPDF required: pip install PyMuPDF")

        if pages is None:
            pages = list(range(total_pages))
        else:
            pages = [p for p in pages if 0 <= p < total_pages]

        logger.info("Processing %d pages out of %d total", len(pages), total_pages)

        result = DocumentResult(
            source_file=pdf_path,
            total_pages=total_pages,
        )

        # Process each page
        for page_num in pages:
            page_result = self._process_page(pdf_path, page_num)
            result.pages.append(page_result)
            logger.info(
                "Page %d/%d complete: %s method, %.1fs",
                page_num + 1,
                total_pages,
                page_result.translation_method,
                page_result.processing_time_seconds,
            )

        # Combine all page translations
        result.full_translation = "\n\n".join(
            f"--- Page {p.page_number + 1} ---\n{p.best_translation}"
            for p in result.pages
            if p.best_translation
        )

        result.total_processing_time = time.time() - start_time

        # Generate summary
        result.summary = self._generate_summary(result)

        logger.info(
            "Translation complete: %d pages, %.1fs total",
            len(result.pages),
            result.total_processing_time,
        )

        # Save output if requested
        if output_path:
            self._save_output(result, output_path)

        if self.config.save_intermediate:
            self._save_intermediate(result)

        return result

    def translate_image(self, image: np.ndarray) -> tuple[str, str, float]:
        """
        Translate a single image containing Arabic text.

        Args:
            image: Image as numpy array.

        Returns:
            Tuple of (original_text, translated_text, confidence).
        """
        # Preprocess
        processed = self.preprocessor.process(image)

        # OCR
        text, confidence, _ = self.ocr_manager.extract_text(processed)

        # Post-process Arabic
        text = self.postprocessor.process(text)

        if not text.strip():
            return "", "", 0.0

        # Translate
        best, all_results, quality = self.ensemble.translate(
            text,
            source_lang=self.config.source_lang,
            target_lang=self.config.target_lang,
        )

        return text, best.translated_text, best.confidence

    def translate_text(self, arabic_text: str) -> tuple[TranslationResult, list[TranslationResult], Optional[QualityScore]]:
        """
        Translate Arabic text directly (skip OCR).

        Useful when you already have extracted text.

        Args:
            arabic_text: Arabic text to translate.

        Returns:
            Tuple of (best_result, all_results, quality_score).
        """
        # Handle long texts by chunking
        chunks = chunk_text(
            arabic_text,
            max_chars=self.config.max_chunk_chars,
            overlap=self.config.chunk_overlap_chars,
        )

        if len(chunks) == 1:
            return self.ensemble.translate(
                arabic_text,
                source_lang=self.config.source_lang,
                target_lang=self.config.target_lang,
            )

        # Translate chunks with context
        all_best_translations = []
        all_results_combined = []
        last_quality = None

        for i, chunk in enumerate(chunks):
            context = chunks[i - 1] if i > 0 else None
            best, results, quality = self.ensemble.translate(
                chunk,
                source_lang=self.config.source_lang,
                target_lang=self.config.target_lang,
                context=context,
            )
            all_best_translations.append(best.translated_text)
            all_results_combined.extend(results)
            last_quality = quality

        # Combine chunk translations
        combined_text = " ".join(all_best_translations)
        combined_result = TranslationResult(
            method="ensemble_chunked",
            source_text=arabic_text,
            translated_text=combined_text,
            confidence=sum(r.confidence for r in all_results_combined if r.is_successful)
            / max(1, len([r for r in all_results_combined if r.is_successful])),
        )

        return combined_result, all_results_combined, last_quality

    def _process_page(self, pdf_path: str, page_num: int) -> PageResult:
        """Process a single PDF page: OCR + Translation."""
        page_start = time.time()

        # Render and preprocess
        try:
            processed_image = self.preprocessor.process_pdf_page(
                pdf_path, page_num, dpi=self.config.ocr.dpi
            )
        except Exception as e:
            logger.error("Failed to render page %d: %s", page_num, e)
            return PageResult(
                page_number=page_num,
                ocr_text="",
                ocr_confidence=0.0,
                best_translation=f"[Error rendering page: {e}]",
                translation_method="error",
                processing_time_seconds=time.time() - page_start,
            )

        # OCR extraction
        ocr_text, ocr_confidence, ocr_results = self.ocr_manager.extract_text(
            processed_image
        )

        # Post-process Arabic text
        ocr_text = self.postprocessor.process(ocr_text)

        if not ocr_text.strip() or not is_arabic(ocr_text):
            logger.warning("Page %d: no Arabic text detected", page_num)
            return PageResult(
                page_number=page_num,
                ocr_text=ocr_text,
                ocr_confidence=ocr_confidence,
                best_translation="[No Arabic text detected on this page]",
                translation_method="none",
                processing_time_seconds=time.time() - page_start,
            )

        # Translate
        best, all_results, quality = self.ensemble.translate(
            ocr_text,
            source_lang=self.config.source_lang,
            target_lang=self.config.target_lang,
        )

        # Build page result
        page_result = PageResult(
            page_number=page_num,
            ocr_text=ocr_text,
            ocr_confidence=ocr_confidence,
            best_translation=best.translated_text,
            translation_method=best.method,
            all_translations=[
                {
                    "method": r.method,
                    "text": r.translated_text,
                    "confidence": r.confidence,
                    "latency": r.latency_seconds,
                    "error": r.error,
                }
                for r in all_results
            ],
            quality_scores=quality.scores if quality else None,
            processing_time_seconds=time.time() - page_start,
        )

        return page_result

    def _generate_summary(self, result: DocumentResult) -> dict:
        """Generate a processing summary."""
        methods_used = {}
        total_ocr_confidence = 0.0
        pages_with_text = 0

        for page in result.pages:
            if page.translation_method and page.translation_method not in ("none", "error"):
                methods_used[page.translation_method] = (
                    methods_used.get(page.translation_method, 0) + 1
                )
                total_ocr_confidence += page.ocr_confidence
                pages_with_text += 1

        return {
            "total_pages_processed": len(result.pages),
            "pages_with_arabic_text": pages_with_text,
            "average_ocr_confidence": (
                total_ocr_confidence / pages_with_text if pages_with_text > 0 else 0
            ),
            "translation_methods_used": methods_used,
            "total_characters_translated": sum(
                len(p.best_translation) for p in result.pages
            ),
            "total_processing_time_seconds": result.total_processing_time,
            "average_time_per_page": (
                result.total_processing_time / len(result.pages)
                if result.pages
                else 0
            ),
        }

    def _save_output(self, result: DocumentResult, output_path: str) -> None:
        """Save translation result to file."""
        output_path = str(Path(output_path).resolve())
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        if output_path.endswith(".json"):
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        elif output_path.endswith(".md"):
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"# Translation: {os.path.basename(result.source_file)}\n\n")
                for page in result.pages:
                    f.write(f"## Page {page.page_number + 1}\n\n")
                    f.write(f"{page.best_translation}\n\n")
                    f.write(f"*Translated by: {page.translation_method} | ")
                    f.write(f"OCR confidence: {page.ocr_confidence:.1%}*\n\n")
                f.write("---\n\n")
                f.write(f"**Processing summary:** {json.dumps(result.summary, indent=2)}\n")
        else:
            # Plain text
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result.full_translation)

        logger.info("Output saved to: %s", output_path)

    def _save_intermediate(self, result: DocumentResult) -> None:
        """Save intermediate results for debugging."""
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save full JSON result
        json_path = output_dir / "full_result.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)

        # Save per-page OCR text
        for page in result.pages:
            ocr_path = output_dir / f"page_{page.page_number + 1}_ocr.txt"
            with open(ocr_path, "w", encoding="utf-8") as f:
                f.write(page.ocr_text)

            # Save all translations for comparison
            for trans in page.all_translations:
                trans_path = (
                    output_dir
                    / f"page_{page.page_number + 1}_translation_{trans['method']}.txt"
                )
                with open(trans_path, "w", encoding="utf-8") as f:
                    f.write(trans.get("text", ""))

        logger.info("Intermediate results saved to: %s", output_dir)
