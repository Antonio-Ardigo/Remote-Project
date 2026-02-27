"""
CLI entry point for Arabic PDF OCR & Translation.

Usage:
    # Translate a PDF with default settings
    python -m arabic_pdf_translator document.pdf

    # Force all 4 methods and compare
    python -m arabic_pdf_translator document.pdf --ensemble --force-multi

    # Translate specific pages
    python -m arabic_pdf_translator document.pdf --pages 1,3,5

    # Save output in different formats
    python -m arabic_pdf_translator document.pdf -o output.json
    python -m arabic_pdf_translator document.pdf -o output.md
    python -m arabic_pdf_translator document.pdf -o output.txt

    # Save intermediate results for debugging
    python -m arabic_pdf_translator document.pdf --save-intermediate
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from arabic_pdf_translator.config import (
    TranslationConfig,
    OCRConfig,
    OCREngine,
    TranslationMethod,
    QualityThreshold,
)
from arabic_pdf_translator.pipeline import ArabicPDFTranslator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="arabic-pdf-translator",
        description=(
            "Arabic PDF OCR & Translation — Extract and translate Arabic text "
            "from scanned PDFs using multi-engine OCR and 4-method ensemble translation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s document.pdf
  %(prog)s document.pdf --ensemble --force-multi -o translated.md
  %(prog)s document.pdf --pages 1,3,5-10 --dpi 400
  %(prog)s document.pdf --methods claude,deepl --save-intermediate

Environment variables for API keys:
  ANTHROPIC_API_KEY       - Anthropic Claude API key
  GOOGLE_TRANSLATE_API_KEY - Google Cloud Translation API key
  DEEPL_API_KEY           - DeepL API key
  OPENAI_API_KEY          - OpenAI API key
        """,
    )

    # Required arguments
    parser.add_argument(
        "pdf_path",
        type=str,
        help="Path to the Arabic PDF document",
    )

    # Output options
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Output file path (.txt, .json, .md). Default: stdout",
    )
    parser.add_argument(
        "--save-intermediate",
        action="store_true",
        help="Save intermediate OCR and translation results",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./output",
        help="Directory for intermediate results (default: ./output)",
    )

    # Page selection
    parser.add_argument(
        "--pages",
        type=str,
        default=None,
        help="Pages to translate (comma-separated, 1-indexed). E.g., '1,3,5-10'",
    )

    # OCR options
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="PDF rendering DPI (default: 300, use 400+ for poor quality scans)",
    )
    parser.add_argument(
        "--ocr-engines",
        type=str,
        default="tesseract,easyocr",
        help="OCR engines to use (comma-separated: tesseract,easyocr,paddleocr)",
    )
    parser.add_argument(
        "--no-preprocess",
        action="store_true",
        help="Disable image preprocessing",
    )

    # Translation options
    parser.add_argument(
        "--methods",
        type=str,
        default=None,
        help="Translation methods (comma-separated: claude,google,deepl,openai)",
    )
    parser.add_argument(
        "--ensemble",
        action="store_true",
        default=True,
        help="Enable ensemble translation (default: True)",
    )
    parser.add_argument(
        "--no-ensemble",
        action="store_true",
        help="Disable ensemble — use single best method",
    )
    parser.add_argument(
        "--force-multi",
        action="store_true",
        help="Always run all 4 methods, even if first result is confident",
    )
    parser.add_argument(
        "--quality-threshold",
        type=str,
        choices=["strict", "moderate", "relaxed", "always"],
        default="moderate",
        help="When to trigger multi-method translation (default: moderate)",
    )

    # Model options
    parser.add_argument(
        "--claude-model",
        type=str,
        default="claude-sonnet-4-6",
        help="Claude model for translation",
    )
    parser.add_argument(
        "--openai-model",
        type=str,
        default="gpt-4o",
        help="OpenAI model for translation",
    )

    # API keys (alternative to env vars)
    parser.add_argument("--anthropic-key", type=str, help="Anthropic API key")
    parser.add_argument("--google-key", type=str, help="Google Translate API key")
    parser.add_argument("--deepl-key", type=str, help="DeepL API key")
    parser.add_argument("--openai-key", type=str, help="OpenAI API key")

    # Misc
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--target-lang",
        type=str,
        default="en",
        help="Target language code (default: en)",
    )

    return parser.parse_args()


def parse_pages(pages_str: str) -> list[int]:
    """Parse page specification like '1,3,5-10' into a list of 0-indexed page numbers."""
    pages = []
    for part in pages_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start) - 1, int(end)))
        else:
            pages.append(int(part) - 1)
    return sorted(set(pages))


def main() -> int:
    args = parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # Build OCR config
    engine_map = {
        "tesseract": OCREngine.TESSERACT,
        "easyocr": OCREngine.EASYOCR,
        "paddleocr": OCREngine.PADDLEOCR,
    }
    ocr_engines = [
        engine_map[e.strip()]
        for e in args.ocr_engines.split(",")
        if e.strip() in engine_map
    ]

    ocr_config = OCRConfig(
        engines=ocr_engines,
        dpi=args.dpi,
        enable_preprocessing=not args.no_preprocess,
        deskew=not args.no_preprocess,
        denoise=not args.no_preprocess,
        binarize=not args.no_preprocess,
        contrast_enhance=not args.no_preprocess,
    )

    # Build translation config
    method_map = {
        "claude": TranslationMethod.CLAUDE,
        "google": TranslationMethod.GOOGLE,
        "deepl": TranslationMethod.DEEPL,
        "openai": TranslationMethod.OPENAI,
    }

    if args.methods:
        methods = [
            method_map[m.strip()]
            for m in args.methods.split(",")
            if m.strip() in method_map
        ]
    else:
        methods = list(TranslationMethod)

    threshold_map = {
        "strict": QualityThreshold.STRICT,
        "moderate": QualityThreshold.MODERATE,
        "relaxed": QualityThreshold.RELAXED,
        "always": QualityThreshold.ALWAYS,
    }

    config = TranslationConfig(
        anthropic_api_key=args.anthropic_key,
        google_api_key=args.google_key,
        deepl_api_key=args.deepl_key,
        openai_api_key=args.openai_key,
        target_lang=args.target_lang,
        methods=methods,
        quality_threshold=threshold_map[args.quality_threshold],
        enable_ensemble=not args.no_ensemble,
        force_multi_method=args.force_multi,
        claude_model=args.claude_model,
        openai_model=args.openai_model,
        ocr=ocr_config,
        save_intermediate=args.save_intermediate,
        output_dir=args.output_dir,
    )

    # Validate PDF exists
    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}", file=sys.stderr)
        return 1

    if not pdf_path.suffix.lower() == ".pdf":
        print(f"Warning: File does not have .pdf extension: {pdf_path}", file=sys.stderr)

    # Check that at least one API key is available
    available = config.get_available_methods()
    if not available:
        print(
            "Error: No translation API keys configured.\n"
            "Set at least one of these environment variables:\n"
            "  ANTHROPIC_API_KEY\n"
            "  GOOGLE_TRANSLATE_API_KEY\n"
            "  DEEPL_API_KEY\n"
            "  OPENAI_API_KEY\n"
            "\nOr pass keys via CLI: --anthropic-key, --google-key, etc.",
            file=sys.stderr,
        )
        return 1

    print(f"Arabic PDF Translator v1.0.0")
    print(f"PDF: {pdf_path}")
    print(f"Translation methods available: {[m.value for m in available]}")
    print(f"Ensemble: {'enabled' if config.enable_ensemble else 'disabled'}")
    print(f"Force multi-method: {config.force_multi_method}")
    print()

    # Parse pages
    pages = parse_pages(args.pages) if args.pages else None

    # Run translation
    try:
        translator = ArabicPDFTranslator(config)
        result = translator.translate_pdf(
            str(pdf_path),
            pages=pages,
            output_path=args.output,
        )
    except Exception as e:
        print(f"Error during translation: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

    # Output results
    if args.output:
        print(f"\nOutput saved to: {args.output}")
    else:
        # Print to stdout
        print("=" * 70)
        print("TRANSLATION RESULT")
        print("=" * 70)
        print(result.full_translation)
        print()

    # Print summary
    print("=" * 70)
    print("PROCESSING SUMMARY")
    print("=" * 70)
    summary = result.summary
    print(f"  Pages processed:      {summary.get('total_pages_processed', 0)}")
    print(f"  Pages with text:      {summary.get('pages_with_arabic_text', 0)}")
    print(f"  Avg OCR confidence:   {summary.get('average_ocr_confidence', 0):.1%}")
    print(f"  Methods used:         {summary.get('translation_methods_used', {})}")
    print(f"  Total chars:          {summary.get('total_characters_translated', 0)}")
    print(f"  Total time:           {summary.get('total_processing_time_seconds', 0):.1f}s")
    print(f"  Avg time/page:        {summary.get('average_time_per_page', 0):.1f}s")

    # Print per-page quality scores if ensemble was used
    for page in result.pages:
        if page.quality_scores:
            print(f"\n  Page {page.page_number + 1} quality scores:")
            for method, score in sorted(
                page.quality_scores.items(), key=lambda x: x[1], reverse=True
            ):
                marker = " ← BEST" if method == page.translation_method else ""
                print(f"    {method:12s}: {score:.3f}{marker}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
