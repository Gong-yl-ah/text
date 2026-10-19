# -*- coding: utf-8 -*-
"""牙齿模板 —— 对应原 DEDD 项目的 TeethImage.java

从 assets/img 加载 t{site}_{kind}.png：
  contour   轮廓图（美学设计-轮廓模式）
  real      真实牙冠图（美学设计-牙冠模式，口内）
  real_front 真实牙冠图（正面视图）
"""
from __future__ import annotations

import os
from typing import Dict, Optional

SITES = [11, 12, 13, 21, 22, 23]   # 上前牙六颗（原版范围）
KINDS = ("contour", "real", "real_front")

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "img")
_cache: Dict[str, object] = {}


def _path(site: int, kind: str) -> str:
    return os.path.join(_ASSETS_DIR, f"t{site}_{kind}.png")


def has_template(site: int, kind: str) -> bool:
    return os.path.exists(_path(site, kind))


def get_template(site: int, kind: str) -> Optional[object]:
    """返回 QImage（缓存）。缺失时返回 None，调用方应回退为图形绘制。"""
    from PySide6.QtGui import QImage
    key = f"{site}_{kind}"
    if key in _cache:
        return _cache[key]
    p = _path(site, kind)
    if not os.path.exists(p):
        _cache[key] = None
        return None
    img = QImage(p)
    if img.isNull():
        _cache[key] = None
        return None
    _cache[key] = img
    return img


def get_teeth_contour() -> Dict[int, object]:
    return {s: get_template(s, "contour") for s in SITES}


def get_teeth_real() -> Dict[int, object]:
    return {s: get_template(s, "real") for s in SITES}


def get_teeth_real_front() -> Dict[int, object]:
    return {s: get_template(s, "real_front") for s in SITES}
