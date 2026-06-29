"""Test MCP server via JSON-RPC over stdin/stdout."""

import subprocess
import json
import sys
import time
from pathlib import Path

# Auto-detect Python and server path (works from any working directory)
PYTHON = sys.executable
SERVER = str(Path(__file__).parent / "paddleocr_mcp_server.py")


def send_msg(proc, msg):
    """Send a JSON-RPC message to the MCP server."""
    data = json.dumps(msg)
    proc.stdin.write(data + "\n")
    proc.stdin.flush()


def read_msg(proc, timeout=30):
    """Read a JSON-RPC response from the MCP server."""
    import select
    start = time.time()
    while time.time() - start < timeout:
        if proc.stdout in select.select([proc.stdout], [], [], 0.5)[0]:
            line = proc.stdout.readline()
            if line.strip():
                try:
                    return json.loads(line.strip())
                except json.JSONDecodeError:
                    pass
    return None


def test_mcp_protocol():
    print("Starting MCP server process...")
    proc = subprocess.Popen(
        [PYTHON, SERVER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )

    try:
        # 1. Initialize
        print("1. Sending initialize...")
        send_msg(proc, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            }
        })
        resp = read_msg(proc)
        if resp:
            print(f"   ✅ Initialize response: {resp.get('result', {}).get('serverInfo', {})}")
        else:
            print("   ❌ No response")
            return False

        # 2. List tools
        print("2. Listing tools...")
        send_msg(proc, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        })
        resp = read_msg(proc)
        if resp and "result" in resp:
            tools = resp["result"].get("tools", [])
            print(f"   ✅ Found {len(tools)} tools:")
            for t in tools:
                print(f"      - {t['name']}: {t['description'][:60]}...")
        else:
            print(f"   ❌ Unexpected: {resp}")
            return False

        # 3. Call ocr_image
        print("3. Calling ocr_image...")
        send_msg(proc, {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "ocr_image",
                "arguments": {
                    "image_path": "/tmp/test_ocr.png",
                    "language": "ch"
                }
            }
        })
        resp = read_msg(proc, timeout=60)
        if resp and "result" in resp:
            content = resp["result"].get("content", [])
            if content:
                text = content[0].get("text", "")
                print(f"   ✅ OCR result ({len(text)} chars):")
                print(f"      {text[:300]}...")
            else:
                print(f"   ❌ Empty content: {resp}")
                return False
        else:
            print(f"   ❌ Unexpected: {resp}")
            return False

        print("\n🎉 All MCP protocol tests passed!")
        return True

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    ok = test_mcp_protocol()
    sys.exit(0 if ok else 1)
