# -*- coding: utf-8 -*-
"""平行合平面面板 —— 口内视图沿合平面点两个点，程序据此把合平面旋转到水平

交互：
  左键单击    —— 依次添加第 1、2 个点（两点即合平面方向）
  左键拖拽点  —— 移动点
  右键单击点  —— 删除该点
  滚轮缩放、中键平移（转发图像视图）
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .image_view import ImageView

PT_RADIUS = 6


class UnifyPanel(QWidget):
    """合平面两点覆盖层（仅口内视图使用）"""

    def __init__(self, image_view: ImageView, parent=None):
        super().__init__(parent)
        self.image_view = image_view
        self.points: List[QPointF] = []      # 视图坐标
        self.img_points: List[QPointF] = []  # 图像坐标
        self.on_points = None                # 两点齐时回调（图像坐标两点）
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self._drag_index = -1
        self._press_pos = None

    # ---------- 数据 ----------
    def clear(self):
        self.points.clear()
        self.img_points.clear()
        self.update()

    def get_img_points(self) -> List[Tuple[float, float]]:
        return [(p.x(), p.y()) for p in self.img_points]

    def has_two(self) -> bool:
        return len(self.img_points) >= 2

    def _notify(self):
        if self.has_two() and self.on_points:
            self.on_points()

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
                if ((sp.x() - p.x()) ** 2 + (sp.y() - p.y()) ** 2) ** 0.5 < PT_RADIUS:
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
                self._drag_index = -1
                self._notify()
                return
            if self._press_pos is None:
                return
            p = QPointF(e.position())
            if ((p.x() - self._press_pos.x()) ** 2 + (p.y() - self._press_pos.y()) ** 2) ** 0.5 > 4:
                return  # 拖拽而非单击
            self._handle_click(p)
        super().mouseReleaseEvent(e)

    def _handle_click(self, p: QPointF):
        # 点中已有点 → 忽略
        for sp in self.points:
            if ((sp.x() - p.x()) ** 2 + (sp.y() - p.y()) ** 2) ** 0.5 < PT_RADIUS:
                return
        if len(self.points) >= 2:
            self.clear()          # 已两点：重新开始
        self.points.append(p)
        self.img_points.append(self._to_img(p))
        self.update()
        self._notify()

    def contextMenuEvent(self, e):
        p = QPointF(e.pos())
        for i in range(len(self.points) - 1, -1, -1):
            if ((self.points[i].x() - p.x()) ** 2 + (self.points[i].y() - p.y()) ** 2) ** 0.5 < PT_RADIUS:
                del self.points[i]
                del self.img_points[i]
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
        if len(self.points) >= 2:
            painter.setPen(QPen(QColor(0, 220, 255), 2, Qt.DashLine))
            painter.drawLine(self.points[0], self.points[1])
        painter.setBrush(QColor(0, 220, 255))
        painter.setPen(Qt.NoPen)
        for p in self.points:
            painter.drawEllipse(p, PT_RADIUS, PT_RADIUS)
        if len(self.points) == 0:
            hint = "沿咬合平面点第 1 点（如牙列左侧）"
        elif len(self.points) == 1:
            hint = "沿咬合平面点第 2 点（如牙列右侧），然后点『应用旋转』"
        else:
            hint = "两点已确定：点『应用旋转』将合平面转水平；右键可删点"
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QFont
        f = QFont()
        f.setPointSize(10)
        painter.setFont(f)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(hint)
        box = QRectF(8, 8, tw + 16, fm.height() + 8)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 140))      # 半透明底，避免压在照片上看不清
        painter.drawRoundedRect(box, 4, 4)
        painter.setPen(QColor(210, 245, 255))
        painter.drawText(box.adjusted(8, 0, 0, 0), Qt.AlignVCenter, hint)
        painter.end()
