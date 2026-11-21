import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QLabel, QPushButton,
                               QFileDialog)

from .. import APP_NAME, branding
from .common import data_dir, logo_file, warn, info

MAX_LOGO = 600


class BrandingDialog(QDialog):
    """تغيير اسم الشركة/البرنامج والشعار. يظهران في سند المرتب وكل التقارير وشاشات البرنامج."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.new_image = None          # QImage مختار ولم يُحفظ بعد
        self.remove_logo = False
        self.setWindowTitle("الاسم والشعار")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(branding.name())
        self.name.setPlaceholderText(APP_NAME)
        form.addRow("الاسم الظاهر في البرنامج والسند", self.name)
        lay.addLayout(form)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(150)
        self.preview.setStyleSheet("border:1px dashed #aaa; border-radius:8px; background:white;")
        lay.addWidget(self.preview)
        self._show(QPixmap(logo_file()))

        row = QHBoxLayout()
        b_pick = QPushButton("اختيار شعار...")
        b_pick.clicked.connect(self.pick)
        b_def = QPushButton("الشعار الافتراضي")
        b_def.setObjectName("secondary")
        b_def.clicked.connect(self.use_default)
        row.addWidget(b_pick)
        row.addWidget(b_def)
        lay.addLayout(row)
        note = QLabel("الصيغ المدعومة: PNG / JPG / BMP / ICO. يُفضَّل شعار مربع بخلفية شفافة. "
                      "يُحفظ مع بيانات البرنامج ولا يتأثر بتحديثه.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#666;")
        lay.addWidget(note)

        row2 = QHBoxLayout()
        b_save, b_reset, b_close = QPushButton("حفظ"), QPushButton("إعادة الاسم والشعار الافتراضيين"), QPushButton("إلغاء")
        b_reset.setObjectName("secondary")
        b_close.setObjectName("secondary")
        b_save.clicked.connect(self.save)
        b_reset.clicked.connect(self.reset)
        b_close.clicked.connect(self.reject)
        row2.addWidget(b_save)
        row2.addWidget(b_reset)
        row2.addStretch()
        row2.addWidget(b_close)
        lay.addLayout(row2)

    def _show(self, pm):
        self.preview.setPixmap(pm.scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def pick(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختر الشعار", "", "صور (*.png *.jpg *.jpeg *.bmp *.ico);;كل الملفات (*)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            return warn(self, "تعذر قراءة الصورة. اختر ملف صورة صالح.")
        if max(img.width(), img.height()) > MAX_LOGO:
            img = img.scaled(MAX_LOGO, MAX_LOGO, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.new_image, self.remove_logo = img, False
        self._show(QPixmap.fromImage(img))

    def use_default(self):
        self.new_image, self.remove_logo = None, True
        self._show(self._default_pixmap())

    @staticmethod
    def _default_pixmap():
        from .common import resource_path
        return QPixmap(resource_path("assets/logo.png"))

    def save(self):
        branding.set_name(self.db, self.name.text())
        if self.new_image is not None:
            target = branding.logo_target(data_dir())
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if not self.new_image.save(target, "PNG"):
                return warn(self, "تعذر حفظ الشعار في مجلد البيانات")
            branding.set_logo(self.db, data_dir())
        elif self.remove_logo:
            branding.clear_logo(self.db, data_dir())
        self.accept()

    def reset(self):
        branding.reset(self.db, data_dir())
        info(self, "تمت إعادة الاسم والشعار الافتراضيين.")
        self.accept()
