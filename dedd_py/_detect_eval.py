# -*- coding: utf-8 -*-
"""检测精度评测：对示例照片跑 AI 检测，输出指标 + 标注图，便于前后对比

用法：python _detect_eval.py [out_dir]
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dedd.optimizer import detect_teeth_front, detect_teeth_intraoral

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.environ.get("TEMP", r"C:\Users\Gong\AppData\Local\Temp"), "detect_eval")

CASES = [
    (os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "patient_retracted.jpg"), "intra"),
    (os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "retracted.JPG"), "intra"),
    (os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "patient_smile.jpg"), "front"),
    (os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "smile.JPG"), "front"),
]


def metrics(boxes):
    """无真值情况下的合理性指标"""
    if not boxes:
        return {"n": 0}
    xs1 = np.array([b[1] for b in boxes], float)
    ys1 = np.array([b[2] for b in boxes], float)
    xs2 = np.array([b[3] for b in boxes], float)
    ys2 = np.array([b[4] for b in boxes], float)
    w = xs2 - xs1
    h = ys2 - ys1
    order = np.argsort(xs1)
    gaps = xs1[order][1:] - xs2[order][:-1]        # 相邻框水平间隙（负=重叠）
    return {
        "n": len(boxes),
        "w": (w.mean(), w.std()),
        "h": (h.mean(), h.std()),
        "h_cv": float(h.std() / h.mean()) if h.mean() else 9.9,
        "gap_mean": float(gaps.mean()) if gaps.size else 0.0,
        "gap_max": float(gaps.max()) if gaps.size else 0.0,
        "overlap": int((gaps < -1).sum()),
        "w_ratio": float(w.max() / max(1.0, w.min())),
        "y_top_std": float(ys1.std()),
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    for path, kind in CASES:
        if not os.path.exists(path):
            print("缺图:", path)
            continue
        img = cv2.imread(path)
        boxes = detect_teeth_intraoral(img) if kind == "intra" else detect_teeth_front(img)
        m = metrics(boxes)
        name = os.path.basename(path)
        print(f"{name:24s} {kind:5s} n={m['n']}", end="")
        if m["n"]:
            print(f"  h_cv={m['h_cv']:.3f} gap={m['gap_mean']:.1f}/{m['gap_max']:.1f}"
                  f"  overlap={m['overlap']} w_ratio={m['w_ratio']:.2f}")
        else:
            print()
        vis = img.copy()
        for site, x1, y1, x2, y2 in boxes:
            cv2.rectangle(vis, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 255), 3)
            cv2.putText(vis, str(site), (int(x1) + 4, int(y1) + 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
            cv2.putText(vis, str(site), (int(x1) + 4, int(y1) + 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        out = os.path.join(OUT, f"{kind}_{os.path.splitext(name)[0]}.jpg")
        cv2.imwrite(out, vis)
        print("   ->", out)


if __name__ == "__main__":
    main()
