"""طباعة السندات: ورقة A4 بسند واحد، أو ورقة A4 بسندين فوق بعض. السند لا يتجاوز مساحته أبداً:
يُقاس ارتفاعه بعد التنسيق ويُصغَّر تلقائياً حتى يدخل بالكامل في الورقة (أو نصفها)."""
import json

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen, QPageSize, QPageLayout
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import QFileDialog

from .common import make_doc, info, warn

DEFAULT_PRINT = {"layout": "single", "margin": 6, "scale": 100, "logo": True}
LAYOUTS = (("single", "سند واحد في الورقة (A4)"), ("double", "سندان فوق بعض في الورقة (A4)"))
MIN_SCALE = 0.30


def load_settings(db):
    st = dict(DEFAULT_PRINT)
    try:
        st.update(json.loads(db.get_setting("print") or "{}"))
    except ValueError:
        pass
    if st["layout"] not in ("single", "double"):
        st["layout"] = "single"
    return st


def save_settings(db, st):
    db.set_setting("print", json.dumps({k: st[k] for k in DEFAULT_PRINT}))


def new_printer(landscape=False):
    p = QPrinter(QPrinter.HighResolution)
    p.setPageSize(QPageSize(QPageSize.A4))
    if landscape:
        p.setPageOrientation(QPageLayout.Landscape)
    return p


def fit_document(builder, width, height, printer, base=1.0):
    """يبني المستند بأكبر معامل تصغير ≤ base بحيث يدخل ارتفاعه في `height` (بوحدات بكسل الطابعة)."""
    f = base
    doc = None
    for _ in range(14):
        doc = make_doc(builder(f))
        doc.setDocumentMargin(0)
        doc.documentLayout().setPaintDevice(printer)
        doc.setTextWidth(width)
        h = doc.size().height()
        if h <= height or f <= MIN_SCALE:
            break
        f = max(MIN_SCALE, f * (height / h) * 0.97)
    return doc


def paint_pages(printer, builders, st, landscape=False):
    """يرسم كل builder داخل خانته. builders: دوال f -> HTML. layout=double: خانتان في الصفحة."""
    painter = QPainter()
    if not painter.begin(printer):
        return False
    try:
        dpi = printer.resolution()
        mm = dpi / 25.4
        page = printer.pageRect(QPrinter.DevicePixel)
        m = st["margin"] * mm
        w, h = page.width() - 2 * m, page.height() - 2 * m
        per = 2 if (st["layout"] == "double" and not landscape) else 1
        gap = 6 * mm if per == 2 else 0
        slot_h = (h - gap * (per - 1)) / per
        base = max(0.3, st["scale"] / 100.0)
        for i, builder in enumerate(builders):
            slot = i % per
            if i and slot == 0:
                printer.newPage()
            y = m + slot * (slot_h + gap)
            doc = fit_document(builder, w, slot_h, printer, base)
            painter.save()
            painter.translate(m, y)
            painter.setClipRect(QRectF(0, 0, w, slot_h))
            doc.drawContents(painter, QRectF(0, 0, w, slot_h))
            painter.restore()
            if per == 2 and slot == 0:               # خط القص بين السندين
                pen = QPen(Qt.gray)
                pen.setStyle(Qt.DashLine)
                pen.setWidthF(max(1.0, dpi / 150.0))
                painter.setPen(pen)
                yy = y + slot_h + gap / 2
                painter.drawLine(int(m), int(yy), int(m + w), int(yy))
        return True
    finally:
        painter.end()


def preview(parent, builders, st, landscape=False):
    printer = new_printer(landscape)
    dlg = QPrintPreviewDialog(printer, parent)
    dlg.paintRequested.connect(lambda p: paint_pages(p, builders, st, landscape))
    dlg.resize(1000, 780)
    dlg.exec()


def save_pdf(parent, builders, st, default_name, landscape=False):
    path, _ = QFileDialog.getSaveFileName(parent, "حفظ PDF", default_name, "PDF (*.pdf)")
    if not path:
        return
    printer = new_printer(landscape)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)
    if paint_pages(printer, builders, st, landscape):
        info(parent, "تم حفظ الملف:\n" + path)
    else:
        warn(parent, "تعذر إنشاء ملف PDF")
