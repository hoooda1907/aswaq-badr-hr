from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QInputDialog)

from .. import APP_NAME
from ..constants import BRANCH_MODE
from .common import logo_label, signature_label, warn


class BranchWindow(QWidget):
    def __init__(self, on_choose, db):
        super().__init__()
        self.on_choose, self.db = on_choose, db
        self.dynamic = BRANCH_MODE == "dynamic"
        self.setObjectName("root")
        self.setWindowTitle(APP_NAME + " — اختيار الفرع")
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.addWidget(logo_label(150))
        t = QLabel("<h1 style='color:#1b9e4b'>%s</h1><p align='center'>اختر الفرع</p>" % APP_NAME)
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        self.box = QVBoxLayout()
        self.box.setAlignment(Qt.AlignCenter)
        lay.addLayout(self.box)
        if self.dynamic:
            add = QPushButton("+ إضافة فرع")
            add.setObjectName("secondary")
            add.clicked.connect(self.add_branch)
            lay.addWidget(add, alignment=Qt.AlignCenter)
        lay.addStretch()
        lay.addWidget(signature_label())
        self.resize(520, 780 if not self.dynamic else 620)
        self.rebuild()

    def rebuild(self):
        while self.box.count():
            item = self.box.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()
        for b in self.db.branches():
            row = QHBoxLayout()
            row.setAlignment(Qt.AlignCenter)
            btn = QPushButton(b)
            btn.setObjectName("branch")
            btn.clicked.connect(lambda _=False, name=b: self.on_choose(name))
            row.addWidget(btn)
            if self.dynamic:
                ed = QPushButton("تعديل الاسم")
                ed.setObjectName("secondary")
                ed.clicked.connect(lambda _=False, name=b: self.rename_branch(name))
                row.addWidget(ed)
            self.box.addLayout(row)

    def add_branch(self):
        name, ok = QInputDialog.getText(self, "إضافة فرع", "اسم الفرع الجديد:")
        if not ok:
            return
        done, msg = self.db.add_branch(name)
        if not done:
            return warn(self, msg)
        self.rebuild()

    def rename_branch(self, old):
        name, ok = QInputDialog.getText(self, "تعديل اسم الفرع", "الاسم الجديد:", text=old)
        if not ok:
            return
        done, msg = self.db.rename_branch(old, name)
        if not done:
            return warn(self, msg)
        self.rebuild()
