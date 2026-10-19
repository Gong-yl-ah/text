# -*- coding: utf-8 -*-
"""牙齿调整面板 —— 对应原 DEDD 项目的 TeethAdjustPanel + ToothPanel

显示模式：
  MODE_CONTOUR  轮廓（模板轮廓图 + 边框 + 牙位文字）
  MODE_REAL     牙冠（模板真实牙冠图，应用亮度/黄度调整）
  MODE_NONE     隐藏

交互：
  左键拖拽矩形 —— 移动 / 八方向缩放（相邻牙水平联动、对侧牙垂直联动）
  右键按住拖动 —— 调整亮度（上下）/ 黄度（左右）
  右键单击 —— 循环切换显示模式
  滚轮缩放、中键平移（转发图像视图）
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..image_utils import adjust_bright_yellow, np_to_qimage, qimage_to_np
from ..models import Rect2D, Tooth, ToothData
from ..teeth_templates import get_template, has_template
from .drawable_rect import (POINT_EB, POINT_IN_RECT, POINT_NE, POINT_NW,
                            POINT_ON_EB, POINT_ON_NB, POINT_ON_SB, POINT_ON_WB,
                            POINT_OUT_RECT, POINT_SE, POINT_SW)
from .image_view import ImageView

MODE_NONE = 0
MODE_CONTOUR = 1
MODE_REAL = 2

_SITES_ORDER = {13: 6, 12: 7, 11: 8, 21: 9, 22: 10, 23: 11}


class ToothItem:
    """一颗可调整的牙齿"""

    def __init__(self, tooth: Tooth):
        self.site = tooth.site
        self.rect_img = tooth.rect.normalized()     # 图像坐标
        self.real_length = tooth.real_length
        self._view_rect = None                       # 视图坐标（懒计算）
        self.image = None                            # 当前显示的模板 QImage
        self.tmp_image = None                        # 亮度调整后的缓存

    def scale(self) -> float:
        h = self.rect_img.height
        return (self.real_length / h) if h else 1.0


class TeethAdjustPanel(QWidget):
    """牙齿调整覆盖层"""

    def __init__(self, image_view: ImageView, view_kind: str = "base", parent=None):
        """view_kind: 'base'（口内，可拖动+轮廓模式） / 'front'（正面，牙冠模式）"""
        super().__init__(parent)
        self.image_view = image_view
        self.view_kind = view_kind
        self.items: List[ToothItem] = []
        self.mode = MODE_REAL if view_kind == "front" else MODE_CONTOUR
        self.show_border_text = True
        self.dragable = (view_kind == "base")
        self.bright = 0
        self.yellow = 0
        self.on_change = None
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self._drag_index = -1
        self._flag = POINT_OUT_RECT
        self._start = QPointF()
        self._p1 = QPointF()
        self._p2 = QPointF()
        self._p3 = QPointF()
        self._p4 = QPointF()
        self._r3_drag = False
        self._bright_now = 0
        self._yellow_now = 0
        self._hover = False

    # ---------- 数据 ----------
    def clear(self):
        self.items.clear()
        self.update()

    def set_teeth(self, data: List[ToothData]):
        self.clear()
        for td in data:
            self.items.append(ToothItem(Tooth(td.site, td.rect, td.length)))
        self._refresh_images()
        self.update()

    def get_current_teeth_data(self) -> List[ToothData]:
        result = []
        for it in self.items:
            r = it.rect_img
            result.append(ToothData(it.site, r.x1, r.y1, r.x2, r.y2, it.real_length))
        return result

    def get_current_teeth(self) -> List[Tooth]:
        return [Tooth.from_data(d) for d in self.get_current_teeth_data()]

    def _notify(self):
        if self.on_change:
            self.on_change()

    # ---------- 模板与亮度 ----------
    def _kind(self) -> str:
        return "real_front" if self.view_kind == "front" else ("contour" if self.mode == MODE_CONTOUR else "real")

    def _refresh_images(self):
        kind = "real_front" if self.view_kind == "front" else "real"
        for it in self.items:
            img = get_template(it.site, kind)
            if img is not None:
                it.image = img
            else:
                it.image = None
        self._apply_bright_yellow()

    def _apply_bright_yellow(self):
        for it in self.items:
            it.tmp_image = None
        if self.mode != MODE_REAL and self.view_kind != "front":
            return
        if self.bright == 0 and self.yellow == 0:
            return
        kind = "real_front" if self.view_kind == "front" else "real"
        for it in self.items:
            base = get_template(it.site, kind)
            if base is None:
                it.tmp_image = None
                continue
            arr = qimage_to_np(base)
            if arr is not None:
                out = adjust_bright_yellow(arr, self.bright, self.yellow)
                it.tmp_image = np_to_qimage(out)
            else:
                it.tmp_image = base

    def set_bright_yellow(self, bright: int, yellow: int):
        self.bright = bright
        self.yellow = yellow
        self._refresh_images()
        self.update()

    def get_bright_yellow(self):
        return self.bright, self.yellow

    def set_mode(self, mode: int):
        if mode == self.mode:
            return
        self.mode = mode
        if mode == MODE_REAL:
            self._refresh_images()
        self.update()

    def next_mode(self):
        if self.mode == MODE_REAL:
            self.set_mode(MODE_CONTOUR if self.show_border_text else MODE_NONE)
        else:
            self.set_mode(MODE_REAL)

    def change_mode(self, mode: int):
        self.set_mode(mode)

    # ---------- 视图变换 ----------
    def _to_view(self, r: Rect2D):
        v1 = self.image_view.to_view(r.x1, r.y1)
        v2 = self.image_view.to_view(r.x2, r.y2)
        return v1.x(), v1.y(), v2.x(), v2.y()

    def _to_img_pt(self, vx: float, vy: float) -> QPointF:
        return self.image_view.to_image(vx, vy)

    # ---------- 鼠标交互 ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self.image_view.mousePressEvent(e)
            return
        p = QPointF(e.position())
        if e.button() == Qt.RightButton:
            self._r3_drag = True
            self._start = p
            self._bright_now = self.bright
            self._yellow_now = self.yellow
            return
        if e.button() == Qt.LeftButton and self.dragable:
            self._start = p
            self._flag = POINT_OUT_RECT
            for i, it in enumerate(self.items):
                vx1, vy1, vx2, vy2 = self._to_view(it.rect_img)
                f = self._rect_flag(it, vx1, vy1, vx2, vy2, p)
                if f != POINT_OUT_RECT:
                    self._drag_index = i
                    self._flag = f
                    self._p1 = QPointF(vx1, vy1)
                    self._p2 = QPointF(vx2, vy2)
                    self._p3 = QPointF(vx2, vy1)
                    self._p4 = QPointF(vx1, vy2)
                    break
        super().mousePressEvent(e)

    @staticmethod
    def _rect_flag(it, x1, y1, x2, y2, p: QPointF) -> int:
        from .drawable_rect import DrawableRect
        dr = DrawableRect(x1, y1, x2, y2)
        return dr.get_point_flag(p)

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MiddleButton:
            self.image_view.mouseMoveEvent(e)
            return
        p = QPointF(e.position())
        if e.buttons() & Qt.RightButton and self._r3_drag:
            if self.mode == MODE_REAL or self.view_kind == "front":
                y_chg = int((self._start.y() - p.y()) / 20)
                x_chg = int((self._start.x() - p.x()) / 50)
                new_b = self._bright_now + y_chg
                new_y = self._yellow_now + x_chg
                if new_b != self.bright or new_y != self.yellow:
                    self.bright = new_b
                    self.yellow = new_y
                    self._apply_bright_yellow()
                    self._notify()
                    self.update()
            return
        if e.buttons() & Qt.LeftButton and self._drag_index != -1 and self.dragable:
            it = self.items[self._drag_index]
            x1, y1, x2, y2 = self._to_view(it.rect_img)
            s = self._start
            if self._flag == POINT_OUT_RECT:
                pass  # 不应出现
            elif self._flag == POINT_NW:
                x1, y1 = p.x(), p.y()
            elif self._flag == POINT_NE:
                x1, y1, x2, y2 = p.x(), p.y(), self._p4.x(), self._p4.y()
            elif self._flag == POINT_SW:
                x1, y1, x2, y2 = p.x(), p.y(), self._p3.x(), self._p3.y()
            elif self._flag == POINT_SE:
                x1, y1, x2, y2 = p.x(), p.y(), self._p1.x(), self._p1.y()
            elif self._flag == POINT_ON_NB:
                y1 = p.y()
            elif self._flag == POINT_ON_SB:
                y2 = p.y()
            elif self._flag == POINT_ON_WB:
                x1 = p.x()
            elif self._flag == POINT_ON_EB:
                x2 = p.x()
            elif self._flag == POINT_IN_RECT:
                ox, oy = p.x() - s.x(), p.y() - s.y()
                self._move_item(it, ox, oy)
                self._start = p
                self.update()
                return
            self._set_item_rect_view(it, x1, y1, x2, y2)
            self.update()
        else:
            # 光标
            flag = POINT_OUT_RECT
            if self.dragable:
                for it in self.items:
                    vx1, vy1, vx2, vy2 = self._to_view(it.rect_img)
                    f = self._rect_flag(it, vx1, vy1, vx2, vy2, p)
                    if f != POINT_OUT_RECT:
                        flag = f
                        break
            self._apply_cursor(flag)
        super().mouseMoveEvent(e)

    def _set_item_rect_view(self, it: ToothItem, vx1, vy1, vx2, vy2):
        p1 = self._to_img_pt(vx1, vy1)
        p2 = self._to_img_pt(vx2, vy2)
        it.rect_img = Rect2D(p1.x(), p1.y(), p2.x(), p2.y()).normalized()

    def _move_item(self, it: ToothItem, ox, oy):
        """移动一颗牙（视图像素偏移 → 图像坐标偏移），并做绑定联动"""
        dix = ox / self.image_view.scale if self.image_view.scale else 0
        diy = oy / self.image_view.scale if self.image_view.scale else 0
        r = it.rect_img
        it.rect_img = Rect2D(r.x1 + dix, r.y1 + diy, r.x2 + dix, r.y2 + diy)
        # 垂直绑定：同个位数（11<->21, 12<->22, 13<->23）y 同步
        for o in self.items:
            if o is it:
                continue
            if o.site % 10 == it.site % 10:
                or_ = o.rect_img
                o.rect_img = Rect2D(or_.x1, or_.y1 + diy, or_.x2, or_.y2 + diy)
        # 水平绑定：同侧相邻牙（13-12-11 / 21-22-23）水平位移联动
        order = _SITES_ORDER.get(it.site)
        if order is not None:
            for o in self.items:
                oo = _SITES_ORDER.get(o.site)
                if oo is not None and abs(oo - order) == 1:
                    or_ = o.rect_img
                    o.rect_img = Rect2D(or_.x1 + dix, or_.y1, or_.x2 + dix, or_.y2)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self.image_view.mouseReleaseEvent(e)
            return
        if e.button() == Qt.RightButton:
            if self._r3_drag:
                if self._start == QPointF(e.position()):
                    # 右键单击：切换显示模式
                    self.next_mode()
                self._r3_drag = False
                self._notify()
            return
        if e.button() == Qt.LeftButton:
            if self._drag_index != -1:
                self._drag_index = -1
                self._notify()
        super().mouseReleaseEvent(e)

    def _apply_cursor(self, flag: int):
        cursors = {
            POINT_NW: Qt.SizeFDiagCursor, POINT_SE: Qt.SizeFDiagCursor,
            POINT_NE: Qt.SizeBDiagCursor, POINT_SW: Qt.SizeBDiagCursor,
            POINT_ON_NB: Qt.SizeVerCursor, POINT_ON_SB: Qt.SizeVerCursor,
            POINT_ON_WB: Qt.SizeHorCursor, POINT_ON_EB: Qt.SizeHorCursor,
            POINT_IN_RECT: Qt.SizeAllCursor,
        }
        c = cursors.get(flag, Qt.ArrowCursor)
        if c == Qt.ArrowCursor:
            self.unsetCursor()
        else:
            from PySide6.QtGui import QCursor
            self.setCursor(QCursor(c))

    def wheelEvent(self, e):
        self.image_view.wheelEvent(e)
        self.update()

    def zoom_sync(self):
        self.update()

    # ---------- 绘制 ----------
    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.Antialiasing, True)
        for it in self.items:
            if self.mode == MODE_NONE:
                continue
            vx1, vy1, vx2, vy2 = self._to_view(it.rect_img)
            if vx2 - vx1 < 2 or vy2 - vy1 < 2:
                continue
            rect = _QRectF(vx1, vy1, vx2 - vx1, vy2 - vy1)
            img = it.tmp_image if (it.tmp_image is not None and (self.mode == MODE_REAL or self.view_kind == "front")) else None
            if img is None and (self.mode == MODE_REAL or self.view_kind == "front"):
                img = it.image
            if self.mode == MODE_CONTOUR or self.view_kind == "front":
                img = it.image if it.image is not None else None
            if img is not None:
                painter.drawImage(rect, img)
            if self.mode == MODE_CONTOUR and self.show_border_text:
                pen = QPen(QColor(0, 170, 255), 1.5)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(rect)
                painter.setPen(QPen(QColor(255, 255, 0), 1))
                font = painter.font()
                font.setPointSize(9)
                painter.setFont(font)
                label = str(it.site)
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(label)
                tx = rect.x() + (rect.width() - tw) / 2
                ty = rect.y() - 4
                painter.drawText(QPointF(tx, ty), label)
        painter.end()


def _QRectF(x, y, w, h):
    from PySide6.QtCore import QRectF
    return QRectF(x, y, w, h)
