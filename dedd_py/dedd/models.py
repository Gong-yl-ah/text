# -*- coding: utf-8 -*-
"""数据模型 —— 对应原 DEDD 项目的 ProjData / Tooth / ToothData / BasicInfo"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Rect2D:
    """浮点矩形（原始图像坐标系）"""
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return abs(self.x2 - self.x1)

    @property
    def height(self) -> float:
        return abs(self.y2 - self.y1)

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2.0

    def normalized(self) -> "Rect2D":
        return Rect2D(min(self.x1, self.x2), min(self.y1, self.y2),
                      max(self.x1, self.x2), max(self.y1, self.y2))

    def to_dict(self) -> dict:
        return {"x1": round(self.x1, 2), "y1": round(self.y1, 2),
                "x2": round(self.x2, 2), "y2": round(self.y2, 2)}


@dataclass
class ToothData:
    """一颗标记牙的持久化数据（对应 ToothData.java）"""
    site: int = 0
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    length: float = 0.0

    @property
    def rect(self) -> Rect2D:
        return Rect2D(self.x1, self.y1, self.x2, self.y2)

    def to_dict(self) -> dict:
        return {"site": self.site, "x1": round(self.x1, 2), "y1": round(self.y1, 2),
                "x2": round(self.x2, 2), "y2": round(self.y2, 2), "length": round(self.length, 2)}

    @staticmethod
    def from_dict(d: dict) -> "ToothData":
        return ToothData(site=int(d.get("site", 0)), x1=float(d.get("x1", 0)),
                         y1=float(d.get("y1", 0)), x2=float(d.get("x2", 0)),
                         y2=float(d.get("y2", 0)), length=float(d.get("length", 0)))


@dataclass
class Tooth:
    """运行时的牙齿对象（对应 Tooth.java）"""
    site: int
    rect: Rect2D
    real_length: float = 0.0

    @property
    def scale(self) -> float:
        """冠长/矩形高的比例"""
        h = self.rect.height
        if h == 0:
            return 1.0
        return self.real_length / h if self.real_length else 1.0

    @property
    def ratio(self) -> float:
        """宽长比"""
        h = self.rect.height
        return (self.rect.width / h) if h else 0.0

    def to_data(self) -> ToothData:
        return ToothData(self.site, self.rect.x1, self.rect.y1,
                         self.rect.x2, self.rect.y2, self.real_length)

    @staticmethod
    def from_data(d: ToothData) -> "Tooth":
        return Tooth(d.site, d.rect, d.length)

    def __eq__(self, other) -> bool:
        if not isinstance(other, Tooth):
            return False
        r = self.rect
        o = other.rect
        return (self.site == other.site and abs(r.x1 - o.x1) < 1e-6
                and abs(r.y1 - o.y1) < 1e-6 and abs(r.x2 - o.x2) < 1e-6
                and abs(r.y2 - o.y2) < 1e-6 and abs(self.real_length - other.real_length) < 1e-6)


@dataclass
class BasicInfo:
    name: str = ""
    age: int = 0
    gender: str = ""        # 男 / 女 / 未知
    phone: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "age": self.age, "gender": self.gender, "phone": self.phone}

    @staticmethod
    def from_dict(d: dict) -> "BasicInfo":
        try:
            age = int(d.get("age", 0))
        except (TypeError, ValueError):
            age = 0
        return BasicInfo(str(d.get("name", "")), age, str(d.get("gender", "")), str(d.get("phone", "")))


@dataclass
class ViewData:
    """单个视图（口内/正面）的数据"""
    image_path: Optional[str] = None        # 工程内文件名（base.jpg / front.jpg）
    marked: List[ToothData] = field(default_factory=list)
    adjusted: List[ToothData] = field(default_factory=list)
    bright: int = 0
    yellow: int = 0

    def to_dict(self) -> dict:
        return {"image": self.image_path,
                "marked": [t.to_dict() for t in self.marked],
                "adjusted": [t.to_dict() for t in self.adjusted],
                "bright": self.bright, "yellow": self.yellow}

    @staticmethod
    def from_dict(d: dict) -> "ViewData":
        v = ViewData()
        v.image_path = d.get("image")
        v.marked = [ToothData.from_dict(t) for t in d.get("marked", [])]
        v.adjusted = [ToothData.from_dict(t) for t in d.get("adjusted", [])]
        v.bright = int(d.get("bright", 0))
        v.yellow = int(d.get("yellow", 0))
        return v


@dataclass
class ProjData:
    """工程数据（对应 ProjData.java）"""
    basic: BasicInfo = field(default_factory=BasicInfo)
    base: ViewData = field(default_factory=ViewData)     # 口内视图
    front: ViewData = field(default_factory=ViewData)    # 正面视图
    lip_points: List[Tuple[float, float]] = field(default_factory=list)
    lip_closed: bool = False

    def to_dict(self) -> dict:
        return {"version": "1.0", "basic": self.basic.to_dict(),
                "base": self.base.to_dict(), "front": self.front.to_dict(),
                "lip": {"points": [[round(x, 2), round(y, 2)] for x, y in self.lip_points],
                        "closed": self.lip_closed}}

    @staticmethod
    def from_dict(d: dict) -> "ProjData":
        p = ProjData()
        p.basic = BasicInfo.from_dict(d.get("basic", {}))
        p.base = ViewData.from_dict(d.get("base", {}))
        p.front = ViewData.from_dict(d.get("front", {}))
        lip = d.get("lip", {}) or {}
        p.lip_points = [(float(x), float(y)) for x, y in lip.get("points", [])]
        p.lip_closed = bool(lip.get("closed", False))
        return p
