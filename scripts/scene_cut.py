#!/usr/bin/env python
"""场景切点检测：用 HSV 直方图相关性检测视频硬切/叠化切点，
并与 Mage-VL 分镜分析合并，修正分析 JSON 的时间戳。

用法：
  # 只检测切点
  python scene_cut.py --input video.mov

  # 检测切点并合并进已有分镜分析（修正时间戳，生成 .analysis.scenes.json）
  python scene_cut.py --input video.mov --analysis video.analysis.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", required=True, help="视频文件")
    parser.add_argument("--analysis", default=None,
                        help="Mage-VL 生成的 .analysis.json，合并后输出修正版")
    parser.add_argument("--threshold-scale", type=float, default=1.5,
                        help="保留参数：现采用百分位法，此值仅影响提示（可忽略）")
    parser.add_argument("--cut-fraction", type=float, default=0.005,
                        help="切点比例：分数前 cut_fraction 的帧为候选（默认 0.5%，越小切点越少）")
    parser.add_argument("--min-scene-sec", type=float, default=2.0,
                        help="最短镜头时长，小于此值的切点被合并")
    parser.add_argument("--stride", type=int, default=1,
                        help="隔 N 帧处理一帧（长视频提速用）")
    parser.add_argument("--work-width", type=int, default=320,
                        help="检测用的工作分辨率宽度")
    parser.add_argument("--output", default=None, help="修正版 JSON 输出路径")
    return parser


def auto_stride(n_frames: int, fps: float, budget_sec: float = 120.0,
                speed_fps: float = 270.0) -> int:
    """长视频自适应抽帧：保证检测耗时约 budget_sec，且切点分辨率不低于 1/10s。"""
    max_frames = max(1, int(speed_fps * budget_sec))
    stride = max(1, -(-n_frames // max_frames))  # ceil
    stride = min(stride, max(1, int(fps * 0.1)))  # 分辨率下限
    return stride


def scene_distances(video_path: str, work_width: int, stride: int):
    """逐帧计算与前帧的 HSV 直方图距离和边缘(Laplacian)差异（原始值，分位融合在 detect_cuts 做）。
    边缘差异能捕捉"色彩相近但内容不同"的硬切。"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_idx = 0
    prev_hist = None
    prev_edge = None
    rows = []  # (frame_idx, fps, d_hist, d_edge)
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % stride != 0:
            frame_idx += 1
            continue
        h = int(round(frame.shape[0] * work_width / frame.shape[1]))
        small = cv2.resize(frame, (work_width, h), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        edge = cv2.Laplacian(gray, cv2.CV_32F)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [24, 8], [0, 180, 0, 256])
        hist = cv2.normalize(hist, hist).flatten()
        if prev_hist is not None:
            d_hist = 1.0 - cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
            d_edge = float(np.mean(np.abs(edge - prev_edge)))
            rows.append((frame_idx, fps, d_hist, d_edge))
        prev_hist = hist
        prev_edge = edge
        frame_idx += 1
    cap.release()
    return rows, fps, n_frames


def detect_cuts(rows, fps, min_scene_sec, stride=1, cut_fraction=0.005,
                peak_window_sec=0.3):
    """切点检测（尺度无关）：
    - 直方图/边缘两个指标各自算百分位（0-1），融合 score = 0.5*rank_hist + 0.5*rank_edge
    - 取 score 前 cut_fraction 比例的帧为切点候选（默认前 0.5%）
    - 峰值抑制：±peak_window_sec 内只留最强；相邻峰合并为 dissolve
    - 首尾 1% 区域的高值识别为 fade_in / fade_out
    """
    if not rows:
        return [], 0.0, []
    n = len(rows)
    h_vals = np.array([r[2] for r in rows])
    e_vals = np.array([r[3] for r in rows])

    def pct_rank(vals):
        order = np.argsort(np.argsort(vals))
        return order / max(n - 1, 1)

    # max 融合：直方图突变（色彩切点）或边缘突变（同色内容切点）任一强即触发
    score = np.maximum(pct_rank(h_vals), pct_rank(e_vals))
    thr = float(np.percentile(score, 100 * (1.0 - cut_fraction)))
    margin = max(int(n * 0.01), int(fps * 0.5))

    candidates = [i for i in range(margin, n - margin) if score[i] > thr]

    # 峰值抑制：按分数降序，窗口内只留最强
    candidates.sort(key=lambda i: score[i], reverse=True)
    peaks = []
    for i in candidates:
        if all(abs(i - p) * stride / fps > peak_window_sec for p in peaks):
            peaks.append(i)
    peaks.sort()

    # 相邻峰合并为 dissolve（间隔 < 0.5s）
    cuts = []
    for i in peaks:
        if cuts and (rows[i][0] - cuts[-1][0]) / fps < 0.5:
            cuts[-1] = (rows[i][0], "dissolve", score[i])
            continue
        cuts.append((rows[i][0], "cut", score[i]))

    # 合并过短的镜头
    merged = []
    prev_cut_sec = 0.0
    for cf, ctype, conf in cuts:
        if cf / fps - prev_cut_sec < min_scene_sec:
            continue
        prev_cut_sec = cf / fps
        merged.append((cf, ctype, conf))

    # 首尾淡入淡出
    fades = []
    if n > margin * 2:
        head = max(score[i] for i in range(min(margin, n)))
        tail = max(score[i] for i in range(max(margin, n - margin), n))
        if head > thr:
            fades.append(("fade_in", head))
        if tail > thr:
            fades.append(("fade_out", tail))
    return merged, thr, fades


def merge_with_analysis(analysis: dict, cuts_sec: list, n_frames: int, fps: float) -> dict:
    """把检测切点映射到模型分镜上，修正 start/end 时间戳。"""
    total_sec = n_frames / fps if fps else 0
    boundaries = [0.0] + sorted(cuts_sec) + [round(total_sec, 2)]
    parsed = analysis.get("parsed")
    if not isinstance(parsed, dict):
        raise ValueError("analysis 文件里没有 parsed 字段")
    model_shots = parsed.get("shots") or []
    if not model_shots:
        raise ValueError("analysis 文件里没有分镜（shots），无法合并")

    shots = []
    for i in range(len(boundaries) - 1):
        start, end = boundaries[i], boundaries[i + 1]
        mid = (start + end) / 2
        best, best_overlap = None, -1.0
        for ms in model_shots:
            ms_s = float(ms.get("start_sec") or 0)
            ms_e = float(ms.get("end_sec") or total_sec)
            overlap = min(end, ms_e) - max(start, ms_s)
            if overlap > best_overlap:
                best_overlap, best = overlap, ms
        if best is None:
            best = {}
        if best_overlap <= 0:
            # 模型分镜时间戳与切点段无重叠（模型时序估计粗）：按中点最近匹配
            nearest = min(model_shots,
                          key=lambda ms: abs((float(ms.get("start_sec") or 0)
                                              + float(ms.get("end_sec") or total_sec)) / 2 - mid))
            shot = dict(nearest)
        else:
            shot = dict(best)
        shot["start_sec"] = round(start, 2)
        shot["end_sec"] = round(end, 2)
        shot["scene_detected"] = True if best_overlap > 0 else "approximate"
        shots.append(shot)

    new_parsed = dict(parsed)
    new_parsed["shots"] = shots
    result = dict(analysis)
    result["parsed"] = new_parsed
    result["scene_detection"] = {
        "cuts_sec": cuts_sec,
        "total_sec": round(total_sec, 2),
    }
    return result


def main() -> int:
    args = build_parser().parse_args()
    src = Path(args.input)
    if not src.exists():
        print(f"错误：文件不存在 {src}", file=sys.stderr)
        return 1

    t0 = time.time()
    print(f"[scenes] 分析 {src.name} ...", flush=True)
    distances, fps, n_frames = scene_distances(str(src), args.work_width, args.stride)
    cuts, thr, fades = detect_cuts(distances, fps, args.min_scene_sec,
                                   stride=args.stride, cut_fraction=args.cut_fraction)
    total_sec = n_frames / fps
    print(f"[scenes] 共 {n_frames} 帧 / {total_sec:.1f}s，切点分数阈值={thr:.3f}，"
          f"耗时 {time.time()-t0:.0f}s", flush=True)

    if not cuts and not fades:
        print("[scenes] 未检测到切点（整段为单镜头或阈值过高），可调低 --threshold-scale")
        return 0

    if fades:
        print("[scenes] 首尾处理：")
        for fade_type, conf in fades:
            print(f"  {fade_type}  置信度 {conf:.3f}")
    if cuts:
        print("[scenes] 检测到切点：")
        for cf, ctype, conf in cuts:
            print(f"  {cf/fps:7.2f}s  {ctype}  置信度 {conf:.3f}")

    if args.analysis:
        analysis_path = Path(args.analysis)
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        out_path = Path(args.output) if args.output else analysis_path
        out_path = out_path.with_name(out_path.stem + ".scenes.json")
        cuts_sec = sorted(round(cf / fps, 2) for cf, _, _ in cuts)
        result = merge_with_analysis(analysis, cuts_sec, n_frames, fps)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[scenes] 修正版已写入: {out_path}")
        print("[scenes] 修正后的分镜：")
        for s in result["parsed"]["shots"]:
            tag = s.get("scene_detected")
            note = "" if tag is True else f" (scene_detected={tag})"
            print(f"  [{s['start_sec']}-{s['end_sec']}s] {s.get('type')} / "
                  f"{s.get('camera_movement')}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
