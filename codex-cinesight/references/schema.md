# Codex CineSight 输出 Schema

## 外层包装

每份分析文件使用以下包装，保持与原 CineSight 下游消费者兼容：

```json
{"input": "/absolute/path/to/media", "task": "scene|video|describe", "parsed": {}, "raw_output": "Codex 的完整观察文本"}
```

## 单图 `scene`（`parsed`）

```json
{
  "summary": "一句话画面总结",
  "subjects": [{"name": "主体", "position_region": "left-third|center|right-third|top|bottom|off-frame", "x_normalized": 0.5, "y_normalized": 0.5, "shot_scale": "closeup|medium|full|wide"}],
  "composition": {"rule_of_thirds": "", "framing": "close-up|medium|wide|extreme-wide", "camera_angle": "", "symmetry": 0.0, "leading_lines": [], "negative_space": 0.0, "depth_of_field": "", "focal_point": ""},
  "lighting": {"direction": "", "quality": "", "color_temperature": "warm|neutral|cool|mixed", "contrast": "", "key_source": "", "shadow_detail": "", "highlight_detail": "", "mood": ""},
  "color": {"palette": [], "saturation": "low|medium|high", "dominant_color": ""},
  "cinematic_notes": [],
  "editing_suggestions": [],
  "evidence": ["基于可见画面……"]
}
```

## 视频 `video`

在单图字段基础上增加：

```json
{
  "shots": [{"start_sec": 0.0, "end_sec": 3.0, "timestamp_basis": "frame_verified|scene_detected|estimated", "type": "", "camera_movement": "", "subjects": [], "composition": "", "lighting": "", "dominant_color": "", "color_temp": "warm|neutral|cool|mixed", "energy": "low|medium|high", "transition_in": {"type": "cut", "reason": ""}, "transition_out": {"type": "cut", "reason": ""}, "b_roll_use": "", "edit_notes": ""}],
  "sequence": {"structure": "montage|continuity|mixed", "pacing": {"tempo": "", "suggested_cut_duration_sec": 3.0, "rhythm": ""}, "color_flow": "", "strongest_moment_sec": 0.0, "transition_suggestions": [], "broll_candidates": [], "color_match_scores": []},
  "editing_suggestions": [],
  "evidence": [{"frame": "frames/frame_0001.jpg", "supports": ""}]
}
```

`evidence` 用来区分观察与推断。视频若做切点合并，再增加：

```json
{"scene_detection": {"cuts_sec": [2.55, 5.0], "cuts": [{"sec": 2.55, "type": "cut", "confidence": 0.99}], "fades": [{"type": "fade_in", "confidence": 0.88}], "total_sec": 69.12}, "parsed": {"shots": [{"scene_detected": true}]}}
```

Markdown 报告建议包含：总结、主体、构图、光影、色彩、镜头表、序列节奏、剪辑建议、证据与限制。JSON 文件应使用 UTF-8、缩进 2 空格；批量总览链接到每个 `.analysis.md`。
