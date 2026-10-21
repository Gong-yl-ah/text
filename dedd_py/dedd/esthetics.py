# -*- coding: utf-8 -*-
"""美学参数分析 —— 依据《口腔美学重建中关键的美学参数及其数字化转移流程》
（中华口腔医学杂志 2026;61(9):1275-1283）中 2D 照片可落地的参数：
  ① 静息上颌中切牙切缘位置（相对唇线提示）
  ② 上颌中切牙牙冠宽长比（= 临床冠宽 / 临床冠长 ≈ 标记框宽 / 框高）
  ③ 上前牙正面观宽度比（黄金分割 1.618:1:0.618 / Preston 1.51:1:0.84）
  ④ 上前牙龈缘位置（侧切牙龈缘位于中切牙与尖牙龈缘连线冠方 0.5~1.0 mm）
垂直距离、穿龈轮廓需要侧貌照片或三维数据，超出本 2D 软件范围，不做计算。

所有函数为纯计算，便于单元测试。输入均为图像坐标（x1<x2, y1<y2，y 向下增大）。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .models import ToothData

# 临床常用参考区间（宽长比），文章未给固定值，标注为临床经验参考
CROWN_RATIO_IDEAL_MIN = 0.75
CROWN_RATIO_IDEAL_MAX = 0.85

# 上前牙正面观宽度比：黄金分割（文章原文）与 Preston（文章原文，中国人更倾向）
GOLDEN_RATIO = (1.618, 1.0, 0.618)      # 中切牙:侧切牙:尖牙
PRESTON_RATIO = (1.51, 1.0, 0.84)       # 中切牙:侧切牙:尖牙

# 龈缘理想带：侧切牙龈缘低于（图像上方=冠方）中切牙/尖牙龈缘连线 0.5~1.0 mm
GINGIVAL_LOWER_MM_MIN = 0.5
GINGIVAL_LOWER_MM_MAX = 1.0


def crown_width_height_ratio(t: ToothData) -> Optional[float]:
    """牙冠宽长比 = 框宽 / 框高（标得准时≈临床冠宽/冠长）"""
    h = abs(t.y2 - t.y1)
    w = abs(t.x2 - t.x1)
    if h <= 0:
        return None
    return w / h


def crown_ratio_status(ratio: Optional[float]) -> str:
    """宽长比判定：ideal / short（偏短宽）/ long（偏窄长）"""
    if ratio is None:
        return "n/a"
    if ratio < CROWN_RATIO_IDEAL_MIN:
        return "short"
    if ratio > CROWN_RATIO_IDEAL_MAX:
        return "long"
    return "ideal"


def frontal_width_ratios(teeth: List[ToothData]) -> Dict[str, dict]:
    """正面观宽度比：分别取左(13/12/11)与右(23/22/21)三颗，
    归一化为 中切牙:侧切牙:尖牙，并给出与黄金分割/Preston 的偏差。
    返回 {'left': {...}, 'right': {...}}
    """
    def _calc(tri: Dict[int, ToothData]) -> Optional[dict]:
        c = tri.get(11) or tri.get(21)
        l = tri.get(12) or tri.get(22)
        k = tri.get(13) or tri.get(23)
        if not all(x is not None for x in (c, l, k)):
            return None
        wc = abs(c.x2 - c.x1)
        wl = abs(l.x2 - l.x1)
        wk = abs(k.x2 - k.x1)
        if min(wc, wl, wk) <= 0:
            return None
        # 归一化：以侧切牙为 1
        ratio = (wc / wl, 1.0, wk / wl)
        g = (wc / wl / GOLDEN_RATIO[0], wk / wl / GOLDEN_RATIO[2])
        p = (wc / wl / PRESTON_RATIO[0], wk / wl / PRESTON_RATIO[2])
        g_dev = (abs(g[0] - 1.0) + abs(g[1] - 1.0)) / 2
        p_dev = (abs(p[0] - 1.0) + abs(p[1] - 1.0)) / 2
        closer = "golden" if g_dev <= p_dev else "preston"
        return {"ratio": ratio,
                "golden_dev": round(g_dev * 100, 1),
                "preston_dev": round(p_dev * 100, 1),
                "closer": closer}
    left = {}
    right = {}
    for t in teeth:
        if t.site in (11, 12, 13):
            left[t.site] = t
        elif t.site in (21, 22, 23):
            right[t.site] = t
    return {"left": _calc(left), "right": _calc(right)}


def gingival_analysis(teeth: List[ToothData], px_per_mm: Optional[float] = None) -> Dict[str, dict]:
    """上前牙龈缘位置分析：中切牙/尖牙上缘(y1)连线，比较侧切牙上缘位置。
    理想：侧切牙龈缘位于连线冠方（y 更小）0.5~1.0 mm。
    px_per_mm：像素/毫米 标尺（可由口内视图冠长校准）；None 时只给像素差。
    """
    def _row(central: int, lateral: int, canine: int):
        c = teeth_map.get(central)
        l = teeth_map.get(lateral)
        k = teeth_map.get(canine)
        if not all(x is not None for x in (c, l, k)):
            return None
        line_y = (c.y1 + k.y1) / 2.0          # 中切牙与尖牙龈缘连线
        lat_y = l.y1
        diff_px = line_y - lat_y              # >0 表示侧切牙在连线冠方（上方）
        mm = diff_px / px_per_mm if px_per_mm else None
        if mm is None:
            verdict = "n/a"
        elif GINGIVAL_LOWER_MM_MIN <= mm <= GINGIVAL_LOWER_MM_MAX:
            verdict = "ideal"
        elif mm < GINGIVAL_LOWER_MM_MIN:
            verdict = "low"                   # 侧切牙龈缘偏龈方（不够靠冠方）
        else:
            verdict = "high"                  # 侧切牙龈缘偏冠方过多
        return {"line_y": round(line_y, 1), "lateral_y": round(lat_y, 1),
                "diff_px": round(diff_px, 1), "diff_mm": None if mm is None else round(mm, 2),
                "verdict": verdict}
    teeth_map = {t.site: t for t in teeth}
    left = _row(11, 12, 13)
    right = _row(21, 22, 23)
    return {"left": left, "right": right}


def incisal_vs_lip(teeth: List[ToothData], lip_points: List[Tuple[float, float]]) -> Dict[str, Optional[float]]:
    """切缘位置相对唇线提示：取中切牙(11/21)切缘(y2)与唇线最低点的距离。
    仅作数值提示（微笑照近似，非静息位标准），文章静息位参考为上唇下方 2~4 mm。
    """
    result: Dict[str, Optional[float]] = {"left": None, "right": None}
    if not lip_points:
        return result
    teeth_map = {t.site: t for t in teeth}
    lip_y = max(p[1] for p in lip_points)       # 唇线最低点（y 向下）
    for site, key in ((11, "left"), (21, "right")):
        t = teeth_map.get(site)
        if t is not None:
            result[key] = round(t.y2 - lip_y, 1)
    return result
