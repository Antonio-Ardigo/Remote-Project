"""
Configuration management for the Arabic PDF OCR & Translation pipeline.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class OCREngine(Enum):
    TESSERACT = "tesseract"
    EASYOCR = "easyocr"
    PADDLEOCR = "paddleocr"


class TranslationMethod(Enum):
    CLAUDE = "claude"
    GOOGLE = "google"
    DEEPL = "deepl"
    OPENAI = "openai"


class QualityThreshold(Enum):
    """When to trigger multi-method translation."""
    STRICT = 0.85       # Trigger ensemble if confidence < 85%
    MODERATE = 0.70     # Trigger ensemble if confidence < 70%
    RELAXED = 0.55      # Trigger ensemble if confidence < 55%
    ALWAYS = 1.0        # Always run all 4 methods


@dataclass
class OCRConfig:
    """OCR processing configuration."""
    engines: list[OCREngine] = field(
        default_factory=lambda: [OCREngine.EASYOCR]
    )
    dpi: int = 300
    enable_preprocessing: bool = True
    # Preprocessing options
    deskew: bool = True
    denoise: bool = True
    binarize: bool = True
    contrast_enhance: bool = True
    # Tesseract-specific
    tesseract_lang: str = "ara"
    tesseract_psm: int = 6  # Assume uniform block of text
    tesseract_oem: int = 3  # LSTM + legacy
    # EasyOCR-specific
    easyocr_langs: list[str] = field(default_factory=lambda: ["ar"])
    easyocr_gpu: bool = False
    # PaddleOCR-specific
    paddleocr_lang: str = "ar"


@dataclass
class TranslationConfig:
    """Translation pipeline configuration."""
    # API keys — loaded from env vars if not set
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    deepl_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # Translation settings
    source_lang: str = "ar"
    target_lang: str = "en"
    methods: list[TranslationMethod] = field(
        default_factory=lambda: [
            TranslationMethod.CLAUDE,
            TranslationMethod.GOOGLE,
            TranslationMethod.DEEPL,
            TranslationMethod.OPENAI,
        ]
    )

    # Quality control
    quality_threshold: QualityThreshold = QualityThreshold.MODERATE
    enable_ensemble: bool = True
    # When True, always run all 4 methods and pick best
    force_multi_method: bool = False

    # Claude model for translation and judging
    claude_model: str = "claude-sonnet-4-20250514"
    claude_judge_model: str = "claude-sonnet-4-20250514"

    # OpenAI model
    openai_model: str = "gpt-4o"

    # Chunking — for long documents
    max_chunk_chars: int = 3000
    chunk_overlap_chars: int = 200

    # OCR settings
    ocr: OCRConfig = field(default_factory=OCRConfig)

    # Output
    output_format: str = "text"  # text, json, markdown, docx
    save_intermediate: bool = False
    output_dir: str = "./output"

    def __post_init__(self):
        """Load API keys from environment variables if not provided."""
        if not self.anthropic_api_key:
            self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.google_api_key:
            self.google_api_key = os.environ.get("GOOGLE_TRANSLATE_API_KEY")
        if not self.deepl_api_key:
            self.deepl_api_key = os.environ.get("DEEPL_API_KEY")
        if not self.openai_api_key:
            self.openai_api_key = os.environ.get("OPENAI_API_KEY")

    def get_available_methods(self) -> list[TranslationMethod]:
        """Return only translation methods that have API keys configured."""
        available = []
        key_map = {
            TranslationMethod.CLAUDE: self.anthropic_api_key,
            TranslationMethod.GOOGLE: self.google_api_key,
            TranslationMethod.DEEPL: self.deepl_api_key,
            TranslationMethod.OPENAI: self.openai_api_key,
        }
        for method in self.methods:
            if key_map.get(method):
                available.append(method)
        return available
