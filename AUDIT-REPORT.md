# PaddleOCR MCP Server — 全面审查报告

> 审查日期：2026-06-29
> 审查范围：paddleocr-mcp-server 全部代码
> 审查方法：15 维度 + 6 轴 + Skills 辅助

---

## 一、审查总览

| 维度 | 状态 | 发现 |
|------|------|------|
| 安全 | ✅ 通过 | 无恶意代码、无硬编码密钥、无数据外传 |
| 输入验证 | ✅ 通过 | 三个 tool 都有 path 验证 |
| 错误处理 | ✅ 通过 | try/finally + 清理，无裸 except |
| 线程安全 | ⚠️ 需关注 | 共享状态无锁（MCP stdio 单线程可接受） |
| 资源清理 | ✅ 通过 | 临时文件有 finally 清理 |
| GPU 适配 | ❌ 缺失 | 无 GPU 检测、无自动切换 |
| 测试覆盖 | ⚠️ 不足 | 仅覆盖 PP-OCRv6 和 MCP 协议 |
| 开源就绪 | ⚠️ 不足 | 缺 .gitignore、LICENSE |

---

## 二、问题清单（按严重性排序）

### CRITICAL — 阻塞发布

**无 CRITICAL 问题。**

### HIGH — 必须修复

#### H1: 无 GPU 检测和自动切换

**现状**：代码硬编码使用 CPU，无法检测/使用 GPU。
**影响**：用户买了 P106 后需要手动改代码。
**修复方案**：

```python
def _detect_device() -> str:
    """自动检测可用设备：CUDA > CPU"""
    try:
        import paddle
        if paddle.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0:
            return "gpu"
    except Exception:
        pass
    return "cpu"

DEVICE = _detect_device()
```

PaddleOCR 和 PaddleOCRVL 都支持 `device` 参数，传 `"gpu"` 即可。

#### H2: 无 .gitignore

**现状**：`__pycache__/`、`*.pyc`、`.env` 等未被忽略。
**修复**：创建 `.gitignore`。

#### H3: 无 LICENSE

**现状**：开源项目必须有许可证。
**修复**：添加 MIT LICENSE。

### MEDIUM — 建议修复

#### M1: 共享状态无线程锁

**现状**：`_ocr_cache` 和 `_vl_model` 是模块级可变 dict/None，无锁保护。
**影响**：MCP stdio 模式是单线程的，当前无问题。但如果未来支持 HTTP 传输，会有竞态。
**修复**：添加 `asyncio.Lock`，防御性编程。

#### M2: 日志用 print(stderr) 而非 logging 模块

**现状**：7 处 `print(..., file=sys.stderr)`。
**影响**：无法控制日志级别、无法对接日志系统。
**修复**：改用 `logging` 模块。

#### M3: 无内部超时机制

**现状**：VL-1.6 可能运行 120+ 秒，无超时控制。
**影响**：MCP 层有 300s 超时，但模型内部卡死时无法中断。
**修复**：添加 `asyncio.wait_for` 包装。

#### M4: 测试覆盖不足

**现状**：仅测试 PP-OCRv6 和 MCP 协议握手。
**未覆盖**：VL-1.6、smart_ocr、路由逻辑、错误处理、边界条件。
**修复**：补充测试用例。

#### M5: 无文件大小限制

**现状**：`MAX_IMAGE_SIZE=1920` 只限制缩放，不限制输入文件大小。
**影响**：攻击者可发送超大图片导致 OOM。
**修复**：添加文件大小检查（如 50MB 限制）。

#### M6: 无路径穿越防护

**现状**：`image_path` 直接传给 `Image.open()`，仅检查 `is_file()`。
**影响**：MCP 调用方可传任意路径（如 `/etc/passwd`）。
**评估**：MCP 协议由调用方控制路径，属于设计范围。但如果要限制访问目录，可添加沙箱。

### LOW — 可选优化

#### L1: pyproject.toml 依赖版本过松

**现状**：`paddleocr>=2.7.0`，但实际需要 `>=3.7.0`（PP-OCRv6）。
**修复**：更新版本约束。

#### L2: README 缺少 GPU 说明

**现状**：README 未提及 GPU 支持情况。
**修复**：添加 GPU/CPU 说明和配置方法。

#### L3: 无 graceful shutdown

**现状**：无 SIGTERM/SIGINT 处理。
**影响**：MCP stdio 模式下进程随父进程退出，影响不大。

---

## 三、与原 GitHub 项目对比

| 特性 | 方案 A (608行) | 方案 C (206行) | 本项目 (425行) |
|------|:-:|:-:|:-:|
| VL-1.6 支持 | ❌ | ❌ | ✅ |
| 自动路由 | ❌ | ❌ | ✅ |
| GPU 自动检测 | ❌ | ❌ | ❌ → 待实现 |
| 置信度分数 | ❌ | ❌ | ✅ |
| 图片预处理 | ✅ | ❌ | ✅ |
| BBox 坐标转换 | ✅ | ❌ | ❌（不需要） |
| 结果直接返回 | ❌ 写文件 | ❌ 写文件 | ✅ 返回文本 |
| 错误处理 | ✅ | ⚠️ stderr丢失 | ✅ |

---

## 四、GPU 适配方案

### 现状分析

当前 PaddlePaddle 3.2.1 是 CPU 版本（`is_compiled_with_cuda() = False`）。
GPU 版需要单独安装 `paddlepaddle-gpu`。

### 推荐方案：运行时检测 + 自动切换

```python
def _detect_device() -> str:
    """自动检测最佳设备"""
    try:
        import paddle
        if paddle.is_compiled_with_cuda():
            gpu_count = paddle.device.cuda.device_count()
            if gpu_count > 0:
                # 检查显存是否够用
                free_mem = paddle.device.cuda.memory_allocated()  # 需要更精确的检测
                return "gpu"
    except Exception:
        pass
    return "cpu"

# 使用
ocr = PaddleOCR(lang="ch", device=DEVICE)
vl = PaddleOCRVL(device=DEVICE)
```

### 关键点

1. **PaddleOCR 和 PaddleOCRVL 都原生支持 `device` 参数**，传 `"gpu"` 即可
2. **自动检测**：`paddle.is_compiled_with_cuda()` + `device_count() > 0`
3. **优雅降级**：检测失败 → 回退 CPU
4. **环境变量覆盖**：`PADDLEOCR_DEVICE=cpu` 可强制指定

### 为什么不做"同时支持 CPU 和 GPU 版本"

- PaddlePaddle 的 CPU 版和 GPU 版是**不同的包**，不能同时安装
- 同一个环境只能有一种
- 运行时检测 `is_compiled_with_cuda()` 就够了

---

## 五、修复优先级

| 优先级 | 问题 | 工作量 |
|--------|------|--------|
| P0 | H1: GPU 检测 + 自动切换 | 30min |
| P0 | H2: .gitignore | 5min |
| P0 | H3: LICENSE | 5min |
| P1 | M1: 线程锁 | 15min |
| P1 | M2: logging 模块 | 15min |
| P1 | M4: 测试补充 | 1h |
| P2 | M3: 内部超时 | 15min |
| P2 | M5: 文件大小限制 | 10min |
| P2 | L1: 依赖版本约束 | 5min |
| P2 | L2: README 更新 | 15min |

---

## 六、结论

**代码质量**：✅ 良好，安全审计通过，架构清晰
**功能完整性**：⚠️ 缺 GPU 适配（用户核心需求）
**开源就绪度**：⚠️ 缺 .gitignore、LICENSE、完整测试
**与原项目差异**：本项目在 VL-1.6 支持和自动路由上优于原项目

**建议**：先修复 P0 问题（GPU 检测 + 开源文件），再处理 P1。
