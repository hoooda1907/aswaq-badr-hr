"""طبقة توافق: يعمل البرنامج بـ PySide6 (ويندوز 10 1809+) وإن لم يوجد يعمل بـ PySide2 (نسخة Legacy لويندوز القديم).
يجب استيراده قبل أي استيراد لـ PySide6."""
import sys

try:
    import PySide6  # noqa: F401
except ImportError:
    try:
        from PySide2 import QtCore, QtGui, QtWidgets, QtPrintSupport
        import PySide2
    except ImportError:
        pass        # لا PySide6 ولا PySide2: يظهر الخطأ الطبيعي للمستخدم من main.py
    else:
        sys.modules["PySide6"] = PySide2
        for _name, _mod in (("QtCore", QtCore), ("QtGui", QtGui), ("QtWidgets", QtWidgets),
                            ("QtPrintSupport", QtPrintSupport)):
            sys.modules["PySide6." + _name] = _mod
        # في PySide2 الدالة اسمها exec_ (و exec غير موجودة في كل الإصدارات)
        for _cls in (QtWidgets.QDialog, QtWidgets.QMessageBox, QtWidgets.QApplication, QtWidgets.QMenu,
                     QtPrintSupport.QPrintPreviewDialog):
            if not hasattr(_cls, "exec") and hasattr(_cls, "exec_"):
                try:
                    _cls.exec = _cls.exec_
                except (TypeError, AttributeError):
                    pass
