#!/usr/bin/env python
"""批量分析脚本：一次加载模型，顺序分析一个文件夹里的所有图片/视频，
产出每份 .analysis.json + .analysis.md，并汇总一份 CSV 剪辑清单。

用法：
  python batch.py --dir ~/Desktop/新疆素材分类
  python batch.py --dir ~/Desktop/素材 --ext mp4,mov --task video --num-frames 8
  python batch.py --dir ~/Desktop/素材 --max-new-tokens 600   # 内存紧张时调小
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze as mage
import scene_cut

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".ts"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", required=True, help="待分析素材目录")
    parser.add_argument("--ext", default=None,
                        help="限定扩展名（逗号分隔，如 mp4,mov；默认图片+视频都分析）")
    parser.add_argument("--task", choices=("scene", "video"), default=None,
                        help="默认：图片用 scene，视频用 video")
    parser.add_argument("--num-frames", type=int, default=8, help="视频抽帧数（省内存设小）")
    parser.add_argument("--max-new-tokens", type=int, default=600,
                        help="生成 token 上限（内存紧张时调小到 400-500）")
    parser.add_argument("--output-dir", default=None, help="分析结果输出目录，默认=素材目录")
    parser.add_argument("--skip-existing", action="store_true",
                        help="跳过已有分析文件的素材（断点续跑）")
    parser.add_argument("--no-scene-cuts", action="store_true",
                        help="视频分析后不自动做精确切点检测（默认自动补）")
    parser.add_argument("--cut-fraction", type=float, default=0.01,
                        help="切点灵敏度：分数前 cut_fraction 的帧为候选（默认 0.01，越小越少）")
    return parser


def _probe_frame_count(video_path: Path) -> int:
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.release()
    return n


def _run_scene_cuts(video_path: Path, analysis_json: str, args) -> str:
    """对已分析的视频补精确切点检测，返回切点 JSON 路径（无切点则空串）。"""
    import json
    t0 = time.time()
    n_frames, fps = _probe_frame_count(video_path), None
    rows, fps, n_frames = scene_cut.scene_distances(
        str(video_path), 320, scene_cut.auto_stride(n_frames, fps or 30.0))
    cuts, thr, fades = scene_cut.detect_cuts(rows, fps, min_scene_sec=2.0,
                                             cut_fraction=args.cut_fraction)
    if not cuts:
        return ""
    analysis = json.loads(Path(analysis_json).read_text(encoding="utf-8"))
    cuts_sec = sorted(round(cf / fps, 2) for cf, _, _ in cuts)
    result = scene_cut.merge_with_analysis(analysis, cuts_sec, n_frames, fps)
    scenes_path = Path(analysis_json).with_name(Path(analysis_json).stem + ".scenes.json")
    scenes_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  切点检测: {len(cuts)} 个切点 + {len(fades)} 处淡入淡出，"
          f"耗时 {time.time()-t0:.0f}s -> {scenes_path.name}", flush=True)
    return str(scenes_path)


def main() -> int:
    args = build_parser().parse_args()
    src_dir = Path(args.dir)
    if not src_dir.is_dir():
        print(f"错误：目录不存在 {src_dir}", file=sys.stderr)
        return 1

    exts = set()
    if args.ext:
        exts = {("." + e.strip().lstrip(".").lower()) for e in args.ext.split(",")}
    candidates = [p for p in sorted(src_dir.iterdir()) if p.is_file() and (
        not exts or p.suffix.lower() in exts
    )]
    media = []
    for p in candidates:
        kind = mage.detect_kind(str(p))
        if kind in ("image", "video"):
            media.append((p, kind))
    if not media:
        print(f"目录里没有可分析的媒体文件: {src_dir}", file=sys.stderr)
        return 1

    out_dir = Path(args.output_dir) if args.output_dir else src_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    todo = []
    for p, kind in media:
        if args.skip_existing and (p.parent / f"{p.stem}.analysis.json").exists():
            print(f"[skip] {p.name}（已有分析）")
            continue
        todo.append((p, kind))

    print(f"待分析 {len(todo)}/{len(media)} 个文件 -> 输出到 {out_dir}")

    processor, model = None, None
    results = []
    t_start = time.time()
    for i, (p, kind) in enumerate(todo, 1):
        task = args.task or ("scene" if kind == "image" else "video")
        print(f"\n[{i}/{len(todo)}] 分析 {p.name} ({kind}, task={task}) ...", flush=True)
        t0 = time.time()
        try:
            if processor is None:
                processor, model = mage.load_model(mage.resolve_model(None), "mps")
            prompt = mage.VIDEO_PROMPT if task == "video" else mage.SCENE_PROMPT
            ns = type("A", (), {})()
            ns.input = str(p)
            ns.task = task
            ns.model = mage.resolve_model(None)
            ns.device = "mps"
            ns.num_frames = args.num_frames
            ns.max_pixels = mage.ARGS_MAX_PIXELS
            ns.video_max_pixels = 38400
            ns.max_new_tokens = args.max_new_tokens
            ns.lang = "zh"
            ns.output_dir = str(out_dir)
            answer = mage.run_inference(processor, model, "mps", kind, prompt, ns)
            parsed = mage.extract_json(answer)
            if parsed is None and task == "video":
                # JSON 被截断：用更多 token 重试一次
                print("  JSON 解析失败（可能被截断），增加 token 重试...", flush=True)
                ns.max_new_tokens = args.max_new_tokens + 400
                answer = mage.run_inference(processor, model, "mps", kind, prompt, ns)
                parsed = mage.extract_json(answer)
            out = mage.write_outputs(ns, answer, parsed, out_dir)
            scenes_path = ""
            if kind == "video" and not args.no_scene_cuts:
                scenes_path = _run_scene_cuts(p, out["json"], args)
            results.append((p.name, kind, "ok", f"{time.time()-t0:.0f}s", out["json"],
                            scenes_path))
            print(f"完成 {p.name}，耗时 {time.time()-t0:.0f}s", flush=True)
        except Exception as error:
            results.append((p.name, kind, "error", f"{time.time()-t0:.0f}s",
                            str(error)[:200], ""))
            print(f"失败 {p.name}: {error}", file=sys.stderr, flush=True)

    csv_path = out_dir / "分析清单.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["文件", "类型", "状态", "耗时", "分析JSON", "切点JSON", "备注"])
        for row in results:
            note = ""
            if row[2] == "ok" and row[1] == "video" and not row[5]:
                note = "未做切点检测（无切点或 --no-scene-cuts）"
            w.writerow([*row[:6], note])

    overview = build_overview_md(todo, results, out_dir)
    overview_path = out_dir / "分析总览.md"
    overview_path.write_text(overview, encoding="utf-8")

    print(f"\n全部完成：{sum(1 for r in results if r[2]=='ok')}/{len(results)} 成功，"
          f"总耗时 {time.time()-t_start:.0f}s")
    print(f"汇总清单: {csv_path}")
    print(f"分析总览: {overview_path}")
    return 0


def build_overview_md(todo, results, out_dir: Path) -> str:
    """素材总览：全部素材索引表 + 每段一句话总结 + 链接到详细分析。"""
    lines = ["# 素材分析总览", ""]
    lines.append(f"共 {len(todo)} 个素材，生成于 {time.strftime('%Y-%m-%d %H:%M')}。")
    lines.append("")
    lines.append("| 文件 | 时长 | 总结 | 详细 |")
    lines.append("|---|---|---|---|")
    ok_by_name = {r[0]: r for r in results if r[2] == "ok"}
    for p, kind in todo:
        name = p.name
        row = ok_by_name.get(name)
        detail = "—"
        summary = "分析失败"
        if row:
            try:
                import json
                data = json.loads(Path(row[4]).read_text(encoding="utf-8"))
                parsed = data.get("parsed") or {}
                summary = str(parsed.get("summary") or "（无总结）")
                md_name = Path(row[4]).stem + ".md"
                detail = f"[md]({md_name})"
            except Exception:
                summary = "分析失败"
        lines.append(f"| {name} | {kind} | {summary} | {detail} |")
    lines.append("")
    lines.append("> 字段说明：总结为模型对素材内容的一句话描述；"
                 "各素材的构图/光影/转场/色彩匹配决策见对应的 .analysis.md。")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
