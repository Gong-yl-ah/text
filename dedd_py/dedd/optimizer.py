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


# 前牙宽度比例（相对中切牙=1.0，按口腔解剖均值：尖牙0.93/侧切牙0.78/中切牙1.0）
# 排列：13 12 11 | 21 22 23
FRONT_TOOTH_RATIOS = (0.93, 0.78, 1.0, 1.0, 0.78, 0.93)


def _ratio_bounds(xl: int, xr: int, ratios):
    """按宽度比例把 [xl,xr] 分成 len(ratios) 段的边界列表（n+1 个）"""
    total = float(sum(ratios))
    bounds = [float(xl)]
    acc = 0.0
    for r in ratios[:-1]:
        acc += r
        bounds.append(xl + (xr - xl) * acc / total)
    bounds.append(float(xr))
    return bounds


def _split_tooth_boxes(mask: np.ndarray, xl: int, xr: int, n: int = 6):
    """在掩膜 x∈[xl,xr] 区域内把牙列分成 n 段牙位框。

    返回 [(x1, y1, x2, y2), ...]；按前牙宽度比例打底（更贴合中切牙宽/侧切牙窄），
    内部边界向最近的投影谷吸附。
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
    # 比例打底边界（缺牙段时退化为等分）
    ratios = FRONT_TOOTH_RATIOS[:n] if n <= len(FRONT_TOOTH_RATIOS) else None
    if ratios:
        bounds = _ratio_bounds(xl, xr, ratios)
    else:
        seg_w = (xr - xl) / n
        bounds = [xl + i * seg_w for i in range(n + 1)]
    seg_w = (xr - xl) / n
    # 边界向谷吸附
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


def _downscale_teeth(image: np.ndarray, max_dim: int = 1600):
    """大图降采样提速，返回 (小图, 缩放比例)；坐标换算用原坐标 = 小图坐标 / scale"""
    h, w = image.shape[:2]
    scale = 1.0
    if max(h, w) > max_dim:
        scale = max_dim / float(max(h, w))
        import cv2
        image = cv2.resize(image, (int(round(w * scale)), int(round(h * scale))),
                           interpolation=cv2.INTER_AREA)
    return image, scale


def _locate_smile_roi(gray: np.ndarray):
    """仅 Haar smile → 嘴框略扩；无 → None"""
    import cv2
    h, w = gray.shape
    smile = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_smile.xml")
    mw, mh = max(30, int(w * 0.08)), max(20, int(h * 0.04))
    for min_nei in (12, 8, 5):
        ss = smile.detectMultiScale(gray, 1.5, min_nei, minSize=(mw, mh))
        if len(ss) > 0:
            x, y, rw, rh = max(ss, key=lambda s: s[2] * s[3])
            return (max(0, x - int(rw * 0.1)), max(0, y - int(rh * 0.15)),
                    min(w, x + rw + int(rw * 0.1)), min(h, y + rh + int(rh * 0.15)))
    return None


def _locate_face_roi(gray: np.ndarray):
    """仅 Haar face → 脸框 0.40~0.92（嘴/上前牙带）；无 → None"""
    import cv2
    h, w = gray.shape
    face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    fs = face.detectMultiScale(gray, 1.1, 5, minSize=(max(40, int(w * 0.12)), max(40, int(h * 0.12))))
    if len(fs) > 0:
        fx, fy, fw, fh = max(fs, key=lambda s: s[2] * s[3])
        return (fx, int(fy + 0.40 * fh), fx + fw, int(fy + 0.92 * fh))
    return None


def _locate_mouth_roi(gray: np.ndarray):
    """定位嘴部 ROI（smile → face → None）"""
    roi = _locate_smile_roi(gray)
    if roi is None:
        roi = _locate_face_roi(gray)
    return roi


def _teeth_mask(roi: np.ndarray) -> np.ndarray:
    """牙齿掩膜：低饱和+高亮（牙/瓷白）与亮度高分位双信号合并"""
    import cv2
    gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
    S, V = hsv[:, :, 1].astype(np.float32), hsv[:, :, 2].astype(np.float32)
    m1 = ((S < 60) & (V > 150)).astype(np.uint8) * 255
    body = V > 60
    vals = gray[body]
    if vals.size:
        thr = max(float(np.percentile(vals, 85)), 165.0)
    else:
        thr = 180.0
    m2 = ((V > thr) & (S < 120)).astype(np.uint8) * 255
    m = cv2.bitwise_or(m1, m2)
    # 排除近白背景（白底照）：V>232 整块剔除，避免背景压过牙齿带
    m[V > 232] = 0
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel, iterations=2)
    return m


def _tooth_band(mask: np.ndarray):
    """在掩膜上找牙齿横带：行/列投影的峰值窗口（牙齿是最亮的横带，非最长带）
    返回 (yy1, yy2, xx1, xx2)（掩膜坐标）或 None"""
    rh, rw = mask.shape
    rowt = mask.sum(axis=1) / 255.0
    rowt = np.convolve(rowt, np.ones(5) / 5.0, mode="same")
    if rowt.max() <= 0:
        return None
    arg = int(np.argmax(rowt))
    peak = rowt[arg]
    # 上前牙先验：峰值落在 ROI 底部（>72%）时，优先取上半部的最强带
    if arg > rh * 0.72:
        top = rowt[:int(rh * 0.7)]
        if top.size and top.max() > peak * 0.5:
            arg = int(np.argmax(top))
            peak = rowt[arg]
    yy1 = arg
    while yy1 > 0 and rowt[yy1 - 1] > peak * 0.5:
        yy1 -= 1
    yy2 = arg
    while yy2 < rh - 1 and rowt[yy2 + 1] > peak * 0.5:
        yy2 += 1
    if yy2 - yy1 < 6:
        return None
    band = mask[yy1:yy2 + 1]
    col = band.sum(axis=0) / 255.0
    col = np.convolve(col, np.ones(5) / 5.0, mode="same")
    if col.max() <= 0:
        return None
    csum = np.cumsum(col)
    total = csum[-1]
    if total <= 0:
        return None
    xx1 = int(np.searchsorted(csum, total * 0.06))
    xx2 = int(np.searchsorted(csum, total * 0.94))
    xx1 = max(0, min(xx1, rw - 1))
    xx2 = max(xx1 + 1, min(xx2, rw - 1))
    if xx2 - xx1 < 20:
        return None
    return yy1, yy2, xx1, xx2


def _anatomy_limit(boxes, sites):
    """解剖限高（保留给旧退化路径）：以中切牙段（11/21）框高为基准，
    尖牙≤1.4×、侧切牙≤1.25×，超高则从下缘裁掉（保留切缘上缘）。"""
    hc = None
    for i, (site, x1, y1, x2, y2) in enumerate(boxes):
        if site in (11, 21):
            hc = y2 - y1
            break
    if not hc or hc <= 0:
        return boxes
    out = []
    for i, (site, x1, y1, x2, y2) in enumerate(boxes):
        limit = hc * (1.25 if site in (12, 22) else 1.4)
        if (y2 - y1) > limit:
            y2 = y1 + int(limit)
        out.append((site, x1, y1, x2, y2))
    return out


def _seg_y_by_gray(gray: np.ndarray, yy1: int, yy2: int, xx1: int, xx2: int):
    """行带内该 x 段的灰度行分布 → 框 y 范围（牙齿行最亮，比掩膜行分布鲁棒）"""
    seg = gray[yy1:yy2 + 1, xx1:xx2].mean(axis=1)
    peak = seg.max()
    if peak <= 0:
        return yy1, yy2
    m = seg > peak * 0.4
    ys = np.where(m)[0]
    if len(ys) < 3:
        return yy1, yy2
    return yy1 + int(ys[0]), yy1 + int(ys[-1])


_CROWN_RATIO = {11: 1.0, 21: 1.0, 12: 0.82, 22: 0.82, 13: 0.92, 23: 0.92}


def _anatomy_boxes(sboxes, sites, band_h):
    """解剖整形：切缘（框顶）对齐，框高按牙冠长比例（中切1.0/侧切0.82/尖牙0.92）；
    超高压缩、异常矮补足。"""
    if not band_h or band_h <= 0:
        return sboxes
    out = []
    for site, x1, y1, x2, y2 in sboxes:
        target = band_h * _CROWN_RATIO.get(site, 1.0)
        h = y2 - y1
        if h > target:
            y2 = y1 + target
        elif h < target * 0.6:
            y2 = y1 + target
        out.append((site, x1, y1, x2, y2))
    return out


def _teeth_detect_core(roi: np.ndarray, sites=(13, 12, 11, 21, 22, 23),
                       require_upper: bool = False):
    """ROI 内牙齿检测核心，返回 [(site, x1,y1,x2,y2)]（ROI 局部坐标）。
    require_upper=True 时校验牙带中心在 ROI 上部 65% 内（上前牙先验），
    误检（如下巴/衬衫带）返回 []。"""
    import cv2
    mask = _teeth_mask(roi)
    band = _tooth_band(mask)
    if band is None:
        return []
    yy1, yy2, xx1, xx2 = band
    if require_upper and (yy1 + yy2) / 2.0 > mask.shape[0] * 0.65:
        return []
    # 行带扩展（含牙冠上下缘淡区），灰度窗在其上收紧
    rh = mask.shape[0]
    bh = yy2 - yy1
    yy1e = max(0, yy1 - int(bh * 0.35))
    yy2e = min(rh - 1, yy2 + int(bh * 0.45))
    gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    boxes = _split_tooth_boxes(mask, xx1, xx2, len(sites))
    if len(boxes) < len(sites):
        bb = _ratio_bounds(xx1, xx2, FRONT_TOOTH_RATIOS[:len(sites)])
        boxes = [(bb[i], float(yy1e), bb[i + 1], float(yy2e)) for i in range(len(sites))]
    sboxes = []
    for i, b in enumerate(boxes):
        if i >= len(sites):
            break
        y1, y2 = _seg_y_by_gray(gray, yy1e, yy2e, int(round(b[0])), int(round(b[2])))
        sboxes.append((sites[i], b[0], float(y1), b[2], float(y2)))
    return _anatomy_boxes(sboxes, sites, float(yy2e - yy1e))


def _try_rois(small, gray, rois, sites, require_upper=True):
    """依次尝试候选 ROI（先过滤位置不合理的），返回 (roi, boxes) 或 (None, [])"""
    ih, iw = small.shape[:2]
    for roi in rois:
        if roi is None:
            continue
        rx1, ry1, rx2, ry2 = roi
        if rx2 - rx1 < 40 or ry2 - ry1 < 20:
            continue
        # 全局位置校验：嘴/牙 ROI 中心不应落在图像底部（Haar 误检下巴/躯干）
        cy = (ry1 + ry2) / 2.0 / ih
        if cy > 0.85 or cy < 0.15:
            continue
        sub = small[ry1:ry2, rx1:rx2]
        boxes = _teeth_detect_core(sub, sites, require_upper)
        if boxes:
            return roi, boxes
    return None, []


def detect_teeth_intraoral(image: np.ndarray, sites=(13, 12, 11, 21, 22, 23)):
    """口内牙列自动检测：返回 [(site, x1, y1, x2, y2), ...]（原图像坐标）

    流程：降采样 → 嘴部定位（smile/face/中央回退）→ 双信号牙齿掩膜 →
    行带定位 → 比例分牙 + 谷吸附 + 解剖限高。"""
    import cv2
    if image is None:
        return []
    small, scale = _downscale_teeth(image)
    h, w = small.shape[:2]
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    roi = _locate_mouth_roi(gray)
    rois = [_locate_smile_roi(gray), _locate_face_roi(gray),
            (int(w * 0.10), int(h * 0.20), int(w * 0.90), int(h * 0.80))]
    roi, boxes = _try_rois(small, gray, rois, sites, require_upper=True)
    if not boxes:
        return []
    rx1, ry1, rx2, ry2 = roi
    if scale == 1.0:
        return [(s, rx1 + x1, ry1 + y1, rx1 + x2, ry1 + y2) for s, x1, y1, x2, y2 in boxes]
    # 坐标换算回原图
    inv = 1.0 / scale
    return [(s, int((rx1 + x1) * inv), int((ry1 + y1) * inv),
             int((rx1 + x2) * inv), int((ry1 + y2) * inv)) for s, x1, y1, x2, y2 in boxes]


def detect_teeth_front(image: np.ndarray, sites=(13, 12, 11, 21, 22, 23)):
    """正面视图自动检测：返回 [(site, x1, y1, x2, y2), ...]（原图像坐标）
    嘴部定位（smile → 脸下1/3 → 下半中央）→ 双信号牙齿掩膜 → 行带分牙。"""
    import cv2
    if image is None:
        return []
    small, scale = _downscale_teeth(image)
    h, w = small.shape[:2]
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    rois = [_locate_smile_roi(gray), _locate_face_roi(gray),
            (int(w * 0.15), int(h * 0.45), int(w * 0.85), int(h * 0.78))]
    roi, boxes = _try_rois(small, gray, rois, sites, require_upper=True)
    if not boxes:
        return []
    rx1, ry1, rx2, ry2 = roi
    if scale == 1.0:
        return [(s, rx1 + x1, ry1 + y1, rx1 + x2, ry1 + y2) for s, x1, y1, x2, y2 in boxes]
    inv = 1.0 / scale
    return [(s, int((rx1 + x1) * inv), int((ry1 + y1) * inv),
             int((rx1 + x2) * inv), int((ry1 + y2) * inv)) for s, x1, y1, x2, y2 in boxes]
