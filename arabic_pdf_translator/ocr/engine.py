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
        # Auto-detect Tesseract binary on Windows (Chocolatey install location)
        import shutil
        if not shutil.which("tesseract"):
            import os
            win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.isfile(win_path):
                self.pytesseract.pytesseract.tesseract_cmd = win_path

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


class ClaudeVisionOCR:
    """Claude Vision API for Arabic text extraction (especially handwriting)."""

    def __init__(self, config: OCRConfig):
        try:
            import anthropic
            self.client = anthropic.Anthropic()
        except ImportError:
            raise ImportError(
                "anthropic SDK is required for Claude Vision OCR. "
                "Install with: pip install anthropic"
            )
        self.config = config
        self.model = "claude-sonnet-4-20250514"

    def extract(self, image: np.ndarray) -> OCRResult:
        """Extract Arabic text using Claude Vision."""
        import base64
        import cv2

        success, buffer = cv2.imencode('.png', image)
        if not success:
            raise RuntimeError("Failed to encode image for Claude Vision")
        image_b64 = base64.b64encode(buffer).decode('utf-8')

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_b64,
                        }
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extract ALL Arabic text visible in this image. "
                            "Include both printed and handwritten text. "
                            "Read right-to-left carefully. "
                            "Preserve line breaks and paragraph structure. "
                            "Output ONLY the Arabic text, nothing else. "
                            "If text is partially illegible, use your best reading."
                        ),
                    }
                ]
            }]
        )

        text = response.content[0].text.strip()
        confidence = 0.90 if text else 0.0
        if response.stop_reason == "end_turn":
            confidence = 0.92

        logger.info(
            "Claude Vision OCR: extracted %d chars, confidence %.2f",
            len(text), confidence,
        )

        return OCRResult(
            engine="claude_vision",
            text=text,
            confidence=confidence,
            word_confidences=[confidence],
            raw_data={"model": self.model, "stop_reason": response.stop_reason},
        )


class OpenAIVisionOCR:
    """GPT-4o Vision API for Arabic text extraction (especially handwriting)."""

    def __init__(self, config: OCRConfig):
        try:
            import openai
            self.client = openai.OpenAI()
        except ImportError:
            raise ImportError(
                "openai SDK is required for OpenAI Vision OCR. "
                "Install with: pip install openai"
            )
        self.config = config
        self.model = "gpt-4o"

    def extract(self, image: np.ndarray) -> OCRResult:
        """Extract Arabic text using GPT-4o Vision."""
        import base64
        import cv2

        success, buffer = cv2.imencode('.png', image)
        if not success:
            raise RuntimeError("Failed to encode image for OpenAI Vision")
        image_b64 = base64.b64encode(buffer).decode('utf-8')

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=4096,
            temperature=0.1,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}",
                        }
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extract ALL Arabic text visible in this image. "
                            "Include both printed and handwritten text. "
                            "Read right-to-left carefully. "
                            "Preserve line breaks and paragraph structure. "
                            "Output ONLY the Arabic text, nothing else. "
                            "If text is partially illegible, use your best reading."
                        ),
                    }
                ]
            }]
        )

        text = response.choices[0].message.content.strip()
        finish_reason = response.choices[0].finish_reason
        confidence = 0.88 if text else 0.0
        if finish_reason == "stop":
            confidence = 0.90

        logger.info(
            "OpenAI Vision OCR: extracted %d chars, confidence %.2f",
            len(text), confidence,
        )

        return OCRResult(
            engine="openai_vision",
            text=text,
            confidence=confidence,
            word_confidences=[confidence],
            raw_data={"model": self.model, "finish_reason": finish_reason},
        )


class QariOCR:
    """NAMAA Qari-OCR for Arabic handwriting recognition (local 2B VLM)."""

    MODEL_ID = "NAMAA-Space/Qari-OCR-v0.3-VL-2B-Instruct"

    def __init__(self, config: OCRConfig):
        try:
            from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
            import torch
        except ImportError:
            raise ImportError(
                "transformers and torch are required for Qari-OCR. "
                "Install with: pip install transformers torch qwen-vl-utils"
            )

        logger.info("Loading Qari-OCR model (first run downloads ~4GB)...")
        self.torch = torch
        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            self.MODEL_ID,
            torch_dtype=torch.bfloat16,
            low_cpu_mem_usage=True,
        )
        self.processor = AutoProcessor.from_pretrained(self.MODEL_ID)
        self.config = config
        logger.info("Qari-OCR model loaded.")

    def extract(self, image: np.ndarray) -> OCRResult:
        """Extract Arabic text using Qari-OCR VLM."""
        from PIL import Image

        if len(image.shape) == 2:
            pil_image = Image.fromarray(image, mode='L').convert('RGB')
        else:
            pil_image = Image.fromarray(image)

        messages = [
            {"role": "user", "content": [
                {"type": "image", "image": pil_image},
                {"type": "text", "text": "Extract all Arabic text from this image exactly as written."}
            ]}
        ]

        try:
            from qwen_vl_utils import process_vision_info
            text_prompt = self.processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = self.processor(
                text=[text_prompt], images=image_inputs, videos=video_inputs,
                padding=True, return_tensors="pt"
            )
        except ImportError:
            text_prompt = self.processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = self.processor(
                text=[text_prompt], images=[pil_image],
                padding=True, return_tensors="pt"
            )

        with self.torch.no_grad():
            output_ids = self.model.generate(**inputs, max_new_tokens=2048)

        generated = output_ids[:, inputs.input_ids.shape[1]:]
        text = self.processor.batch_decode(
            generated, skip_special_tokens=True
        )[0].strip()

        confidence = 0.85 if text else 0.0

        logger.info(
            "Qari-OCR: extracted %d chars, confidence %.2f",
            len(text), confidence,
        )

        return OCRResult(
            engine="qari",
            text=text,
            confidence=confidence,
            word_confidences=[confidence],
            raw_data={"model": self.MODEL_ID},
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
        OCREngine.CLAUDE_VISION: ClaudeVisionOCR,
        OCREngine.OPENAI_VISION: OpenAIVisionOCR,
        OCREngine.QARI: QariOCR,
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
                "easyocr, pytesseract, paddleocr, anthropic (for claude_vision), "
                "transformers+torch (for qari)"
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
