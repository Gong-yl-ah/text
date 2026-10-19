# -*- coding: utf-8 -*-
"""可拖拽矩形 —— 对应原 DEDD 项目的 DrawableBorderRect + BorderRect"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

# 点位标记
POINT_OUT_RECT = 0
POINT_NW = 1
POINT_NE = 2
POINT_SW = 3
POINT_SE = 4
POINT_ON_NB = 5
POINT_ON_SB = 6
POINT_ON_WB = 7
POINT_ON_EB = 8
POINT_IN_RECT = 9

# 兼容别名（原版命名）
POINT_NB = POINT_ON_NB
POINT_SB = POINT_ON_SB
POINT_WB = POINT_ON_WB
POINT_EB = POINT_ON_EB

_HANDLE = 5          # 控制点半边长
_EDGE = 6            # 边/角点命中容差


class DrawableRect:
    """一个可绘制、可拖拽的矩形（视图坐标）"""

    def __init__(self, x1=0.0, y1=0.0, x2=0.0, y2=0.0, color: QColor = None):
        self.rect = QRectF(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
        self.color = color or QColor(0, 170, 255)
        self.draw_border = True

    # ---------- 几何 ----------
    def get_x1(self) -> float:
        return self.rect.left()

    def get_y1(self) -> float:
        return self.rect.top()

    def get_x2(self) -> float:
        return self.rect.right()

    def get_y2(self) -> float:
        return self.rect.bottom()

    def set_point(self, x1: float, y1: float, x2: float, y2: float):
        self.rect = QRectF(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))

    def set_rect(self, x1: float, y1: float, x2: float, y2: float):
        self.rect = QRectF(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))

    def center(self) -> QPointF:
        return self.rect.center()

    # ---------- 点位判定 ----------
    def get_point_flag(self, p: QPointF) -> int:
        x, y = p.x(), p.y()
        r = self.rect
        if not r.contains(p) and not (r.adjusted(-_EDGE, -_EDGE, _EDGE, _EDGE).contains(p)):
            return POINT_OUT_RECT
        # 角点
        if abs(x - r.left()) <= _HANDLE + 2 and abs(y - r.top()) <= _HANDLE + 2:
            return POINT_NW
        if abs(x - r.right()) <= _HANDLE + 2 and abs(y - r.top()) <= _HANDLE + 2:
            return POINT_NE
        if abs(x - r.left()) <= _HANDLE + 2 and abs(y - r.bottom()) <= _HANDLE + 2:
            return POINT_SW
        if abs(x - r.right()) <= _HANDLE + 2 and abs(y - r.bottom()) <= _HANDLE + 2:
            return POINT_SE
        # 边
        if abs(y - r.top()) <= _EDGE and r.left() <= x <= r.right():
            return POINT_ON_NB
        if abs(y - r.bottom()) <= _EDGE and r.left() <= x <= r.right():
            return POINT_ON_SB
        if abs(x - r.left()) <= _EDGE and r.top() <= y <= r.bottom():
            return POINT_ON_WB
        if abs(x - r.right()) <= _EDGE and r.top() <= y <= r.bottom():
            return POINT_ON_EB
        if r.contains(p):
            return POINT_IN_RECT
        return POINT_OUT_RECT

    # ---------- 绘制 ----------
    def draw(self, painter: QPainter, label: str = None):
        r = self.rect
        pen = QPen(self.color, 1.5)
        pen.setStyle(Qt.SolidLine)
        painter.setPen(pen)
        painter.drawRect(r)
        # 八个控制点
        points = [
            QPointF(r.left(), r.top()), QPointF(r.right(), r.top()),
            QPointF(r.left(), r.bottom()), QPointF(r.right(), r.bottom()),
            QPointF(r.center().x(), r.top()), QPointF(r.center().x(), r.bottom()),
            QPointF(r.left(), r.center().y()), QPointF(r.right(), r.center().y()),
        ]
        painter.setBrush(self.color)
        painter.setPen(Qt.NoPen)
        for p in points:
            painter.drawRect(QRectF(p.x() - _HANDLE / 2, p.y() - _HANDLE / 2, _HANDLE, _HANDLE))
        if label:
            painter.setPen(QPen(QColor(255, 255, 255), 1))
            painter.drawText(QPointF(r.left(), max(0, r.top() - 4)), label)
