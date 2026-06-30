---
name: paddleocr-mcp
description: "Local OCR service via MCP — PP-OCRv6 (fast text extraction) + VL-1.6 (document structure parsing). Use when needing to extract text from images, parse document layouts, OCR PDFs, or process screenshots."
version: 1.0.0
category: media
tags: [ocr, paddleocr, document-parsing, image-text, mcp, agent-skill]
triggers:
  - "提取文字"
  - "OCR"
  - "图片文字"
  - "文档解析"
  - "PDF 解析"
  - "截图识别"
  - "表格提取"
---

# PaddleOCR MCP Skill

> 给 Agent 用的 PaddleOCR MCP Server 使用指南。

## 前置条件

- MCP Server 已安装并配置（见 [README 安装步骤](../README.md)）
- 你的 Agent/MCP 客户端已添加 `paddleocr` 服务器配置

## 可用 Tools

### `mcp_paddleocr_ocr_image` — 快速文字提取

PP-OCRv6 模型，**速度最快**，适合简单文字场景。

```
参数:
  image_path: string (必填) — 图片文件路径
  language: string (可选) — 语言代码，默认 "ch"

返回: 文本块列表 + 置信度分数
```

**适用场景：**
- 截图、照片、手机拍的文档
- 发票、收据、名片
- 简单布局的文档
- 实时 OCR 需求

**速度：** CPU ~12-18s | GPU ~1-2s

### `mcp_paddleocr_parse_document` — 文档结构解析

VL-1.6 视觉语言模型，**理解文档结构**，返回 Markdown。

```
参数:
  image_path: string (必填) — 图片或 PDF 文件路径

返回: 结构化 Markdown 文档
```

**适用场景：**
- 复杂布局文档（多栏、图文混排）
- 表格数据提取
- PDF 整书解析
- 需要保留文档结构的场景

**速度：** CPU 30-120s | GPU ~5-15s

### `mcp_paddleocr_smart_ocr` — 自动路由

根据输入自动选择最佳模型，**无需手动判断**。

```
参数:
  image_path: string (必填) — 文件路径
  language: string (可选) — 语言代码
  force_model: string (可选) — "ocr" 或 "vl" 强制指定

路由规则:
  PDF 文件          → VL-1.6
  图片 > 2000px     → VL-1.6
  其他              → PP-OCRv6
```

## Agent 使用决策树

```
用户要求处理图片/PDF/文档
  │
  ├─ 用户明确指定模型？
  │   ├─ 是 → 用 smart_ocr + force_model
  │   └─ 否 ↓
  │
  ├─ 文件是 PDF？
  │   └─ 是 → parse_document（VL-1.6）
  │
  ├─ 简单截图/照片/发票？
  │   └─ 是 → ocr_image（PP-OCRv6，快）
  │
  ├─ 复杂布局/表格/多栏？
  │   └─ 是 → parse_document（VL-1.6，准）
  │
  └─ 不确定？
      └─ smart_ocr（自动路由）
```

## 语言选择

| 语言 | language 参数 |
|------|--------------|
| 中文 + 英文（默认） | `ch` |
| 纯英文 | `en` |
| 日文 | `japan` |
| 韩文 | `korean` |
| 法文 | `fr` |
| 德文 | `german` |

## 输出格式

### OCR 输出示例

```
OCR Result (143 text blocks, 17.7s, PP-OCRv6)
Source: /path/to/image.png

- 助力双方交往 [100.00%]
- 搭建友谊桥梁 [99.96%]
- 本报记者 沈小晓 [92.98%]
```

每行包含：
- 识别到的文字
- 置信度分数（百分比）

### 文档解析输出示例

返回 Markdown 格式，保留：
- 标题层级
- 段落结构
- 表格格式
- 图片描述

## 性能提示

> ⚡ 以下速度为 **CPU 硬算**基准。GPU 可提升 10-25 倍。

| 场景 | 建议 |
|------|------|
| 批量处理多张图 | 逐张调用，模型有缓存加速 |
| 首次调用慢 | 正常，模型加载需 5-10s |
| VL-1.6 超时 | 检查图片大小，大图会更慢 |
| 内存不足 | 减少并发，VL-1.6 需 ~4GB RAM |
| 需要更快 | 安装 GPU 版 PaddlePaddle，自动检测 |

**硬件参考：**

| 配置 | PP-OCRv6 速度 (OneDNN) | PP-OCRv6 速度 (OneDNN 关闭) | VL-1.6 速度 |
|------|----------------------|---------------------------|------------|
| CPU（Xeon E5-2698B v3） | ~12-18s | ~20-30s | 30-120s |
| GPU（GTX 1060 / P106 6GB） | ~1-2s | ~1-2s | ~5-15s |

> ⚠️ 部分 CPU 需要禁用 OneDNN（`enable_mkldnn=False`）以避免兼容性问题，此时 PP-OCRv6 速度约慢 50%。服务器已内置自动处理。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PADDLEOCR_DEVICE` | 自动检测 | 强制设备：`cpu` 或 `gpu` |
| `PADDLEOCR_VL_TIMEOUT` | `300` | VL-1.6 超时时间（秒） |

## 错误处理

| 错误 | 原因 | 解决 |
|------|------|------|
| `FileNotFoundError` | 文件路径错误 | 检查路径是否正确 |
| `ValueError: empty image_path` | 未传路径 | 确保 image_path 不为空 |
| `ValueError: exceeds 50MB` | 文件过大 | 压缩图片或裁剪 |
| `asyncio.TimeoutError` | VL-1.6 超时 | 增加 PADDLEOCR_VL_TIMEOUT |
| `(no text detected)` | 图片无文字 | 检查图片质量/内容 |
| `NotImplementedError: ConvertPirAttribute` | OneDNN/PIR 不兼容 | 服务器已自动处理，如仍报错设置 `FLAGS_use_mkldnn=0` |

## 示例对话

### 场景 1：用户发了一张截图

```
用户：帮我看看这张截图上写了什么
Agent：使用 mcp_paddleocr_ocr_image 提取文字（简单截图 → PP-OCRv6）
```

### 场景 2：用户发了一个 PDF

```
用户：解析这个合同 PDF
Agent：使用 mcp_paddleocr_parse_document（PDF → VL-1.6）
```

### 场景 3：用户不确定

```
用户：帮我处理这个文件
Agent：使用 mcp_paddleocr_smart_ocr（自动路由）
```

### 场景 4：用户要提取表格

```
用户：把这张表格转成文本
Agent：使用 mcp_paddleocr_parse_document（表格 → VL-1.6）
```
