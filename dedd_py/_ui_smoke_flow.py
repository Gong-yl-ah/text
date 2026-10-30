# -*- coding: utf-8 -*-
"""UI 冒烟测试：引导页 → 打开工程 → 一键完成 → 导出页 → 关闭回引导页

不弹对话框、不改动仓库里的示例工程（用临时副本）。
"""
import hashlib
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication

from dedd.widgets.main_window import MainWindow

OUT = os.environ.get("TEMP", r"C:\Users\Gong\AppData\Local\Temp")
HERE = os.path.dirname(os.path.abspath(__file__))


def shot(widget, name):
    path = os.path.join(OUT, name)
    widget.grab().save(path)
    print("shot:", path, widget.size().width(), "x", widget.size().height())


def md5(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(1400, 900)
    w.show()
    app.processEvents()

    assert w.stack.currentWidget() is w.welcome, "启动应显示引导页"
    assert not w.tabs.isEnabled(), "无项目时标签应禁用"
    shot(w, "ui_1_welcome.png")

    sample = os.path.join(HERE, "示例工程.deddp")
    sample_md5 = md5(sample)
    work = os.path.join(OUT, "smoke_work.deddp")
    shutil.copyfile(sample, work)

    w._load_project_path(work)
    app.processEvents()
    print("has base img:", w.workspace.base_panel.has_image(),
          "| has front img:", w.workspace.front_panel.has_image())
    print("marked before:", len(w.workspace.get_marked_teeth_data(0)),
          len(w.workspace.get_marked_teeth_data(1)))
    shot(w, "ui_2_project.png")

    w.one_click_flow()
    app.processEvents()
    print("tab index after one-click:", w.tabs.currentIndex())
    base_adj = w.workspace.base_panel.adjust_panel.get_current_teeth_data()
    front_adj = w.workspace.front_panel.adjust_panel.get_current_teeth_data()
    print("adjusted teeth: base", len(base_adj), "front", len(front_adj))
    print("status:", w.statusBar().currentMessage())
    assert w.tabs.currentIndex() == 4, "一键完成应停在『美学设计』"
    assert base_adj and front_adj, "自动优化后应有调整牙数据"
    shot(w, "ui_3_adjust.png")

    w.tabs.setCurrentIndex(5)
    app.processEvents()
    shot(w, "ui_4_export.png")
    print("export btn enabled:", w.act_export.isEnabled())
    assert w.act_export.isEnabled(), "导出页应可保存"

    # 关闭项目 → 应回到引导页
    w.dirty = False
    w._close_workspace()
    app.processEvents()
    print("after close -> welcome:", w.stack.currentWidget() is w.welcome,
          "| tabs disabled:", not w.tabs.isEnabled())
    assert w.stack.currentWidget() is w.welcome

    # 引导页『打开示例工程』：可载入，且作为模板不指向源文件
    w.open_sample_project()
    app.processEvents()
    print("sample loaded:", w.workspace is not None and w.workspace.front_panel.has_image(),
          "| proj_file is None(模板):", w.proj_file is None)
    assert w.workspace is not None and w.proj_file is None
    w.dirty = False
    w.close()
    app.processEvents()
    print("sample untouched:", md5(sample) == sample_md5)
    assert md5(sample) == sample_md5, "示例工程不应被改动"
    os.remove(work)
    print("OK")


if __name__ == "__main__":
    main()
