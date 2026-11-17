from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QSpinBox, QCheckBox, QLineEdit,
                               QPushButton, QApplication)

from ..passgen import generate_password


class PasswordGeneratorDialog(QDialog):
    """مولّد كلمات مرور عشوائية للمستخدمين."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("مولّد كلمات المرور")
        self.setMinimumWidth(400)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.length = QSpinBox(); self.length.setRange(6, 40); self.length.setValue(12)
        self.upper, self.lower = QCheckBox("حروف كبيرة A-Z"), QCheckBox("حروف صغيرة a-z")
        self.digits, self.symbols = QCheckBox("أرقام 0-9"), QCheckBox("رموز !@#$%")
        for c in (self.upper, self.lower, self.digits):
            c.setChecked(True)
        form.addRow("الطول", self.length)
        for c in (self.upper, self.lower, self.digits, self.symbols):
            form.addRow(c)
        lay.addLayout(form)
        self.out = QLineEdit()
        self.out.setReadOnly(True)
        self.out.setAlignment(Qt.AlignCenter)
        self.out.setStyleSheet("font-size:15pt; font-family:Consolas,monospace;")
        lay.addWidget(self.out)
        row = QHBoxLayout()
        g, c = QPushButton("توليد"), QPushButton("نسخ")
        c.setObjectName("secondary")
        g.clicked.connect(self.generate)
        c.clicked.connect(lambda: QApplication.clipboard().setText(self.out.text()))
        row.addWidget(g); row.addWidget(c)
        lay.addLayout(row)
        self.generate()

    def generate(self):
        self.out.setText(generate_password(self.length.value(), self.upper.isChecked(), self.lower.isChecked(),
                                           self.digits.isChecked(), self.symbols.isChecked()))
