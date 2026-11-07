import os
import sys

try:
    from PySide6.QtCore import Qt
except ImportError as _e:   # عادةً: مكتبات Visual C++ ناقصة على الجهاز
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            "تعذر تحميل مكتبات الواجهة (Qt).\n\nالحل: ثبّت Microsoft Visual C++ Redistributable (x64) ثم أعد تشغيل البرنامج:\n"
            "https://aka.ms/vs/17/release/vc_redist.x64.exe\n\n"
            "ملاحظة: البرنامج يحتاج ويندوز 10 (64 بت) أو أحدث.\n\nالتفاصيل: %s" % _e,
            "Aswaq Badr HR", 0x10)
    except Exception:
        pass
    sys.exit(1)
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog

from aswaq_hr import APP_NAME
from aswaq_hr.db import Database
from aswaq_hr.ui.branch import BranchWindow
from aswaq_hr.ui.common import STYLE, data_dir, resource_path
from aswaq_hr.ui.login import LoginDialog, SetupPasswordDialog
from aswaq_hr.ui.main_window import MainWindow


class Controller:
    def __init__(self, db, user):
        self.db, self.user, self.main = db, user, None
        self.branch_win = BranchWindow(self.open_branch)

    def start(self):
        self.branch_win.show()

    def open_branch(self, branch):
        old = self.main
        self.main = MainWindow(self.db, self.user, branch, self.back_to_branches)
        self.main.show()
        self.branch_win.hide()
        if old:
            old.close()

    def back_to_branches(self):
        self.branch_win.show()
        if self.main:
            self.main.close()
            self.main = None


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setLayoutDirection(Qt.RightToLeft)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setWindowIcon(QIcon(resource_path("assets/icon.ico")))

    db = Database(os.path.join(data_dir(), "aswaq_hr.db"))

    if db.user_count() == 0:
        SetupPasswordDialog(db).exec()      # الاستخدام الأول (يمكن لمدير النظام الدخول حتى لو أُلغيت)

    login = LoginDialog(db)
    if login.exec() != QDialog.Accepted:
        return 0

    ctl = Controller(db, login.user)
    ctl.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
