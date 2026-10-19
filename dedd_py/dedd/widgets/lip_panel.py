# -*- coding: utf-8 -*-
"""唇线标记面板 —— 对应原 DEDD 项目的 CurvePanel

交互：
  左键单击    —— 添加点；点中起点则闭合曲线
  左键拖拽点  —— 移动点
  右键单击    —— 删除最近点 / 结束绘制
  滚轮缩放、中键平移（转发图像视图）
"""
from __future__ import annotations

from typing import List, Tuple

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .image_view import ImageView

PT_RADIUS = 5


def _dist(a: QPointF, b: QPointF) -> float:
    return ((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2) ** 0.5


def _bezier_segments(points: List[QPointF], closed: bool):
    """生成贝塞尔曲线段（与原版 CurvePanel.genPath 一致）"""
    n = len(points)
    if n < 2:
        return []
    if n == 2:
        return [(points[0], points[0], points[1])]
    ctl: List[Tuple[QPointF, QPointF]] = []
    for i in range(n):
        p0 = points[(i - 1) % n]
        p1 = points[i]
        p2 = points[(i + 1) % n]
        d1 = _dist(p1, p0)
        d2 = _dist(p1, p2)
        t = d1 / (d1 + d2) if (d1 + d2) > 1e-9 else 0.5
        mx, my = (p0.x() + p1.x()) / 2, (p0.y() + p1.y()) / 2
        nx, ny = (p2.x() + p1.x()) / 2, (p2.y() + p1.y()) / 2
        sx = (1 - t) * mx + t * nx
        sy = (1 - t) * my + t * ny
        ox, oy = p1.x() - sx, p1.y() - sy
        ctl.append((QPointF(mx + ox, my + oy), QPointF(nx + ox, ny + oy)))
    segs = []
    for i in range(1, n):
        c0 = ctl[i - 1][1] if not closed or i > 1 else ctl[0][1]
        segs.append((c0, ctl[i][0], points[i]))
    if closed:
        segs.append((ctl[-1][1], ctl[0][0], points[0]))
    return segs


class LipPanel(QWidget):
    """唇线覆盖层"""

    def __init__(self, image_view: ImageView, parent=None):
        super().__init__(parent)
        self.image_view = image_view
        self.points: List[QPointF] = []      # 视图坐标
        self.img_points: List[QPointF] = []  # 图像坐标
        self.is_closed = False
        self.on_change = None
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self._paint_mode = False
        self._drag_index = -1
        self._press_pos = None

    # ---------- 数据 ----------
    def clear(self):
        self.points.clear()
        self.img_points.clear()
        self.is_closed = False
        self._paint_mode = False
        self.update()

    def set_img_points(self, img_points: List[Tuple[float, float]]):
        self.clear()
        for x, y in img_points:
            self.img_points.append(QPointF(x, y))
            self.points.append(self.image_view.to_view(x, y))
        self.update()

    def get_img_points(self) -> List[Tuple[float, float]]:
        return [(p.x(), p.y()) for p in self.img_points]

    def _notify(self):
        if self.on_change:
            self.on_change()

    def _to_img(self, v: QPointF) -> QPointF:
        return self.image_view.to_image(v.x(), v.y())

    def zoom_sync(self):
        self.points = [self.image_view.to_view(p.x(), p.y()) for p in self.img_points]
        self.update()

    # ---------- 交互 ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self.image_view.mousePressEvent(e)
            return
        if e.button() == Qt.LeftButton:
            p = QPointF(e.position())
            self._press_pos = p
            self._drag_index = -1
            for i, sp in enumerate(self.points):
                if _dist(sp, p) < PT_RADIUS:
                    self._drag_index = i
                    break
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MiddleButton:
            self.image_view.mouseMoveEvent(e)
            return
        p = QPointF(e.position())
        if self._drag_index != -1 and (e.buttons() & Qt.LeftButton):
            self.points[self._drag_index] = p
            self.img_points[self._drag_index] = self._to_img(p)
            self.update()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self.image_view.mouseReleaseEvent(e)
            return
        if e.button() == Qt.LeftButton:
            if self._drag_index != -1:
                # 拖动过点：结束
                self._drag_index = -1
                self._notify()
                return
            if self._press_pos is None:
                return
            p = QPointF(e.position())
            if _dist(p, self._press_pos) > 4:
                return  # 发生了拖拽但不是点拖拽，忽略
            self._handle_click(p)
        super().mouseReleaseEvent(e)

    def _handle_click(self, p: QPointF):
        if self.is_closed:
            return
        # 点中第一个点 → 闭合
        if len(self.points) >= 2 and _dist(p, self.points[0]) < PT_RADIUS:
            self.is_closed = True
            self._paint_mode = False
            self._notify()
            self.update()
            return
        # 点中已有点（非起点）→ 忽略
        for i in range(1, len(self.points)):
            if _dist(p, self.points[i]) < PT_RADIUS:
                return
        # 点中最后一个点 → 继续绘制
        if len(self.points) >= 1 and _dist(p, self.points[-1]) < PT_RADIUS:
            self._paint_mode = True
        # 加点
        self.points.append(p)
        self.img_points.append(self._to_img(p))
        self.update()

    def contextMenuEvent(self, e):
        p = QPointF(e.pos())
        if self._paint_mode:
            self._paint_mode = False
            self._notify()
            e.accept()
            return
        for i in range(len(self.points) - 1, -1, -1):
            if _dist(self.points[i], p) < PT_RADIUS:
                del self.points[i]
                del self.img_points[i]
                if len(self.points) <= 2:
                    self.is_closed = False
                self._notify()
                self.update()
                e.accept()
                return
        e.ignore()

    def wheelEvent(self, e):
        self.image_view.wheelEvent(e)
        self.update()

    # ---------- 绘制 ----------
    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor(0, 220, 0), 2))
        if len(self.points) >= 2:
            path = QPainterPath(self.points[0])
            for c0, c1, p1 in _bezier_segments(self.points, self.is_closed):
                path.cubicTo(c0, c1, p1)
            painter.drawPath(path)
        painter.setBrush(QColor(0, 220, 0))
        painter.setPen(Qt.NoPen)
        for p in self.points:
            painter.drawEllipse(p, PT_RADIUS, PT_RADIUS)
        painter.end()
