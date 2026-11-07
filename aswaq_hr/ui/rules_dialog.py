from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QSpinBox,
                               QDoubleSpinBox, QPushButton, QGroupBox)

from ..constants import DEFAULT_FP_RULES, FP_STEPS
from .common import warn


def _days_spin(step):
    sp = QDoubleSpinBox()
    sp.setRange(0, 60)
    sp.setDecimals(2)
    sp.setSingleStep(step)
    sp.setAlignment(Qt.AlignCenter)
    sp.setSuffix(" يوم")
    return sp


def _count_spin(lo, hi):
    sp = QSpinBox()
    sp.setRange(lo, hi)
    sp.setAlignment(Qt.AlignCenter)
    return sp


class FpRulesDialog(QDialog):
    """قواعد جزاء نسيان البصمة: عدد البصمات المنسية في الشهر ← أيام الخصم."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("قواعد جزاء نسيان البصمة")
        self.resize(640, 380)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("البصمة المنسية = يوم حضور ينقصه بصمة دخول أو خروج. الخصم = عدد الأيام × أجر اليوم "
                             "(المرتب ÷ أيام الشهر)."))

        g = QGroupBox("شرائح الجزاء الشهري")
        gl = QGridLayout(g)
        self.t1, self.t2, self.t3 = _count_spin(1, 100), _count_spin(1, 100), _count_spin(1, 200)
        self.d = {k: _days_spin(FP_STEPS[k]) for k in ("d0", "d1", "d2", "d3")}
        self.l2a, self.l3a, self.l4a = QLabel(), QLabel(), QLabel()
        rows = [
            (self._hbox(QLabel("أقل من"), self.t1, QLabel("بصمات منسية")), "d0", "ربع يوم (0.25)"),
            (self._hbox(QLabel("من"), self.l2a, QLabel("إلى"), self.t2, QLabel("بصمة")), "d1", "نصف يوم (0.5)"),
            (self._hbox(QLabel("أكثر من"), self.l3a, QLabel("إلى"), self.t3, QLabel("بصمة")), "d2", "يوم كامل"),
            (self._hbox(QLabel("أكثر من"), self.l4a, QLabel("بصمة")), "d3", "يوم كامل"),
        ]
        for i, (cond, key, step_txt) in enumerate(rows):
            gl.addWidget(cond, i, 0)
            gl.addWidget(QLabel("خصم"), i, 1)
            gl.addWidget(self.d[key], i, 2)
            hint = QLabel("(يتغير بمضاعفات %s)" % step_txt)
            hint.setStyleSheet("color:#666;")
            gl.addWidget(hint, i, 3)
        lay.addWidget(g)
        for sp in (self.t1, self.t2, self.t3):
            sp.valueChanged.connect(self._labels)

        row = QHBoxLayout()
        b_save = QPushButton("حفظ")
        b_def = QPushButton("القيم الافتراضية")
        b_def.setObjectName("secondary")
        b_close = QPushButton("إغلاق")
        b_close.setObjectName("secondary")
        b_save.clicked.connect(self._save)
        b_def.clicked.connect(lambda: self._load(DEFAULT_FP_RULES))
        b_close.clicked.connect(self.reject)
        for b in (b_save, b_def):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(b_close)
        lay.addLayout(row)
        self._load(db.fp_rules())

    @staticmethod
    def _hbox(*widgets):
        from PySide6.QtWidgets import QWidget
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        for x in widgets:
            h.addWidget(x)
        h.addStretch()
        return w

    def _load(self, r):
        self.t1.setValue(int(r["t1"]))
        self.t2.setValue(int(r["t2"]))
        self.t3.setValue(int(r["t3"]))
        for k, sp in self.d.items():
            sp.setValue(float(r[k]))
        self._labels()

    def _labels(self, *_):
        self.l2a.setText("<b>%d</b>" % self.t1.value())
        self.l3a.setText("<b>%d</b>" % self.t2.value())
        self.l4a.setText("<b>%d</b>" % self.t3.value())

    def _save(self):
        t1, t2, t3 = self.t1.value(), self.t2.value(), self.t3.value()
        if not (t1 <= t2 < t3):
            return warn(self, "الحدود لازم تكون مرتبة: الحد الأول ≤ الثاني < الثالث")
        for k, sp in self.d.items():
            q = sp.value() / FP_STEPS[k]
            if abs(q - round(q)) > 1e-9:
                names = {"d0": "ربع يوم", "d1": "نصف يوم", "d2": "يوم", "d3": "يوم"}
                return warn(self, "قيمة الخصم لازم تكون من مضاعفات %s" % names[k])
        rules = {"t1": t1, "t2": t2, "t3": t3}
        rules.update({k: sp.value() for k, sp in self.d.items()})
        self.db.set_fp_rules(rules)
        self.accept()
