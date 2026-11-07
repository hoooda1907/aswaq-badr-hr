from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
                               QLabel, QPushButton, QFileDialog, QAbstractItemView, QGroupBox, QGridLayout)

from .. import reports
from ..service import compute_all
from .common import print_preview, save_pdf, info, warn


class SummaryDialog(QDialog):
    def __init__(self, db, branch, ym, parent=None):
        super().__init__(parent)
        self.branch, self.ym = branch, ym
        self.items = compute_all(db, branch, ym)
        self.setWindowTitle("إجمالي المرتبات — %s — %s" % (branch, reports.month_label(ym)))
        self.resize(1150, 720)
        lay = QVBoxLayout(self)

        cols = reports.SUMMARY_COLS
        t = QTableWidget(len(self.items) + 1, len(cols))
        t.setHorizontalHeaderLabels([c for c, _ in cols])
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setAlternatingRowColors(True)
        t.verticalHeader().setVisible(False)
        bold = QFont()
        bold.setBold(True)
        for r, (emp, _, s, pay) in enumerate(self.items):
            vals = [emp["code"], emp["name"]] + [reports.money(pay[k]) for _, k in cols[2:]]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignCenter if c != 1 else Qt.AlignVCenter | Qt.AlignRight)
                t.setItem(r, c, it)
        tot = reports.totals_of(self.items)
        last = len(self.items)
        vals = ["", "الإجمالي"] + [reports.money(tot[k]) for _, k in cols[2:]]
        for c, v in enumerate(vals):
            it = QTableWidgetItem(v)
            it.setFont(bold)
            it.setTextAlignment(Qt.AlignCenter)
            it.setBackground(QColor('#fff3cd'))
            t.setItem(last, c, it)
        lay.addWidget(t, 1)

        g = QGroupBox("الملخص العام")
        gl = QGridLayout(g)
        rows = [("إجمالي المرتبات قبل خصم السلف", tot["net_before_advance"]),
                ("إجمالي مبلغ السلف", tot["advance"]),
                ("المبلغ المطلوب بعد خصم السلف", tot["net"]),
                ("إجمالي التأمينات", tot["insurance"]), ("إجمالي البدلات", tot["allowances"]),
                ("إجمالي الوقت الإضافي", tot["ot_pay"]), ("إجمالي الجزاءات", tot["penalties_total"]),
                ("إجمالي خصم الغياب والإجازات", tot["absence_ded"] + tot["leave_ded"] + tot["short_ded"])]
        for i, (a, b) in enumerate(rows):
            lb = QLabel(a)
            vb = QLabel(reports.money(b))
            vb.setStyleSheet("font-weight:bold; color:#147a3a;" + ("font-size:15pt;" if i == 2 else ""))
            if i == 2:
                lb.setStyleSheet("font-weight:bold; font-size:13pt;")
            gl.addWidget(lb, i % 4, (i // 4) * 2)
            gl.addWidget(vb, i % 4, (i // 4) * 2 + 1)
        lay.addWidget(g)

        row = QHBoxLayout()
        for text, fn, obj in (("طباعة التقرير", self.print_, ""), ("حفظ PDF", self.pdf, "secondary"),
                              ("تصدير Excel", self.xlsx, "secondary"), ("إغلاق", self.close, "secondary")):
            b = QPushButton(text)
            if obj:
                b.setObjectName(obj)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)

    def _html(self):
        return reports.summary_html(self.branch, self.ym, self.items)

    def print_(self):
        print_preview(self, self._html(), landscape=True)

    def pdf(self):
        save_pdf(self, self._html(), "إجمالي_المرتبات_%s.pdf" % self.ym, landscape=True)

    def xlsx(self):
        path, _ = QFileDialog.getSaveFileName(self, "تصدير Excel", "مرتبات_%s.xlsx" % self.ym, "Excel (*.xlsx)")
        if not path:
            return
        try:
            reports.export_summary_xlsx(path, self.branch, self.ym, self.items)
            info(self, "تم التصدير:\n" + path)
        except Exception as e:
            warn(self, "تعذر التصدير: %s" % e)
