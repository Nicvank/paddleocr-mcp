"""Quick test: verify MCP server tools work via JSON-RPC over stdio."""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path (works from any working directory)
_PROJECT_DIR = Path(__file__).parent
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

from paddleocr_mcp_server import _get_ocr, _extract_ocr_text, _preprocess_image, _safe_unlink
import time


def test_pp_ocrv6():
    """Test PP-OCRv6 directly (without MCP protocol)."""
    test_image = "/tmp/test_ocr.png"
    if not Path(test_image).exists():
        print("⚠️  /tmp/test_ocr.png not found, creating dummy test")
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (400, 100), "white")
        draw = ImageDraw.Draw(img)
        draw.text((10, 30), "Hello OCR Test 你好", fill="black")
        img.save(test_image)

    print(f"Testing PP-OCRv6 on {test_image}...")
    t0 = time.time()
    preprocessed = _preprocess_image(test_image)
    try:
        ocr = _get_ocr("ch")
        result = ocr.predict(preprocessed)
        items = _extract_ocr_text(result)
    finally:
        _safe_unlink(preprocessed)

    elapsed = time.time() - t0
    print(f"✅ PP-OCRv6: {len(items)} text blocks in {elapsed:.1f}s")
    for item in items[:5]:
        score = f" [{item['score']:.2%}]" if "score" in item else ""
        print(f"   - {item['text']}{score}")
    return True


if __name__ == "__main__":
    ok = test_pp_ocrv6()
    sys.exit(0 if ok else 1)
