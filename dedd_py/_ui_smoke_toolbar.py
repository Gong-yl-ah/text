# -*- coding: utf-8 -*-
"""工具栏分发回归测试：每个流程步骤只显示相关按钮"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication

from dedd.constants import (TAB_ADJUST, TAB_EDIT, TAB_EXPORT, TAB_MARK_LIP,
                            TAB_MARK_TEETH, TAB_UNIFY)
from dedd.widgets.main_window import MainWindow

OUT = os.environ.get("TEMP", r"C:\Users\Gong\AppData\Local\Temp")
HERE = os.path.dirname(os.path.abspath(__file__))

EXPECT = {
    0: {"一键完成", "导入照片", "人脸分析"},
    1: {"撤销", "重做"},
    2: {"撤销", "重做"},
    3: {"AI检测", "撤销", "重做", "中轴线", "镜像复制"},
    4: {"自动优化", "重新设计", "撤销", "重做", "中轴线", "镜像复制", "美学参数", "一键完成"},
    5: {"保存设计图", "导出全部图（设计图 / 两向对比 / 总图）"},
}


def toolbar_texts(win):
    return {a.text() for a in win.toolbar.actions() if a.text()}


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(1500, 1000)
    w.show()
    app.processEvents()

    print("引导页工具栏:", toolbar_texts(w))
    assert toolbar_texts(w) == {"导入照片"}, "引导页只应显示『导入照片』"

    work = os.path.join(OUT, "smoke_toolbar.deddp")
    shutil.copyfile(os.path.join(HERE, "示例工程.deddp"), work)
    w._load_project_path(work)
    app.processEvents()

    labels = (TAB_EDIT, TAB_UNIFY, TAB_MARK_LIP, TAB_MARK_TEETH, TAB_ADJUST, TAB_EXPORT)
    for i, name in enumerate(labels):
        w.tabs.setCurrentIndex(i)
        app.processEvents()
        got = toolbar_texts(w)
        print(f"[{i}] {name}: {sorted(got)}")
        assert got == EXPECT[i], f"{name} 工具栏不符：{sorted(got)} != {sorted(EXPECT[i])}"
        if i in (3, 5):
            w.grab().save(os.path.join(OUT, f"ui_7_toolbar_tab{i}.png"))

    # 关闭工程后回到引导页工具栏
    w.dirty = False
    w._close_workspace()
    app.processEvents()
    print("关闭后工具栏:", toolbar_texts(w))
    assert toolbar_texts(w) == {"导入照片"}

    w.close()
    os.remove(work)
    print("OK")


if __name__ == "__main__":
    main()
