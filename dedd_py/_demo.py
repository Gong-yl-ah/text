# -*- coding: utf-8 -*-
"""生成演示效果图（供用户查看程序运行效果）"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PIL import Image, ImageDraw
from PySide6.QtWidgets import QApplication

app = QApplication([])

from dedd.image_utils import np_to_qimage
from dedd.models import BasicInfo, ToothData
from dedd.widgets.main_window import MainWindow


def make_test_image(w=800, h=600, kind="base"):
    img = np.full((h, w, 3), (208, 203, 198), np.uint8)
    if kind == "front":
        # 模拟面部
        img[40:520, 160:640] = (232, 198, 176)
        # 模拟嘴部
        img[290:400, 280:520] = (176, 118, 108)
        # 牙齿
        for i in range(6):
            x = 300 + i * 36
            img[300:380, x:x + 30] = (240, 238, 234)
    else:
        # 模拟牙龈
        img[140:460, 180:620] = (222, 158, 148)
        # 模拟牙齿
        for i in range(6):
            x = 210 + i * 62
            img[190:390, x:x + 48] = (243, 242, 240)
            img[195:385, x + 5:x + 43] = (250, 249, 247)
    return img


def main():
    w = MainWindow()
    w.basic_info = BasicInfo(name="演示患者", age=30, gender="男", phone="13800000000")
    w.proj_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "示例工程.deddp")
    w._new_workspace()
    w.show()
    app.processEvents()

    w.workspace.base_panel.set_image(np_to_qimage(make_test_image(kind="base")))
    w.workspace.front_panel.set_image(np_to_qimage(make_test_image(kind="front")))
    app.processEvents()

    base_teeth = [
        ToothData(site=13, x1=200, y1=150, x2=258, y2=340, length=9.6),
        ToothData(site=12, x1=268, y1=155, x2=322, y2=342, length=8.8),
        ToothData(site=11, x1=332, y1=148, x2=392, y2=348, length=9.3),
        ToothData(site=21, x1=402, y1=150, x2=462, y2=346, length=9.1),
        ToothData(site=22, x1=472, y1=156, x2=524, y2=340, length=8.7),
        ToothData(site=23, x1=534, y1=152, x2=590, y2=338, length=9.4),
    ]
    front_teeth = [
        ToothData(site=13, x1=296, y1=296, x2=330, y2=386, length=9.6),
        ToothData(site=12, x1=336, y1=298, x2=368, y2=388, length=8.8),
        ToothData(site=11, x1=374, y1=294, x2=410, y2=392, length=9.3),
        ToothData(site=21, x1=416, y1=295, x2=452, y2=390, length=9.1),
        ToothData(site=22, x1=458, y1=299, x2=488, y2=386, length=8.7),
        ToothData(site=23, x1=494, y1=297, x2=526, y2=384, length=9.4),
    ]
    w.workspace.base_panel.set_marked_teeth(base_teeth)
    w.workspace.front_panel.set_marked_teeth(front_teeth)
    w.workspace.set_lip_points([(300, 262), (360, 250), (420, 246), (480, 250), (530, 262)])
    w.workspace.set_lip_closed(False)

    w.workspace.enter_adjust()
    w.workspace.auto_adjust()
    w.workspace.set_bright_yellow(0, 22, 6)
    w.workspace.set_bright_yellow(1, 14, 4)
    app.processEvents()

    out_dir = os.path.dirname(os.path.abspath(__file__))
    base_after = w.workspace.base_panel.render_to_np(with_overlay=True)
    front_after = w.workspace.front_panel.render_to_np(with_overlay=True)
    if base_after is not None:
        Image.fromarray(base_after).save(os.path.join(out_dir, "演示_口内设计效果.jpg"), "JPEG", quality=90)
    if front_after is not None:
        Image.fromarray(front_after).save(os.path.join(out_dir, "演示_正面设计效果.jpg"), "JPEG", quality=90)
    print("demo images saved")

    # 界面截图
    w.tabs.setCurrentIndex(4)
    w.workspace.enter_adjust()
    app.processEvents()
    pm = w.grab()
    pm.save(os.path.join(out_dir, "演示_程序界面.png"), "PNG")
    print("ui screenshot saved")


if __name__ == "__main__":
    main()
