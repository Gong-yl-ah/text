# -*- coding: utf-8 -*-
"""数字化美学牙科分析与设计 —— 程序入口

运行：python main.py
"""
import sys


def main():
    from PySide6.QtWidgets import QApplication
    from dedd.widgets.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("数字化美学牙科分析与设计")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
