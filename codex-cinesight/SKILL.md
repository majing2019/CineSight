---
name: codex-cinesight
description: 分析图片或视频的主体、构图、光影、色彩、镜头语言、分镜、转场与剪辑节奏，并输出可供剪辑工作流消费的结构化 JSON/Markdown；需要视觉理解或生成封面、分镜关键帧、B-roll 参考时触发。纯文本或与视觉内容无关的数据分析不触发。
---

# Codex CineSight：用 Codex 视觉能力读懂素材

将 CineSight 的“语义分析 + 可读报告 + 剪辑决策”能力迁移到 Codex：不安装、不调用任何本地 VLM；由 Codex 直接查看本地图片或视频抽帧，并在用户明确需要视觉产物时调用图片生成能力。

脚本层只需要系统 `ffmpeg/ffprobe`；运行精确切点检测还需要 `numpy` 和 `opencv-python`。这些是媒体处理依赖，不是视觉理解模型；若未安装，仍可使用 Codex 直接分析抽帧。

## 输入与工作方式

- 单图：直接用图片理解，重点判断主体位置、景别、构图、机位、光影、色温、色彩、情绪和封面适配性。
- 视频：先用 `scripts/extract_frames.py` 均匀抽帧并生成 `manifest.json`；用 `view_image` 逐帧查看。镜头较多时，先看 contact sheet，再对疑似切点前后补抽帧。不要把单帧印象冒充整段视频事实。
- 视频切点：用 `scripts/detect_cuts.py` 的 HSV 直方图 + Laplacian 边缘差异双指标产生候选切点，并可用 `--min-scene-sec`、`--stride`、`--auto-stride`、`--cut-fraction` 调整；输出还包含相邻峰的 `dissolve` 候选和首尾 `fade_in/fade_out` 候选。候选点只作为时间边界，仍需用前后帧复核；语义分镜的时间戳应标注为估计值，帧级切点应标注检测/复核状态。
- 批量素材：先列出目录内图片/视频，可按扩展名过滤（等价 `--ext mp4,mov`），逐个分析并为每个文件输出同名 `.analysis.json`、`.analysis.md`，另输出 `分析清单.csv` 和 `分析总览.md`。可指定独立 `--output-dir`；已有结果且用户要求断点续跑时跳过（等价 `--skip-existing`），不覆盖用户手工修改的结果。视频默认做切点检测，需要时关闭（等价 `--no-scene-cuts`）或调整 `--cut-fraction`。批量时一次只处理一个素材，避免把不同素材的主体和色彩混淆。

临时抽帧目录应放在输出目录下的隐藏或明确命名子目录中；分析完成后除非用户要求保留，不把大量帧混入最终交付。原始素材和 `sources/` 目录只读。

## 任务路由

默认任务：

1. `scene`：单图构图/光影/主体/色彩分析。
2. `video`：视频分镜、景别、运镜、主体、色彩流、能量、转场、B-roll 和剪辑指令。
3. `describe`：回答用户针对画面的自由问题，仍尽量引用观察证据。
4. `generate`：仅在用户要视觉产物时调用图片生成：封面候选、分镜关键帧、B-roll 概念图或风格参考。生成图是创意参考，不是对原素材的事实分析。

若用户没有指定输出格式，先给简短结论，再给 JSON；视频另外给镜头表。不要为了“结构化”编造不可从画面判断的精确参数。

## 固定输出契约

使用 [references/schema.md](references/schema.md) 中的字段名。最终 `.analysis.json` 采用兼容 CineSight 的外层 `{input, task, parsed, raw_output}`，其中 `parsed` 至少保留 `summary`、`subjects`、`composition`、`lighting`、`color`、`cinematic_notes`、`editing_suggestions`；视频再保留 `shots`、`sequence` 和 `evidence`。`raw_output` 保存未经压缩的观察/推理文本，便于人工复核。不确定值写 `unknown` 或在 `evidence` 中说明，不要猜测镜头外信息。

每个主体的位置同时给出区域（`left-third|center|right-third|top|bottom|off-frame`）和 0–1 归一化坐标；每个视频镜头给出 `start_sec` / `end_sec`、`timestamp_basis`（`frame_verified`、`scene_detected` 或 `estimated`）。转场只能从 `cut`、`dissolve`、`fade`、`dip-to-black`、`match-cut`、`whip-pan`、`L-cut`、`J-cut`、`crossfade`、`zoom-transition` 中选择，并附理由。

## 视觉判断规则

- 先描述看见的事实，再给审美或剪辑建议；将推断和事实分开。
- 构图分析至少覆盖：景别、取景/裁切、三分法或对称、机位角度、引导线、留白、景深和视觉焦点。
- 光影分析至少覆盖：方向、软硬、色温、反差、主光源、阴影/高光细节和情绪。
- 视频分析按视觉连续性和动作连续性划镜头；相邻帧颜色相似不代表没有切镜，候选切点必须复核。
- 对封面判断给出“适合/有条件适合/不建议”及一到三条可执行修改建议。
- Markdown 报告中的枚举可用中文展示（如 `close-up=特写`、`medium=中景`、`wide=远景`、`extreme-wide=大远景`、`pan=横摇`、`tracking=跟拍`、`cut=硬切`、`dissolve=叠化`），但 JSON 保持英文枚举，方便下游程序消费。

## 生成视觉产物

调用图片生成时，提示词必须包含：画幅比例、主体与构图、镜头/景别、光线与色彩、风格、文字是否出现（默认不生成文字）、以及“保持与分析结论一致但不要虚构原图事实”。需要基于用户提供的参考图编辑时，先确认已能访问该图；新图与原素材事实分析分开呈现。

## 参考资源

- 输出字段、示例和批量文件命名： [references/schema.md](references/schema.md)
- 可直接复用的 scene/video/describe 提示词： [references/prompts.md](references/prompts.md)
- 视频抽帧与候选切点： `scripts/extract_frames.py`、`scripts/detect_cuts.py`
