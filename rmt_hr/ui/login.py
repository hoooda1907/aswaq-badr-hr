from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFormLayout,
                               QListWidget, QHBoxLayout, QInputDialog)

from .. import APP_NAME, auth
from .common import logo_label, signature_label, warn, info, ask
from .passgen import PasswordGeneratorDialog


def _pw(placeholder=""):
    e = QLineEdit()
    e.setEchoMode(QLineEdit.Password)
    e.setPlaceholderText(placeholder)
    return e


class LoginDialog(QDialog):
    def __init__(self, db):
        super().__init__()
        self.db, self.user = db, None
        self.setWindowTitle(APP_NAME + " — تسجيل الدخول")
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        lay.addWidget(logo_label(130))
        t = QLabel("<h2 style='color:#1b9e4b'>%s</h2>" % APP_NAME)
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        self.u, self.p = QLineEdit(), _pw()
        self.u.setPlaceholderText("اسم المستخدم")
        self.p.setPlaceholderText("كلمة المرور")
        lay.addWidget(self.u)
        lay.addWidget(self.p)
        self.err = QLabel("")
        self.err.setStyleSheet("color:#c0392b")
        self.err.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.err)
        b = QPushButton("دخول")
        b.setDefault(True)
        b.clicked.connect(self.try_login)
        lay.addWidget(b)
        lay.addWidget(signature_label())
        users = db.list_users()
        if len(users) == 1:
            self.u.setText(users[0])
            self.p.setFocus()

    def try_login(self):
        user = auth.verify(self.db, self.u.text(), self.p.text())
        if user:
            self.user = user
            self.accept()
        else:
            self.err.setText("اسم المستخدم أو كلمة المرور غير صحيحة")
            self.p.clear()
            self.p.setFocus()


class SetupPasswordDialog(QDialog):
    """تظهر في أول استخدام لإنشاء كلمة مرور البرنامج."""

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setWindowTitle("الاستخدام الأول — إنشاء كلمة مرور")
        self.setMinimumWidth(400)
        lay = QVBoxLayout(self)
        lay.addWidget(logo_label(110))
        lay.addWidget(QLabel("<b>مرحباً بك في %s</b><br>من فضلك أنشئ اسم مستخدم وكلمة مرور للبرنامج.<br>"
                             "يمكنك تغييرها في أي وقت من قائمة الإعدادات." % APP_NAME))
        form = QFormLayout()
        self.u = QLineEdit("admin")
        self.p1, self.p2 = _pw(), _pw()
        form.addRow("اسم المستخدم", self.u)
        form.addRow("كلمة المرور", self.p1)
        form.addRow("تأكيد كلمة المرور", self.p2)
        lay.addLayout(form)
        b = QPushButton("حفظ ومتابعة")
        b.clicked.connect(self.save)
        lay.addWidget(b)
        lay.addWidget(signature_label())

    def save(self):
        u, p1, p2 = self.u.text().strip(), self.p1.text(), self.p2.text()
        if not u or u.lower() == "mahmoud":
            return warn(self, "اسم المستخدم غير صالح")
        if len(p1) < 4:
            return warn(self, "كلمة المرور يجب ألا تقل عن 4 أحرف")
        if p1 != p2:
            return warn(self, "كلمتا المرور غير متطابقتين")
        self.db.set_user(u, p1)
        self.accept()


class ChangePasswordDialog(QDialog):
    def __init__(self, db, user):
        super().__init__()
        self.db, self.user = db, user
        self.setWindowTitle("تغيير كلمة المرور")
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.old, self.p1, self.p2 = _pw(), _pw(), _pw()
        form.addRow("كلمة المرور الحالية", self.old)
        form.addRow("كلمة المرور الجديدة", self.p1)
        form.addRow("تأكيد الجديدة", self.p2)
        lay.addLayout(form)
        b = QPushButton("تغيير")
        b.clicked.connect(self.save)
        lay.addWidget(b)

    def save(self):
        if not auth.verify(self.db, self.user["username"], self.old.text()):
            return warn(self, "كلمة المرور الحالية غير صحيحة")
        if len(self.p1.text()) < 4:
            return warn(self, "كلمة المرور يجب ألا تقل عن 4 أحرف")
        if self.p1.text() != self.p2.text():
            return warn(self, "كلمتا المرور غير متطابقتين")
        self.db.set_user(self.user["username"], self.p1.text())
        info(self, "تم تغيير كلمة المرور")
        self.accept()


class UsersDialog(QDialog):
    """إدارة المستخدمين — متاحة لمدير النظام فقط."""

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setWindowTitle("إدارة المستخدمين")
        self.setMinimumSize(360, 320)
        lay = QVBoxLayout(self)
        self.lst = QListWidget()
        lay.addWidget(self.lst)
        row = QHBoxLayout()
        for text, fn, obj in (("إضافة مستخدم", self.add, ""), ("تعيين كلمة مرور", self.reset, "secondary"),
                              ("مولّد كلمات المرور", lambda: PasswordGeneratorDialog(self).exec(), "secondary"),
                              ("حذف", self.delete, "danger")):
            b = QPushButton(text)
            if obj:
                b.setObjectName(obj)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        self.load()

    def load(self):
        self.lst.clear()
        self.lst.addItems(self.db.list_users())

    def _sel(self):
        it = self.lst.currentItem()
        return it.text() if it else None

    def add(self):
        u, ok = QInputDialog.getText(self, "مستخدم جديد", "اسم المستخدم:")
        if not ok or not u.strip() or u.strip().lower() == "mahmoud":
            return
        if self.db.get_user(u.strip()):
            return warn(self, "المستخدم موجود بالفعل")
        p, ok = QInputDialog.getText(self, "كلمة المرور", "كلمة المرور:", QLineEdit.Password)
        if ok and len(p) >= 4:
            self.db.set_user(u.strip(), p)
            self.load()

    def reset(self):
        u = self._sel()
        if not u:
            return
        p, ok = QInputDialog.getText(self, "كلمة مرور جديدة", "كلمة المرور الجديدة لـ %s:" % u, QLineEdit.Password)
        if ok and len(p) >= 4:
            self.db.set_user(u, p)
            info(self, "تم التعيين")

    def delete(self):
        u = self._sel()
        if u and ask(self, "حذف المستخدم %s؟" % u):
            self.db.delete_user(u)
            self.load()
