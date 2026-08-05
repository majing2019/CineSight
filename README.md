# 🎬 CineSight — AI 剪辑的第一步：让 AI 读懂画面

> **v1.0** | 给纯文本大模型装上"眼睛"的本地视觉分析 Skill
>
> 面向**视频剪辑自动化**的本地视觉理解方案：把图片 / 视频变成**可直接执行的剪辑决策 JSON**（构图、光影、主体、分镜、转场、B-roll 候选、色彩匹配），同时输出一份人读的 Markdown 报告。
>
> 基于微软开源的 **Mage-VL-4B** 多模态模型（Apache-2.0），100% 本地推理，素材不出本机。

**CineSight = 影视之眼。** 这是完整 AI 剪辑流水线的**第一阶段**：让 AI 能看懂素材。
后续版本将在此基础上继续演进（见 [路线图](#路线图)）。

---

## 目录

- [这是什么](#这是什么)
- [效果展示（真实输出）](#效果展示真实输出)
- [它能做什么](#它能做什么)
- [工作原理](#工作原理)
- [为什么选 Mage-VL-4B](#为什么选-mage-vl-4b)
- [快速开始（一键部署）](#快速开始一键部署)
- [详细部署指南](#详细部署指南)
- [使用指南](#使用指南)
- [输出格式（JSON Schema）](#输出格式json-schema)
- [性能参考](#性能参考)
- [常见问题 FAQ](#常见问题-faq)
- [与剪辑工作流集成](#与剪辑工作流集成)
- [路线图](#路线图)
- [项目结构](#项目结构)
- [作者与联系方式](#作者与联系方式)
- [致谢（使用的开源项目）](#致谢使用的开源项目)
- [License](#license)

> **版本**：v1.0（2026-08）· **平台**：macOS（Apple Silicon）
> **开发/实测设备**：Mac mini M2 Pro · **目前仅支持 Mac**
>
> **版本说明**：v1.0 聚焦「让 AI 读懂视频和文件」——语义分析 + 帧级切点 + 批量盘点，
> 输出机器可消费的决策 JSON，为后续自动化剪辑打地基。

---

## 这是什么

DeepSeek 等纯文本大模型**没有视觉能力**，看不到图片和视频。本项目是一个 **Claude/opencode Skill**：
当用户要求"看看这张图""分析这段视频的构图光影"时，skill 自动调用本地部署的 **Mage-VL-4B** 多模态模型，
把画面转成**结构化 JSON + 可读报告**，喂回给主模型做决策。

设计目标：**为 AI 剪辑而生**。输出的每个字段都是一条剪辑脚本可以直接执行的决策，
不是泛泛的画面描述。

典型场景：

- 📷 摄影素材筛选：这张图构图/光影怎么样，适不适合做封面
- 🎬 视频分镜分析：每个镜头的景别/运镜/转场建议
- 🗂️ 批量素材盘点：一整个文件夹的素材 → 总览清单
- ✂️ 剪辑自动化：帧级精确切点 + 转场决策 + B-roll 候选 + 色彩匹配度

---

## 效果展示（真实输出）

`examples/` 目录包含完整示例。以下为真实运行输出摘录。

### 示例 1：无人机风景照片（大疆，新疆雪山）

输入 `DJI_20250621185315_0450_D.png`（1024×2048），输出摘要：

```
**总结**：A wide shot of a mountainous landscape with green rolling hills and a snow-capped peak in the background.

构图：大远景 / 眼平机位 / 主体贴合三分线（雪峰 x=0.45, y=0.25）
光影：正面光（太阳）/ 柔和 / 中性色温 / 中等反差 / 情绪宁静
剪辑建议：向右慢摇以展开更多景观
```

### 示例 2：短视频分镜 + 精确切点（雪中跳舞，69 秒）

Mage-VL 语义分析输出（节选）：

```
## 分镜
| 时间 | 景别 | 运镜 | 能量 | 冷暖 | 主体 | 出点转场 |
|---|---|---|---|---|---|---|
| 0.0-5.0s | 大远景 | 静止 | low | cool | 两人铲雪+房屋 | 黑场 (切特写) |
| 5.0-10.0s | 特写 | 静止 | medium | warm | 手部工作 | 硬切 (结束) |

序列决策：节奏 slow · 建议镜头 3.0s · 色彩走向 cool to warm
剪辑建议：加铲雪声效 + 房屋室内环境声
```

`scene_cut.py` 场景检测补充**帧级精确切点**（HSV 直方图 + 边缘差异双指标，置信度 0.997-1.0）：

```
[0.00s fade_in] → [2.55s cut] → [5.00s cut] → [59.73s cut] → [64.88s cut] → [67.08s cut] → [69.12s fade_out]
```

### 示例 3：西藏旅行素材批量分析（48 段 4K 素材）

`batch.py` 一键分析整个素材文件夹，生成 `分析总览.md`（素材索引 + 一句话总结 + 链接）：

```
| 文件 | 时长 | 总结 | 详细 |
|---|---|---|---|
| C0117.MP4 | video | A serene view of a turquoise lake surrounded by snow-capped mountains, with people swimming and wading in the water. | md |
| C0048.MP4 | video | A timelapse of a mountainous landscape with power lines and a tree, showing the sky changing from overcast to partly cloudy. | md |
...
```

完整输出见 [examples/](examples/)。

---

## 它能做什么

| 功能 | 说明 | 命令 |
|---|---|---|
| 单图分析（scene） | 构图/光影/主体/色调/剪辑建议 | `analyze.py --input 图片` |
| 视频分镜（video） | 分镜切分 + 每镜头转场/B-roll/色彩 + 序列节奏 | `analyze.py --input 视频 --task video` |
| 自由问答（describe） | 任意视觉问题 | `analyze.py --input X --task describe --question "..."` |
| 批量分析 | 一次加载模型扫描整个文件夹，产出总览 | `batch.py --dir 素材目录` |
| 精确切点 | 帧级场景检测，修正模型时间戳 | `scene_cut.py --input X --analysis X.analysis.json` |
| 断点续跑 | 跳过已分析文件 | `batch.py --skip-existing` |

## 使用方式：本地模型 + NAS 自动分析工作流

CineSight 的典型使用方式：

1. **依赖本地模型**：所有分析在本机（Mac mini M2 Pro）完成，素材不出本机，无需联网推理
2. **连接 NAS**：素材统一存放在 NAS 网络存储中（航拍、照片、旅行素材等）
3. **自动分析**：素材拷入 NAS 后，批量脚本自动分析每个视频/图片里有什么
4. **产出决策**：每段素材 → 结构化 JSON（构图/光影/转场/B-roll/色彩匹配）+ 分析总览清单

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   NAS 素材库   │ ──→ │   CineSight      │ ──→ │   剪辑决策 JSON    │
│ (视频/图片…)   │     │  本地 Mage-VL-4B  │     │  + 分析总览清单    │
└──────────────┘     └──────────────────┘     └──────────────────┘
   素材拷入即分析        Mac mini M2 Pro          供后续剪辑/调色 skill 消费
```

## 识别耗时（图片 / 视频）

> 实测设备：Mac mini M2 Pro（16GB 统一内存）。耗时含模型加载；冷启动 ~20-30s 只算一次。

| 识别内容 | 耗时 |
|---|---|
| 📷 单张图片（构图/光影/主体） | **约 1 分钟** |
| 🎬 短视频（30-70s 素材，8 帧分镜分析） | **1-4 分钟** |
| ✂️ 视频精确切点（帧级，69s 素材） | **约 15 秒** |
| 🗂️ 批量 48 段 4K 素材（语义 + 切点全流程） | **约 62 分钟** |

> 💡 耗时主要取决于生成 token 数（`--max-new-tokens`）和系统内存压力。
> 分析时关闭浏览器等大内存应用可提速 10 倍以上。

---

## 工作原理

```
┌─────────────────────────────────────────────────────────────┐
│  DeepSeek / opencode / 任意纯文本大模型（无视觉能力）          │
│       │                                                      │
│       │ 用户:"分析一下这个视频的构图光影"                      │
│       ▼                                                      │
│  CineSight Skill（SKILL.md 触发规则 + 工作流说明）          │
│       │                                                      │
│       ▼ 调用 scripts/analyze.py（模型只加载一次，批量复用）     │
│  ┌──────────────────────────────────────────────┐            │
│  │ 本地 Mage-VL-4B（Mage-ViT + Qwen3-4B，4B 参数）│            │
│  │ · 图片 → 384px 降采样（模型训练分辨率）        │            │
│  │ · 视频 → 均匀抽帧 + 192px 预缩放               │            │
│  │ · 提示词工程 → 强制输出固定 JSON Schema         │            │
│  └──────────────────────────────────────────────┘            │
│       │                                                      │
│       ├──→ xxx.analysis.json   （结构化决策，剪辑脚本可消费）   │
│       ├──→ xxx.analysis.md     （人读报告）                   │
│       └──→ scene_cut.py        （帧级精确切点，修正时间戳）     │
│              └──→ xxx.analysis.scenes.json                    │
└─────────────────────────────────────────────────────────────┘
```

**两个关键组件**：

1. **Mage-VL-4B 语义分析**（慢而准）：理解构图、光影、主体、转场、B-roll 等语义决策。
   优点：理解力强；缺点：时间戳是估计值。
2. **场景切点检测**（快而精）：opencv 直方图 + 边缘差异，帧级精度，50 分钟视频约 2 分钟内
   完成。优点：精确；缺点：不理解内容。

两者合并 = **语义（模型） + 精度（检测器）**，正好互补。

---

## 为什么选 Mage-VL-4B

做视频语义分析（构图/光影/分镜）时对比过两个开源方案：

| | **Mage-VL-4B**（微软，本方案） | LocateAnything-3B（英伟达） |
|---|---|---|
| 模型类型 | 通用多模态理解模型 | 视觉定位/检测模型 |
| 强项 | 视频理解、空间推理、场景描述 | 物体定位框（bounding box） |
| 能否给构图/光影分析 | ✅ 擅长 | ❌ 只会"框出物体在哪" |
| 视频理解 | ✅ 主打卖点（codec-native 流式） | ❌ 面向图像 |
| 许可证 | Apache-2.0 | 需核实 |

结论：**构图/光影/分镜分析必须用通用 VLM**，LocateAnything 定位能力无法替代。
Mage-VL-4B 在视频理解上甚至超过同规模的 Qwen3-VL-4B（官方报告：+22.5 QVHighlight、+11.0 VSI-Bench），
且 4B 参数在 Apple Silicon 上可跑。

---

## 快速开始（一键部署）

### 前置要求

> ⚠️ **目前仅支持 macOS（Apple Silicon）**。Linux/Windows 支持规划中（v1.x），
> 暂未验证，不保证可用。

| 项目 | 要求 |
|---|---|
| 系统 | **macOS 14+（Apple Silicon，M1/M2/M3/M4 均可）** |
| 开发设备 | Mac mini M2 Pro（本项目的开发与实测设备） |
| 内存 | **≥ 16GB**（模型 bf16 权重约 9.5GB；16GB 机器分析时请关闭浏览器等大内存应用） |
| 磁盘 | ≥ 15GB（模型约 10.8GB） |
| 网络 | 能访问 **ModelScope**（默认下载源，国内可达）或 HuggingFace（备用） |
| Python | 无需预装 ≥3.10；脚本用 uv 自动安装独立的 Python 3.12 |

### 给人类用户

```bash
git clone <你的仓库地址> CineSight
cd CineSight
bash scripts/setup.sh
# 等模型下载完（约 10.8GB），然后用 venv 里的 python 分析：
venv/bin/python scripts/analyze.py --input 你的图片.jpg
venv/bin/python scripts/analyze.py --input 你的视频.mp4 --task video
```

### 给 AI 助手（把你的 AI 指向本 README，它会按步骤执行）

> 你是部署助手。请严格按以下步骤执行，不要跳过：
>
> 1. 运行 `bash scripts/setup.sh`（幂等：会自动创建 Python 3.12 虚拟环境、安装 torch 等依赖、
>    从 ModelScope 下载约 10.8GB 模型权重到 `~/.cache/mage-vl/microsoft/Mage-VL`）。
>    脚本耗时较长（下载依赖 + 模型），耐心等待，不要中断。
> 2. 若 `setup.sh` 报网络错误，检查是否设置了代理，或重试（下载断点可续传）。
> 3. 验证：`venv/bin/python -c "from transformers import AutoProcessor; print('ok')"`
> 4. 测试单图：`venv/bin/python scripts/analyze.py --input 图片路径`。
>    首次运行含冷启动（约 20-60 秒），属正常。
> 5. 视频分镜：`venv/bin/python scripts/analyze.py --input 视频路径 --task video --num-frames 8`
> 6. 精确切点：`venv/bin/python scripts/scene_cut.py --input 视频路径 --analysis 视频路径.analysis.json`

### 30 秒验证安装是否成功

```bash
venv/bin/python -c "
import torch, transformers
print('torch', torch.__version__, '| mps:', torch.backends.mps.is_available())
print('transformers', transformers.__version__)
"
```

---

## 详细部署指南

### 0. 前置要求说明

- **系统**：**仅支持 macOS（Apple Silicon）**。本项目所有优化（MPS 加速、eager 注意力、
  内存管理）都是针对 Apple Silicon 实测调优的；Linux/Windows 暂未验证（规划中）。
  开发与实测设备：**Mac mini M2 Pro**。
- **Python**：需要 ≥ 3.10（torch 2.x / transformers 5.x 的要求）。`setup.sh` 会用
  [uv](https://docs.astral.sh/uv/) 自动安装独立的 Python 3.12，不依赖系统 Python 版本，
  macOS 无需 Homebrew。
- **ffmpeg**：可选。视频抽帧走 opencv 内置 FFmpeg，没有系统 ffmpeg 也能工作。

### 1. 安装 uv（如未安装）

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 运行一键部署脚本

```bash
bash scripts/setup.sh
```

脚本会依次完成（幂等，可重复执行）：

1. 创建 `venv/`（Python 3.12，uv 管理）
2. 安装 `torch` / `torchvision`（Apple Silicon 版本）
3. 安装其余依赖（`transformers`、`opencv-python` 等，见 `scripts/requirements-mac.txt`）——
   **刻意排除了 `flash-attn` 和 `mamba-ssm`**（CUDA-only，macOS 无法编译）
4. 从 **ModelScope** 下载模型权重 `microsoft/Mage-VL`（约 10.8GB，含主权重 9.5GB +
   流式 gate 权重 1GB）到 `~/.cache/mage-vl/microsoft/Mage-VL`
5. 冒烟测试依赖导入

### 3. 网络说明（重要）

- 模型默认从 **ModelScope**（`modelscope.cn`）下载——HuggingFace 在国内网络常被墙，
  ModelScope 可达且速度快。
- 需要从 HuggingFace 下载时：`USE_HF=1 bash scripts/setup.sh`（会尝试直连 HF）。
- 下载断点：ModelScope SDK 支持断点续传，中断后重跑脚本即可。

### 4. 部署后的关键配置（脚本已自动处理，了解即可）

以下优化是本项目在 Apple Silicon 上实测调优的结果，**不要随意改回默认值**：

| 配置 | 默认问题 | 本项目做法 | 效果 |
|---|---|---|---|
| 注意力后端 | `sdpa` 在 MPS 上极慢（实测 ~35s/token） | `attn_implementation="eager"` | 快 20 倍+ |
| 权重加载 | CPU/MPS 双份拷贝 → 16GB 机器 OOM | `device_map="mps"` 直接载入 MPS | 省 9.5GB 内存 |
| MPS 内存上限 | 默认限制导致生成时 OOM | `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0` | 不再 OOM |
| 图片分辨率 | 默认 4M 像素不缩放（数千视觉 token） | `max_pixels=150000`（≈384px，模型训练分辨率） | prefill 快 10 倍+ |
| 视频帧分辨率 | 视频处理器忽略 max_pixels（12.8M 像素/帧） | 抽帧时 PIL 预缩放至 192px | 视频分析从 20 分钟+ 降到 1-2 分钟 |

### 5. Linux / NVIDIA GPU 用户（规划中，暂未验证）

> ⚠️ 目前仅官方支持 macOS。以下为规划中的 Linux 部署方式，**未经测试，不保证可用**，
> 遇到问题欢迎反馈到 Issues。

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install flash-attn mamba-ssm   # 可选，加速
bash scripts/setup.sh
venv/bin/python scripts/analyze.py --input 图片.jpg --device cuda
```

Linux 规划中的额外能力：官方 codec 视频后端（`--video-backend codec`，需 ffmpeg +
cv-preinfer），以及更快的 flash attention。

---

## 使用指南

> 所有命令用 `venv/bin/python` 执行（`venv` 由 setup.sh 创建）。

### 单张图片分析

```bash
venv/bin/python scripts/analyze.py --input 图片.jpg
# 输出：图片.analysis.json + 图片.analysis.md（可读报告打印在终端）
```

### 视频分镜分析

```bash
venv/bin/python scripts/analyze.py --input 视频.mp4 --task video --num-frames 8
# 输出：视频.analysis.json + 视频.analysis.md
```

### 自由问答

```bash
venv/bin/python scripts/analyze.py --input 图片.jpg --task describe --question "光线从哪个方向来？色温偏暖还是偏冷？"
```

### 批量分析整个素材文件夹

```bash
venv/bin/python scripts/batch.py --dir /path/to/素材 --output-dir /path/to/分析结果
# 每个视频自动：Mage-VL 语义分析 → scene_cut 精确切点
# 产出：每份 .analysis.json/.md/.scenes.json + 分析清单.csv + 分析总览.md
```

常用参数：`--skip-existing`（断点续跑）、`--ext mp4,mov`（限定类型）、
`--num-frames 8`（视频抽帧数）、`--max-new-tokens 600`（生成上限，内存紧张调小）。

### 精确切点检测（单独使用）

```bash
venv/bin/python scripts/scene_cut.py --input 视频.mp4 --analysis 视频.analysis.json
# 输出：视频.analysis.scenes.json（时间戳为帧级精度）
# 调灵敏度：--cut-fraction 0.005（默认 0.01，越小切点越少）
```

### 全部参数表

`analyze.py`：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--input` | 必填 | 图片或视频路径 |
| `--task` | `scene` | `scene`/`video`/`describe` |
| `--question` | 无 | describe 的问题，或覆盖默认提示词 |
| `--num-frames` | `8` | 视频抽帧数 |
| `--max-pixels` | `150000` | 图片最大像素（≈384px） |
| `--video-max-pixels` | `38400` | 视频每帧最大像素 |
| `--max-new-tokens` | `1024` | 生成 token 上限 |
| `--lang` | `zh` | 可读输出语言 |
| `--model` | 本地缓存 | 模型路径/ID |
| `--device` | 自动 | `mps`/`cpu`/`cuda` |

`batch.py`：`--dir`（必填）、`--ext`、`--task`、`--num-frames`、`--max-new-tokens`、
`--output-dir`、`--skip-existing`、`--no-scene-cuts`、`--cut-fraction`。

`scene_cut.py`：`--input`（必填）、`--analysis`、`--cut-fraction`（默认 0.01）、
`--min-scene-sec`（默认 2.0）、`--stride`、`--work-width`、`--output`。

---

## 输出格式（JSON Schema）

### 单图（`scene`）

```json
{
  "summary": "一句话总结",
  "subjects": [{
    "name": "主体描述",
    "position_region": "left-third|center|right-third|top|bottom|off-frame",
    "x_normalized": 0.45, "y_normalized": 0.25,
    "shot_scale": "closeup|medium|full|wide"
  }],
  "composition": {
    "rule_of_thirds": "与三分线的对齐关系",
    "framing": "close-up|medium|wide|extreme-wide",
    "camera_angle": "eye-level|high|low|dutch|overhead",
    "symmetry": 0.0, "leading_lines": [], "negative_space": 0.0,
    "depth_of_field": "shallow|medium|deep",
    "focal_point": "视觉焦点"
  },
  "lighting": {
    "direction": "front|side|back|top|under|mixed",
    "quality": "hard|soft|diffuse|mixed",
    "color_temperature": "warm|neutral|cool|mixed",
    "contrast": "low|medium|high",
    "key_source": "主光源", "shadow_detail": "阴影", "highlight_detail": "高光",
    "mood": "情绪"
  },
  "color": {"palette": [], "saturation": 0.0, "dominant_color": ""},
  "cinematic_notes": [],
  "editing_suggestions": []
}
```

### 视频（`video`，为自动化剪辑设计的决策字段）

```json
{
  "summary": "...",
  "shots": [{
    "start_sec": 0.0, "end_sec": 5.0,
    "type": "establishing|wide|medium|close-up|aerial|timelapse|...",
    "camera_movement": "static|pan|tilt|zoom|handheld|tracking|...",
    "subjects": [],
    "composition": "...", "lighting": "...",
    "dominant_color": "...", "color_temp": "warm|neutral|cool",
    "energy": "low|medium|high",
    "transition_in": {"type": "cut|dissolve|fade|dip-to-black|match-cut|whip-pan|L-cut|J-cut|crossfade|zoom-transition", "reason": "..."},
    "transition_out": {"type": "...", "reason": "..."},
    "b_roll_use": "该镜头适合的角色：转场垫片/氛围空镜/主体引入/定场/时间流逝",
    "edit_notes": "具体剪辑指令"
  }],
  "sequence": {
    "structure": "montage|continuity|mixed",
    "pacing": {"tempo": "...", "suggested_cut_duration_sec": 3.0, "rhythm": "..."},
    "color_flow": "整段色彩走向",
    "strongest_moment_sec": 0.0,
    "transition_suggestions": ["具体转场方案"],
    "broll_candidates": [{"shot_sec": 0.0, "use_for": "B-roll 角色"}],
    "color_match_scores": [{"from_sec": 0.0, "to_sec": 5.0, "match": 0.8, "note": "调色建议"}]
  },
  "editing_suggestions": []
}
```

### 切点修正版（`scene_detection` 附加字段）

```json
{
  "scene_detection": {"cuts_sec": [2.55, 5.0, 59.73], "total_sec": 69.1},
  "parsed": { "shots": [ { "start_sec": 0.0, "end_sec": 2.55, "scene_detected": true, ... } ] }
}
```

---

## 性能参考

实测环境：**Mac mini M2 Pro，16GB 统一内存**（macOS，分析时无其他大内存应用）：

| 任务 | 耗时 |
|---|---|
| 模型冷启动（含 MPS kernel 编译） | ~20-30s |
| 单图分析（scene，700 tokens） | ~1 分钟 |
| 短视频分析（video，8 帧，30-70s 素材） | 1-4 分钟 |
| 场景切点检测（69s 视频，帧级） | ~15s |
| 批量 48 段 4K 素材（含全部语义+切点） | ~62 分钟 |

内存紧张（浏览器未关、swap 换页）时速度会暴跌 10 倍以上，属预期行为。

---

## 常见问题 FAQ

**Q: 模型下载失败 / 网络超时？**
A: 默认走 ModelScope（国内可达）。若失败：检查代理设置后重跑（断点续传）；
或 `USE_HF=1 bash scripts/setup.sh` 改用 HuggingFace。

**Q: Mac 上分析很慢 / 卡死？**
A: ① 关闭 Chrome/Safari 等大内存应用（16GB 机器模型占 9.5GB）；② 调小
`--max-new-tokens`（400-500）；③ 视频 `--num-frames` 调小到 4-6。

**Q: 出现 OOM / MPS out of memory？**
A: 确认环境变量 `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0` 已生效（analyze.py 内置），
且模型通过 `device_map="mps"` 加载（避免双份拷贝）。

**Q: JSON 输出被截断 / parsed 为 null？**
A: `extract_json` 内置截断修复（自动补全括号），batch 模式还会自动用更多 token 重试一次。
也可手动调大 `--max-new-tokens`。

**Q: 视频时间戳不准？**
A: 模型的时间戳是估计值（稀疏抽帧的固有局限）。用 `scene_cut.py` 补帧级精确切点，
语义标注按重叠/最近匹配自动映射。

**Q: `flash-attn` / `mamba-ssm` 装不上？**
A: 这两个包是 CUDA-only，macOS 装不上是正常的——本项目刻意不依赖它们
（用 eager 注意力 + transformers 标准实现）。

**Q: 必须用 Mac 吗？**
A: **目前仅支持 macOS（Apple Silicon，开发设备 Mac mini M2 Pro）**。Linux/Windows
支持在路线图中（v1.x），尚未验证。届时会补充 CUDA 部署说明。

---

## 与剪辑工作流集成

`xxx.analysis.scenes.json` 是为剪辑脚本设计的机器可读格式，示例消费逻辑：

```python
import json

data = json.load(open("素材.analysis.scenes.json"))
for shot in data["parsed"]["shots"]:
    print(f"剪切点: {shot['start_sec']:.2f}s -> {shot['end_sec']:.2f}s")
    print(f"转场: {shot['transition_out']['type']}  (理由: {shot['transition_out']['reason']})")
    print(f"B-roll 用途: {shot['b_roll_use']}")
```

配合 ffmpeg 即可自动生成剪切/转场草稿：

```bash
ffmpeg -ss 0 -to 2.55 -i 素材.mov -c copy shot1.mp4
ffmpeg -ss 2.55 -to 59.73 -i 素材.mov -c copy shot2.mp4
```

---

## 项目结构

```
CineSight/
├── README.md                  # 本文档
├── SKILL.md                   # Skill 定义（触发规则 + 工作流，供 AI 助手消费）
├── LICENSE                    # CineSight 软件使用许可协议 v1（宽松业务授权）
├── scripts/
│   ├── setup.sh               # 一键部署（venv + 依赖 + 模型下载，幂等）
│   ├── analyze.py             # 单图/视频/自由问答分析
│   ├── batch.py               # 批量分析 + 自动切点 + 总览/CSV
│   ├── scene_cut.py           # 帧级精确切点检测
│   └── requirements-mac.txt   # macOS 依赖（剔除 CUDA-only 包）
├── references/
│   └── prompts.md             # 提示词模板与扩展指南
├── evals/
│   └── evals.json             # 触发测试用例
└── examples/                  # 真实输出示例
    ├── dog.jpg                # 测试图（模型官方素材）
    ├── dog.analysis.md
    ├── DJI_20250621185315_0450_D.analysis.md   # 无人机照片分析
    ├── 雪中跳舞.analysis.md                      # 视频分镜分析
    ├── 雪中跳舞.analysis.scenes.json             # 切点修正版
    └── C0117.analysis.md                        # 西藏素材分析
```

## 路线图

CineSight 是**完整 AI 剪辑流水线的第一阶段**（v1.0：让 AI 读懂素材）。规划中的后续版本：

| 版本 | 主题 | 内容（规划） |
|---|---|---|
| v1.0（当前） | 视觉理解 | 单图/视频语义分析、帧级切点、批量盘点、决策 JSON |
| v1.x | 素材智能盘点 | 按能量/色彩/主体类型自动筛选最强素材、重复镜头去重、B-roll 推荐排序 |
| v2.0 | **CutSkill 剪辑 skill** | 自动化粗剪：根据节奏/色彩匹配自动生成剪辑序列（EDL/XML 导出，Final Cut/Premiere 可直接导入） |
| v2.x | **ColorSkill 调色 skill** | 转场匹配建议落地、自动调色参数建议、音画节奏对齐（BPM 检测） |
| v3.0 | 全自动剪辑 | 输入素材库 + 风格参数 → 输出成片草稿 |

> **敬请期待**：CutSkill（AI 剪辑）与 ColorSkill（AI 调色）将与 CineSight 组成
> "看懂 → 剪好 → 调好"的完整自动化流水线。
> 欢迎贡献想法、报告问题或参与开发。你的使用反馈会直接进入路线图。

## 作者与联系方式

**作者**：erick

一个独立视频创作者 & 全栈开发者。做这个项目的初衷：拍完几十 GB 的素材，靠人肉逐段看
找镜头太痛苦了——干脆让 AI 替我们"看"。

- 📧 邮箱：2429058447@qq.com
- 💬 微信：Hzhuang2429
- 🐙 GitHub：欢迎在 Issues 里提建议和 bug

任何关于剪辑自动化、素材管理、AI 工作流的问题都欢迎交流。

> **后续计划**：本系列将陆续推出 **CutSkill（AI 剪辑 skill）** 和 **ColorSkill（AI 调色
> skill）**，与 CineSight 组成完整的"看懂 → 剪好 → 调好"自动化流水线，敬请期待！
>
> 特别感谢 **梁圣（DeepSeek / 深度求索）**——DeepSeek API 价格巨便宜，
> 让整个项目的 AI 辅助开发成本几乎为零，大力出奇迹 😄

## 致谢（使用的开源项目）

本项目站在这些优秀的开源项目肩膀上，感谢所有作者：

| 项目 | 用途 | 许可证 |
|---|---|---|
| [Mage-VL](https://github.com/microsoft/Mage)（微软） | 视觉理解模型（Mage-ViT + Qwen3-4B） | Apache-2.0 |
| [Qwen3](https://github.com/QwenLM/Qwen3)（阿里） | Mage-VL 的语言解码器 | Apache-2.0 |
| [HuggingFace Transformers](https://github.com/huggingface/transformers) | 模型加载与推理框架 | Apache-2.0 |
| [PyTorch](https://github.com/pytorch/pytorch) | 深度学习框架（MPS 加速） | BSD-3-Clause |
| [OpenCV](https://github.com/opencv/opencv) | 视频抽帧、场景切点检测 | Apache-2.0 |
| [ModelScope](https://github.com/modelscope/modelscope)（阿里） | 模型权重下载通道（国内可达） | Apache-2.0 |
| [DeepSeek](https://github.com/deepseek-ai)（深度求索） | AI 辅助开发全流程（本项目由 DeepSeek 驱动开发） | — |
| [uv](https://github.com/astral-sh/uv) | Python 环境管理（自动安装 Python 3.12） | MIT |
| [LocateAnything](https://arxiv.org/abs/2605.27365)（英伟达） | 视觉定位模型（调研对比对象） | — |

## License

本软件使用 **CineSight 软件使用许可协议 v1**（见 [LICENSE](LICENSE)）。

核心条款一览：

| | |
|---|---|
| ✅ **免费使用** | 个人、团队、商业摄影师均可免费使用 |
| ✅ **业务可用** | 允许在**收费拍摄 / 剪辑业务**中使用（客户付的是拍摄服务费，软件只是内部工具） |
| ✅ **免费分发** | 原样免费分享安装包（需保留版权声明与本协议） |
| 🚫 **禁止售卖软件本身** | 原版 / 改名 / 二次打包 / 上架商店 / 付费 SaaS / 收费小程序 / 在线选片网站 |
| 🚫 **禁止商业再分发** | 未经授权不得对外收费分发或二次开发后售卖 |
| 📞 **二次开发授权** | 商业授权、定制、企业采购请联系微信 **Hzhuang2429** |

> **免费使用 · 禁止售卖本软件 / 商业再分发 · 二次开发授权请联系微信 Hzhuang2429**

拿不准自己的用法是否合规？LICENSE 内含 **12 个边界场景判断表**（含 12 项禁止行为清单），一眼可查。

视觉模型 `Mage-VL` 为微软开源（Apache-2.0），使用其权重时请遵循上游许可证；
示例素材版权归原作者所有，仅作演示。
