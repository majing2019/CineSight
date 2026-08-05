---
name: cinesight
description: 给 DeepSeek/opencode 加上"眼睛"——当用户要求分析或描述一张图片/一段视频、询问画面构图/光影/主体/镜头语言/分镜/运镜/色调，或希望为视频剪辑与后期自动化提供视觉输入时触发。通过本地 Microsoft Mage-VL-4B 多模态模型（Apple Silicon 可跑）把图像/视频转成结构化 JSON（构图/光影/主体/分镜）+ 可读总结。
---

# CineSight — AI 剪辑的第一步：让 AI 读懂画面

用本地 **Mage-VL-4B**（Microsoft，Apache-2.0）给纯文本模型补上视觉能力。
核心产出：**结构化 JSON**（构图、光影、主体、分镜、剪辑建议）+ **可读总结**，
供下游视频剪辑/后期自动化做程序化消费。

模型为 `microsoft/Mage-VL`（Mage-ViT + Qwen3-4B），单 checkpoint 同时支持图像与视频理解。

## 何时使用

- 用户给出一个**图片文件路径**，要求"看看/分析/描述/看懂"画面内容
- 用户给出一个**视频文件路径**，要求分析构图、光影、镜头、分镜、运镜、转场、节奏
- 用户在做剪辑/后期工作流，需要把某个镜头/片段转成结构化视觉描述供决策
- 用户问"这张图的构图/光影怎么样""这段视频适不适合做 XX 转场"

## 工作流

1. **检查部署**：若 `scripts/venv/.mage_ready` 不存在或报错，先跑
   `bash scripts/setup.sh`（用 uv 建 Python 3.12 venv、装依赖、从 **ModelScope** 预下载
   ~10.8GB 模型权重到 `~/.cache/mage-vl/microsoft/Mage-VL`，幂等；`USE_HF=1` 可改用 HF 通道）。
2. **确认媒体类型**：看扩展名。图片 → `--task scene`（默认）；视频 → `--task video`。
3. **运行分析**（用 skill 的 venv）：
   - 图片：`venv/bin/python scripts/analyze.py --input <path>`
   - 视频：`venv/bin/python scripts/analyze.py --input <path> --task video --num-frames 24`
   - 自由问答：`venv/bin/python scripts/analyze.py --input <path> --task describe --question "<问题>"`
   - 批量分析整个素材文件夹：
     `venv/bin/python scripts/batch.py --dir <素材目录> [--ext mp4,mov] [--skip-existing]`
     （一次加载模型顺序分析：每个视频自动补精确切点检测，产出每份
     `.analysis.json/.md` + `.analysis.scenes.json` + 汇总 `分析清单.csv`；
     `--no-scene-cuts` 关闭切点检测，`--cut-fraction` 调灵敏度）
   - 精确切点检测（修正模型时间戳）：
     `venv/bin/python scripts/scene_cut.py --input <视频> --analysis <xx.analysis.json>`
     （HSV 直方图 + 边缘差异双指标百分位融合，检测硬切/叠化/首尾淡入淡出，
     与分镜分析合并后输出 `<xx.analysis.scenes.json>`，时间戳为帧级精度；
     用 `--cut-fraction` 调灵敏度，默认 0.01 即 top 1%）
   - 模型默认用本地目录，也可 `--model <id|路径>` 覆盖。
4. **读取结果**：
   - 可读总结直接打印在 stdout（`*.analysis.md` 同内容）
   - 结构化数据在 `*.analysis.json`（含 `parsed` 字段和 `raw_output`）
5. **下游使用**：把 `parsed` 的构图/光影/分镜字段作为 DeepSeek 的视觉输入，
   用于剪辑决策（如判断该用何种转场、是否需要补拍、节奏如何调整）。

## 输出 JSON Schema（`parsed`）

单帧（`scene`）：
```json
{
  "summary": "...",
  "subjects": [{"name": "...", "position_region": "left-third|center|...", "x_normalized": 0.3, "y_normalized": 0.5, "shot_scale": "closeup|medium|full|wide"}],
  "composition": {"rule_of_thirds": "...", "framing": "...", "camera_angle": "...", "symmetry": 0.0, "leading_lines": [], "negative_space": 0.0, "depth_of_field": "...", "focal_point": "..."},
  "lighting": {"direction": "...", "quality": "...", "color_temperature": "...", "contrast": "...", "key_source": "...", "shadow_detail": "...", "highlight_detail": "...", "mood": "..."},
  "color": {"palette": [], "saturation": 0.0, "dominant_color": "..."},
  "cinematic_notes": [],
  "editing_suggestions": []
}
```

视频（`video`）额外含（面向自动化剪辑的决策输出）：
```json
{
  "shots": [{"start_sec": 0.0, "end_sec": 5.0, "type": "...", "camera_movement": "...",
             "subjects": [], "composition": "...", "lighting": "...",
             "dominant_color": "...", "color_temp": "warm|neutral|cool", "energy": "low|medium|high",
             "transition_in": {"type": "cut|dissolve|fade|dip-to-black|match-cut|whip-pan|L-cut|J-cut|crossfade|zoom-transition", "reason": "..."},
             "transition_out": {"type": "...", "reason": "..."},
             "b_roll_use": "...", "edit_notes": "..."}],
  "sequence": {
    "structure": "montage|continuity|mixed",
    "pacing": {"tempo": "...", "suggested_cut_duration_sec": 3.0, "rhythm": "..."},
    "color_flow": "...",
    "strongest_moment_sec": 0.0,
    "transition_suggestions": ["..."],
    "broll_candidates": [{"shot_sec": 0.0, "use_for": "..."}],
    "color_match_scores": [{"from_sec": 0.0, "to_sec": 5.0, "match": 0.8, "note": "..."}]
  },
  "editing_suggestions": []
}
```

提示词模板与扩展思路见 `references/prompts.md`（构图/光影专项、剪辑决策专项、切镜点输出）。

## 平台注意事项（Apple Silicon / macOS）

- **注意力后端用 `eager`**：官方 requirements 里的 `flash-attn` 和 `mamba-ssm` 是
  CUDA-only，macOS 无法编译，故不安装。注意**不能用 sdpa**——MPS 上 sdpa 的 Metal
  内核极慢（实测 ~35s/token），eager 反而快 20x+。
- **模型直接加载到 MPS**（`device_map="mps"`）：避免 CPU/MPS 双份权重拷贝导致 OOM
  （24GB 内存机器实测必须这样做）。脚本已设 `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0`。
- **图片会缩到 ~384px**（`max_pixels=150000`，Mage-VL 的训练分辨率）：否则高分辨率
  图片产生数千视觉 token，prefill 慢 10x+。本地 `preprocessor_config.json` 的
  `max_pixels` 已从默认 4000000 改为 150000。
- **视频用 `frames` 后端 + 帧预缩放**：官方 codec 视频路径依赖 Linux 工具，Mac 不可用。
  抽帧时每帧先缩放到 192px 内（脚本内置）——Mage-VL 的视频处理器会**忽略
  `max_pixels` 参数**（`video_preprocessor_config.json` 默认 12.8M 像素/帧），
  不预缩放会导致每帧上千视觉 token、分析 20 分钟+；预缩放后 30s 视频约 1-2 分钟。
  构图/光影是全局特征，低分辨率足够。
- **内存/显存**：4B bf16 权重约 9.5GB。**16GB 内存的 Mac 会吃紧**——模型 + 浏览器等
  应用同时运行时系统会重度换页（swap），生成速度暴跌到 0.5 token/s 以下、单次分析
  30 分钟+。实用规则：
  - 分析前关闭 Chrome/Safari 等大内存应用（实测内存宽松时单图 ~1 分钟、短视频 1-4 分钟）
  - 用 `scripts/batch.py` 批量分析（模型只加载一次，比逐个跑快得多）
  - `--max-new-tokens` 调小到 500（转场决策字段已是短值版）可显著提速
- **模型权重要预下载到本地**（约 10.8GB，含 gate 权重）。默认从 ModelScope
  （国内可达，`modelscope download --model microsoft/Mage-VL --local_dir ~/.cache/mage-vl/microsoft/Mage-VL`）
  拉取；analyze.py 默认直接加载该本地目录。需 HF 时设 `USE_HF=1` 重跑 setup.sh。

## 已知限制

- Mage-VL 为 research 用途模型，构图/光影/时间戳为**估计值**，不保证绝对精确；
  关键剪辑决策建议人工复核。
- 帧级时间戳精度有限，长视频建议按分段分析。
- 若模型输出未被解析为 JSON，`parsed` 为 `null`，此时用 `raw_output` 兜底。
