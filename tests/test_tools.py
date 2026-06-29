"""Comprehensive tests for paddleocr_mcp_server."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from paddleocr_mcp_server import (
    _detect_device,
    _should_use_vl,
    _tool_ocr,
    _tool_parse,
    _tool_smart,
    MAX_FILE_SIZE,
)

TEST_IMAGE = "/tmp/test_ocr.png"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously (no pytest-asyncio needed)."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests — OCR basic
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not os.path.isfile(TEST_IMAGE), reason=f"{TEST_IMAGE} not found")
def test_ocr_image_basic():
    """Call _tool_ocr with a real image and verify text blocks are returned."""
    result = _run(_tool_ocr({"image_path": TEST_IMAGE, "language": "ch"}))
    assert len(result) == 1, "Expected exactly one TextContent result"
    text = result[0].text
    assert "OCR Result" in text, "Result header should mention 'OCR Result'"
    # The result should contain at least some extracted text blocks
    assert "text blocks" in text, "Result should report text block count"


# ---------------------------------------------------------------------------
# Tests — Error handling
# ---------------------------------------------------------------------------

def test_ocr_image_missing_file():
    """_tool_ocr should raise FileNotFoundError for a nonexistent path."""
    with pytest.raises(FileNotFoundError):
        _run(_tool_ocr({"image_path": "/nonexistent/path/image.png"}))


def test_ocr_image_empty_path():
    """_tool_ocr should raise ValueError for an empty image_path."""
    with pytest.raises(ValueError, match="image_path is required"):
        _run(_tool_ocr({"image_path": ""}))


def test_parse_document_missing_file():
    """_tool_parse should raise FileNotFoundError for a nonexistent path."""
    with pytest.raises(FileNotFoundError):
        _run(_tool_parse({"image_path": "/nonexistent/path/doc.pdf"}))


# ---------------------------------------------------------------------------
# Tests — smart_ocr routing
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not os.path.isfile(TEST_IMAGE), reason=f"{TEST_IMAGE} not found")
def test_smart_ocr_routes_to_ocr():
    """smart_ocr with force_model='ocr' should use PP-OCRv6."""
    result = _run(
        _tool_smart({
            "image_path": TEST_IMAGE,
            "force_model": "ocr",
        })
    )
    text = result[0].text
    assert "PP-OCRv6" in text, "Result should indicate PP-OCRv6 was used"
    assert "Auto-routed to PP-OCRv6" in text, "Should show routing info"


# ---------------------------------------------------------------------------
# Tests — Routing logic (_should_use_vl)
# ---------------------------------------------------------------------------

def test_should_use_vl_pdf():
    """PDF files should always route to VL."""
    with patch("paddleocr_mcp_server.Path.is_file", return_value=True):
        assert _should_use_vl("report.pdf") is True
    assert _should_use_vl("document.PDF") is True


def test_should_use_vl_large_image():
    """Very large images (>2000px on any side) should route to VL."""
    # Create a temporary large image
    from PIL import Image

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name
    try:
        img = Image.new("RGB", (3000, 1000), "white")
        img.save(tmp_path)
        assert _should_use_vl(tmp_path) is True
    finally:
        os.unlink(tmp_path)


def test_should_use_vl_small_image():
    """Small images should NOT route to VL (default is OCR)."""
    from PIL import Image

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name
    try:
        img = Image.new("RGB", (400, 300), "white")
        img.save(tmp_path)
        assert _should_use_vl(tmp_path) is False
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Tests — Device detection
# ---------------------------------------------------------------------------

def test_detect_device():
    """_detect_device should return either 'gpu' or 'cpu'."""
    device = _detect_device()
    assert isinstance(device, str), "Device must be a string"
    assert device in ("gpu", "cpu"), f"Device must be 'gpu' or 'cpu', got '{device}'"


# ---------------------------------------------------------------------------
# Tests — File size limit
# ---------------------------------------------------------------------------

def test_file_size_limit():
    """Files over 50 MB should be rejected by _tool_ocr."""
    # Create a sparse temp file that appears > 50 MB to the OS
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name
    try:
        # Use os.truncate to create a sparse file (appears 60 MB, minimal disk usage)
        os.truncate(tmp_path, 60 * 1024 * 1024)
        with pytest.raises(ValueError, match="File too large"):
            _run(_tool_ocr({"image_path": tmp_path}))
    finally:
        os.unlink(tmp_path)
