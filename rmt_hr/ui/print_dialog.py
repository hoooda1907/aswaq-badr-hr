from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QRadioButton, QSpinBox, QCheckBox,
                               QPushButton, QLabel, QGroupBox, QButtonGroup)

from .printing import LAYOUTS, DEFAULT_PRINT, load_settings, save_settings


class PrintSettingsDialog(QDialog):
    """تنسيق طباعة سند المرتب."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("إعدادات الطباعة")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)

        g = QGroupBox("تنسيق السند على الورقة")
        gl = QVBoxLayout(g)
        self.group = QButtonGroup(self)
        self.radios = {}
        for key, label in LAYOUTS:
            r = QRadioButton(label)
            self.group.addButton(r)
            self.radios[key] = r
            gl.addWidget(r)
        lay.addWidget(g)

        form = QFormLayout()
        self.margin = QSpinBox(); self.margin.setRange(3, 25); self.margin.setSuffix(" مم")
        self.scale = QSpinBox(); self.scale.setRange(40, 130); self.scale.setSuffix(" %")
        self.logo = QCheckBox("طباعة الشعار في السند")
        form.addRow("الهوامش", self.margin)
        form.addRow("حجم الخط (الحد الأقصى)", self.scale)
        form.addRow(self.logo)
        lay.addLayout(form)
        note = QLabel("السند لا يتجاوز الورقة أبداً: لو كان أطول من مساحته يُصغَّر تلقائياً حتى يدخل بالكامل. "
                      "حجم الخط هنا هو الحد الأقصى الذي يبدأ منه التصغير.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#666;")
        lay.addWidget(note)

        row = QHBoxLayout()
        b_save, b_def, b_close = QPushButton("حفظ"), QPushButton("القيم الافتراضية"), QPushButton("إغلاق")
        b_def.setObjectName("secondary"); b_close.setObjectName("secondary")
        b_save.clicked.connect(self._save)
        b_def.clicked.connect(lambda: self._load(DEFAULT_PRINT))
        b_close.clicked.connect(self.reject)
        row.addWidget(b_save); row.addWidget(b_def); row.addStretch(); row.addWidget(b_close)
        lay.addLayout(row)
        self._load(load_settings(db))

    def _load(self, st):
        self.radios[st["layout"]].setChecked(True)
        self.margin.setValue(int(st["margin"]))
        self.scale.setValue(int(st["scale"]))
        self.logo.setChecked(bool(st["logo"]))

    def _save(self):
        layout = next(k for k, r in self.radios.items() if r.isChecked())
        save_settings(self.db, {"layout": layout, "margin": self.margin.value(),
                                "scale": self.scale.value(), "logo": self.logo.isChecked()})
        self.accept()
