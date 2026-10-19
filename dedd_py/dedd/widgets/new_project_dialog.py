# -*- coding: utf-8 -*-
"""新建项目对话框 —— 对应原 DEDD 项目的 NewProjPane"""
from __future__ import annotations

import os

from PySide6.QtWidgets import (QDialog, QFileDialog, QFormLayout, QHBoxLayout,
                               QLineEdit, QPushButton, QRadioButton,
                               QVBoxLayout)

from ..constants import (AGE, CANCEL, FEMALE, GENDER, MALE, NAME, OK, PHONE,
                         SAVE_PATH, TITLE_NEW_PROJ, UNNAMED)
from ..models import BasicInfo


class NewProjectDialog(QDialog):
    def __init__(self, default_dir: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(TITLE_NEW_PROJ)
        self.setMinimumWidth(460)
        self.basic_info: BasicInfo = BasicInfo()
        self.save_path: str = ""

        root = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(UNNAMED)
        form.addRow(f"{NAME}:", self.name_edit)

        gender_row = QHBoxLayout()
        self.rb_male = QRadioButton(MALE)
        self.rb_female = QRadioButton(FEMALE)
        self.rb_male.setChecked(True)
        gender_row.addWidget(self.rb_male)
        gender_row.addWidget(self.rb_female)
        gender_row.addStretch(1)
        form.addRow(f"{GENDER}:", gender_row)

        self.age_edit = QLineEdit()
        self.age_edit.setPlaceholderText("0-120")
        form.addRow(f"{AGE}:", self.age_edit)

        self.phone_edit = QLineEdit()
        form.addRow(f"{PHONE}:", self.phone_edit)

        self.path_edit = QLineEdit()
        btn_browse = QPushButton("...")
        btn_browse.setFixedWidth(40)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(btn_browse)
        form.addRow(SAVE_PATH, path_row)

        root.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_ok = QPushButton(OK)
        self.btn_cancel = QPushButton(CANCEL)
        btn_row.addWidget(self.btn_ok)
        btn_row.addWidget(self.btn_cancel)
        root.addLayout(btn_row)

        # 默认保存路径
        default_path = os.path.join(default_dir or os.path.expanduser("~/Documents"),
                                    UNNAMED + ".deddp")
        self.path_edit.setText(default_path)

        btn_browse.clicked.connect(self._browse)
        self.btn_ok.clicked.connect(self._ok)
        self.btn_cancel.clicked.connect(self.reject)

    def _browse(self):
        path, _ = QFileDialog.getSaveFileName(self, SAVE_PATH, self.path_edit.text(), "DEDD工程 (*.deddp)")
        if path:
            self.path_edit.setText(path)

    def _ok(self):
        name = self.name_edit.text().strip() or UNNAMED
        gender = MALE if self.rb_male.isChecked() else FEMALE
        try:
            age = int(self.age_edit.text()) if self.age_edit.text().strip() else 0
        except ValueError:
            age = 0
        phone = self.phone_edit.text().strip()
        self.basic_info = BasicInfo(name=name, age=age, gender=gender, phone=phone)
        path = self.path_edit.text().strip()
        if not path.lower().endswith(".deddp"):
            path += ".deddp"
        self.save_path = path
        self.accept()
