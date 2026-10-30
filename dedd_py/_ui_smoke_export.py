# -*- coding: utf-8 -*-
"""导出排版回归测试：按原图分辨率导出（与窗口大小无关）+ 四张图版式"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image
from PySide6.QtWidgets import QApplication

from dedd.export_render import export_case
from dedd.widgets.main_window import MainWindow

OUT = os.environ.get("TEMP", r"C:\Users\Gong\AppData\Local\Temp")
HERE = os.path.dirname(os.path.abspath(__file__))
D1 = os.path.join(OUT, "dedd_export_big")
D2 = os.path.join(OUT, "dedd_export_small")


def clean(d):
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(1500, 1000)
    w.show()
    app.processEvents()

    work = os.path.join(OUT, "smoke_export.deddp")
    shutil.copyfile(os.path.join(HERE, "示例工程.deddp"), work)
    w._load_project_path(work)
    app.processEvents()
    w.one_click_flow()
    app.processEvents()

    orig = w.workspace.base_panel.get_image()
    print("原始口内图:", orig.width(), "x", orig.height())

    clean(D1)
    files = export_case(w.workspace, w.basic_info, D1, stem="smoke")
    for f in files:
        im = Image.open(f)
        print(os.path.basename(f), im.size, round(os.path.getsize(f) / 1024), "KB")
    assert len(files) == 4, "应导出四张图"

    design = Image.open([f for f in files if "设计图" in f][0])
    expect_w = min(orig.width(), 1800) + 128
    print("设计图宽度:", design.width, "期望:", expect_w)
    assert design.width == expect_w, "设计图应为原图分辨率（+两侧边距）"

    # 窗口缩小后导出，分辨率必须不变（原来截界面会跟着窗口缩水）
    w.resize(520, 380)
    app.processEvents()
    clean(D2)
    files2 = export_case(w.workspace, w.basic_info, D2, stem="smoke")
    design2 = Image.open([f for f in files2 if "设计图" in f][0])
    print("缩小窗口后设计图:", design2.size, "（应与上面一致）")
    assert design2.size == design.size, "导出分辨率不应受窗口大小影响"

    best = [f for f in files if "总图" in f][0]
    shutil.copyfile(best, os.path.join(OUT, "ui_6_export_sheet.jpg"))
    print("OK")
    w.dirty = False
    w.close()
    os.remove(work)


if __name__ == "__main__":
    main()
