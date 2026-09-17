#!/usr/bin/env python3
"""Extract evenly spaced video frames for Codex visual inspection."""
import argparse, json, shutil, subprocess
from pathlib import Path

def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout

def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--output-dir", default=None)
    p.add_argument("--num-frames", type=int, default=12)
    p.add_argument("--width", type=int, default=640)
    a = p.parse_args()
    src = Path(a.input).expanduser().resolve()
    if not src.is_file(): raise SystemExit(f"input not found: {src}")
    out = Path(a.output_dir).expanduser().resolve() if a.output_dir else src.parent / f".{src.stem}.cinesight-frames"
    out.mkdir(parents=True, exist_ok=True)
    probe = json.loads(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(src)))
    duration = float(probe["format"]["duration"])
    n = max(1, a.num_frames)
    times = [0.0 if n == 1 else duration * i / (n - 1) for i in range(n)]
    for i, t in enumerate(times):
        target = out / f"frame_{i:04d}.jpg"
        subprocess.run(["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1", "-vf", f"scale={a.width}:-2", "-q:v", "2", str(target)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (out / "manifest.json").write_text(json.dumps({"input": str(src), "duration_sec": duration, "frames": [{"path": str(out / f"frame_{i:04d}.jpg"), "time_sec": round(t, 3)} for i, t in enumerate(times)]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out / "manifest.json")

if __name__ == "__main__": main()
