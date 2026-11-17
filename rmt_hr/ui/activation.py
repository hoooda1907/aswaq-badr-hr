from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QGroupBox, QFormLayout,
                               QHBoxLayout)

from .. import APP_NAME, licensing
from .common import logo_label, signature_label, warn, info

_REASONS = {"trial": "انتهت مدة النسخة التجريبية (أسبوع).",
            "clock": "تم اكتشاف تغيير في تاريخ الجهاز. يلزم تفعيل البرنامج.",
            "tamper": "تعذر التحقق من بيانات الترخيص. يلزم تفعيل البرنامج."}


class ActivationDialog(QDialog):
    """نافذة التفعيل. expired=True: لا يمكن إغلاقها إلا بالتفعيل أو الخروج من البرنامج."""

    def __init__(self, lic, expired=False, reason="trial", parent=None):
        super().__init__(parent)
        self.lic = lic
        self.setWindowTitle(APP_NAME + " — تفعيل البرنامج")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.addWidget(logo_label(100))
        st = lic.status()
        if expired:
            head = "<b style='color:#c0392b'>%s</b><br>أدخل كود التفعيل للمتابعة." % _REASONS.get(reason, _REASONS["trial"])
        elif st["state"] == "trial":
            head = "نسخة تجريبية — المتبقي <b>%d</b> يوم. أدخل كود التفعيل لإلغاء القيود." % st["days_left"]
        else:
            head = "<b style='color:#1b9e4b'>البرنامج مفعّل على هذا الجهاز.</b>"
        t = QLabel(head)
        t.setWordWrap(True)
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        mid = QLabel("رقم الجهاز: <b>%s</b>" % licensing.machine_short())
        mid.setAlignment(Qt.AlignCenter)
        mid.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(mid)

        form = QFormLayout()
        self.code = QLineEdit()
        self.code.setPlaceholderText("كود التفعيل")
        self.code.setAlignment(Qt.AlignCenter)
        form.addRow("كود التفعيل", self.code)
        lay.addLayout(form)
        g = QGroupBox("في حالة فشل التفعيل بالكود")
        gl = QFormLayout(g)
        self.master = QLineEdit()
        self.master.setEchoMode(QLineEdit.Password)
        gl.addRow("كلمة السر الرئيسية", self.master)
        lay.addWidget(g)

        row = QHBoxLayout()
        b = QPushButton("تفعيل")
        b.setDefault(True)
        b.clicked.connect(self._activate)
        c = QPushButton("خروج من البرنامج" if expired else "إغلاق")
        c.setObjectName("secondary")
        c.clicked.connect(self.reject)
        row.addWidget(b)
        row.addWidget(c)
        lay.addLayout(row)
        lay.addWidget(signature_label())

    def _activate(self):
        ok, msg = self.lic.activate(self.code.text(), self.master.text())
        if ok:
            info(self, msg)
            self.accept()
        else:
            warn(self, msg)
            self.master.clear()
