# -*- coding: utf-8 -*-
"""本地算法 —— 对应原 DEDD 项目的 LocalTeethOptimizer / 网络检测的本地替代

原版"自动优化/对齐"和"人脸分析/AI检测"依赖作者后端服务器，现已不可用。
这里实现纯本地方案：
  1. optimize_base  —— 口内视图：按美学比例（宽长比）自动优化牙冠高度
  2. align_front    —— 正面视图：中切牙中线对齐 + 左右对称化
  3. detect_face    —— 人脸分析：OpenCV Haar 检测人脸/眼睛，返回旋转角与裁剪框
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np

from .models import Rect2D, Tooth

# 前牙美学宽长比参考（切牙区）
TARGET_RATIO = {
    11: 0.80, 12: 0.75, 13: 0.70,
    21: 0.80, 22: 0.75, 23: 0.70,
}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def optimize_base(teeth: List[Tooth], image_w: int, image_h: int) -> List[Tooth]:
    """口内视图自动优化：
    1) 全部牙齿统一到平均冠长（避免长短不齐）；
    2) 按牙位目标宽长比调整牙冠高度（保持宽度与位置），宽长比优于目标时不缩小。
    """
    if not teeth:
        return list(teeth)
    out: List[Tooth] = []
    lengths = [t.real_length for t in teeth if t.real_length > 0]
    avg_len = sum(lengths) / len(lengths) if lengths else 0.0

    for t in teeth:
        r = t.rect.normalized()
        w = r.width
        h = r.height
        if w <= 0 or h <= 0:
            out.append(t)
            continue
        target = TARGET_RATIO.get(t.site, 0.75)
        # 期望高度 = 宽度 / 目标宽长比
        ideal_h = w / target
        # 若当前宽长比已优于目标（更窄长），保持不变；否则修正为理想高度
        new_h = ideal_h if (w / h) > target else h
        # 限制在图像内
        cy = r.cy
        new_h = min(new_h, image_h * 0.5, h * 1.6)
        y1 = max(0.0, cy - new_h / 2)
        y2 = min(float(image_h), cy + new_h / 2)
        if y2 - y1 < 2:
            y1, y2 = r.y1, r.y2
        new_len = avg_len if avg_len > 0 else t.real_length
        out.append(Tooth(t.site, Rect2D(r.x1, y1, r.x2, y2), new_len))
    return out


def align_front(teeth: List[Tooth], image_w: int, image_h: int) -> List[Tooth]:
    """正面视图自动对齐：
    1) 平移：使 11/21 两中切牙中点连线中心对齐到图像水平中线；
    2) 对称化：12 与 22、13 与 23 相对中线镜像对齐（取双侧平均偏移）；
    3) 切端对齐：同侧相邻牙切端 y 平滑（简化为中切牙对齐）。
    """
    if not teeth:
        return list(teeth)
    out = [Tooth(t.site, t.rect.normalized(), t.real_length) for t in teeth]

    def find(site):
        for t in out:
            if t.site == site:
                return t
        return None

    c11, c21 = find(11), find(21)
    mid = image_w / 2.0
    if c11 is not None and c21 is not None:
        center_x = (c11.rect.cx + c21.rect.cx) / 2.0
    else:
        xs = [t.rect.cx for t in out]
        center_x = sum(xs) / len(xs) if xs else mid
    dx = mid - center_x

    for t in out:
        t.rect = Rect2D(t.rect.x1 + dx, t.rect.y1, t.rect.x2 + dx, t.rect.y2)

    # 左右对称化（13-23 / 12-22 相对中线）
    for l_site, r_site in ((13, 23), (12, 22)):
        l, r = find(l_site), find(r_site)
        if l is None or r is None:
            continue
        l_d = mid - l.rect.cx
        r_d = r.rect.cx - mid
        avg_d = (l_d + r_d) / 2.0
        wl, wr = l.rect.width, r.rect.width
        l.rect = Rect2D(mid - avg_d - wl, l.rect.y1, mid - avg_d, l.rect.y2)
        r.rect = Rect2D(mid + avg_d, r.rect.y1, mid + avg_d + wr, r.rect.y2)

    # 切端(y2)对齐：中切牙切端线取 11/21 均值，侧切牙/尖牙向下略降（微笑曲线）
    if c11 is not None and c21 is not None:
        base_y = (c11.rect.y2 + c21.rect.y2) / 2.0
        for site, drop in ((12, 0.15), (22, 0.15), (13, 0.30), (23, 0.30)):
            t = find(site)
            if t is None:
                continue
            h = t.rect.height
            y2 = min(float(image_h), base_y + drop * h)
            t.rect = Rect2D(t.rect.x1, y2 - h, t.rect.x2, y2)
    return out


def detect_face_and_eyes(image: np.ndarray):
    """人脸分析（本地替代原网络 API）：
    使用 OpenCV Haar 级联检测人脸与眼睛，返回：
      (rotation_deg, crop_box)  或  None（未检测到人脸）
    rotation_deg > 0 表示需顺时针旋转，使眼线水平。
    crop_box = (x, y, w, h) 为包含人脸的区域（适当外扩）。
    """
    import cv2

    if image is None:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    gray_eq = cv2.equalizeHist(gray)

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    eye_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_eye.xml")

    faces = face_cascade.detectMultiScale(gray_eq, 1.1, 5, minSize=(80, 80))
    if len(faces) == 0:
        return None
    # 取最大人脸
    fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])

    # 眼睛检测（取两只眼睛，计算连线角度）
    roi_gray = gray_eq[fy:fy + fh, fx:fx + fw]
    eyes = eye_cascade.detectMultiScale(roi_gray, 1.1, 4, minSize=(20, 20))
    rotation = 0.0
    if len(eyes) >= 2:
        eyes = sorted(eyes, key=lambda e: e[0])
        ex1, ey1 = eyes[0][0] + eyes[0][2] / 2, eyes[0][1] + eyes[0][3] / 2
        ex2, ey2 = eyes[-1][0] + eyes[-1][2] / 2, eyes[-1][1] + eyes[-1][3] / 2
        dx, dy = ex2 - ex1, ey2 - ey1
        if abs(dx) > 1e-6:
            rotation = math.degrees(math.atan2(dy, dx))

    # 裁剪框：人脸外扩（与原版一致：四周各扩 1/3）
    ex = fx - fw // 3
    ey = fy - fh // 3
    ew = fw + 2 * (fw // 3)
    eh = fh + 2 * (fh // 3)
    h, w = image.shape[:2]
    ex = _clamp(ex, 0, max(0, w - 1))
    ey = _clamp(ey, 0, max(0, h - 1))
    ew = min(ew, w - ex)
    eh = min(eh, h - ey)
    return rotation, (ex, ey, ew, eh)


# ---------------------------------------------------------------------------
# AI 牙位检测（本地启发式增强）
#   口内视图：亮度分割出牙列区 → 列投影找牙间谷 → 6 段分牙
#   正面视图：Haar smile 定位嘴部 → 嘴部区域内做同样的亮度分牙
# ---------------------------------------------------------------------------

def _bright_mask(image: np.ndarray):
    """牙齿亮度掩膜：Otsu 二值化 + 开运算去噪；牙齿通常比牙龈/嘴唇亮"""
    import cv2
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, mask = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
    # 掩膜占比过高说明前景/背景反了（如暗底亮边），取反重试
    if mask.mean() / 255.0 > 0.62:
        mask = 255 - mask
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
    return mask


def _split_tooth_boxes(mask: np.ndarray, xl: int, xr: int, n: int = 6):
    """在掩膜 x∈[xl,xr] 区域内把牙列分成 n 段牙位框。

    返回 [(x1, y1, x2, y2), ...]；等分打底，内部边界向最近的投影谷吸附。
    """
    import cv2
    h, w = mask.shape
    if xr - xl < n * 4:
        return []
    roi = mask[:, xl:xr + 1]
    colsum = roi.sum(axis=0) / 255.0
    k = np.ones(5) / 5.0
    cs = np.convolve(colsum, k, mode="same")
    # 谷：列投影的局部最小值（牙齿间隙），相对阈值
    thr = cs.max() * 0.45
    valley = [i for i in range(2, len(cs) - 2) if cs[i] < thr
              and cs[i] <= cs[i - 1] and cs[i] <= cs[i + 1]]
    seg_w = (xr - xl) / n
    # 等分边界 + 向谷吸附
    bounds = [xl + i * seg_w for i in range(n + 1)]
    for i in range(1, n):
        b = bounds[i]
        lo, hi = b - seg_w * 0.35, b + seg_w * 0.35
        near = [xl + v for v in valley if lo <= xl + v <= hi]
        if near:
            bounds[i] = float(min(near, key=lambda v: abs(v - b)))
    boxes = []
    for i in range(n):
        bx1 = int(round(bounds[i]))
        bx2 = int(round(bounds[i + 1]))
        if bx2 - bx1 < 3:
            continue
        seg = mask[:, bx1:bx2]
        ys = np.where(seg.sum(axis=1) / 255.0 > 0)
        if len(ys[0]) == 0:
            continue
        lo, hi = np.percentile(ys[0], 8), np.percentile(ys[0], 92)
        by1 = max(0, int(lo) - 4)
        by2 = min(h - 1, int(hi) + 4)
        boxes.append((float(bx1), float(by1), float(bx2), float(by2)))
    return boxes


def detect_teeth_intraoral(image: np.ndarray, sites=(13, 12, 11, 21, 22, 23)):
    """口内牙列自动检测：返回 [(site, x1, y1, x2, y2), ...]（图像坐标）

    两种场景自适应：
      - 标准牙列照（背景暗/主体即牙列）：Otsu 亮度分割 → 列投影分牙；
      - 白背景牵拉/微笑照（脸为主）：排除背景 → 主体下部+牙齿高光带定位嘴部。
    """
    import cv2
    if image is None:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    mask = _bright_mask(image)

    if mask.mean() / 255.0 > 0.45:
        # ---- 白背景照：背景最亮且占大头，脸为低亮主体 ----
        body = (gray < 215).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        body = cv2.morphologyEx(body, cv2.MORPH_OPEN, kernel, iterations=2)
        rowb = body.sum(axis=1) / 255.0
        if rowb.max() <= 0:
            return []
        rb = np.where(rowb > rowb.max() * 0.15)[0]
        if len(rb) == 0:
            return []
        # 牙齿在主体（脸）下部：取下半 50% 起
        y_top = int(rb[0] + 0.5 * (rb[-1] - rb[0]))
        y_bot = int(rb[-1])
        if y_bot - y_top < 20:
            y_top = int(rb[0])
        # 牙齿高光：仅在脸掩膜内 > 80 分位亮度（且不低于 175），排除白背景
        sub_body = body[y_top:y_bot + 1]
        sub_gray = gray[y_top:y_bot + 1]
        vals = sub_gray[sub_body > 0]
        p80 = float(np.percentile(vals, 80)) if vals.size else 175.0
        tm = ((sub_body > 0) & (sub_gray > max(p80, 175))).astype(np.uint8) * 255
        tm = cv2.morphologyEx(tm, cv2.MORPH_OPEN, kernel, iterations=2)
        col = tm.sum(axis=0) / 255.0
        if col.max() <= 0:
            # 牙齿高光不足：退回主体宽度
            col = sub_body.sum(axis=0) / 255.0
            tm = sub_body
        # 中央能量带：取包含中央 76% 列能量的区间（排除两侧背景晕影/杂物）
        csum = np.cumsum(col)
        total = csum[-1] if csum.size else 0.0
        if total <= 0:
            return []
        xl = int(np.searchsorted(csum, total * 0.12))
        xr = int(np.searchsorted(csum, total * 0.88))
        xl = max(0, min(xl, w - 1))
        xr = max(xl + 1, min(xr, w - 1))
        if xr - xl < 20:
            return []
        boxes = _split_tooth_boxes(tm, xl, xr, len(sites))
        if len(boxes) < len(sites):
            seg_w = (xr - xl) / len(sites)
            boxes = [(xl + i * seg_w, 0.0, xl + (i + 1) * seg_w, float(tm.shape[0] - 1))
                     for i in range(len(sites))]
        # 每框 y 用牙齿高光行带约束（贴牙冠）
        rowt = tm.sum(axis=1) / 255.0
        rt = np.where(rowt > rowt.max() * 0.15)[0] if rowt.max() > 0 else np.array([])
        if len(rt) > 0:
            ty1, ty2 = int(rt[0]), int(rt[-1])
            return [(sites[i],
                     max(0.0, b[0]),
                     float(y_top + ty1 - 4),
                     min(float(w), b[2]),
                     float(y_top + ty2 + 4))
                    for i, b in enumerate(boxes) if i < len(sites)]
        return [(sites[i], b[0], float(y_top + b[1]), b[2], float(y_top + b[3]))
                for i, b in enumerate(boxes) if i < len(sites)]

    # ---- 标准牙列照（背景暗/牙列即主体）----
    rowsum = mask.sum(axis=1) / 255.0
    rows = np.where(rowsum > rowsum.max() * 0.25)[0] if rowsum.max() > 0 else np.array([])
    if len(rows) == 0:
        return []
    y_top, y_bot = int(rows[0]), int(rows[-1])
    roi_y = mask[y_top:y_bot + 1, :]
    colsum = roi_y.sum(axis=0) / 255.0
    k = np.ones(5) / 5.0
    cs = np.convolve(colsum, k, mode="same")
    xs = np.where(cs > cs.max() * 0.25)[0] if cs.max() > 0 else np.array([])
    if len(xs) == 0:
        return []
    xl, xr = int(xs[0]), int(xs[-1])
    boxes = _split_tooth_boxes(mask, xl, xr, len(sites))
    if len(boxes) < len(sites):
        # 分牙失败：退化为等分
        seg_w = (xr - xl) / len(sites)
        boxes = []
        for i in range(len(sites)):
            bx1, bx2 = xl + i * seg_w, xl + (i + 1) * seg_w
            seg = mask[y_top:y_bot + 1, int(bx1):int(bx2)]
            ys = np.where(seg.sum(axis=1) / 255.0 > 0)
            if len(ys[0]) == 0:
                continue
            lo, hi = np.percentile(ys[0], 8), np.percentile(ys[0], 92)
            boxes.append((float(bx1), float(y_top + lo - 4), float(bx2), float(y_top + hi + 4)))
    return [(sites[i], b[0], b[1], b[2], b[3]) for i, b in enumerate(boxes) if i < len(sites)]


def detect_teeth_front(image: np.ndarray, sites=(13, 12, 11, 21, 22, 23)):
    """正面视图自动检测：优先 Haar smile 定位嘴部 → 嘴部区域内亮度分牙；
    无笑脸时回退到图像下半中央区（露齿照也适用）。
    返回 [(site, x1, y1, x2, y2), ...]（图像坐标）"""
    import cv2
    if image is None:
        return []
    h, w = image.shape[:2]
    roi = None
    ox = oy = 0
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    smile = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_smile.xml")
    smiles = smile.detectMultiScale(gray, 1.7, 18, minSize=(50, 50))
    if len(smiles) > 0:
        x, y, rw, rh = max(smiles, key=lambda s: s[2] * s[3])
        roi = image[y:y + rh, x:x + rw]
        ox, oy = x, y
    else:
        # 回退：下半部中央区域（牙齿通常在笑线/嘴部）
        rx1, ry1 = int(w * 0.15), int(h * 0.52)
        rx2, ry2 = int(w * 0.85), int(h * 0.96)
        if rx2 - rx1 < 60 or ry2 - ry1 < 30:
            return []
        roi = image[ry1:ry2, rx1:rx2]
        ox, oy = rx1, ry1
    mask = _bright_mask(roi)
    rw, rh = roi.shape[1], roi.shape[0]
    boxes = _split_tooth_boxes(mask, 0, rw - 1, len(sites))
    if len(boxes) < len(sites):
        # 退化：等分（原行为）
        tw = rw / len(sites)
        boxes = [(i * tw, rh * 0.05, (i + 1) * tw, rh * 1.05) for i in range(len(sites))]
    return [(sites[i], ox + b[0], oy + b[1], ox + b[2], oy + b[3]) for i, b in enumerate(boxes)]
