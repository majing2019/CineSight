# Mage-VL 提示词模板

`scripts/analyze.py` 内置了 `scene`（单帧构图/光影）和 `video`（分镜）两个默认提示词，
本文件是它们的说明与扩展指南。

## scene（单帧）默认模板要点

要求模型只输出一个合法 JSON，字段为：

- `summary`：一句自然语言总结
- `subjects[]`：主体 + 画面位置（三分区）+ 归一化坐标 + 景别
- `composition`：构图（三分法/景别/机位角度/对称度/引导线/留白/景深/视觉焦点）
- `lighting`：光影（方向/软硬/色温/反差/主光来源/阴影/高光/情绪）
- `color`：色调（主色调/饱和度）
- `cinematic_notes`、`editing_suggestions`

## video（分镜）默认模板要点

面向**自动化剪辑**的决策输出（影视飓风《样片日记》风格旅行样片工作流），每个镜头都是可直接执行的决策：

- `shots[]`：
  - 时间切分（`start_sec`/`end_sec`）、镜头类型、运镜方式、主体
  - 构图/光影简述、`dominant_color`、`color_temp`（冷暖）、`energy`（低/中/高）
  - `transition_in` / `transition_out`：转场类型（cut/dissolve/fade/dip-to-black/match-cut/whip-pan/L-cut/J-cut/crossfade/zoom-transition）+ 理由
  - `b_roll_use`：该镜头最适合的用途（转场垫片/氛围空镜/主体引入/定场/时间流逝）
  - `edit_notes`：具体剪辑指令
- `sequence`（序列级决策）：
  - `structure`：蒙太奇/连续性/混合
  - `pacing`：节奏（tempo + 建议镜头时长 + 节奏描述，如"跟着动作/鼓点切"）
  - `color_flow`：整段色彩走向（如冷→暖、统一冷调）
  - `strongest_moment_sec`：最强时刻
  - `transition_suggestions[]`：具体转场方案列表
  - `broll_candidates[]`：B-roll 候选（时间点 + 用途）
  - `color_match_scores[]`：相邻镜头色彩匹配度 0-1 + 调色统一建议
- `editing_suggestions[]`：可直接执行的剪辑动作

## 扩展建议

- **构图专项**：追问 "frame-by-frame rule of thirds, symmetry axis, leading lines, headroom, negative space score 0-1 for each"。
- **光影专项**：追问 "estimate light direction, light quality, color temperature in Kelvin, contrast ratio, whether shadows are crushed or highlights blown, overall mood"。
- **剪辑决策专项**（默认已内置）：对 video 任务输出 `transition_in/out`、`broll_use`、
  `sequence.transition_suggestions`、`sequence.broll_candidates`、`sequence.color_match_scores`、
  `sequence.pacing`，让下游剪辑脚本可以直接消费。
- **多主体/多人**：`subjects[]` 允许复数，描述主次关系（`role: "primary|secondary"`）。
- **配乐节奏**（可选扩展）：追问 "suggest BPM range and beat-sync cut points: the strongest 3 cut times (sec) aligned to a hypothetical 100 BPM track"。

## 语言

模型基于 Qwen3-4B，中英文均支持良好。为便于程序消费，JSON 的键保持英文，
`summary` 等文本字段可由 `--lang zh|en` 控制。默认 zh。
