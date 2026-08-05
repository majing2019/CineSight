#!/usr/bin/env python
"""CineSight：用本地 Microsoft Mage-VL-4B 分析图像/视频，
输出结构化 JSON（构图/光影/主体/镜头）+ 可读总结，供剪辑决策使用。

用法：
  python analyze.py --input /path/to/image.jpg
  python analyze.py --input /path/to/video.mp4 --task video --num-frames 24
  python analyze.py --input /path/to/image.png --question "画面里有几个人？" --task describe

在 Apple Silicon 上会自动使用 MPS，回退到 CPU。

性能关键配置（经实测调优）：
- 注意力后端用 eager（MPS 上 sdpa 极慢，实测慢 20x+）
- device_map="mps" 直接加载到 MPS，避免 CPU/MPS 双份权重导致 OOM
- PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0 放开 MPS 内存上限
- 图片用 max_pixels=150000 缩到 ~384px（Mage-VL 训练分辨率），
  否则高分辨率图片会产生数千视觉 token，预填充慢 10x+
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
import time
from pathlib import Path

os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".ts"}

HF_MODEL_ID = "microsoft/Mage-VL"
LOCAL_MODEL_DIR = Path.home() / ".cache/mage-vl/microsoft/Mage-VL"

ARGS_MAX_PIXELS = 150000
ARGS_VIDEO_MAX_PIXELS = 38400
ARGS_NUM_FRAMES = 8

SCENE_PROMPT = textwrap.dedent(
    """\
You are a professional cinematography analyst working for a video editing automation pipeline.
Analyze the given image and reply with ONLY one valid JSON object, no markdown fences, no commentary, using exactly this schema:
{
  "summary": "one or two natural-language sentences summarizing the shot",
  "subjects": [
    {
      "name": "main subject description",
      "position_region": "left-third|center|right-third|top|bottom|off-frame",
      "x_normalized": 0.0,
      "y_normalized": 0.0,
      "shot_scale": "closeup|medium|full|wide"
    }
  ],
  "composition": {
    "rule_of_thirds": "how subjects align with the rule of thirds",
    "framing": "close-up|medium|wide|extreme-wide",
    "camera_angle": "eye-level|high|low|dutch|overhead",
    "symmetry": 0.0,
    "leading_lines": ["lines that guide the eye"],
    "negative_space": 0.0,
    "depth_of_field": "shallow|medium|deep",
    "focal_point": "what draws the eye first"
  },
  "lighting": {
    "direction": "front|side|back|top|under|mixed",
    "quality": "hard|soft|diffuse|mixed",
    "color_temperature": "warm|neutral|cool|mixed",
    "contrast": "low|medium|high",
    "key_source": "where the main light comes from",
    "shadow_detail": "how shadows are rendered",
    "highlight_detail": "how highlights are rendered",
    "mood": "overall mood conveyed by light"
  },
  "color": {"palette": ["dominant colors"], "saturation": 0.0, "dominant_color": "..."},
  "cinematic_notes": ["observations relevant to editing"],
  "editing_suggestions": ["concrete editing actions"]
}
Use null for anything you cannot determine; never invent values.
"""
)

VIDEO_PROMPT = textwrap.dedent(
    """\
You are a professional film editor and cinematography analyst working for an AUTOMATED video editing pipeline.
Analyze the given video and reply with ONLY one valid JSON object, no markdown fences, no commentary, using exactly this schema:
{
  "summary": "one or two sentences describing the overall scene and its progression",
  "shots": [
    {
      "start_sec": 0.0,
      "end_sec": 5.0,
      "type": "establishing|wide|medium|close-up|insert|two-shot|over-the-shoulder|aerial|timelapse",
      "camera_movement": "static|pan|tilt|zoom|handheld|tracking|dolly|push-in|pull-out|aerial-drone|none",
      "subjects": ["what is in frame"],
      "composition": "brief composition description",
      "lighting": "brief lighting description",
      "dominant_color": "dominant color of this shot",
      "color_temp": "warm|neutral|cool",
      "energy": "low|medium|high",
      "transition_in": {"type": "cut|dissolve|fade|dip-to-black|match-cut|whip-pan|L-cut|J-cut|crossfade|zoom-transition", "reason": "short reason, max 6 words"},
      "transition_out": {"type": "cut|dissolve|fade|dip-to-black|match-cut|whip-pan|L-cut|J-cut|crossfade|zoom-transition", "reason": "short reason, max 6 words"},
      "b_roll_use": "one short phrase, max 6 words",
      "edit_notes": "one short phrase, max 6 words"
    }
  ],
  "sequence": {
    "structure": "montage|continuity|mixed",
    "pacing": {"tempo": "slow|medium|fast", "suggested_cut_duration_sec": 3.0, "rhythm": "one short phrase, max 6 words"},
    "color_flow": "one short phrase, max 6 words",
    "strongest_moment_sec": 0.0,
    "transition_suggestions": ["concrete transition, max 8 words each"],
    "broll_candidates": [{"shot_sec": 0.0, "use_for": "short role, max 4 words"}],
    "color_match_scores": [{"from_sec": 0.0, "to_sec": 5.0, "match": 0.0, "note": "short grade note, max 6 words"}]
  },
  "editing_suggestions": ["concrete short actions, max 8 words each"]
}
Be specific and decisive: every field is a decision the pipeline can execute directly. Use null only for truly unknown values. Timestamps are estimates; keep them reasonable.
"""
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", required=True, help="图像或视频文件路径")
    parser.add_argument("--task", choices=("scene", "video", "describe"), default="scene",
                        help="scene=单帧构图光影; video=整段视频分镜; describe=自由问答")
    parser.add_argument("--question", default=None,
                        help="describe 任务的自定义问题；其他任务也可覆盖默认提示词")
    parser.add_argument("--num-frames", type=int, default=ARGS_NUM_FRAMES,
                        help="视频抽帧数量（省内存设小，8 对短片足够）")
    parser.add_argument("--max-pixels", type=int, default=ARGS_MAX_PIXELS,
                        help="图片最大像素（~384px，Mage-VL 训练分辨率）")
    parser.add_argument("--video-max-pixels", type=int, default=ARGS_VIDEO_MAX_PIXELS,
                        help="视频每帧最大像素（~192px；构图/光影是全局特征，低分辨率够用且快）")
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--lang", choices=("zh", "en"), default="zh",
                        help="summary/可读文本输出语言（JSON 键始终为英文）")
    parser.add_argument("--model", default=None,
                        help="模型路径/ID。默认优先用本地 ModelScope 下载目录 "
                             "~/.cache/mage-vl/microsoft/Mage-VL，不存在时回退到 HF id microsoft/Mage-VL")
    parser.add_argument("--output-dir", default=None,
                        help="输出目录，默认与 --input 同级")
    parser.add_argument("--device", default=None, help="强制设备: mps|cpu")
    return parser


def detect_kind(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return "unknown"


def pick_device(force: str | None) -> str:
    if force:
        return force
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def resolve_model(explicit: str | None) -> str:
    if explicit:
        return explicit
    if LOCAL_MODEL_DIR.is_dir():
        return str(LOCAL_MODEL_DIR)
    return HF_MODEL_ID


def sample_video_frames(video_path: str, num_frames: int, max_side: int = 192) -> list:
    """opencv 均匀抽帧。帧先缩放到 max_side 内（构图/光影是全局特征，
    低分辨率足够，且视频处理器会忽略 max_pixels 参数——必须在这里预缩放）。"""
    import cv2
    import numpy as np
    from PIL import Image

    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise RuntimeError(f"无法打开视频: {video_path}")
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if frame_count <= 0:
        capture.release()
        raise RuntimeError(f"无法读取视频: {video_path}")
    indices = np.linspace(0, frame_count - 1, min(num_frames, frame_count), dtype=int)
    frames = []
    for index in indices:
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
        ok, frame = capture.read()
        if not ok:
            continue
        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        img.thumbnail((max_side, max_side), Image.LANCZOS)
        frames.append(img)
    capture.release()
    if not frames:
        raise RuntimeError(f"视频抽帧失败: {video_path}")
    return frames


def load_model(model_name: str, device: str):
    import torch
    from transformers import AutoModelForCausalLM, AutoProcessor

    print(f"[magent] 加载模型 {model_name} 到 {device} ...", file=sys.stderr)
    processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)
    if device == "mps":
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            trust_remote_code=True,
            dtype=torch.bfloat16,
            attn_implementation="eager",
            device_map="mps",
            low_cpu_mem_usage=True,
        )
    else:
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            trust_remote_code=True,
            dtype=torch.bfloat16,
            attn_implementation="eager",
        ).to(device)
    model = model.eval()
    return processor, model


def run_inference(processor, model, device, kind, prompt, args):
    import torch

    messages = [{"role": "user", "content": [
        {"type": "image" if kind == "image" else "video"},
        {"type": "text", "text": prompt},
    ]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    if kind == "image":
        from PIL import Image
        inputs = processor(
            text=[text], images=[Image.open(args.input).convert("RGB")],
            max_pixels=args.max_pixels, return_tensors="pt", padding=True,
        )
    else:
        frames = sample_video_frames(args.input, args.num_frames, max_side=192)
        inputs = processor(
            text=[text], videos=[frames],
            max_pixels=args.video_max_pixels, return_tensors="pt", padding=True,
        )

    inputs = {k: (v.to(device) if hasattr(v, "to") else v) for k, v in inputs.items()}
    if "pixel_values" in inputs:
        inputs["pixel_values"] = inputs["pixel_values"].to(model.dtype)

    print(f"[magent] 推理中 (max_new_tokens={args.max_new_tokens}) ...", file=sys.stderr)
    t0 = time.time()
    with torch.inference_mode():
        output = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False)
    answer = processor.tokenizer.decode(
        output[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True
    ).strip()
    print(f"[magent] 推理完成 {time.time() - t0:.1f}s", file=sys.stderr)
    return answer


def extract_json(text: str):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.M)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        # 截断修复：max_new_tokens 不足导致 JSON 被截断时，尝试补全。
        # 三种截断位置：值前（[]/""/null）、分隔符处（补 }）、字符串中（补 "）
        suffixes = set()
        for k in range(1, 8):
            suffixes.add("}" * k)
            suffixes.add('[]' + "}" * k)
            suffixes.add('""' + "}" * k)
            suffixes.add('null' + "}" * k)
            suffixes.add('"' + "}" * k)
        for suffix in sorted(suffixes, key=len):
            try:
                return json.loads(candidate + suffix)
            except json.JSONDecodeError:
                continue
    return None


def localize_summary(summary: str, lang: str) -> str:
    if lang == "zh" and summary and not re.search(r"[\u4e00-\u9fff]", summary):
        return summary
    return summary


# 常用枚举值的中文标签（只做展示，不改变 JSON 原文）
_ZH = {
    "close-up": "特写", "closeup": "特写", "medium": "中景", "wide": "远景", "full": "全景",
    "extreme-wide": "大远景", "establishing": "定场", "insert": "插入", "two-shot": "双人",
    "over-the-shoulder": "过肩", "aerial": "航拍", "timelapse": "延时", "insert": "插入镜头",
    "static": "静止", "pan": "横摇", "tilt": "俯仰", "zoom": "变焦", "handheld": "手持",
    "tracking": "跟拍", "dolly": "轨道", "push-in": "推镜", "pull-out": "拉镜",
    "aerial-drone": "航拍", "none": "无",
    "cut": "硬切", "dissolve": "叠化", "fade": "淡入淡出", "dip-to-black": "黑场",
    "match-cut": "匹配切", "whip-pan": "甩镜", "L-cut": "L切", "J-cut": "J切",
    "crossfade": "交叉叠化", "zoom-transition": "变焦转场",
    "low": "低", "medium": "中", "high": "高",
    "warm": "暖", "cool": "冷", "neutral": "中性",
    "slow": "慢", "fast": "快",
    "montage": "蒙太奇", "continuity": "连续性", "mixed": "混合",
    "front": "正面光", "side": "侧光", "back": "逆光", "top": "顶光", "under": "底光",
    "hard": "硬光", "soft": "柔光", "diffuse": "漫射光",
    "eye-level": "平视", "dutch": "斜角", "overhead": "俯拍",
    "shallow": "浅", "deep": "深",
}


def zh(v):
    """展示用中文标签：命中字典翻译，否则原样返回。"""
    if v is None:
        return ""
    return _ZH.get(str(v), str(v))


def build_decision_overview(parsed: dict) -> list:
    """顶部决策速览：节奏/结构/色彩/最强时刻/转场方案/剪辑建议。"""
    lines = ["> **决策速览**"]
    seq = parsed.get("sequence") or {}
    p = seq.get("pacing") or {}
    bits = []
    if p.get("tempo"):
        bits.append(f"节奏 {zh(p.get('tempo'))}")
    if p.get("suggested_cut_duration_sec") is not None:
        bits.append(f"建议镜头 {p.get('suggested_cut_duration_sec')}s")
    if seq.get("structure"):
        bits.append(f"结构 {zh(seq.get('structure'))}")
    if seq.get("color_flow"):
        bits.append(f"色彩 {seq.get('color_flow')}")
    if seq.get("strongest_moment_sec") is not None:
        bits.append(f"最强 {seq.get('strongest_moment_sec')}s")
    if bits:
        lines.append(f"> {' · '.join(bits)}")
    if seq.get("transition_suggestions"):
        lines.append("> 转场: " + "；".join(str(t) for t in seq["transition_suggestions"]))
    if parsed.get("editing_suggestions"):
        lines.append("> 建议: " + "；".join(str(s) for s in parsed["editing_suggestions"]))
    return lines


def build_shot_table(shots: list) -> list:
    """分镜表格。"""
    lines = ["| 时间 | 景别 | 运镜 | 能量 | 冷暖 | 主体 | 出点转场 |",
             "|---|---|---|---|---|---|---|"]
    for s in shots:
        t_out = s.get("transition_out") or {}
        t_out_txt = zh(t_out.get("type")) if t_out.get("type") else ""
        if t_out.get("reason"):
            t_out_txt += f" ({t_out.get('reason')})"
        subjects = "、".join(str(x) for x in (s.get("subjects") or []))[:36]
        lines.append(
            f"| {s.get('start_sec')}-{s.get('end_sec')}s "
            f"| {zh(s.get('type'))} | {zh(s.get('camera_movement'))} "
            f"| {zh(s.get('energy'))} | {zh(s.get('color_temp'))} "
            f"| {subjects} | {t_out_txt} |")
    return lines


def write_outputs(args, answer: str, parsed, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / Path(args.input).stem

    payload = {
        "input": args.input,
        "task": args.task,
        "model": args.model,
        "device": args.device,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "parsed": parsed,
        "raw_output": answer,
    }
    json_path = base.with_suffix(".analysis.json")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = []
    lines.append(f"# 视觉分析：{Path(args.input).name}")
    if isinstance(parsed, dict):
        if parsed.get("summary"):
            lines.append("")
            lines.append(f"**总结**：{parsed.get('summary')}")
        overview = build_decision_overview(parsed)
        if len(overview) > 1:
            lines.append("")
            lines.extend(overview)
        shots = parsed.get("shots")
        if shots:
            lines.append("")
            lines.append("## 分镜")
            lines.extend(build_shot_table(shots))
            for i, s in enumerate(shots, 1):
                detail = []
                if s.get("composition"):
                    detail.append(f"构图 {s.get('composition')}")
                if s.get("lighting"):
                    detail.append(f"光影 {s.get('lighting')}")
                if s.get("b_roll_use"):
                    detail.append(f"用途 {s.get('b_roll_use')}")
                if s.get("edit_notes"):
                    detail.append(f"剪辑 {s.get('edit_notes')}")
                t_in = s.get("transition_in") or {}
                if t_in.get("type"):
                    detail.append(f"入点转场 {zh(t_in.get('type'))}"
                                  + (f" ({t_in.get('reason')})" if t_in.get("reason") else ""))
                if detail:
                    lines.append(f"- 镜头{i}: " + " · ".join(detail))
        seq = parsed.get("sequence")
        if seq:
            lines.append("")
            lines.append("## 序列决策")
            p = seq.get("pacing") or {}
            if p:
                lines.append(f"- 节奏: {zh(p.get('tempo'))} | 建议镜头时长: "
                             f"{p.get('suggested_cut_duration_sec')}s | {p.get('rhythm')}")
            if seq.get("structure"):
                lines.append(f"- 结构: {zh(seq.get('structure'))}")
            if seq.get("color_flow"):
                lines.append(f"- 色彩走向: {seq.get('color_flow')}")
            if seq.get("strongest_moment_sec") is not None:
                lines.append(f"- 最强时刻: {seq.get('strongest_moment_sec')}s")
            if seq.get("transition_suggestions"):
                lines.append("- 转场方案:")
                lines.extend(f"  - {t}" for t in seq["transition_suggestions"])
            if seq.get("broll_candidates"):
                lines.append("- B-roll 候选:")
                for b in seq["broll_candidates"]:
                    lines.append(f"  - [{b.get('shot_sec')}s] {b.get('use_for')}")
            if seq.get("color_match_scores"):
                lines.append("- 色彩匹配:")
                for m in seq["color_match_scores"]:
                    lines.append(f"  - {m.get('from_sec')}s->{m.get('to_sec')}s 匹配度 {m.get('match')}"
                                 f" — {m.get('note')}")
        if parsed.get("editing_suggestions"):
            lines.append("")
            lines.append("## 剪辑建议")
            lines.extend(f"- {s}" for s in parsed["editing_suggestions"])
        if parsed.get("composition"):
            c = parsed["composition"]
            lines.append("")
            lines.append("## 构图")
            for k in ("framing", "camera_angle", "rule_of_thirds", "depth_of_field", "focal_point"):
                if c.get(k):
                    lines.append(f"- {k}: {zh(c[k])}")
        if parsed.get("lighting"):
            l = parsed["lighting"]
            lines.append("")
            lines.append("## 光影")
            for k in ("direction", "quality", "color_temperature", "contrast", "key_source", "mood"):
                if l.get(k):
                    lines.append(f"- {k}: {zh(l[k])}")
    if not parsed:
        lines.append("")
        lines.append("**原始输出**（未能解析为 JSON）：")
        lines.append(answer)
    lines.append("")
    lines.append(f"完整 JSON：`{json_path}`")

    md_path = base.with_suffix(".analysis.md")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path), "text": "\n".join(lines)}


def main() -> int:
    args = build_parser().parse_args()
    args.device = pick_device(args.device)
    args.model = resolve_model(args.model)

    src = Path(args.input)
    if not src.exists():
        print(f"错误：文件不存在 {args.input}", file=sys.stderr)
        return 1
    kind = detect_kind(args.input)
    if kind == "unknown":
        print(f"错误：无法识别媒体类型（支持的扩展名见脚本头部）", file=sys.stderr)
        return 1

    if args.task == "describe":
        if not args.question:
            print("错误：describe 任务需要 --question", file=sys.stderr)
            return 1
        prompt = args.question
    elif args.task == "video":
        prompt = args.question or VIDEO_PROMPT
    else:
        prompt = args.question or SCENE_PROMPT

    try:
        processor, model = load_model(args.model, args.device)
    except Exception as error:
        print(f"模型加载失败：{error}\n提示：请先运行 scripts/setup.sh 完成部署。", file=sys.stderr)
        return 1

    answer = run_inference(processor, model, args.device, kind, prompt, args)
    parsed = extract_json(answer)

    out_dir = Path(args.output_dir) if args.output_dir else src.parent
    result = write_outputs(args, answer, parsed, out_dir)
    print(result["text"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
