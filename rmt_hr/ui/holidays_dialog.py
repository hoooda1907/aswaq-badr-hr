from datetime import date

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
                               QPushButton, QLabel, QDateEdit, QLineEdit, QComboBox, QAbstractItemView)

from .. import reports
from ..constants import DAY_NAMES_AR
from ..leaves import HOLIDAY_MULTS
from .common import warn


class HolidaysDialog(QDialog):
    """الأجازات الرسمية للشهر. لكل يوم: اسمه ومقابل العمل فيه (لا يحتسب / يوم / يوم ونصف / يومان).
    يحسب البرنامج تلقائياً أجر العمل في هذا اليوم لمن حضر فيه فقط؛ ومن كان في إجازة أو غائباً لا يستحق مقابلاً."""

    def __init__(self, db, branch, ym, parent=None):
        super().__init__(parent)
        self.db, self.branch, self.ym = db, branch, ym
        self.setWindowTitle("الأجازات الرسمية — " + reports.month_label(ym))
        self.resize(640, 480)
        lay = QVBoxLayout(self)
        note = QLabel("أضف أيام الأجازات الرسمية لهذا الشهر وحدّد مقابل العمل فيها. يمكن تغيير الاحتساب لكل موظف "
                      "(أجر إضافي أو بدل إجازة يضاف لرصيده) من شيت الموظف.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#666;")
        lay.addWidget(note)

        y, m = int(ym[:4]), int(ym[5:7])
        last = (date(y + (m == 12), m % 12 + 1, 1) - date(y, m, 1)).days
        row = QHBoxLayout()
        self.de = QDateEdit(QDate(y, m, 1))
        self.de.setDisplayFormat("dd/MM/yyyy")
        self.de.setCalendarPopup(True)
        self.de.setDateRange(QDate(y, m, 1), QDate(y, m, last))
        self.name = QLineEdit()
        self.name.setPlaceholderText("اسم الأجازة (اختياري)")
        self.mult = QComboBox()
        for v, label in HOLIDAY_MULTS:
            self.mult.addItem("مقابل العمل: " + label, v)
        self.mult.setCurrentIndex(1)
        add = QPushButton("إضافة / تحديث")
        add.clicked.connect(self.add)
        for w in (self.de, self.name, self.mult, add):
            row.addWidget(w)
        lay.addLayout(row)

        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["التاريخ", "اليوم", "الاسم", "مقابل العمل"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.verticalHeader().setVisible(False)
        lay.addWidget(self.tbl, 1)
        row2 = QHBoxLayout()
        dele = QPushButton("حذف المحدد")
        dele.setObjectName("danger")
        dele.clicked.connect(self.delete)
        close = QPushButton("إغلاق")
        close.setObjectName("secondary")
        close.clicked.connect(self.accept)
        row2.addWidget(dele)
        row2.addStretch()
        row2.addWidget(close)
        lay.addLayout(row2)
        self.rows = []
        self.reload()

    def reload(self):
        self.rows = self.db.holidays_of(self.branch, self.ym)
        labels = dict(HOLIDAY_MULTS)
        self.tbl.setRowCount(len(self.rows))
        for r, h in enumerate(self.rows):
            for c, v in enumerate((h["day"].strftime("%d/%m/%Y"), DAY_NAMES_AR[h["day"].weekday()], h["name"],
                                   labels.get(h["mult"], "%g يوم" % h["mult"]))):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignCenter)
                self.tbl.setItem(r, c, it)

    def add(self):
        q = self.de.date()
        self.db.set_holiday(self.branch, date(q.year(), q.month(), q.day()), self.name.text(), self.mult.currentData())
        self.name.clear()
        self.reload()

    def delete(self):
        r = self.tbl.currentRow()
        if r < 0 or r >= len(self.rows):
            return warn(self, "اختر أجازة من الجدول أولاً")
        self.db.delete_holiday(self.branch, self.rows[r]["day"])
        self.reload()
