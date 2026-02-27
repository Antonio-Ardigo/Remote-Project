"""
Generate a synthetic 'imperfectly scanned' Arabic PDF for testing the OCR pipeline.

Creates a 3-page PDF with real Arabic newspaper-style text, rendered as images
with scan artifacts: noise, slight skew, uneven lighting, and compression artifacts.
"""

import random
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import fitz  # PyMuPDF

# --- Arabic text content (real Arabic newspaper-style text) ---
ARABIC_PAGES = [
    # Page 1: News article about technology
    """بسم الله الرحمن الرحيم

الذكاء الاصطناعي يغير مستقبل التعليم في العالم العربي

في تطور لافت يشهده قطاع التعليم في المنطقة العربية، بدأت عدة دول
عربية في تبني تقنيات الذكاء الاصطناعي لتحسين جودة التعليم وتوفير
فرص تعليمية متكافئة لجميع الطلاب. وقد أعلنت وزارة التربية والتعليم
عن خطة شاملة لإدماج هذه التقنيات في المناهج الدراسية بحلول العام
المقبل.

وأكد وزير التعليم في تصريحات صحفية أن المملكة العربية السعودية
تسعى لتكون رائدة في مجال التعليم الرقمي، مشيراً إلى أن الاستثمارات
في هذا القطاع تجاوزت خمسة مليارات ريال خلال السنوات الثلاث الماضية.
""",
    # Page 2: Economics article
    """الاقتصاد العربي والتحولات الكبرى

تشهد الأسواق العربية تحولات اقتصادية كبرى مع تزايد الاهتمام
بالتنويع الاقتصادي وتقليل الاعتماد على النفط كمصدر رئيسي للدخل.
وقد حققت عدة دول خليجية نجاحات ملموسة في جذب الاستثمارات الأجنبية
وتطوير قطاعات السياحة والتكنولوجيا والخدمات المالية.

أظهرت البيانات الصادرة عن صندوق النقد العربي أن معدل النمو
الاقتصادي في المنطقة العربية بلغ ثلاثة بالمائة خلال الربع الأخير
من العام الماضي، متجاوزاً التوقعات التي كانت تشير إلى نمو بنسبة
اثنين ونصف بالمائة فقط.

وتوقع خبراء اقتصاديون أن يستمر هذا الاتجاه الإيجابي خلال العام
الحالي مع تحسن أسعار النفط وزيادة الإنفاق الحكومي على مشاريع
البنية التحتية والتحول الرقمي.
""",
    # Page 3: Culture and heritage
    """التراث العربي الإسلامي وأهميته في العصر الحديث

يُعدّ التراث العربي الإسلامي من أغنى التراثات الثقافية في العالم
ويشمل إسهامات عظيمة في مجالات العلوم والأدب والفنون والعمارة.
وقد أسهم العلماء العرب والمسلمون في تأسيس العديد من العلوم
الحديثة كالجبر والكيمياء والطب والفلك.

إن الحفاظ على هذا التراث الغني ليس مجرد واجب ثقافي بل هو
ضرورة حضارية تسهم في تعزيز الهوية العربية وربط الأجيال الحالية
بتاريخها العريق. وتبذل المؤسسات الثقافية جهوداً كبيرة لرقمنة
المخطوطات القديمة وإتاحتها للباحثين والمهتمين حول العالم.

كما تعمل عدة جامعات عربية على إنشاء مراكز متخصصة لدراسة
التراث الإسلامي وتحقيق المخطوطات ونشرها بأحدث الأساليب العلمية.
""",
]


def render_arabic_text_to_image(text: str, width=2480, height=3508, dpi=300) -> np.ndarray:
    """Render Arabic text onto an A4-sized image (simulating a printed page)."""
    # Create white background
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)

    # Load an Arabic-supporting font
    font_path = "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"
    try:
        font = ImageFont.truetype(font_path, 42)
        title_font = ImageFont.truetype(font_path, 56)
    except IOError:
        font = ImageFont.load_default()
        title_font = font

    # Margins
    margin_left = 200
    margin_right = 200
    margin_top = 250
    line_spacing = 70
    max_width = width - margin_left - margin_right

    y = margin_top
    lines = text.strip().split("\n")

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            y += line_spacing // 2
            continue

        # Use title font for first non-empty content line (after bismillah)
        use_font = title_font if i <= 2 and len(line) < 60 else font

        # Simple right-aligned text (Arabic is RTL)
        # PIL doesn't handle bidi well, but for OCR testing this is sufficient
        draw.text((margin_left, y), line, fill=0, font=use_font, anchor="lt")
        y += line_spacing

        if y > height - 200:
            break

    return np.array(img)


def add_scan_artifacts(image: np.ndarray, severity="medium") -> np.ndarray:
    """Add realistic scan imperfections to an image."""
    img = image.copy().astype(np.float32)
    h, w = img.shape[:2]

    # 1. Add Gaussian noise (simulating scanner sensor noise)
    noise_level = {"light": 8, "medium": 15, "heavy": 25}[severity]
    noise = np.random.normal(0, noise_level, img.shape)
    img = img + noise

    # 2. Uneven lighting / vignette (scanner lid not fully closed)
    y_coords, x_coords = np.mgrid[0:h, 0:w]
    cx, cy = w // 2 + random.randint(-100, 100), h // 2 + random.randint(-100, 100)
    dist = np.sqrt((x_coords - cx) ** 2 + (y_coords - cy) ** 2)
    max_dist = np.sqrt(cx**2 + cy**2)
    vignette = 1.0 - 0.15 * (dist / max_dist)
    img = img * vignette

    # 3. Random dark spots (dust / smudges)
    for _ in range(random.randint(5, 20)):
        sx = random.randint(0, w - 1)
        sy = random.randint(0, h - 1)
        radius = random.randint(2, 8)
        y_r, x_r = np.ogrid[-radius:radius+1, -radius:radius+1]
        mask = x_r**2 + y_r**2 <= radius**2
        y_start = max(0, sy - radius)
        y_end = min(h, sy + radius + 1)
        x_start = max(0, sx - radius)
        x_end = min(w, sx + radius + 1)
        m_y_start = radius - (sy - y_start)
        m_y_end = radius + (y_end - sy)
        m_x_start = radius - (sx - x_start)
        m_x_end = radius + (x_end - sx)
        region_mask = mask[m_y_start:m_y_end, m_x_start:m_x_end]
        img[y_start:y_end, x_start:x_end][region_mask] -= random.randint(20, 60)

    # 4. Slight background discoloration (aged paper)
    bg_tint = np.random.uniform(0.92, 1.0, (h, w)).astype(np.float32)
    bg_tint = Image.fromarray((bg_tint * 255).astype(np.uint8))
    bg_tint = bg_tint.filter(ImageFilter.GaussianBlur(radius=50))
    bg_tint = np.array(bg_tint).astype(np.float32) / 255.0
    # Only affect light areas (background)
    light_mask = img > 200
    img[light_mask] = img[light_mask] * bg_tint.flatten()[np.where(light_mask.flatten())][:light_mask.sum()]

    # 5. Clip and convert
    img = np.clip(img, 0, 255).astype(np.uint8)

    # 6. Slight rotation (scanner skew)
    pil_img = Image.fromarray(img)
    angle = random.uniform(-1.5, 1.5)
    pil_img = pil_img.rotate(angle, resample=Image.BICUBIC, fillcolor=240, expand=False)

    # 7. Slight blur (focus issues)
    if severity in ("medium", "heavy"):
        pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=0.8))

    return np.array(pil_img)


def create_scanned_pdf(output_path: str):
    """Create a multi-page 'scanned' Arabic PDF."""
    doc = fitz.open()

    for i, text in enumerate(ARABIC_PAGES):
        print(f"  Generating page {i + 1}...")
        # Render text to image
        page_img = render_arabic_text_to_image(text)

        # Add scan artifacts with varying severity
        severities = ["light", "medium", "heavy"]
        degraded = add_scan_artifacts(page_img, severity=severities[i % 3])

        # Convert to PIL and save as temporary PNG for embedding
        pil_img = Image.fromarray(degraded)

        # Create a PDF page and insert the image
        page = doc.new_page(width=595, height=842)  # A4 in points

        # Save image to bytes
        from io import BytesIO
        buf = BytesIO()
        # Save as JPEG with moderate quality (more scan-like)
        pil_img_rgb = pil_img.convert("RGB")
        pil_img_rgb.save(buf, format="JPEG", quality=75)
        buf.seek(0)

        # Insert the image to fill the page
        rect = fitz.Rect(0, 0, 595, 842)
        page.insert_image(rect, stream=buf.read())

    doc.save(output_path)
    doc.close()
    print(f"  Saved: {output_path}")


if __name__ == "__main__":
    output = "/home/user/Remote-Project/test_arabic_scan.pdf"
    print("Creating imperfectly-scanned Arabic PDF...")
    create_scanned_pdf(output)
    print("Done!")
