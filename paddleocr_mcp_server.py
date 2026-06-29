"""PaddleOCR MCP Server — PP-OCRv6 (fast) + VL-1.6 (document parsing) with auto-routing."""

import asyncio
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("paddleocr-mcp")

try:
    from mcp.server import NotificationOptions, Server
    from mcp.server.models import InitializationOptions
    import mcp.server.stdio
    import mcp.types as types
except ImportError:
    logger.error("mcp package not installed. Run: pip install mcp")
    sys.exit(1)

try:
    from paddleocr import PaddleOCR
except ImportError:
    logger.error("paddleocr not installed. Run: pip install paddleocr>=3.7.0")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    logger.error("pillow not installed. Run: pip install pillow")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Server & model singletons
# ---------------------------------------------------------------------------

server = Server("paddleocr-mcp")

# Lazy-loaded model caches
_ocr_cache: dict[str, PaddleOCR] = {}
_vl_model = None

# Locks for shared state (M1)
_ocr_lock = asyncio.Lock()
_vl_lock = asyncio.Lock()

# Image preprocessing
MAX_IMAGE_SIZE = 1920
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB (M5)
VL_TIMEOUT = float(os.environ.get("PADDLEOCR_VL_TIMEOUT", "300"))  # M3


def _detect_device() -> str:  # H1
    """Auto-detect available GPU, fallback to CPU. Override with PADDLEOCR_DEVICE env var."""
    env_device = os.environ.get("PADDLEOCR_DEVICE", "").strip().lower()
    if env_device in ("gpu", "cpu"):
        return env_device
    try:
        import paddle
        if paddle.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0:
            logger.info("GPU detected — using CUDA device")
            return "gpu"
    except Exception as exc:
        logger.debug("GPU detection failed: %s", exc)
    return "cpu"


DEVICE = _detect_device()


# ---------------------------------------------------------------------------
# Model loaders
# ---------------------------------------------------------------------------

async def _get_ocr(lang: str = "ch") -> PaddleOCR:
    """Get or create PP-OCRv6 instance (cached per language)."""
    key = lang.lower().strip() or "ch"
    async with _ocr_lock:
        if key not in _ocr_cache:
            logger.info("Loading PP-OCRv6 (lang=%s, device=%s)...", key, DEVICE)
            _ocr_cache[key] = await asyncio.to_thread(
                PaddleOCR,
                lang=key,
                use_textline_orientation=False,
                text_recognition_batch_size=1,
                device=DEVICE,
            )
            logger.info("PP-OCRv6 ready (lang=%s).", key)
    return _ocr_cache[key]


async def _get_vl():
    """Get or create VL-1.6 instance (singleton)."""
    global _vl_model
    async with _vl_lock:
        if _vl_model is None:
            from paddleocr._pipelines.paddleocr_vl import PaddleOCRVL
            logger.info("Loading VL-1.6 (device=%s, this may take a while)...", DEVICE)
            _vl_model = await asyncio.to_thread(
                PaddleOCRVL,
                use_layout_detection=True,
                use_chart_recognition=True,
                device=DEVICE,
                engine="paddle_dynamic",  # VL-1.6 only supports this engine (CPU/GPU universal)
            )
            logger.info("VL-1.6 ready.")
    return _vl_model


# ---------------------------------------------------------------------------
# Image preprocessing (from original PaddleOCR-MCP, cleaned up)
# ---------------------------------------------------------------------------

def _preprocess_image(image_path: str) -> str:
    """Downsample large images + sharpen. Returns path to temp file."""
    from PIL import ImageEnhance, ImageFilter

    img = Image.open(image_path)

    # Convert to RGB
    if img.mode != "RGB":
        if img.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                bg.paste(img, mask=img.split()[3])
            else:
                rgb = img.convert("RGB")
                alpha = img.split()[1]
                bg.paste(rgb, mask=alpha)
            img = bg
        elif img.mode == "P":
            if "transparency" in img.info:
                img = img.convert("RGBA")
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            else:
                img = img.convert("RGB")
        else:
            img = img.convert("RGB")

    # Downsample
    w, h = img.size
    if max(w, h) > MAX_IMAGE_SIZE:
        scale = MAX_IMAGE_SIZE / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

    # Sharpen
    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
    img = ImageEnhance.Sharpness(img).enhance(1.2)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg", prefix="ocr_")
    img.save(tmp.name, "JPEG", quality=95, optimize=True)
    return tmp.name


def _safe_unlink(path: str):
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# OCR result extraction
# ---------------------------------------------------------------------------

def _extract_ocr_text(result: list) -> list[dict]:
    """Extract text + bbox from PP-OCRv6 result list."""
    items = []
    for page in result:
        data = page.json.get("res", {})
        texts = data.get("rec_texts", [])
        scores = data.get("rec_scores", [])
        polys = data.get("rec_polys", [])
        boxes = data.get("rec_boxes", [])

        for i, text in enumerate(texts):
            if not text or not text.strip():
                continue
            entry: dict[str, Any] = {"text": text.strip()}
            if i < len(scores):
                entry["score"] = round(float(scores[i]), 4)
            # Prefer rec_boxes (rect) over rec_polys (polygon)
            if i < len(boxes):
                b = boxes[i]
                if hasattr(b, "tolist"):
                    b = b.tolist()
                if isinstance(b, (list, tuple)) and len(b) >= 4:
                    entry["bbox"] = [int(x) for x in b[:4]]
            elif i < len(polys):
                p = polys[i]
                if hasattr(p, "tolist"):
                    p = p.tolist()
                coords = []
                for pt in p[:4]:
                    if hasattr(pt, "tolist"):
                        pt = pt.tolist()
                    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                        coords.append([int(pt[0]), int(pt[1])])
                if len(coords) == 4:
                    entry["bbox"] = coords
            items.append(entry)
    return items


def _extract_vl_result(result) -> str:
    """Extract markdown from VL-1.6 result."""
    pages = []
    for page in result:
        # VL result has markdown output
        data = page.json if hasattr(page, "json") else {}
        md = data.get("res", {}).get("markdown", "")
        if md:
            pages.append(md)
    return "\n\n---\n\n".join(pages) if pages else "(no content extracted)"


# ---------------------------------------------------------------------------
# Routing logic
# ---------------------------------------------------------------------------

def _should_use_vl(image_path: str, force_vl: bool = False, force_ocr: bool = False) -> bool:
    """Decide whether to use VL-1.6 or PP-OCRv6."""
    if force_vl:
        return True
    if force_ocr:
        return False

    lower = image_path.lower()

    # PDF → always VL
    if lower.endswith(".pdf"):
        return True

    # Check image dimensions — large/multi-page documents benefit from VL
    try:
        with Image.open(image_path) as img:
            w, h = img.size
            # Very large images (likely documents) → VL
            if w > 2000 or h > 2000:
                return True
    except Exception:
        pass

    return False


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="ocr_image",
            description=(
                "Fast OCR on an image using PP-OCRv6. Best for: screenshots, photos, "
                "invoices, receipts, simple documents. Returns extracted text with confidence scores."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "Path to the image file (png/jpg/bmp/webp)",
                    },
                    "language": {
                        "type": "string",
                        "description": "Language: 'ch' (Chinese+English, default), 'en', 'japan', 'korean', etc.",
                        "default": "ch",
                    },
                },
                "required": ["image_path"],
            },
        ),
        types.Tool(
            name="parse_document",
            description=(
                "Deep document parsing using VL-1.6 vision-language model. Best for: "
                "complex layouts, tables, multi-column documents, PDFs. Returns structured Markdown. "
                "Slower than ocr_image (30-120s) but understands document structure."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "Path to the image or PDF file",
                    },
                },
                "required": ["image_path"],
            },
        ),
        types.Tool(
            name="smart_ocr",
            description=(
                "Auto-routing OCR: automatically picks the best model based on input. "
                "Simple images → PP-OCRv6 (fast). Complex documents/PDFs → VL-1.6 (accurate). "
                "You can override with force_model parameter."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "Path to the image or PDF file",
                    },
                    "language": {
                        "type": "string",
                        "description": "Language for OCR mode (default: 'ch')",
                        "default": "ch",
                    },
                    "force_model": {
                        "type": "string",
                        "description": "Force a specific model: 'ocr' (PP-OCRv6) or 'vl' (VL-1.6). Omit for auto-routing.",
                        "enum": ["ocr", "vl"],
                    },
                },
                "required": ["image_path"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: Optional[dict[str, Any]]) -> list[types.TextContent]:
    if name == "ocr_image":
        return await _tool_ocr(arguments)
    elif name == "parse_document":
        return await _tool_parse(arguments)
    elif name == "smart_ocr":
        return await _tool_smart(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def _tool_ocr(args: dict) -> list[types.TextContent]:
    """PP-OCRv6 fast OCR."""
    image_path = args.get("image_path", "")
    language = args.get("language", "ch")

    if not image_path:
        raise ValueError("image_path is required")
    if not Path(image_path).is_file():
        raise FileNotFoundError(f"File not found: {image_path}")
    if Path(image_path).stat().st_size > MAX_FILE_SIZE:
        raise ValueError(f"File too large ({Path(image_path).stat().st_size / 1024 / 1024:.1f} MB). Max: 50 MB")

    t0 = time.time()
    preprocessed = None
    try:
        preprocessed = await asyncio.to_thread(_preprocess_image, image_path)
        ocr = await _get_ocr(language)
        result = await asyncio.to_thread(ocr.predict, preprocessed)
        items = _extract_ocr_text(result)
    finally:
        _safe_unlink(preprocessed)

    elapsed = time.time() - t0

    # Format output
    if not items:
        text = f"(no text detected in {Path(image_path).name})"
    else:
        lines = []
        for item in items:
            score_str = f" [{item['score']:.2%}]" if "score" in item else ""
            lines.append(f"- {item['text']}{score_str}")
        text = "\n".join(lines)

    header = f"OCR Result ({len(items)} text blocks, {elapsed:.1f}s, PP-OCRv6)\nSource: {image_path}\n\n"
    return [types.TextContent(type="text", text=header + text)]


async def _tool_parse(args: dict) -> list[types.TextContent]:
    """VL-1.6 document parsing."""
    image_path = args.get("image_path", "")
    if not image_path:
        raise ValueError("image_path is required")
    if not Path(image_path).is_file():
        raise FileNotFoundError(f"File not found: {image_path}")
    if Path(image_path).stat().st_size > MAX_FILE_SIZE:
        raise ValueError(f"File too large ({Path(image_path).stat().st_size / 1024 / 1024:.1f} MB). Max: 50 MB")

    t0 = time.time()
    try:
        vl = await _get_vl()
        result = await asyncio.wait_for(
            asyncio.to_thread(vl.predict, image_path),
            timeout=VL_TIMEOUT,
        )
        md = _extract_vl_result(result)
    except asyncio.TimeoutError:
        return [types.TextContent(type="text", text=f"VL-1.6 timed out after {VL_TIMEOUT}s for: {image_path}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error parsing document: {e}")]

    elapsed = time.time() - t0
    header = f"Document Parse Result ({elapsed:.1f}s, VL-1.6)\nSource: {image_path}\n\n"
    return [types.TextContent(type="text", text=header + md)]


async def _tool_smart(args: dict) -> list[types.TextContent]:
    """Auto-routing OCR."""
    image_path = args.get("image_path", "")
    language = args.get("language", "ch")
    force = args.get("force_model", "")

    if not image_path:
        raise ValueError("image_path is required")
    if not Path(image_path).is_file():
        raise FileNotFoundError(f"File not found: {image_path}")
    if Path(image_path).stat().st_size > MAX_FILE_SIZE:
        raise ValueError(f"File too large ({Path(image_path).stat().st_size / 1024 / 1024:.1f} MB). Max: 50 MB")

    use_vl = _should_use_vl(
        image_path,
        force_vl=(force == "vl"),
        force_ocr=(force == "ocr"),
    )

    model_name = "VL-1.6" if use_vl else "PP-OCRv6"

    if use_vl:
        result = await _tool_parse({"image_path": image_path})
    else:
        result = await _tool_ocr({"image_path": image_path, "language": language})

    # Prepend routing info
    original = result[0].text
    routed = f"[Auto-routed to {model_name}]\n{original}"
    return [types.TextContent(type="text", text=routed)]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="paddleocr-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main():
    # Startup status — goes to stderr so MCP clients can see it
    sys.stderr.write(f"[paddleocr-mcp] Starting v1.0.0...\n")
    sys.stderr.write(f"[paddleocr-mcp] Device: {DEVICE}\n")
    sys.stderr.write(f"[paddleocr-mcp] Tools: ocr_image, parse_document, smart_ocr\n")
    sys.stderr.write(f"[paddleocr-mcp] Ready.\n")
    sys.stderr.flush()
    asyncio.run(_main())


if __name__ == "__main__":
    main()
