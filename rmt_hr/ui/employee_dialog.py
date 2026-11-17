import calendar
from datetime import date

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QTableWidget,
                               QTableWidgetItem, QHeaderView, QLabel, QGroupBox, QGridLayout, QSpinBox,
                               QDoubleSpinBox, QFormLayout, QComboBox, QCheckBox, QLineEdit, QPushButton,
                               QMessageBox, QAbstractItemView, QAbstractSpinBox)

from .. import reports
from ..constants import SHIFT_MODES, SHIFT_LABELS, DAY_NAMES_AR
from ..leaves import PICKABLE, STATUS_LABELS, CHOICE_LABELS
from ..service import compute_employee, ledger
from . import printing
from .common import warn
from .punch_editor import PunchEditorDialog
from .dates_dialog import DatesListDialog


def _money_spin(maxv=10_000_000):
    s = QDoubleSpinBox()
    s.setRange(0, maxv)
    s.setDecimals(2)
    s.setGroupSeparatorShown(True)
    s.setButtonSymbols(QAbstractSpinBox.NoButtons)
    return s


def _big(text, color="#1b9e4b"):
    lb = QLabel(text)
    lb.setAlignment(Qt.AlignCenter)
    lb.setStyleSheet("font-size:20pt; font-weight:bold; color:%s;" % color)
    return lb


class EmployeeDialog(QDialog):
    def __init__(self, db, branch, ym, code, parent=None):
        super().__init__(parent)
        self.db, self.branch, self.ym, self.code = db, branch, ym, code
        self.emp = db.get_employee(branch, ym, code)
        self.punches = db.punches_of(branch, ym, code, with_kind=True)
        self.dirty = False
        self._loading = True
        self._cur = None
        self.setWindowTitle("%s — %s" % (self.emp["name"], reports.month_label(ym)))
        self.resize(980, 700)

        root = QVBoxLayout(self)
        self.header = QLabel()
        self.header.setStyleSheet("font-size:14pt; font-weight:bold; color:#147a3a;")
        root.addWidget(self.header)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_attendance_tab()
        self._build_days_tab()
        self._build_salary_tab()

        row = QHBoxLayout()
        self.b_save = QPushButton("حفظ")
        self.b_print = QPushButton("طباعة سند المرتب")
        self.b_pdf = QPushButton("حفظ السند PDF")
        self.b_close = QPushButton("إغلاق")
        for b in (self.b_pdf, self.b_close):
            b.setObjectName("secondary")
        self.b_save.clicked.connect(self.save)
        self.b_print.clicked.connect(self.print_voucher)
        self.b_pdf.clicked.connect(self.pdf_voucher)
        self.b_close.clicked.connect(self.close)
        row.addWidget(self.b_save)
        row.addWidget(self.b_print)
        row.addWidget(self.b_pdf)
        row.addStretch()
        row.addWidget(self.b_close)
        root.addLayout(row)

        self._fill_inputs()
        self._loading = False
        self.recalc()
        self.dirty = False

    # ------------------------------------------------------------ تبويب الحضور
    def _build_attendance_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.tbl = QTableWidget(0, 8)
        self.tbl.setHorizontalHeaderLabels(["التاريخ", "اليوم", "الشيفت", "الدخول", "الخروج", "ساعات العمل", "ملاحظات", "الحالة (اختيار يدوي)"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.verticalHeader().setVisible(False)
        lay.addWidget(self.tbl)
        prow = QHBoxLayout()
        self.b_print_punches = QPushButton("طباعة البصمات")
        self.b_print_punches.setObjectName("secondary")
        self.b_print_punches.clicked.connect(self.print_punches)
        prow.addWidget(self.b_print_punches)
        self.b_edit_punches = QPushButton("تعديل البصمات")
        self.b_edit_punches.clicked.connect(self.edit_punches)
        prow.addWidget(self.b_edit_punches)
        self.lb_edits = QLabel("")
        self.lb_edits.setStyleSheet("color:#c0392b; font-weight:bold;")
        prow.addWidget(self.lb_edits)
        prow.addStretch()
        lay.addLayout(prow)
        self.tabs.addTab(w, "الحضور والانصراف")

    # ------------------------------------------------------------ تبويب الأيام
    def _build_days_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox("ملخص أيام الشهر")
        gl = QGridLayout(g)
        self.lb_present, self.lb_rest, self.lb_remain = _big("0"), _big("0", "#2e86c1"), _big("0", "#e67e22")
        self.lb_hours, self.lb_avg = _big("0:00"), _big("0:00")
        self.lb_in, self.lb_out = _big("0", "#2e86c1"), _big("0", "#2e86c1")
        self.lb_miss = _big("0", "#c0392b")
        for i, (t, lb) in enumerate((("أيام الحضور", self.lb_present), ("الراحة الأسبوعية المستحقة", self.lb_rest),
                                     ("أيام غير مستحقة الراحة (المتبقي)", self.lb_remain),
                                     ("إجمالي ساعات العمل", self.lb_hours), ("متوسط الساعات اليومي", self.lb_avg),
                                     ("بصمات الدخول", self.lb_in), ("بصمات الخروج", self.lb_out),
                                     ("بصمات ناقصة", self.lb_miss))):
            gl.addWidget(QLabel(t), 0, i, alignment=Qt.AlignCenter)
            gl.addWidget(lb, 1, i)
        lay.addWidget(g)

        g2 = QGroupBox("توزيع أيام الشهر (حضور + راحة + سنوية + بدون أجر + غياب + خصم رصيد = أيام الشهر) — اضغط أي رقم لعرض التواريخ")
        g2l = QGridLayout(g2)
        self.STATUS_COLS = (("rest", "راحة أسبوعية"), ("annual", "إجازة سنوية"), ("unpaid", "إجازة بإذن / بدون أجر"),
                            ("absent", "غياب"), ("comp", "خصم من رصيد البدلات"))
        self.bt_month, self.bt_year = {}, {}
        g2l.addWidget(QLabel(""), 0, 0)
        g2l.addWidget(QLabel("<b>هذا الشهر</b>"), 1, 0)
        g2l.addWidget(QLabel("<b>هذه السنة</b>"), 2, 0)
        for i, (key, label) in enumerate(self.STATUS_COLS, start=1):
            g2l.addWidget(QLabel(label), 0, i, alignment=Qt.AlignCenter)
            for row_i, store, scope in ((1, self.bt_month, "month"), (2, self.bt_year, "year")):
                bt = QPushButton("0")
                bt.setObjectName("secondary")
                bt.setStyleSheet("font-size:16pt; font-weight:bold; padding:6px;")
                bt.clicked.connect(lambda _=False, k=key, sc=scope: self._show_dates(k, sc))
                store[key] = bt
                g2l.addWidget(bt, row_i, i)
        self.sp_leave, self.sp_absent = QSpinBox(), QSpinBox()
        self.sp_leave.setAlignment(Qt.AlignCenter)
        self.sp_absent.setVisible(False)
        g2l.addWidget(QLabel("إجازة بإذن (تلقائي) — عدد أيام يوزعها البرنامج على الأيام غير المحددة"), 3, 0, 1, 3)
        g2l.addWidget(self.sp_leave, 3, 3, 1, 2)
        self.lb_ledger = QLabel()
        self.lb_ledger.setStyleSheet("font-size:12pt;")
        self.lb_ledger.setAlignment(Qt.AlignCenter)
        g2l.addWidget(self.lb_ledger, 4, 0, 1, 6)
        self.lb_check = QLabel()
        self.lb_check.setAlignment(Qt.AlignCenter)
        g2l.addWidget(self.lb_check, 5, 0, 1, 6)
        self.lb_excess = QLabel()
        self.lb_excess.setAlignment(Qt.AlignCenter)
        self.lb_excess.setStyleSheet("color:#c0392b; font-weight:bold;")
        self.b_excess = QPushButton("تحويل الزيادة إلى خصم من رصيد البدلات")
        self.b_excess.clicked.connect(self._convert_excess)
        g2l.addWidget(self.lb_excess, 6, 0, 1, 4)
        g2l.addWidget(self.b_excess, 6, 4, 1, 2)
        lay.addWidget(g2)
        lay.addStretch()
        self.sp_leave.valueChanged.connect(self._leave_changed)
        self.tabs.addTab(w, "الحضور والغياب والإجازات")

    # ------------------------------------------------------------ تبويب الراتب
    def _build_salary_tab(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        left = QGroupBox("بيانات الأجر")
        form = QFormLayout(left)
        self.f_salary, self.f_allow, self.f_pen = _money_spin(), _money_spin(), _money_spin()
        self.f_ins, self.f_adv = _money_spin(), _money_spin()
        self.f_req = QDoubleSpinBox(); self.f_req.setRange(1, 24); self.f_req.setDecimals(2)
        self.f_grace = QSpinBox(); self.f_grace.setRange(0, 240); self.f_grace.setSuffix(" دقيقة")
        self.f_rate = QDoubleSpinBox(); self.f_rate.setRange(0, 5); self.f_rate.setSingleStep(0.25); self.f_rate.setDecimals(2)
        self.f_shift = QComboBox()
        for k, label in SHIFT_MODES:
            self.f_shift.addItem(label, k)
        self.c_ot = QCheckBox("تعديل الوقت الإضافي يدوياً (بالساعات)")
        self.f_ot = QDoubleSpinBox(); self.f_ot.setRange(0, 1000); self.f_ot.setDecimals(2)
        self.c_leave_paid = QCheckBox("الإجازة بإذن مدفوعة الأجر")
        self.c_short = QCheckBox("خصم نقص ساعات العمل (بعد فترة السماح)")
        self.f_notes = QLineEdit()
        self.lb_fp = QLabel()
        self.lb_fp.setWordWrap(True)
        self.c_fp = QCheckBox("تعديل مبلغ جزاء نسيان البصمة يدوياً")
        self.f_fp = _money_spin()
        self.b_fp_del = QPushButton("حذف الجزاء")
        self.b_fp_del.setObjectName("danger")
        self.b_fp_auto = QPushButton("استعادة الحساب التلقائي")
        self.b_fp_auto.setObjectName("secondary")
        self.b_fp_del.clicked.connect(self._fp_delete)
        self.b_fp_auto.clicked.connect(lambda: self.c_fp.setChecked(False))
        form.addRow("المرتب الأساسي", self.f_salary)
        form.addRow("بدلات", self.f_allow)
        form.addRow("جزاءات", self.f_pen)
        form.addRow("خصم تأمينات", self.f_ins)
        form.addRow("قيمة السلف الشهرية", self.f_adv)
        form.addRow("ساعات العمل اليومية", self.f_req)
        form.addRow("فترة السماح اليومية", self.f_grace)
        form.addRow("معامل الوقت الإضافي (×)", self.f_rate)
        form.addRow("نظام الشيفت", self.f_shift)
        form.addRow(self.c_ot, self.f_ot)
        form.addRow(self.c_leave_paid)
        form.addRow(self.c_short)
        form.addRow("ملاحظات", self.f_notes)
        self.f_comp = QDoubleSpinBox()
        self.f_comp.setRange(0, 366)
        self.f_comp.setDecimals(1)
        self.f_comp.setSingleStep(0.5)
        self.f_comp.setSuffix(" يوم")
        form.addRow("بدلات إجازة مستحقة (أيام تُضاف للرصيد)", self.f_comp)
        self.hol_lbl = QLabel("<b>الأجازات الرسمية في هذا الشهر</b>")
        self.hol_tbl = QTableWidget(0, 4)
        self.hol_tbl.setHorizontalHeaderLabels(["التاريخ", "الأجازة", "مقابل العمل", "الاحتساب لهذا الموظف"])
        self.hol_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hol_tbl.verticalHeader().setVisible(False)
        self.hol_tbl.setMaximumHeight(130)
        form.addRow(self.hol_lbl)
        form.addRow(self.hol_tbl)
        form.addRow(self.lb_fp)
        form.addRow(self.c_fp, self.f_fp)
        fprow = QHBoxLayout()
        fprow.addWidget(self.b_fp_del)
        fprow.addWidget(self.b_fp_auto)
        form.addRow(fprow)
        lay.addWidget(left, 3)

        right = QGroupBox("حساب صافي المرتب")
        rl = QVBoxLayout(right)
        self.result = QLabel()
        self.result.setTextFormat(Qt.RichText)
        self.result.setAlignment(Qt.AlignTop | Qt.AlignRight)
        rl.addWidget(self.result)
        rl.addStretch()
        lay.addWidget(right, 2)
        self.tabs.addTab(w, "الراتب")

        for sp in (self.f_salary, self.f_allow, self.f_pen, self.f_ins, self.f_adv, self.f_req, self.f_grace,
                   self.f_rate, self.f_ot, self.f_fp, self.f_comp):
            sp.valueChanged.connect(self._changed)
        self.f_shift.currentIndexChanged.connect(self._changed)
        self.f_notes.textChanged.connect(self._changed)
        for c in (self.c_ot, self.c_leave_paid, self.c_short, self.c_fp):
            c.toggled.connect(self._changed)

    # ------------------------------------------------------------ تعبئة وجمع البيانات
    def _fill_inputs(self):
        e = self.emp
        self.f_salary.setValue(e["salary"] or 0)
        self.f_allow.setValue(e["allowances"] or 0)
        self.f_pen.setValue(e["penalties"] or 0)
        self.f_ins.setValue(e["insurance"] or 0)
        self.f_adv.setValue(e["advance"] or 0)
        self.f_req.setValue(e["req_hours"] or 10)
        self.f_grace.setValue(e["grace_min"] if e["grace_min"] is not None else 20)
        self.f_rate.setValue(e["ot_rate"] or 1)
        i = self.f_shift.findData(e["shift_mode"] or "auto")
        self.f_shift.setCurrentIndex(max(i, 0))
        self.c_ot.setChecked(e["ot_manual"] is not None)
        self.f_ot.setValue(e["ot_manual"] or 0)
        self.c_fp.setChecked(e.get("fp_manual") is not None)
        self.f_fp.setValue(e.get("fp_manual") or 0)
        self.c_leave_paid.setChecked(bool(e["leave_paid"]))
        self.c_short.setChecked(bool(e["deduct_short"]))
        self.f_notes.setText(e["notes"] or "")
        self.f_comp.setValue(e.get("comp_added") or 0)
        self.sp_leave.setValue(e["leave_days"] or 0)

    def collect(self):
        e = dict(self.emp)
        e.update(
            salary=self.f_salary.value(), allowances=self.f_allow.value(), penalties=self.f_pen.value(),
            insurance=self.f_ins.value(), advance=self.f_adv.value(), req_hours=self.f_req.value(),
            grace_min=self.f_grace.value(), ot_rate=self.f_rate.value(), shift_mode=self.f_shift.currentData(),
            ot_manual=self.f_ot.value() if self.c_ot.isChecked() else None,
            fp_manual=self.f_fp.value() if self.c_fp.isChecked() else None,
            leave_paid=int(self.c_leave_paid.isChecked()), deduct_short=int(self.c_short.isChecked()),
            notes=self.f_notes.text(), leave_days=self.sp_leave.value(), comp_added=self.f_comp.value())
        return e

    # ------------------------------------------------------------ ردود الأفعال
    def _changed(self, *_):
        if self._loading:
            return
        self.dirty = True
        self.recalc()

    def _fp_delete(self):
        self.c_fp.setChecked(True)
        self.f_fp.setValue(0)

    def _leave_changed(self, v):
        if self._loading or not self._cur:
            return
        self.dirty = True
        self.recalc()

    def _status_changed(self, dt, status):
        self.db.set_day_status(self.branch, self.code, dt, status)
        QTimer.singleShot(0, self.recalc)

    def _holiday_choice_changed(self, dt, choice):
        self.db.set_holiday_choice(self.branch, self.code, dt, choice)
        QTimer.singleShot(0, self.recalc)

    def _show_dates(self, key, scope):
        led = self._ledger
        dates = led["month_dates" if scope == "month" else "year_dates"].get(key, [])
        label = dict(self.STATUS_COLS)[key]
        DatesListDialog("%s — %s" % (label, "هذا الشهر" if scope == "month" else "سنة " + self.ym[:4]), dates, self).exec()

    def _convert_excess(self):
        """يحوّل أيام الراحة الزائدة عن المسموح (يوم بعد كل 6 أيام عمل) إلى «خصم من رصيد البدلات»."""
        plan = self._cur[2]["plan"]
        n = plan.rest_excess
        if not n:
            return
        rest_dates = plan.dates_of("rest")
        for dt in sorted(plan.explicit & set(rest_dates), reverse=True)[:n]:
            self.db.set_day_status(self.branch, self.code, dt, "comp")
        self.recalc()

    # ------------------------------------------------------------ إعادة الحساب
    def recalc(self):
        if self._loading:
            return
        emp = self.collect()
        days, s, pay = compute_employee(self.db, self.branch, self.ym, emp, self.punches)
        self._cur = (days, s, pay, emp)

        plan = pay["plan"]
        self._loading = True
        self.sp_leave.setMaximum(max(0, s.month_days - s.present))
        self._loading = False

        self._loading = True
        self.f_fp.setEnabled(self.c_fp.isChecked())
        if not self.c_fp.isChecked():
            self.f_fp.setValue(pay["fp_auto"])
        self._loading = False
        self.lb_fp.setText("<b>نسيان البصمة:</b> %d بصمة منسية هذا الشهر ← خصم %g يوم = %s%s"
                           % (pay["fp_count"], pay["fp_days"], reports.money(pay["fp_auto"]),
                              "  (المبلغ المعتمد بعد التعديل: %s)" % reports.money(pay["fp_amount"]) if pay["fp_edited"] else ""))
        self.header.setText("الكود: %s    |    الاسم: %s    |    الشيفت: %s    |    الفرع: %s    |    %s"
                            % (emp["code"], emp["name"], s.shift_label or "—", self.branch, reports.month_label(self.ym)))
        self.lb_present.setText(str(s.present))
        self.lb_rest.setText(str(s.rest))
        self.lb_remain.setText(str(s.remaining))
        self.lb_hours.setText(reports.hrs(s.total_hours))
        self.lb_avg.setText(reports.hrs(s.avg_hours))
        self._update_edits_label()
        self.lb_in.setText(str(s.in_punches))
        self.lb_out.setText(str(s.out_punches))
        self.lb_miss.setText(str(s.missing_punches))
        total = s.present + pay["rest_n"] + pay["annual"] + pay["leave"] + pay["absent"] + pay["comp_days"]
        ok = total == s.month_days
        self.lb_check.setText("حضور %d + راحة %d + سنوية %d + بدون أجر %d + غياب %d + خصم رصيد %d = %d يوم (أيام الشهر: %d) %s"
                              % (s.present, pay["rest_n"], pay["annual"], pay["leave"], pay["absent"], pay["comp_days"],
                                 total, s.month_days, "✔" if ok else "✘"))
        self.lb_check.setStyleSheet("font-size:12pt; color:%s;" % ("#1b9e4b" if ok else "#c0392b"))
        self._ledger = ledger(self.db, self.branch, self.code, self.ym, override=(emp, plan))
        led = self._ledger
        month_counts = {"rest": pay["rest_n"], "annual": pay["annual"], "unpaid": pay["leave"],
                        "absent": pay["absent"], "comp": pay["comp_days"]}
        for key, _ in self.STATUS_COLS:
            self.bt_month[key].setText(str(month_counts[key]))
            self.bt_year[key].setText(str(len(led["year_dates"][key])))
        left = led["annual_left"]
        self.lb_ledger.setText("الإجازة السنوية: المستحق <b>%g</b> − المستخدم هذه السنة <b>%d</b> = المتبقي <b style='color:%s'>%g</b>"
                               "      |      رصيد بدلات الإجازة: <b>%g</b> يوم"
                               % (led["entitlement"], led["annual_used"], "#1b9e4b" if left >= 0 else "#c0392b", left, led["comp_balance"]))
        ex = plan.rest_excess
        self.lb_excess.setText("الراحة المأخوذة %d أكبر من المسموح %d (يوم بعد كل 6 أيام عمل): الزيادة %d يوم" %
                               (pay["rest_n"], plan.rest_allowed, ex) if ex else "")
        self.lb_excess.setVisible(bool(ex))
        self.b_excess.setVisible(bool(ex))
        self._refresh_holidays(plan)
        self._refresh_table(days, s, plan)
        self._refresh_result(s, pay)

    def _refresh_table(self, days, s, plan=None):
        y, m = int(self.ym[:4]), int(self.ym[5:7])
        self.tbl.setRowCount(s.month_days)
        for d in range(1, s.month_days + 1):
            dt = date(y, m, d)
            rec = days.get(dt)
            vals = ["%02d/%02d/%d" % (d, m, y), DAY_NAMES_AR[dt.weekday()], "", "", "", "", ""]
            color = None
            orph = getattr(days, "orphans", {}).get(dt)
            onote = ("بصمة خروج %s بدون دخول — اعتُبر راحة" % "، ".join(t.strftime("%H:%M") for t in orph)) if orph else ""
            if rec:
                vals[2] = SHIFT_LABELS[rec.shift]
                if rec.in_dt:
                    vals[3] = rec.in_dt.strftime("%H:%M" if rec.in_dt.date() == dt else "%H:%M  (%d/%m)")
                if rec.out_dt:
                    vals[4] = rec.out_dt.strftime("%H:%M" if rec.out_dt.date() == dt else "%H:%M  (%d/%m)")
                if rec.complete:
                    vals[5] = reports.hrs(rec.hours)
                vals[6] = " - ".join(x for x in (rec.note, onote) if x)
                if not rec.complete:
                    color = QColor("#fff3cd")
                elif rec.change:
                    color = QColor("#d6eaf8")
            else:
                vals[6] = onote or "لا توجد بصمة"
                color = QColor("#ffe8cc") if onote else QColor("#fdecea")
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignCenter)
                if color:
                    it.setBackground(color)
                if rec and rec.change:
                    f = it.font(); f.setBold(True); it.setFont(f)
                self.tbl.setItem(d - 1, c, it)
            # عمود الحالة: «حضور» أو قائمة اختيار يدوي لليوم (التلقائي يظهر باسم الحالة المحسوبة)
            if rec:
                it = QTableWidgetItem("حضور")
                it.setTextAlignment(Qt.AlignCenter)
                self.tbl.removeCellWidget(d - 1, 7)
                self.tbl.setItem(d - 1, 7, it)
            else:
                auto = STATUS_LABELS.get(plan.statuses.get(dt), "") if plan else ""
                cb = QComboBox()
                cb.addItem("تلقائي: " + auto, None)
                for st in PICKABLE:
                    cb.addItem(STATUS_LABELS[st] if st != "unpaid" else "إجازة بدون أجر", st)
                explicit = plan.statuses.get(dt) if (plan and dt in plan.explicit) else None
                cb.setCurrentIndex(0 if not explicit else 1 + PICKABLE.index(explicit))
                cb.currentIndexChanged.connect(lambda _i, _dt=dt, _cb=cb: self._status_changed(_dt, _cb.currentData()))
                self.tbl.setItem(d - 1, 7, QTableWidgetItem(""))
                self.tbl.setCellWidget(d - 1, 7, cb)

    def _refresh_holidays(self, plan):
        rows = plan.holidays
        self.hol_tbl.setRowCount(len(rows))
        self.hol_tbl.setVisible(bool(rows))
        self.hol_lbl.setText("<b>الأجازات الرسمية في هذا الشهر</b>" if rows else
                             "<b>الأجازات الرسمية:</b> لا توجد (تُضاف من الشاشة الرئيسية ← الأجازات الرسمية)")
        for r, h in enumerate(rows):
            for c, v in enumerate((h["date"].strftime("%d/%m"), h["name"] or "—",
                                   {0.0: "لا يحتسب", 1.0: "يوم", 1.5: "يوم ونصف", 2.0: "يومان"}.get(h["mult"], "%g يوم" % h["mult"]))):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignCenter)
                self.hol_tbl.setItem(r, c, it)
            if h["worked"]:
                cb = QComboBox()
                cb.addItem(CHOICE_LABELS["pay"], "pay")
                cb.addItem(CHOICE_LABELS["comp"], "comp")
                cb.setCurrentIndex(1 if h["choice"] == "comp" else 0)
                cb.currentIndexChanged.connect(lambda _i, _d=h["date"], _cb=cb: self._holiday_choice_changed(_d, _cb.currentData()))
                self.hol_tbl.setCellWidget(r, 3, cb)
            else:
                self.hol_tbl.removeCellWidget(r, 3)
                it = QTableWidgetItem("لم يعمل — لا مقابل")
                it.setTextAlignment(Qt.AlignCenter)
                self.hol_tbl.setItem(r, 3, it)

    def _refresh_result(self, s, p):
        m = reports.money
        def row(a, b, bold=False, color=None):
            st = "color:%s;" % color if color else ""
            txt = "<b>%s</b>" % b if bold else b
            return "<tr><td style='padding:3px 8px;%s'>%s</td><td align='left' style='padding:3px 8px;%s'>%s</td></tr>" % (st, a, st, txt)
        h = ["<table width='100%'>",
             row("أجر اليوم", m(p["daily"])), row("أجر الساعة", m(p["hourly"])),
             "<tr><td colspan='2'><hr></td></tr>",
             row("المرتب الأساسي", m(p["salary"])), row("بدلات", m(p["allowances"])),
             row("وقت إضافي (%s ساعة)" % reports.hrs(p["ot_hours"]), m(p["ot_pay"])),
             row("أجر الأجازات الرسمية (%g يوم)" % p["holiday_pay_days"], m(p["holiday_pay"])) if p["holiday_pay_days"] else "",
             row("إجمالي المستحقات", m(p["gross"]), True, "#147a3a"),
             "<tr><td colspan='2'><hr></td></tr>",
             row("خصم الغياب (%d يوم)" % p["absent"], m(p["absence_ded"]), color="#c0392b"),
             row("جزاءات", m(p["penalties"]), color="#c0392b"),
             row("جزاء نسيان البصمة (%d بصمة%s)" % (p["fp_count"], " - معدّل" if p["fp_edited"] else ""),
                 m(p["fp_amount"]), color="#c0392b"),
             row("تأمينات", m(p["insurance"]), color="#c0392b"),
             row("سلف", m(p["advance"]), color="#c0392b")]
        if p["leave_ded"]:
            h.append(row("إجازة بدون أجر", m(p["leave_ded"]), color="#c0392b"))
        if p["short_ded"]:
            h.append(row("نقص ساعات", m(p["short_ded"]), color="#c0392b"))
        h.append(row("إجمالي الاستقطاعات", m(p["total_ded"]), True, "#c0392b"))
        h.append("<tr><td colspan='2'><hr></td></tr>")
        h.append("<tr><td style='font-size:16pt;color:#147a3a'><b>صافي المرتب</b></td>"
                 "<td align='left' style='font-size:16pt;color:#147a3a'><b>%s</b></td></tr></table>" % m(p["net"]))
        self.result.setText("".join(h))

    # ------------------------------------------------------------ حفظ وطباعة
    def save(self):
        days, s, pay, emp = self._cur
        if s.present + pay["rest_n"] + pay["annual"] + pay["leave"] + pay["absent"] + pay["comp_days"] != s.month_days:
            return warn(self, "مجموع أيام الحضور والراحة والإجازات والغياب والخصم من الرصيد لا يساوي عدد أيام الشهر")
        self.db.save_employee(emp)
        self.emp = emp
        self.dirty = False
        return True

    def _voucher_builders(self):
        if self.dirty and not self.save():
            return None, None
        days, s, pay, emp = self._cur
        st = printing.load_settings(self.db)
        led = ledger(self.db, self.branch, self.code, self.ym)
        return [lambda f: reports.voucher_html(self.branch, self.ym, emp, s, pay, scale=f, show_logo=st["logo"], ledger=led)], st

    def print_voucher(self):
        builders, st = self._voucher_builders()
        if builders:
            printing.preview(self, builders, st)

    def pdf_voucher(self):
        builders, st = self._voucher_builders()
        if builders:
            printing.save_pdf(self, builders, st, "سند_مرتب_%s_%s.pdf" % (self.code, self.ym))

    def edit_punches(self):
        dlg = PunchEditorDialog(self.db, self.branch, self.ym, self.code, self)
        dlg.exec()
        if dlg.changed:
            self.punches = self.db.punches_of(self.branch, self.ym, self.code, with_kind=True)
            self.recalc()

    def _update_edits_label(self):
        n = self.db.punch_edit_count(self.branch, self.ym, self.code)
        self.lb_edits.setText("بصمات معدّلة يدوياً: %d" % n if n else "")

    def print_punches(self):
        days, s, pay, emp = self._cur
        st = dict(printing.load_settings(self.db), layout="single")
        builder = lambda f: reports.punches_html(self.branch, self.ym, emp, days, s, scale=f, show_logo=st["logo"], plan=pay["plan"])
        printing.preview(self, [builder], st)

    def closeEvent(self, ev):
        if self.dirty:
            box = QMessageBox(QMessageBox.Question, "حفظ التغييرات", "هل تريد حفظ التغييرات قبل الإغلاق؟",
                              QMessageBox.NoButton, self)
            yes = box.addButton("حفظ", QMessageBox.AcceptRole)
            no = box.addButton("تجاهل", QMessageBox.DestructiveRole)
            cancel = box.addButton("رجوع", QMessageBox.RejectRole)
            box.exec()
            b = box.clickedButton()
            if b is cancel:
                return ev.ignore()
            if b is yes and not self.save():
                return ev.ignore()
        ev.accept()
