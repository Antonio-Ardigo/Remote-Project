"""
Arabic-specific OCR post-processing.

Fixes common OCR errors in Arabic text:
- Character confusion (ب/ت/ث, ح/خ/ج, etc.)
- Broken ligatures
- Misplaced diacritics
- RTL ordering issues
- Stray characters and noise
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class ArabicPostProcessor:
    """
    Post-processes OCR output to fix Arabic-specific errors.

    Pipeline:
    1. Remove non-Arabic noise
    2. Fix common OCR character substitutions
    3. Repair broken ligatures and word boundaries
    4. Normalize whitespace and punctuation
    5. Reorder RTL/LTR mixed content
    """

    # Common OCR confusion pairs for Arabic characters
    CONFUSION_PAIRS = {
        # Isolated forms that get confused
        '\u06A9': '\u0643',  # keheh → kaf (Persian vs Arabic kaf)
        '\u06CC': '\u064A',  # Farsi yeh → Arabic yeh
        '\u0649': '\u064A',  # Alef maqsura sometimes confused with yeh
    }

    # Arabic punctuation that OCR often mangles
    PUNCTUATION_MAP = {
        ',': '،',   # Latin comma → Arabic comma (when surrounded by Arabic)
        ';': '؛',   # Latin semicolon → Arabic semicolon
        '?': '؟',   # Latin question mark → Arabic question mark
    }

    def __init__(self):
        # Regex patterns
        self._arabic_range = r'\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF'
        self._arabic_char = re.compile(f'[{self._arabic_range}]')
        self._non_arabic_noise = re.compile(
            f'[^{self._arabic_range}'
            r'\u0660-\u0669'   # Arabic-Indic digits
            r'0-9'             # Western digits
            r'\s\.\,\،\؛\؟\!\:\-\(\)\[\]\"\'\n]'
        )

    def process(self, text: str) -> str:
        """
        Run full Arabic post-processing pipeline on OCR text.

        Args:
            text: Raw OCR output text.

        Returns:
            Cleaned and corrected Arabic text.
        """
        if not text or not text.strip():
            return ""

        logger.info("Post-processing Arabic text (%d chars)", len(text))

        # 1. Remove non-Arabic noise characters
        text = self._remove_noise(text)

        # 2. Fix character substitutions
        text = self._fix_character_confusion(text)

        # 3. Fix broken words and ligatures
        text = self._fix_broken_words(text)

        # 4. Normalize whitespace
        text = self._normalize_whitespace(text)

        # 5. Fix punctuation in Arabic context
        text = self._fix_punctuation(text)

        # 6. Remove isolated single characters (likely noise)
        text = self._remove_isolated_chars(text)

        # 7. Fix line ordering for RTL
        text = self._fix_line_order(text)

        logger.info("Post-processing complete (%d chars)", len(text))
        return text.strip()

    def _remove_noise(self, text: str) -> str:
        """Remove characters that don't belong in Arabic text."""
        # Keep Arabic, digits, common punctuation, whitespace
        cleaned = self._non_arabic_noise.sub('', text)
        return cleaned

    def _fix_character_confusion(self, text: str) -> str:
        """Fix common OCR character confusion in Arabic."""
        for wrong, correct in self.CONFUSION_PAIRS.items():
            text = text.replace(wrong, correct)
        return text

    def _fix_broken_words(self, text: str) -> str:
        """
        Repair words broken by OCR (e.g., spaces inserted mid-word).

        Arabic words are connected — if a space appears between two
        characters that should be connected, remove it.
        """
        # Fix single-char fragments that should be part of adjacent words
        # Pattern: Arabic char, space, single Arabic char, space, Arabic char
        # This catches broken words like: ا ل ع ر ب ي ة → العربية
        text = re.compile(
            f'([{self._arabic_range}]) ([{self._arabic_range}]) ([{self._arabic_range}])'
        ).sub(r'\1\2\3', text)

        # Fix common "al-" prefix that gets separated: ال كتاب → الكتاب
        text = re.sub(r'(ال)\s+', r'\1', text)

        return text

    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace: collapse multiple spaces, fix line breaks."""
        # Collapse multiple spaces to single
        text = re.sub(r'[ \t]+', ' ', text)

        # Collapse multiple newlines to double (paragraph break)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Remove spaces at start/end of lines
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)

        return text

    def _fix_punctuation(self, text: str) -> str:
        """
        Convert Latin punctuation to Arabic equivalents when
        surrounded by Arabic text.
        """
        for latin, arabic in self.PUNCTUATION_MAP.items():
            # Only replace if surrounded by Arabic characters
            pattern = f'([{self._arabic_range}])\\{latin}([{self._arabic_range}\\s])'
            text = re.sub(pattern, f'\\1{arabic}\\2', text)
        return text

    def _remove_isolated_chars(self, text: str) -> str:
        """Remove isolated single characters that are likely OCR noise."""
        # Don't remove و (waw = "and") as it's a valid single-char word
        valid_single_chars = {'و', 'أ', 'إ', 'ا', 'ب', 'ف', 'ل', 'ك'}

        words = text.split()
        filtered = []
        for word in words:
            # Keep word if it's longer than 1 char, or is a valid single-char word
            if len(word) > 1 or word in valid_single_chars or not self._arabic_char.search(word):
                filtered.append(word)

        return ' '.join(filtered)

    def _fix_line_order(self, text: str) -> str:
        """
        Ensure consistent line ordering.

        Some OCR engines may reverse line order or mix RTL/LTR segments.
        This function ensures each line's internal order is correct.
        """
        lines = text.split('\n')
        fixed_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                fixed_lines.append('')
                continue

            # Check if line is predominantly Arabic
            arabic_chars = len(self._arabic_char.findall(line))
            total_alpha = sum(1 for c in line if c.isalpha())

            if total_alpha > 0 and arabic_chars / total_alpha > 0.5:
                # Line is predominantly Arabic — ensure RTL markers
                # Add RTL embedding if not present
                if not line.startswith('\u200F') and not line.startswith('\u202B'):
                    line = '\u200F' + line
            fixed_lines.append(line)

        return '\n'.join(fixed_lines)

    def merge_ocr_results(self, results: list[str]) -> str:
        """
        Merge text from multiple OCR engines into a consensus result.

        Uses line-by-line comparison to pick the best version of each line
        across engines.
        """
        if not results:
            return ""
        if len(results) == 1:
            return results[0]

        # Split all results into lines
        all_lines = [r.split('\n') for r in results]
        max_lines = max(len(lines) for lines in all_lines)

        merged = []
        for i in range(max_lines):
            candidates = []
            for lines in all_lines:
                if i < len(lines) and lines[i].strip():
                    candidates.append(lines[i].strip())

            if not candidates:
                continue

            # Pick the longest non-empty candidate (usually most complete)
            best = max(candidates, key=len)
            merged.append(best)

        return '\n'.join(merged)
