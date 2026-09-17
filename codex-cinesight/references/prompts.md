# Codex CineSight 提示词模板

这些模板用于调用 Codex 图片理解能力时约束输出；可按用户目标追加问题，但不要删除字段。

## scene

“只根据可见画面分析这张图。先写可验证事实，再给剪辑建议。输出合法 JSON，字段为 `summary`、`subjects`（name、position_region=`left-third|center|right-third|top|bottom|off-frame`、x_normalized、y_normalized、shot_scale）、`composition`（rule_of_thirds、framing=`close-up|medium|wide|extreme-wide`、camera_angle、symmetry、leading_lines、negative_space、depth_of_field、focal_point）、`lighting`（direction、quality、color_temperature、contrast、key_source、shadow_detail、highlight_detail、mood）、`color`（palette、saturation、dominant_color）、`cinematic_notes`、`editing_suggestions`、`evidence`。无法判断写 null，不要虚构镜头外信息。”

## video

“根据附带帧及其时间 manifest 分析整段视频。按视觉连续性和动作连续性划分镜头，输出合法 JSON。每个 `shots[]` 必须有 `start_sec`、`end_sec`、`timestamp_basis`、`type`、`camera_movement`、`subjects`、`composition`、`lighting`、`dominant_color`、`color_temp`、`energy`、`transition_in`、`transition_out`、`b_roll_use`、`edit_notes`；另输出 `sequence`（structure、pacing、color_flow、strongest_moment_sec、transition_suggestions、broll_candidates、color_match_scores）、`editing_suggestions`、`evidence`。时间仅来自 manifest 或已复核切点；稀疏抽帧无法证明的内容标记 estimated。”

## describe

“只回答这个视觉问题：{question}。引用具体可见证据，区分事实与推断；如涉及方向、色温、位置或景别，使用明确术语，并说明不确定性。”

## generate

“基于已经确认的视觉分析生成{cover/storyboard/b-roll}参考图。保持{aspect_ratio}画幅、{subject}主体、{composition}构图、{lighting}光线、{palette}色彩与{style}风格；不要生成文字（除非用户明确要求），不要把未确认的原图细节当作事实。”
