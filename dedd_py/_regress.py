# -*- coding: utf-8 -*-
"""AI 牙位检测回归测试：批量扫描样本库 → 检测 → 标注图 + 报告 + 拼图预览
用法：双击 回归测试.bat（或手动：dedd 环境 python _regress.py）
"""
import os
import sys
import time
import glob

import cv2
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from dedd.optimizer import detect_teeth_front, detect_teeth_intraoral

SAMPLE_DIR = os.path.join(BASE, "样本库")
OUT_DIR = os.path.join(BASE, "_regress_out")
EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
SITES = (13, 12, 11, 21, 22, 23)


def list_images(sub):
    d = os.path.join(SAMPLE_DIR, sub)
    if not os.path.isdir(d):
        return []
    files = set()
    for ext in EXTS:
        files |= set(glob.glob(os.path.join(d, "*" + ext)))
        files |= set(glob.glob(os.path.join(d, "*" + ext.upper())))
    return sorted(files)


def imread_unicode(path):
    """支持中文路径读图（cv2.imread 不支持非 ASCII 路径）"""
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def imwrite_unicode(path, img):
    """支持中文路径写图"""
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, img)
    if ok:
        buf.tofile(path)
    return ok


def check_boxes(boxes, h, w):
    """合理性检查，返回预警列表（空=通过）"""
    warns = []
    if len(boxes) < len(SITES):
        warns.append(f"少框({len(boxes)}/{len(SITES)})")
        return warns
    y1s = [b[2] for b in boxes]
    y2s = [b[3] for b in boxes]
    x1s = [b[1] for b in boxes]
    x2s = [b[4] for b in boxes]
    bh = max(y2s) - min(y1s)
    bw = max(x2s) - min(x1s)
    if bh > h * 0.25:
        warns.append(f"框过高({bh / h:.0%}图高)")
    if max(y1s) - min(y1s) > h * 0.05:
        warns.append(f"切缘未对齐({max(y1s) - min(y1s)}px)")
    if bw < w * 0.10:
        warns.append(f"牙列过窄({bw / w:.0%}图宽)")
    if bw > w * 0.80:
        warns.append(f"牙列过宽({bw / w:.0%}图宽)")
    if boxes[0][1] < w * 0.02 or boxes[-1][4] > w * 0.98:
        warns.append("牙列贴边(疑漏牙)")
    return warns


def draw_boxes(img, boxes, h, w):
    out = img.copy()
    scale = max(w, h) / 900.0
    fs = max(10, int(14 / scale)) if scale > 0 else 14
    for site, x1, y1, x2, y2 in boxes:
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), max(2, int(3 / scale)))
        cv2.putText(out, str(site), (x1, max(10, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 200, 255), 2)
    return out


def make_grid(images, cols=4, cell=560):
    """标注图拼网格（自适应行列）"""
    if not images:
        return None
    rows = (len(images) + cols - 1) // cols
    # 统一缩放为方形格子
    cells = []
    for img in images:
        h, w = img.shape[:2]
        s = cell / max(h, w)
        cells.append(cv2.resize(img, (int(w * s), int(h * s))))
    grid_h = cell * rows
    grid_w = cell * cols
    grid = np.full((grid_h, grid_w, 3), 255, np.uint8)
    for i, c in enumerate(cells):
        r, col = divmod(i, cols)
        y0, x0 = r * cell, col * cell
        grid[y0:y0 + c.shape[0], x0:x0 + c.shape[1]] = c
    return grid


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    # 清空上次输出
    for f in glob.glob(os.path.join(OUT_DIR, "*")):
        try:
            os.remove(f)
        except OSError:
            pass

    groups = [("口内", "口内", detect_teeth_intraoral),
              ("正面", "正面", detect_teeth_front)]
    report = []
    all_imgs = []
    total_fail = 0
    total_warn = 0

    for sub, label, fn in groups:
        files = list_images(sub)
        report.append(f"【{label}视图】共 {len(files)} 张")
        if not files:
            report.append("  （空目录，请把照片放进 样本库\\口内\\ 或 样本库\\正面\\）")
        for path in files:
            name = os.path.splitext(os.path.basename(path))[0]
            try:
                img = imread_unicode(path)
                if img is None:
                    report.append(f"  {name} | 读取失败")
                    total_fail += 1
                    continue
                h, w = img.shape[:2]
                t0 = time.time()
                boxes = fn(img)
                dt = time.time() - t0
                warns = check_boxes(boxes, h, w)
                marked = draw_boxes(img, boxes, h, w)
                out_path = os.path.join(OUT_DIR, f"{label}_{name}.png")
                imwrite_unicode(out_path, marked)
                all_imgs.append(marked)
                status = "PASS" if not warns else "预警"
                if warns:
                    total_warn += 1
                if len(boxes) < len(SITES):
                    total_fail += 1
                report.append(f"  {name} | {len(boxes)}框 | {dt * 1000:.0f}ms | {status}"
                              + (f" | {'; '.join(warns)}" if warns else ""))
            except Exception as e:  # noqa: BLE001
                report.append(f"  {name} | 异常: {e}")
                total_fail += 1

        report.append("")

    report.append("=" * 46)
    report.append(f"汇总：共处理 {sum(len(list_images(g[0])) for g in groups)} 张，"
                  f"失败 {total_fail} 张，预警 {total_warn} 张")
    report.append("PASS=通过（无预警）；预警=疑测偏需看图确认；少框=检测失败")

    with open(os.path.join(OUT_DIR, "报告.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    grid = make_grid(all_imgs)
    if grid is not None:
        imwrite_unicode(os.path.join(OUT_DIR, "拼图预览.png"), grid)

    print("\n".join(report))
    print(f"\n输出目录: {OUT_DIR}")
    if total_fail or total_warn:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
