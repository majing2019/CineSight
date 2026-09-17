#!/usr/bin/env python3
"""Detect candidate cuts with HSV histogram and edge-difference signals."""
import argparse, json
from pathlib import Path
try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

def distances(path, width, stride):
    cap = cv2.VideoCapture(str(path)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    rows=[]; prev_h=None; prev_e=None; i=0
    while True:
        ok, frame=cap.read()
        if not ok: break
        if i % stride: i += 1; continue
        h=max(1, round(frame.shape[0]*width/frame.shape[1])); small=cv2.resize(frame,(width,h))
        hsv=cv2.cvtColor(small,cv2.COLOR_BGR2HSV); hist=cv2.normalize(cv2.calcHist([hsv],[0,1],None,[24,8],[0,180,0,256]),None).flatten()
        edge=cv2.Laplacian(cv2.cvtColor(small,cv2.COLOR_BGR2GRAY),cv2.CV_32F)
        if prev_h is not None: rows.append((i,1.0-cv2.compareHist(prev_h,hist,cv2.HISTCMP_CORREL),float(np.mean(np.abs(edge-prev_e)))))
        prev_h,prev_e=hist,edge; i+=1
    cap.release(); return rows,fps,i

def auto_stride(n_frames, fps, budget_sec=120.0, speed_fps=270.0):
    max_frames=max(1,int(speed_fps*budget_sec))
    stride=max(1,-(-n_frames//max_frames))
    return min(stride,max(1,int(fps*.1)))

def main():
    if cv2 is None:
        raise SystemExit("detect_cuts.py 需要 OpenCV：python -m pip install opencv-python numpy；不需要安装任何本地模型。")
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--cut-fraction", type=float, default=0.01)
    p.add_argument("--min-scene-sec", type=float, default=2.0)
    p.add_argument("--stride", type=int, default=1)
    p.add_argument("--auto-stride", action="store_true", help="按视频长度自动选择 stride")
    p.add_argument("--work-width", type=int, default=320)
    p.add_argument("--analysis", default=None, help="兼容 CineSight 的分析 JSON；合并切点后写 .scenes.json")
    p.add_argument("--output", default=None)
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    # Probe once so long clips can use the same bounded-cost behavior as CineSight.
    probe=cv2.VideoCapture(a.input); n_probe=int(probe.get(cv2.CAP_PROP_FRAME_COUNT)); fps_probe=probe.get(cv2.CAP_PROP_FPS) or 30.0; probe.release()
    stride=auto_stride(n_probe,fps_probe) if a.auto_stride else max(1,a.stride)
    rows,fps,n=distances(Path(a.input),a.work_width,stride)
    if not rows: return
    h=np.array([x[1] for x in rows]); e=np.array([x[2] for x in rows])
    rank=lambda x: np.argsort(np.argsort(x))/max(len(x)-1,1)
    score=np.maximum(rank(h),rank(e)); threshold=float(np.percentile(score,100*(1-a.cut_fraction)))
    margin=max(int(len(rows)*.01),int(fps*.5)); cand=[i for i in range(margin,len(rows)-margin) if score[i]>threshold]
    peaks=[]
    for i in sorted(cand,key=lambda j:score[j],reverse=True):
        if all(abs(i-j)*a.stride/fps>.3 for j in peaks): peaks.append(i)
    cuts=[]; last=0.0
    previous=None
    for i in sorted(peaks):
        sec=rows[i][0]/fps
        if sec-last<a.min_scene_sec: continue
        kind="dissolve" if previous is not None and sec-previous<0.5 else "cut"
        cuts.append({"sec":round(sec,2),"type":kind,"confidence":round(float(score[i]),4)}); last=sec; previous=sec
    total=round(n/fps,2); margin=max(int(len(rows)*.01),int(fps*.5))
    fades=[]
    if len(rows)>margin*2:
        if max(score[:margin])>threshold: fades.append({"type":"fade_in","confidence":round(float(max(score[:margin])),4)})
        if max(score[-margin:])>threshold: fades.append({"type":"fade_out","confidence":round(float(max(score[-margin:])),4)})
    result={"cuts_sec":[x["sec"] for x in cuts],"cuts":cuts,"fades":fades,"total_sec":total,"threshold":round(threshold,4),"stride":stride,"method":"hsv_histogram+laplacian_edge"}
    if a.analysis:
        source=json.loads(Path(a.analysis).read_text(encoding="utf-8")); parsed=source.get("parsed") or {}
        model_shots=parsed.get("shots") or []; boundaries=[0.0,*result["cuts_sec"],result["total_sec"]]; shots=[]
        for start,end in zip(boundaries,boundaries[1:]):
            overlaps=[(min(end,float(s.get("end_sec",end)))-max(start,float(s.get("start_sec",0))),s) for s in model_shots]
            shot=dict(max(overlaps,key=lambda x:x[0])[1]) if overlaps else {}
            shot.update(start_sec=start,end_sec=end,timestamp_basis="scene_detected",scene_detected=True); shots.append(shot)
        parsed["shots"]=shots; source["parsed"]=parsed; source["scene_detection"]=result
        target=Path(a.output) if a.output else Path(a.analysis).with_name(Path(a.analysis).stem+".scenes.json")
        target.write_text(json.dumps(source,ensure_ascii=False,indent=2),encoding="utf-8"); print(target)
    elif a.json: print(json.dumps(result,ensure_ascii=False))
    else: print("\n".join(map(str,cuts)))

if __name__ == "__main__": main()
