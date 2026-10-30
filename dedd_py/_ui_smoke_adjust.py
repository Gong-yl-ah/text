# -*- coding: utf-8 -*-
"""操作手感回归测试：选中读数 / 键盘微调 / 撤销重做覆盖调整 / Shift 等比缩放"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from dedd.widgets.main_window import MainWindow

OUT = os.environ.get("TEMP", r"C:\Users\Gong\AppData\Local\Temp")
HERE = os.path.dirname(os.path.abspath(__file__))


def mouse(kind, x, y, button, buttons, mods=Qt.NoModifier):
    p = QPointF(x, y)
    return QMouseEvent(kind, p, p, button, buttons, mods)


def rect_of(panel, i=0):
    d = panel.get_current_teeth_data()[i]
    return d.x1, d.y1, d.x2, d.y2


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(1400, 900)
    w.show()
    app.processEvents()

    work = os.path.join(OUT, "smoke_adjust.deddp")
    shutil.copyfile(os.path.join(HERE, "示例工程.deddp"), work)
    w._load_project_path(work)
    app.processEvents()

    w.tabs.setCurrentIndex(4)          # 美学设计
    app.processEvents()
    bp = w.workspace.base_panel
    ap = bp.adjust_panel
    print("adjust teeth:", len(ap.items))
    assert ap.items, "调整面板应有牙"

    # 1) 选中 + 状态栏读数
    ap.select(0)
    msg = w.statusBar().currentMessage()
    print("status:", msg)
    assert "宽长比" in msg and "选中牙位" in msg, "状态栏应显示选中读数"

    # 2) 键盘微调（1px / Shift 10px）
    r0 = rect_of(ap)
    ap.setFocus()
    QTest.keyClick(ap, Qt.Key_Right)
    app.processEvents()
    r1 = rect_of(ap)
    print("nudge 1px dx:", round(r1[0] - r0[0], 2))
    assert abs((r1[0] - r0[0]) - 1.0) < 0.01, "方向键应微移 1px"

    QTest.keyClick(ap, Qt.Key_Right, Qt.ShiftModifier)
    app.processEvents()
    r2 = rect_of(ap)
    print("nudge shift dx:", round(r2[0] - r1[0], 2))
    assert abs((r2[0] - r1[0]) - 10.0) < 0.01, "Shift+方向键应移 10px"

    # 3) 撤销覆盖调整面板
    ok = w.workspace.undo()
    app.processEvents()
    r3 = rect_of(ap)
    print("undo ok:", ok, "-> dx from r1:", round(r3[0] - r1[0], 2))
    assert ok and abs(r3[0] - r1[0]) < 0.01, "撤销应回到 Shift 微调之前"

    ok = w.workspace.redo()
    app.processEvents()
    r4 = rect_of(ap)
    print("redo ok:", ok, "-> dx from r2:", round(r4[0] - r2[0], 2))
    assert ok and abs(r4[0] - r2[0]) < 0.01, "重做应回到 Shift 微调之后"

    # 4) 宽 / 高键盘调整
    w0 = ap.items[0].rect_img.width
    QTest.keyClick(ap, Qt.Key_BracketRight)
    app.processEvents()
    w1 = ap.items[0].rect_img.width
    print("width grow:", round(w1 - w0, 2))
    assert w1 > w0, "[ 应能加宽"

    # 5) Shift 等比缩放（角落拖拽）
    it = ap.items[0]
    vx1, vy1, vx2, vy2 = ap._to_view(it.rect_img)
    aspect0 = (vx2 - vx1) / (vy2 - vy1)
    ap.mousePressEvent(mouse(QEvent.MouseButtonPress, vx2 - 1, vy2 - 1,
                             Qt.LeftButton, Qt.LeftButton))
    ap.mouseMoveEvent(mouse(QEvent.MouseMove, vx2 + 40, vy2 + 2,
                            Qt.NoButton, Qt.LeftButton, Qt.ShiftModifier))
    ap.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, vx2 + 40, vy2 + 2,
                               Qt.LeftButton, Qt.NoButton, Qt.ShiftModifier))
    app.processEvents()
    nvx1, nvy1, nvx2, nvy2 = ap._to_view(it.rect_img)
    aspect1 = (nvx2 - nvx1) / (nvy2 - nvy1)
    print(f"aspect before {aspect0:.3f} after {aspect1:.3f}")
    assert abs(aspect1 - aspect0) < 0.02, "Shift 拖角应保持宽高比"

    # 6) 亮度改动也能撤销
    b0, y0 = ap.get_bright_yellow()
    ap.bright, ap.yellow = b0 + 12, y0 - 6
    ap._apply_bright_yellow()
    ap._notify()
    app.processEvents()
    w.workspace.undo()
    app.processEvents()
    print("bright after undo:", ap.bright, ap.yellow, "(baseline", b0, y0, ")")
    assert (ap.bright, ap.yellow) == (b0, y0), "撤销应恢复亮度/黄度"

    w.grab().save(os.path.join(OUT, "ui_5_adjust_handles.png"))
    w.dirty = False
    w.close()
    os.remove(work)
    print("OK")


if __name__ == "__main__":
    main()
