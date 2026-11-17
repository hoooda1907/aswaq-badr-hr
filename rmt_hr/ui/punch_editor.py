from datetime import datetime

from PySide6.QtCore import Qt, QDate, QTime, QDateTime
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
                               QPushButton, QLabel, QFormLayout, QDateTimeEdit, QComboBox, QAbstractItemView)

from .. import reports
from ..constants import DAY_NAMES_AR
from .common import warn, ask

KINDS = (("", "غير محدد"), ("I", "دخول"), ("O", "خروج"))
KIND_AR = {"": "—", "I": "دخول", "O": "خروج", "IO": "متعارض"}
STATE_AR = {"raw": "", "mod": "معدّلة", "add": "مضافة يدوياً", "del": "محذوفة"}
STATE_COLOR = {"mod": "#ffe8cc", "add": "#d6f5dd", "del": "#e0e0e0"}


def _to_py(q):
    d, t = q.date(), q.time()
    return datetime(d.year(), d.month(), d.day(), t.hour(), t.minute())


def _to_q(dt):
    return QDateTime(QDate(dt.year, dt.month, dt.day), QTime(dt.hour, dt.minute))


class PunchDialog(QDialog):
    """إضافة بصمة أو تعديل توقيتها."""

    def __init__(self, start, editing, parent=None):
        super().__init__(parent)
        self.setWindowTitle("تعديل بصمة" if editing else "إضافة بصمة")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.dt = QDateTimeEdit(_to_q(start))
        self.dt.setDisplayFormat("dd/MM/yyyy  HH:mm")
        self.dt.setCalendarPopup(True)
        self.kind = QComboBox()
        if editing:
            self.kind.addItem("بدون تغيير", None)
        for k, label in KINDS:
            self.kind.addItem(label, k)
        form.addRow("التاريخ والوقت", self.dt)
        form.addRow("الاتجاه", self.kind)
        lay.addLayout(form)
        row = QHBoxLayout()
        ok, cancel = QPushButton("موافق"), QPushButton("إلغاء")
        cancel.setObjectName("secondary")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)

    def result_values(self):
        return _to_py(self.dt.dateTime()), self.kind.currentData()


class PunchEditorDialog(QDialog):
    """تعديل بصمات الموظف في الشهر: حذف بصمة / تعديل توقيتها / إضافة بصمة.
    التعديلات تُحفظ منفصلة عن شيت الجهاز فلا تضيع عند إعادة استيراد الشيت، ويمكن استرجاع أي بصمة."""

    def __init__(self, db, branch, ym, code, parent=None):
        super().__init__(parent)
        self.db, self.branch, self.ym, self.code = db, branch, ym, code
        self.changed = False
        self.rows = []
        self.setWindowTitle("تعديل البصمات — %s — %s" % (code, reports.month_label(ym)))
        self.resize(760, 560)
        lay = QVBoxLayout(self)
        note = QLabel("استخدمها لعلاج الشيفت المتغيّر: احذف بصمة زائدة، أو عدّل توقيت بصمة، أو أضف بصمة ناقصة. "
                      "يظهر معها أول يوم من الشهر التالي لأنه يكمّل الشيفت المسائي في آخر الشهر.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#666;")
        lay.addWidget(note)
        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["التاريخ", "اليوم", "الوقت / الاتجاه", "الحالة"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.verticalHeader().setVisible(False)
        lay.addWidget(self.tbl, 1)
        row = QHBoxLayout()
        for text, fn, name in (("إضافة بصمة", self.add, None), ("تعديل التوقيت", self.edit, None),
                               ("حذف", self.delete, "danger"), ("استرجاع الأصل", self.restore, "secondary")):
            b = QPushButton(text)
            if name:
                b.setObjectName(name)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        c = QPushButton("إغلاق")
        c.setObjectName("secondary")
        c.clicked.connect(self.accept)
        row.addWidget(c)
        lay.addLayout(row)
        self.reload()

    def reload(self):
        self.rows = self.db.punch_rows(self.branch, self.ym, self.code)
        self.tbl.setRowCount(len(self.rows))
        for r, p in enumerate(self.rows):
            dt = p["dt"]
            vals = [dt.strftime("%d/%m/%Y"), DAY_NAMES_AR[dt.weekday()],
                    "%s   %s" % (dt.strftime("%H:%M"), KIND_AR.get(p["kind"], "—")),
                    STATE_AR[p["state"]] + (("  (الأصل %s)" % p["orig"].strftime("%d/%m %H:%M")) if p["state"] == "mod" else "")]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignCenter)
                if p["state"] in STATE_COLOR:
                    it.setBackground(QColor(STATE_COLOR[p["state"]]))
                if p["state"] == "del":
                    f = it.font()
                    f.setStrikeOut(True)
                    it.setFont(f)
                self.tbl.setItem(r, c, it)

    def _sel(self):
        r = self.tbl.currentRow()
        if r < 0 or r >= len(self.rows):
            warn(self, "اختر بصمة من الجدول أولاً")
            return None
        return self.rows[r]

    def add(self):
        y, m = int(self.ym[:4]), int(self.ym[5:7])
        d = PunchDialog(datetime(y, m, 1, 8, 0), False, self)
        if d.exec() != QDialog.Accepted:
            return
        dt, kind = d.result_values()
        self.db.punch_add(self.branch, self.code, dt, kind or "")
        self.changed = True
        shown = dt.strftime("%Y-%m") == self.ym or (dt.day == 1 and dt.strftime("%Y-%m") > self.ym)
        self.reload()
        if not shown:
            warn(self, "البصمة المضافة خارج هذا الشهر فلن تظهر هنا (ستُحسب في شهرها).")

    def edit(self):
        p = self._sel()
        if not p:
            return
        if p["state"] == "del":
            return warn(self, "البصمة محذوفة. استرجعها أولاً.")
        d = PunchDialog(p["dt"], True, self)
        if d.exec() != QDialog.Accepted:
            return
        dt, kind = d.result_values()
        self.db.punch_modify(self.branch, self.code, p["dt"], dt, kind)
        self.changed = True
        self.reload()

    def delete(self):
        p = self._sel()
        if not p or p["state"] == "del":
            return
        self.db.punch_delete(self.branch, self.code, p["dt"])
        self.changed = True
        self.reload()

    def restore(self):
        p = self._sel()
        if not p:
            return
        if p["state"] == "raw":
            return warn(self, "هذه البصمة أصلية ولم تُعدَّل")
        self.db.punch_restore(self.branch, self.code, p["dt"])
        self.changed = True
        self.reload()
