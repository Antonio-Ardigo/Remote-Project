"""
Image preprocessing pipeline optimized for Arabic OCR.

Applies a sequence of transformations to maximize OCR accuracy
on Arabic script, which has unique challenges:
- Connected cursive letters
- Diacritical marks (dots, tashkeel) that are easily lost
- Right-to-left text direction
- Varying font styles (Naskh, Nastaliq, Ruq'ah)
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from PIL import Image, ImageEnhance, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class ImagePreprocessor:
    """
    Multi-stage image preprocessing for Arabic document OCR.

    Pipeline stages:
    1. Grayscale conversion
    2. Noise reduction (non-local means denoising)
    3. Contrast enhancement (CLAHE)
    4. Deskewing (Hough transform based)
    5. Adaptive binarization (Sauvola/Otsu)
    6. Morphological cleanup (preserve diacritics)
    7. Border removal and page crop
    """

    def __init__(
        self,
        deskew: bool = True,
        denoise: bool = True,
        binarize: bool = True,
        contrast_enhance: bool = True,
        target_dpi: int = 300,
    ):
        self.deskew = deskew
        self.denoise = denoise
        self.binarize = binarize
        self.contrast_enhance = contrast_enhance
        self.target_dpi = target_dpi

        if not CV2_AVAILABLE and not PIL_AVAILABLE:
            raise ImportError(
                "Either opencv-python or Pillow is required for image preprocessing. "
                "Install with: pip install opencv-python-headless Pillow"
            )

    def process(self, image: np.ndarray) -> np.ndarray:
        """
        Run the full preprocessing pipeline on an image.

        Args:
            image: Input image as numpy array (BGR or grayscale).

        Returns:
            Preprocessed image optimized for Arabic OCR.
        """
        if not CV2_AVAILABLE:
            return self._process_pil(image)

        logger.info("Starting image preprocessing pipeline")
        img = image.copy()

        # 1. Convert to grayscale
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        logger.debug("Converted to grayscale: %s", gray.shape)

        # 2. Upscale if resolution is too low
        gray = self._upscale_if_needed(gray)

        # 3. Denoise — preserve fine Arabic diacritical marks
        if self.denoise:
            gray = self._denoise(gray)

        # 4. Contrast enhancement via CLAHE
        if self.contrast_enhance:
            gray = self._enhance_contrast(gray)

        # 5. Deskew
        if self.deskew:
            gray = self._deskew(gray)

        # 6. Binarize
        if self.binarize:
            gray = self._binarize(gray)

        # 7. Morphological cleanup — careful to preserve Arabic dots
        gray = self._morphological_cleanup(gray)

        logger.info("Preprocessing complete: output shape %s", gray.shape)
        return gray

    def _upscale_if_needed(self, img: np.ndarray, min_height: int = 2000) -> np.ndarray:
        """Upscale image if it's too small for reliable OCR."""
        h, w = img.shape[:2]
        if h < min_height:
            scale = min_height / h
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
            logger.debug("Upscaled image from %dx%d to %dx%d", w, h, new_w, new_h)
        return img

    def _denoise(self, img: np.ndarray) -> np.ndarray:
        """
        Apply non-local means denoising with parameters tuned for Arabic script.

        Lower h value (filter strength) to preserve thin strokes and dots.
        """
        # h=8 is gentler than default 10, preserving Arabic diacritics
        denoised = cv2.fastNlMeansDenoising(
            img,
            h=8,
            templateWindowSize=7,
            searchWindowSize=21,
        )
        logger.debug("Applied non-local means denoising (h=8)")
        return denoised

    def _enhance_contrast(self, img: np.ndarray) -> np.ndarray:
        """
        Apply CLAHE (Contrast Limited Adaptive Histogram Equalization).

        Improves contrast in locally dark/light regions common in scanned docs.
        """
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(img)
        logger.debug("Applied CLAHE contrast enhancement")
        return enhanced

    def _deskew(self, img: np.ndarray) -> np.ndarray:
        """
        Detect and correct skew using Hough line transform.

        Critical for Arabic since even slight skew disrupts line detection
        and character segmentation.
        """
        # Detect edges
        edges = cv2.Canny(img, 50, 150, apertureSize=3)

        # Detect lines
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=100,
            minLineLength=img.shape[1] // 4,
            maxLineGap=20,
        )

        if lines is None:
            logger.debug("No lines detected for deskewing, skipping")
            return img

        # Calculate median angle
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            if abs(angle) < 45:  # Only consider near-horizontal lines
                angles.append(angle)

        if not angles:
            return img

        median_angle = np.median(angles)

        if abs(median_angle) < 0.5:
            logger.debug("Skew angle %.2f° is negligible, skipping", median_angle)
            return img

        logger.debug("Correcting skew angle: %.2f°", median_angle)

        # Rotate
        h, w = img.shape[:2]
        center = (w // 2, h // 2)
        rotation_matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
        rotated = cv2.warpAffine(
            img,
            rotation_matrix,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
        return rotated

    def _binarize(self, img: np.ndarray) -> np.ndarray:
        """
        Adaptive thresholding optimized for Arabic documents.

        Uses Gaussian adaptive thresholding with a large block size
        to handle uneven illumination from scanning.
        """
        # Gaussian adaptive threshold — works well for Arabic fonts
        binary = cv2.adaptiveThreshold(
            img,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=31,  # Large block for uneven lighting
            C=10,
        )
        logger.debug("Applied adaptive Gaussian binarization")
        return binary

    def _morphological_cleanup(self, img: np.ndarray) -> np.ndarray:
        """
        Light morphological operations to clean noise without destroying
        Arabic diacritical dots (nuqat) and tashkeel marks.

        Uses a very small kernel to only remove isolated noise pixels.
        """
        # Very small kernel — 2x2 to avoid destroying Arabic dots
        kernel = np.ones((2, 2), np.uint8)

        # Opening removes small noise
        cleaned = cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel, iterations=1)

        # Gentle closing to reconnect broken strokes
        kernel_close = np.ones((2, 2), np.uint8)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel_close, iterations=1)

        logger.debug("Applied morphological cleanup (2x2 kernel)")
        return cleaned

    def _process_pil(self, image: np.ndarray) -> np.ndarray:
        """Fallback preprocessing using Pillow when OpenCV is not available."""
        img = Image.fromarray(image)

        # Convert to grayscale
        img = img.convert("L")

        # Enhance contrast
        if self.contrast_enhance:
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.8)

        # Sharpen
        img = img.filter(ImageFilter.SHARPEN)

        # Denoise with median filter
        if self.denoise:
            img = img.filter(ImageFilter.MedianFilter(size=3))

        return np.array(img)

    def process_pdf_page(
        self,
        pdf_path: str,
        page_num: int,
        dpi: int = 300,
    ) -> np.ndarray:
        """
        Render a PDF page to image and preprocess it.

        Args:
            pdf_path: Path to the PDF file.
            page_num: Page number (0-indexed).
            dpi: Rendering DPI.

        Returns:
            Preprocessed image as numpy array.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError(
                "PyMuPDF is required for PDF rendering. "
                "Install with: pip install PyMuPDF"
            )

        doc = fitz.open(pdf_path)
        if page_num >= len(doc):
            raise ValueError(f"Page {page_num} out of range (document has {len(doc)} pages)")

        page = doc[page_num]
        # Render at high DPI for better OCR
        zoom = dpi / 72  # 72 is default PDF DPI
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix)

        # Convert to numpy array
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )

        # Convert RGBA to BGR if needed
        if pix.n == 4:
            if CV2_AVAILABLE:
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
            else:
                img = img[:, :, :3]
        elif pix.n == 3 and CV2_AVAILABLE:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        doc.close()

        return self.process(img)
