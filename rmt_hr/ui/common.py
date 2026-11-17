import os
import sys

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QImage, QPixmap, QTextDocument, QPageSize, QPageLayout
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import QFileDialog, QLabel, QMessageBox

from .. import DEVELOPER, APP_ID

GREEN = "#1b9e4b"
GREEN_DARK = "#147a3a"


def project_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return project_root()


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", project_root())
    return os.path.join(base, rel)


def data_dir():
    """نسخة محمولة: لو يوجد ملف portable.txt بجوار البرنامج تُحفظ البيانات في مجلد data بجواره."""
    if os.path.exists(os.path.join(app_dir(), "portable.txt")):
        return os.path.join(app_dir(), "data")
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_ID)


STYLE = """
* { font-family: 'Segoe UI', 'Tahoma', 'Arial'; font-size: 11pt; }
QDialog, QMainWindow, QWidget#root { background: #f4f8f5; }
QPushButton { background: %(g)s; color: white; border: none; padding: 7px 16px; border-radius: 6px; }
QPushButton:hover { background: %(gd)s; }
QPushButton:disabled { background: #a8b8ad; }
QPushButton[flat="true"], QPushButton#secondary { background: #e3ece6; color: #234; }
QPushButton#secondary:hover { background: #d3e2d8; }
QPushButton#danger { background: #c0392b; }
QPushButton#branch { font-size: 15pt; padding: 16px 30px; min-width: 320px; border-radius: 10px; }
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox { padding: 5px; border: 1px solid #b9c9be; border-radius: 5px; background: white; }
QTableWidget { background: white; alternate-background-color: #f1f8f3; gridline-color: #dbe6de; }
QHeaderView::section { background: %(g)s; color: white; padding: 6px; border: none; border-left: 1px solid #fff; }
QTabBar::tab { padding: 8px 18px; background: #e3ece6; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-left: 2px; }
QTabBar::tab:selected { background: %(g)s; color: white; }
QGroupBox { border: 1px solid #b9c9be; border-radius: 8px; margin-top: 12px; padding-top: 10px; background: white; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top right; padding: 0 8px; color: %(gd)s; font-weight: bold; }
""" % {"g": GREEN, "gd": GREEN_DARK}


def logo_pixmap(size):
    pm = QPixmap(resource_path("assets/logo.png"))
    return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def logo_label(size):
    lb = QLabel()
    lb.setPixmap(logo_pixmap(size))
    lb.setAlignment(Qt.AlignCenter)
    return lb


def signature_label():
    lb = QLabel("تصميم وتطوير:  <b>%s</b>" % DEVELOPER)
    lb.setAlignment(Qt.AlignCenter)
    lb.setStyleSheet("color:#6b7a70; font-size:10pt; padding:4px;")
    return lb


def info(parent, text, title="RMT HR"):
    QMessageBox.information(parent, title, text)


def warn(parent, text, title="تنبيه"):
    QMessageBox.warning(parent, title, text)


def ask(parent, text, title="تأكيد"):
    box = QMessageBox(QMessageBox.Question, title, text, QMessageBox.NoButton, parent)
    yes = box.addButton("نعم", QMessageBox.YesRole)
    box.addButton("لا", QMessageBox.NoRole)
    box.exec()
    return box.clickedButton() is yes


def make_doc(html):
    doc = QTextDocument()
    doc.addResource(QTextDocument.ImageResource, QUrl("logo"), QImage(resource_path("assets/logo.png")))
    doc.setHtml(html)
    return doc


def _printer(landscape=False):
    p = QPrinter(QPrinter.HighResolution)
    p.setPageSize(QPageSize(QPageSize.A4))
    if landscape:
        p.setPageOrientation(QPageLayout.Landscape)
    return p


def print_preview(parent, html, landscape=False):
    doc = make_doc(html)
    printer = _printer(landscape)
    dlg = QPrintPreviewDialog(printer, parent)
    dlg.paintRequested.connect(lambda p: doc.print_(p))
    dlg.resize(1000, 750)
    dlg.exec()


def save_pdf(parent, html, default_name, landscape=False):
    path, _ = QFileDialog.getSaveFileName(parent, "حفظ PDF", default_name, "PDF (*.pdf)")
    if not path:
        return
    doc = make_doc(html)
    printer = _printer(landscape)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)
    doc.print_(printer)
    info(parent, "تم حفظ الملف:\n" + path)
