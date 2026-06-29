# PaddleOCR MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PaddleOCR: Apache 2.0](https://img.shields.io/badge/PaddleOCR-Apache%202.0-blue.svg)](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE)
[![Python 3.10-3.12](https://img.shields.io/badge/python-3.10--3.12-blue.svg)](https://www.python.org/downloads/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io)

本地运行的 PaddleOCR MCP Server，支持双模型 + 自动路由 + GPU 自动检测。

---

## ⚡ 一键安装（复制给你的 Agent）

> 把下面这段话直接发给任何 AI Agent，它会自动完成安装配置。

```
请帮我安装 paddleocr-mcp（https://github.com/Nicvank/paddleocr-mcp），
这是一个本地 OCR MCP 服务，支持 PP-OCRv6（快速文字提取）和 VL-1.6（文档结构解析），
自动路由，自动检测 GPU/CPU。

安装步骤：
1. git clone https://github.com/Nicvank/paddleocr-mcp.git ~/paddleocr-mcp
   （如果 clone 失败，试试 ghproxy 镜像：git clone https://ghproxy.net/https://github.com/Nicvank/paddleocr-mcp.git ~/paddleocr-mcp）
2. 检查 Python 版本（需要 3.10-3.12，不支持 3.13+），如果不是则先安装 Python 3.12
3. cd ~/paddleocr-mcp && python -m venv .venv && .venv/bin/pip install -e .
   （首次安装需下载 ~300MB 依赖，请耐心等待）
4. 把 MCP 服务器配置添加到我的 Agent 客户端：
   command: ~/paddleocr-mcp/.venv/bin/python（必须用 venv 的 python，不要用系统 python）
   args: ["~/paddleocr-mcp/paddleocr_mcp_server.py"]
   timeout: 600（VL-1.6 在 CPU 上较慢，首次还需下载 ~300MB 模型）
5. 读一下 ~/paddleocr-mcp/skill/SKILL.md，按你平台的方式加载它
6. 重启后告诉用户："请发一张图片给我，我来测试 OCR 是否正常工作"

如果任何步骤失败，报告错误并修复。完成后告诉我结果。
```

---

| 特性 | 说明 |
|------|------|
| **双模型** | PP-OCRv6（快速）+ VL-1.6（文档结构化） |
| **自动路由** | 根据输入自动选择最佳模型 |
| **GPU 自动检测** | 检测 CUDA 可用性，自动切换 CPU/GPU |
| **MCP 协议** | 标准 Model Context Protocol，兼容所有 MCP 客户端 |
| **Hermes 集成** | 一行配置即可接入 Hermes Agent |

## 模型对比

> ⚡ 以下速度为 **CPU 硬算**基准（Xeon E5-2698B v3）。使用 GPU（如 NVIDIA P106/GTX 1060）可提升 **10-25 倍**。

| 模型 | 用途 | 速度 (CPU) | 速度 (GPU 预估) | 最佳场景 |
|------|------|-----------|----------------|---------|
| **PP-OCRv6** | 快速文字提取 | ~12-18s | ~1-2s | 截图、照片、发票、收据 |
| **VL-1.6** | 文档结构解析 | 30-120s | ~5-15s | 复杂布局、表格、多栏文档、PDF |

**硬件推荐：**
- **纯 CPU**：任何 x86_64 处理器即可运行，适合低频使用
- **GPU 加速**：NVIDIA CUDA 显卡（GTX 1060 / P106 6GB 及以上），显存 ≥ 6GB，适合高频或实时场景

> ⚠️ **首次使用 VL-1.6 时**会自动从 ModelScope 下载模型文件（~300MB），需额外等待 1-5 分钟。模型缓存在 `~/.paddlex/official_models/`，后续调用无需重复下载。

## 安装

### 前置条件

- Python 3.10 ~ 3.12（不支持 3.13+）
- PaddlePaddle 3.2+（CPU 或 GPU 版）
- PaddleOCR 3.7+

### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/Nicvank/paddleocr-mcp.git
cd paddleocr-mcp

# 2. 创建虚拟环境并安装依赖
python -m venv .venv
.venv/bin/pip install -e .

# ⚠️ 首次安装需下载 ~300MB 依赖（paddlepaddle 195MB + opencv 69MB），
#    网络慢请耐心等待，或使用 uv 加速：uv pip install -e .

# 🇨🇳 中国大陆用户如 git clone 失败，可尝试镜像：
# git clone https://ghproxy.net/https://github.com/Nicvank/paddleocr-mcp.git
```

### GPU 支持（可选）

```bash
# 安装 GPU 版 PaddlePaddle
pip install paddlepaddle-gpu==3.2.1

# 验证 GPU 可用
python -c "import paddle; print(paddle.is_compiled_with_cuda())"
```

## 使用

### 直接运行

```bash
python paddleocr_mcp_server.py
```

### Hermes Agent 集成

#### Gateway 模式（systemd 守护进程）

在 **全局配置** `~/.hermes/config.yaml` 添加：

```yaml
mcp_servers:
  paddleocr:
    command: /path/to/paddleocr-mcp/.venv/bin/python
    args: [/path/to/paddleocr-mcp/paddleocr_mcp_server.py]
    timeout: 600
    connect_timeout: 120
```

> ⚠️ Gateway 模式下 MCP 配置读自 `$HERMES_HOME/config.yaml`（即 `~/.hermes/config.yaml`），不是 profile 级别的。

#### CLI 模式

在 `~/.hermes/profiles/<your-profile>/config.yaml` 添加（同上配置）。

重启 Hermes 后自动可用。

### 其他 MCP 客户端

任何支持 MCP stdio 传输的客户端都可以连接：

```json
// Claude Desktop (claude_desktop_config.json)
{
  "mcpServers": {
    "paddleocr": {
      "command": "python",
      "args": ["/path/to/paddleocr_mcp_server.py"]
    }
  }
}
```

## 🤖 Agent Skill

本项目附带一个 **Agent Skill**（[skill/SKILL.md](skill/SKILL.md)），让 AI Agent 知道何时、如何调用 OCR 工具。

### 什么是 Agent Skill？

Skill 是一份结构化文档，告诉 Agent：
- **什么时候** 该调用 OCR（触发条件）
- **用哪个 tool**（ocr_image vs parse_document vs smart_ocr）
- **怎么用**（参数、返回值、错误处理）
- **决策树**（根据场景自动选择最佳模型）

### 安装到 Hermes

```bash
# Gateway 模式：复制到全局 skills 目录
cp -r skill/ ~/.hermes/skills/paddleocr-mcp/

# CLI 模式：复制到 profile 的 skills 目录
cp -r skill/ ~/.hermes/profiles/<your-profile>/skills/media/paddleocr-mcp/

# 或者创建符号链接（推荐，方便更新）
ln -s /path/to/paddleocr-mcp/skill ~/.hermes/skills/paddleocr-mcp
```

安装后 Agent 在以下情况会自动加载此 Skill：
- 用户发送图片并要求提取文字
- 用户要求解析 PDF 或文档
- 任何涉及 OCR 的任务

### Skill 触发条件

Agent 会在以下关键词出现时加载 Skill：

```
提取文字、OCR、图片文字、文档解析、PDF 解析、
截图识别、表格提取、识别图片、读取图片
```

### 不用 Skill 直接用

即使不安装 Skill，只要 MCP Server 已配置，Agent 也能直接调用工具：

```
用户：帮我看看这张截图写了什么
Agent：调用 mcp_paddleocr_ocr_image（自动选择）
```

Skill 的作用是让 Agent **更聪明地选择**和**更好地处理结果**。

## MCP Tools

### `ocr_image` — 快速 OCR

PP-OCRv6 模型，适合简单文字提取。

```json
{
  "image_path": "/path/to/image.png",
  "language": "ch"
}
```

**参数：**
- `image_path`（必填）：图片文件路径
- `language`（可选）：语言代码，默认 `"ch"`（中英文）

**支持语言：** `ch`（中英）、`en`、`japan`、`korean`、`fr`、`german` 等

### `parse_document` — 文档解析

VL-1.6 视觉语言模型，适合复杂文档结构化。

```json
{
  "image_path": "/path/to/document.pdf"
}
```

**返回：** Markdown 格式的文档结构

### `smart_ocr` — 自动路由

根据输入自动选择最佳模型。

```json
{
  "image_path": "/path/to/file",
  "language": "ch",
  "force_model": "ocr"
}
```

**路由规则：**
- PDF 文件 → VL-1.6
- 图片 > 2000px → VL-1.6
- 其他 → PP-OCRv6
- `force_model`：`"ocr"` 或 `"vl"` 强制指定

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PADDLEOCR_DEVICE` | `auto` | 强制设备：`cpu` 或 `gpu` |
| `PADDLEOCR_VL_TIMEOUT` | `300` | VL-1.6 超时时间（秒） |

## 测试

```bash
# 安装测试依赖
pip install pytest

# 运行测试
python -m pytest tests/ -v

# 快速功能测试
python test_quick.py

# MCP 协议测试
python test_mcp.py
```

## 项目结构

```
paddleocr-mcp/
├── paddleocr_mcp_server.py    # MCP Server 主程序
├── pyproject.toml             # 项目配置
├── skill/
│   └── SKILL.md               # Agent Skill 文档
├── tests/
│   └── test_tools.py          # 单元测试
├── test_quick.py              # 快速功能测试
├── test_mcp.py                # MCP 协议测试
├── LICENSE                    # MIT 许可证
├── .gitignore
└── README.md
```

## 许可证

本项目使用 [MIT 许可证](LICENSE)。

**依赖项许可证：**
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) — Apache License 2.0
- [PaddleOCR-VL-1.6 模型](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6) — Apache License 2.0
- [PaddlePaddle](https://github.com/PaddlePaddle/PaddlePaddle) — Apache License 2.0
- [MCP SDK](https://github.com/modelcontextprotocol/python-sdk) — MIT License

Apache 2.0 是宽松许可证，与 MIT 完全兼容。使用本项目无需额外许可证义务。

## 致谢

- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) — 百度飞桨 OCR 工具套件
- [Model Context Protocol](https://modelcontextprotocol.io) — MCP 协议标准
- [trotsky1997/PaddleOCR-MCP](https://github.com/trotsky1997/PaddleOCR-MCP) — 原始 MCP 实现参考
