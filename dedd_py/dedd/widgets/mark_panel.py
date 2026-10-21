# -*- coding: utf-8 -*-
"""牙位标记面板 —— 对应原 DEDD 项目的 TeethMarkPanel + DragRectsAdapter

交互：
  左键拖拽  —— 空白处新建矩形 / 移动 / 八方向缩放
  左键单击空白  —— 删除刚创建的空矩形
  右键点击矩形内部 —— 删除该矩形
  滚轮缩放、中键平移（转发给图像视图）
每个矩形附带两个数字输入框：牙位（整数）、冠长（口内视图显示，mm）
"""
from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLineEdit, QWidget

from ..models import Rect2D, Tooth, ToothData
from .drawable_rect import (POINT_EB, POINT_IN_RECT, POINT_NE, POINT_NW,
                            POINT_ON_EB, POINT_ON_NB, POINT_ON_SB, POINT_ON_WB,
                            POINT_OUT_RECT, POINT_SE, POINT_SW, DrawableRect)
from .image_view import ImageView


class NumberEdit(QLineEdit):
    """只允许数字输入的输入框"""

    def __init__(self, allow_dot: bool, parent=None):
        super().__init__(parent)
        self._allow_dot = allow_dot
        self.setMaximumWidth(54)
        self.setMinimumHeight(20)

    def keyPressEvent(self, e):
        from PySide6.QtGui import QKeyEvent
        txt = e.text()
        if txt and txt.isprintable():
            if not (txt.isdigit() or (self._allow_dot and txt == ".")):
                e.ignore()
                return
        super().keyPressEvent(e)


class TeethMarkPanel(QWidget):
    """牙位标记覆盖层"""

    def __init__(self, image_view: ImageView, parent=None):
        super().__init__(parent)
        self.image_view = image_view
        self.view_id = 0            # 0=口内(BASE) 1=正面(FRONT)
        self.is_front = False       # 是否正面视图（正面才显示/拖动中轴线）
        self.sym_axis = None        # 中轴线图像x坐标（None=不显示）
        self.rects: List[DrawableRect] = []
        self.site_edits: List[NumberEdit] = []
        self.length_edits: List[NumberEdit] = []
        self.on_change: Optional[Callable[[], None]] = None   # 任何修改后回调（撤销快照）
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self._dragging = False
        self._flag = POINT_OUT_RECT
        self._start = QPointF()
        self._p1 = QPointF()
        self._p2 = QPointF()
        self._p3 = QPointF()
        self._p4 = QPointF()
        self._index = -1
        self._hover_cursor = False
        self._sym_drag = False      # 正在拖动中轴线

    # ---------- 数据 ----------
    def clear(self):
        for ed in self.site_edits + self.length_edits:
            ed.deleteLater()
        self.site_edits.clear()
        self.length_edits.clear()
        self.rects.clear()
        self.update()

    def set_teeth(self, data: List[ToothData]):
        self.clear()
        for td in data:
            p1 = self.image_view.to_view(td.rect.x1, td.rect.y1)
            p2 = self.image_view.to_view(td.rect.x2, td.rect.y2)
            self._add_rect_with_edits(p1.x(), p1.y(), p2.x(), p2.y(),
                                      str(td.site) if td.site else "", str(td.length) if td.length else "")
        self.update()

    # ---------- 中轴线 ----------
    def set_sym_axis(self, axis_x):
        """设置中轴线（图像x坐标，None=隐藏）"""
        self.sym_axis = axis_x
        self.update()

    def get_sym_axis(self):
        return self.sym_axis

    def _sym_view_x(self) -> Optional[float]:
        """中轴线的视图x坐标"""
        if self.sym_axis is None or not self.image_view.has_image():
            return None
        return self.sym_axis * self.image_view.scale + self.image_view.offset_x

    def _hit_sym(self, vx: float) -> bool:
        """点击是否命中中轴线（±8视图像素）"""
        sx = self._sym_view_x()
        return self.is_front and sx is not None and abs(vx - sx) <= 8

    def _draw_sym(self, painter: QPainter):
        """绘制中轴线（正面视图）"""
        if not self.is_front or self.sym_axis is None or not self.image_view.has_image():
            return
        sx = self._sym_view_x()
        if sx is None:
            return
        pen = QPen(QColor(255, 80, 80), 1.5)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(int(sx), 0, int(sx), self.height())
        # 顶部小标签
        painter.setPen(QColor(255, 200, 200))
        f = painter.font()
        f.setPointSize(9)
        painter.setFont(f)
        painter.drawText(int(sx) + 3, 12, "中线")

    def get_teeth_data(self) -> List[ToothData]:
        result = []
        for i, r in enumerate(self.rects):
            site = self._parse_int(self.site_edits[i].text())
            length = self._parse_float(self.length_edits[i].text())
            # 视图坐标 -> 图像坐标
            p1 = self.image_view.to_image(r.get_x1(), r.get_y1())
            p2 = self.image_view.to_image(r.get_x2(), r.get_y2())
            result.append(ToothData(site, p1.x(), p1.y(), p2.x(), p2.y(), length))
        return result

    def get_teeth(self) -> List[Tooth]:
        return [Tooth.from_data(d) for d in self.get_teeth_data()]

    @staticmethod
    def _parse_int(s: str) -> int:
        try:
            return int(s)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _parse_float(s: str) -> float:
        try:
            return float(s)
        except (TypeError, ValueError):
            return 0.0

    # ---------- 内部 ----------
    def _add_rect_with_edits(self, x1, y1, x2, y2, site_text="", length_text=""):
        r = DrawableRect(x1, y1, x2, y2)
        self.rects.append(r)
        se = NumberEdit(False, self)
        le = NumberEdit(True, self)
        se.setText(site_text)
        le.setText(length_text)
        se.setPlaceholderText("牙位")
        le.setPlaceholderText("冠长")
        se.show()
        le.show()
        self.site_edits.append(se)
        self.length_edits.append(le)
        self._layout_edits(len(self.rects) - 1)

    def _remove_at(self, index: int):
        self.site_edits[index].deleteLater()
        self.length_edits[index].deleteLater()
        del self.site_edits[index]
        del self.length_edits[index]
        del self.rects[index]
        self.update()

    def _layout_edits(self, index: int):
        r = self.rects[index]
        x1, y1 = r.get_x1(), r.get_y1()
        x2 = r.get_x2()
        se, le = self.site_edits[index], self.length_edits[index]
        w = min(54, max(40, int((x2 - x1) / 2 - 2)))
        top = max(0, int(y1 - 44))
        se.setGeometry(int(x1), top, w, 20)
        le.setGeometry(int(x1) + w + 2, top, w, 20)
        le.setVisible(self.view_id == 0)   # 仅口内视图显示冠长

    def _notify(self):
        if self.on_change:
            self.on_change()

    # ---------- 鼠标交互（照搬 DragRectsAdapter） ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self.image_view.mousePressEvent(e)
            return
        if e.button() == Qt.LeftButton:
            p = QPointF(e.position())
            # 优先：命中中轴线则进入拖动
            if self._hit_sym(p.x()):
                self._sym_drag = True
                self._start = p
                super().mousePressEvent(e)
                return
            self._start = p
            self._flag = POINT_OUT_RECT
            for i, r in enumerate(self.rects):
                f = r.get_point_flag(self._start)
                if f != POINT_OUT_RECT:
                    self._index = i
                    self._flag = f
                    break
            if self._flag == POINT_OUT_RECT:
                r = DrawableRect(self._start.x(), self._start.y(), self._start.x(), self._start.y())
                self.rects.append(r)
                self._add_edits_only()
                self._index = len(self.rects) - 1
                self._dragging = True
                self.update()
            else:
                r = self.rects[self._index]
                self._p1 = QPointF(r.get_x1(), r.get_y1())
                self._p2 = QPointF(r.get_x2(), r.get_y2())
                self._p3 = QPointF(r.get_x2(), r.get_y1())
                self._p4 = QPointF(r.get_x1(), r.get_y2())
                self._dragging = True
        super().mousePressEvent(e)

    def _add_edits_only(self):
        se = NumberEdit(False, self)
        le = NumberEdit(True, self)
        se.setPlaceholderText("牙位")
        le.setPlaceholderText("冠长")
        se.show()
        le.show()
        self.site_edits.append(se)
        self.length_edits.append(le)

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MiddleButton:
            self.image_view.mouseMoveEvent(e)
            return
        p = QPointF(e.position())
        if self._sym_drag and (e.buttons() & Qt.LeftButton):
            # 拖动中轴线：更新图像坐标
            ip = self.image_view.to_image(p.x(), p.y())
            self.sym_axis = max(0.0, ip.x())
            self.update()
            return
        if self._dragging and (e.buttons() & Qt.LeftButton):
            tmp = p
            bdp = self.rects[self._index]
            x1 = y1 = x2 = y2 = 0.0
            s = self._start
            if self._flag == POINT_OUT_RECT:
                x1, y1, x2, y2 = s.x(), s.y(), tmp.x(), tmp.y()
            elif self._flag == POINT_NW:
                x1, y1, x2, y2 = tmp.x(), tmp.y(), self._p2.x(), self._p2.y()
            elif self._flag == POINT_NE:
                x1, y1, x2, y2 = tmp.x(), tmp.y(), self._p4.x(), self._p4.y()
            elif self._flag == POINT_SW:
                x1, y1, x2, y2 = tmp.x(), tmp.y(), self._p3.x(), self._p3.y()
            elif self._flag == POINT_SE:
                x1, y1, x2, y2 = tmp.x(), tmp.y(), self._p1.x(), self._p1.y()
            elif self._flag == POINT_ON_NB:
                x1, y1, x2, y2 = bdp.get_x1(), tmp.y(), self._p2.x(), self._p2.y()
            elif self._flag == POINT_ON_SB:
                x1, y1, x2, y2 = self._p1.x(), self._p1.y(), bdp.get_x2(), tmp.y()
            elif self._flag == POINT_ON_WB:
                x1, y1, x2, y2 = self._p2.x(), self._p2.y(), tmp.x(), bdp.get_y1()
            elif self._flag == POINT_ON_EB:
                x1, y1, x2, y2 = self._p1.x(), self._p1.y(), tmp.x(), bdp.get_y2()
            elif self._flag == POINT_IN_RECT:
                ox = tmp.x() - s.x()
                oy = tmp.y() - s.y()
                x1, y1 = self._p1.x() + ox, self._p1.y() + oy
                x2, y2 = self._p2.x() + ox, self._p2.y() + oy
            bdp.set_point(x1, y1, x2, y2)
            self._layout_edits(self._index)
            self.update()
        else:
            # 光标变化
            flag = POINT_OUT_RECT
            for r in self.rects:
                f = r.get_point_flag(QPointF(e.position()))
                if f != POINT_OUT_RECT:
                    flag = f
                    break
            self._apply_cursor(flag)
        super().mouseMoveEvent(e)

    def _apply_cursor(self, flag: int):
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtGui import QCursor
        cursors = {
            POINT_NW: _Qt.SizeFDiagCursor, POINT_SE: _Qt.SizeFDiagCursor,
            POINT_NE: _Qt.SizeBDiagCursor, POINT_SW: _Qt.SizeBDiagCursor,
            POINT_ON_NB: _Qt.SizeVerCursor, POINT_ON_SB: _Qt.SizeVerCursor,
            POINT_ON_WB: _Qt.SizeHorCursor, POINT_ON_EB: _Qt.SizeHorCursor,
            POINT_IN_RECT: _Qt.SizeAllCursor,
        }
        c = cursors.get(flag, _Qt.ArrowCursor)
        if c == _Qt.ArrowCursor:
            self.unsetCursor()
        else:
            self.setCursor(QCursor(c))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self.image_view.mouseReleaseEvent(e)
            return
        if e.button() == Qt.LeftButton:
            if self._sym_drag:
                self._sym_drag = False
                self._notify()
                super().mouseReleaseEvent(e)
                return
            if self._dragging:
                end = QPointF(e.position())
                if self._start == end and self._flag == POINT_OUT_RECT:
                    self._remove_at(self._index)
                self._dragging = False
                self._notify()
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        # 双击也结束当前画框（避免误删除）
        super().mouseDoubleClickEvent(e)

    def contextMenuEvent(self, e):
        """右键删除矩形"""
        pos = QPointF(e.pos())
        for i in range(len(self.rects) - 1, -1, -1):
            if self.rects[i].get_point_flag(pos) == POINT_IN_RECT:
                self._remove_at(i)
                self._notify()
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
        for r in self.rects:
            r.draw(painter)
        self._draw_sym(painter)
        painter.end()

    def zoom_sync(self):
        """图像视图缩放/平移后同步"""
        for i in range(len(self.rects)):
            self._layout_edits(i)
        self.update()

    def sync_edits_from_view(self):
        for i in range(len(self.rects)):
            self._layout_edits(i)
