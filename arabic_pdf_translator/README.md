# Arabic PDF OCR & Translation Plugin

A production-grade pipeline that extracts Arabic text from scanned PDF documents using multi-engine OCR, then translates to English using an ensemble of 4 methods with automatic quality evaluation and best-result selection.

## Architecture

```
PDF → Image Rendering (PyMuPDF, 300+ DPI)
    → Image Preprocessing (deskew, denoise, binarize, CLAHE contrast)
    → Multi-Engine OCR (Tesseract + EasyOCR + PaddleOCR)
    → Arabic Post-Processing (fix ligatures, diacritics, RTL ordering)
    → 4-Method Translation Ensemble:
        1. Claude (Anthropic) — contextual, culturally-aware
        2. Google Cloud Translation — neural MT, high throughput
        3. DeepL — fluency-focused neural MT
        4. OpenAI GPT-4o — LLM-based contextual translation
    → Quality Evaluation:
        - Heuristic scoring (completeness, fluency, accuracy, consistency)
        - Cross-method agreement analysis
        - Claude-as-judge arbitration (when scores are close)
    → Best Translation Selected
```

## Why This Beats Market Standard

| Feature | Market Standard | This Plugin |
|---|---|---|
| OCR | Single engine | Multi-engine with consensus |
| Preprocessing | Basic threshold | 7-stage pipeline tuned for Arabic |
| Translation | Single API | 4 independent methods |
| Quality control | None | Multi-dimensional evaluation + LLM judge |
| Arabic-specific | Generic | Arabic post-processing, diacritics preservation, RTL handling |
| Deskewing | Rarely | Hough-transform based automatic deskew |

## Quick Start

### 1. Install

```bash
# Core dependencies
pip install -e ".[all]"

# Or install manually
pip install PyMuPDF Pillow numpy opencv-python-headless pytesseract easyocr anthropic

# Install Tesseract OCR with Arabic data
sudo apt-get install tesseract-ocr tesseract-ocr-ara
```

### 2. Set API Keys

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export DEEPL_API_KEY="..."
export GOOGLE_TRANSLATE_API_KEY="..."
```

At minimum, set **one** API key. For best results (ensemble mode), set all four.

### 3. Translate

```bash
# Basic usage
python -m arabic_pdf_translator document.pdf

# Force all 4 methods and compare
python -m arabic_pdf_translator document.pdf --force-multi

# Specific pages, save as JSON
python -m arabic_pdf_translator document.pdf --pages 1,3,5-10 -o result.json

# High DPI for poor quality scans
python -m arabic_pdf_translator document.pdf --dpi 400 --force-multi
```

### Python API

```python
from arabic_pdf_translator import ArabicPDFTranslator, TranslationConfig

config = TranslationConfig(
    anthropic_api_key="sk-ant-...",
    force_multi_method=True,  # Always run all 4 methods
)

translator = ArabicPDFTranslator(config)

# Translate entire PDF
result = translator.translate_pdf("document.pdf")
print(result.full_translation)

# Check which method won per page
for page in result.pages:
    print(f"Page {page.page_number + 1}: {page.translation_method}")
    if page.quality_scores:
        for method, score in page.quality_scores.items():
            print(f"  {method}: {score:.3f}")

# Translate text directly (skip OCR)
best, all_results, quality = translator.translate_text("بسم الله الرحمن الرحيم")
print(best.translated_text)
```

## CLI Reference

```
arabic-pdf-translate document.pdf [OPTIONS]

Options:
  -o, --output PATH         Output file (.txt, .json, .md)
  --pages PAGES             Pages to translate (1-indexed, e.g., "1,3,5-10")
  --dpi DPI                 PDF rendering DPI (default: 300)
  --ocr-engines ENGINES     OCR engines (tesseract,easyocr,paddleocr)
  --methods METHODS         Translation methods (claude,google,deepl,openai)
  --force-multi             Always run all methods and compare
  --no-ensemble             Use single best method only
  --quality-threshold LEVEL Ensemble trigger: strict/moderate/relaxed/always
  --save-intermediate       Save per-page OCR and all translations
  --target-lang LANG        Target language (default: en)
  -v, --verbose             Verbose logging
```

## Configuration

All settings can be controlled via `TranslationConfig`:

```python
config = TranslationConfig(
    # API keys (or set via environment variables)
    anthropic_api_key="...",
    google_api_key="...",
    deepl_api_key="...",
    openai_api_key="...",

    # Translation
    source_lang="ar",
    target_lang="en",
    force_multi_method=True,

    # Quality
    quality_threshold=QualityThreshold.STRICT,  # Always use ensemble if <85% confident

    # OCR
    ocr=OCRConfig(
        engines=[OCREngine.TESSERACT, OCREngine.EASYOCR],
        dpi=400,
        deskew=True,
        denoise=True,
    ),

    # Output
    save_intermediate=True,
    output_dir="./debug_output",
)
```

## How the Ensemble Works

1. **Primary translation**: Run the first available method
2. **Confidence check**: If confidence < threshold, or `force_multi_method=True`:
3. **Parallel execution**: Run all 4 methods simultaneously
4. **Heuristic scoring**: Each translation scored on:
   - Completeness (length ratio, sentence count)
   - Accuracy (untranslated Arabic detection, self-confidence)
   - Fluency (sentence structure, capitalization, variety)
   - Consistency (no repetitive phrases)
5. **Cross-agreement**: Translations similar to the majority score higher
6. **Claude-as-judge**: If top scores are within 0.1, Claude evaluates all translations
   on accuracy, fluency, completeness, terminology, and register
7. **Final blend**: 60% judge score + 40% heuristic score → winner selected

## Tests

```bash
pip install pytest
pytest tests/ -v
```
