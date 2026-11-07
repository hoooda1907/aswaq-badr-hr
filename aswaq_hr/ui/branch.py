from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton

from .. import APP_NAME
from ..constants import BRANCHES
from .common import logo_label, signature_label


class BranchWindow(QWidget):
    def __init__(self, on_choose):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle(APP_NAME + " — اختيار الفرع")
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.addWidget(logo_label(150))
        t = QLabel("<h1 style='color:#1b9e4b'>%s</h1><p align='center'>اختر الفرع</p>" % APP_NAME)
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        for b in BRANCHES:
            btn = QPushButton(b)
            btn.setObjectName("branch")
            btn.clicked.connect(lambda _=False, name=b: on_choose(name))
            lay.addWidget(btn, alignment=Qt.AlignCenter)
        lay.addStretch()
        lay.addWidget(signature_label())
        self.resize(520, 780)
