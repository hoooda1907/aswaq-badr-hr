import calendar
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QTableWidget,
                               QTableWidgetItem, QHeaderView, QLabel, QGroupBox, QGridLayout, QSpinBox,
                               QDoubleSpinBox, QFormLayout, QComboBox, QCheckBox, QLineEdit, QPushButton,
                               QMessageBox, QAbstractItemView, QAbstractSpinBox)

from .. import reports
from ..constants import SHIFT_MODES, SHIFT_LABELS, DAY_NAMES_AR
from ..service import compute_employee
from .common import print_preview, save_pdf, warn


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
        self.punches = db.punches_of(branch, ym, code)
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
        self.tbl = QTableWidget(0, 7)
        self.tbl.setHorizontalHeaderLabels(["التاريخ", "اليوم", "الشيفت", "الدخول", "الخروج", "ساعات العمل", "ملاحظات"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.verticalHeader().setVisible(False)
        lay.addWidget(self.tbl)
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

        g2 = QGroupBox("توزيع الأيام المتبقية (مجموعها يساوي المتبقي دائماً)")
        g2l = QGridLayout(g2)
        self.sp_leave, self.sp_absent = QSpinBox(), QSpinBox()
        for sp in (self.sp_leave, self.sp_absent):
            sp.setAlignment(Qt.AlignCenter)
            sp.setStyleSheet("font-size:18pt; padding:6px;")
        g2l.addWidget(QLabel("إجازة بإذن"), 0, 0, alignment=Qt.AlignCenter)
        g2l.addWidget(QLabel("غياب"), 0, 1, alignment=Qt.AlignCenter)
        g2l.addWidget(self.sp_leave, 1, 0)
        g2l.addWidget(self.sp_absent, 1, 1)
        self.lb_check = QLabel()
        self.lb_check.setAlignment(Qt.AlignCenter)
        g2l.addWidget(self.lb_check, 2, 0, 1, 2)
        lay.addWidget(g2)
        lay.addStretch()
        self.sp_leave.valueChanged.connect(self._leave_changed)
        self.sp_absent.valueChanged.connect(self._absent_changed)
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
                   self.f_rate, self.f_ot, self.f_fp):
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
            notes=self.f_notes.text(), leave_days=self.sp_leave.value())
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
        self._loading = True
        self.sp_absent.setValue(self._cur[1].remaining - v)
        self._loading = False
        self.dirty = True
        self.recalc()

    def _absent_changed(self, v):
        if self._loading or not self._cur:
            return
        self._loading = True
        self.sp_leave.setValue(self._cur[1].remaining - v)
        self._loading = False
        self.dirty = True
        self.recalc()

    # ------------------------------------------------------------ إعادة الحساب
    def recalc(self):
        if self._loading:
            return
        emp = self.collect()
        days, s, pay = compute_employee(self.db, self.branch, self.ym, emp, self.punches)
        self._cur = (days, s, pay, emp)

        self._loading = True
        self.sp_leave.setMaximum(s.remaining)
        self.sp_absent.setMaximum(s.remaining)
        leave = min(self.sp_leave.value(), s.remaining)
        self.sp_leave.setValue(leave)
        self.sp_absent.setValue(s.remaining - leave)
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
        self.lb_in.setText(str(s.in_punches))
        self.lb_out.setText(str(s.out_punches))
        self.lb_miss.setText(str(s.missing_punches))
        total = s.present + s.rest + pay["leave"] + pay["absent"]
        ok = total == s.month_days
        self.lb_check.setText("حضور %d + راحة %d + إجازة %d + غياب %d = %d يوم (أيام الشهر: %d) %s"
                              % (s.present, s.rest, pay["leave"], pay["absent"], total, s.month_days, "✔" if ok else "✘"))
        self.lb_check.setStyleSheet("font-size:12pt; color:%s;" % ("#1b9e4b" if ok else "#c0392b"))
        self._refresh_table(days, s)
        self._refresh_result(s, pay)

    def _refresh_table(self, days, s):
        y, m = int(self.ym[:4]), int(self.ym[5:7])
        self.tbl.setRowCount(s.month_days)
        for d in range(1, s.month_days + 1):
            dt = date(y, m, d)
            rec = days.get(dt)
            vals = ["%02d/%02d/%d" % (d, m, y), DAY_NAMES_AR[dt.weekday()], "", "", "", "", ""]
            color = None
            if rec:
                vals[2] = SHIFT_LABELS[rec.shift]
                if rec.in_dt:
                    vals[3] = rec.in_dt.strftime("%H:%M" if rec.in_dt.date() == dt else "%H:%M  (%d/%m)")
                if rec.out_dt:
                    vals[4] = rec.out_dt.strftime("%H:%M" if rec.out_dt.date() == dt else "%H:%M  (%d/%m)")
                if rec.complete:
                    vals[5] = reports.hrs(rec.hours)
                vals[6] = rec.note
                if not rec.complete:
                    color = QColor("#fff3cd")
                elif rec.change:
                    color = QColor("#d6eaf8")
            else:
                vals[6] = "لا توجد بصمة"
                color = QColor("#fdecea")
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignCenter)
                if color:
                    it.setBackground(color)
                if rec and rec.change:
                    f = it.font(); f.setBold(True); it.setFont(f)
                self.tbl.setItem(d - 1, c, it)

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
        if s.present + s.rest + pay["leave"] + pay["absent"] != s.month_days:
            return warn(self, "مجموع الحضور والراحة والإجازة والغياب لا يساوي عدد أيام الشهر")
        self.db.save_employee(emp)
        self.emp = emp
        self.dirty = False
        return True

    def _voucher(self):
        if self.dirty and not self.save():
            return None
        days, s, pay, emp = self._cur
        return reports.voucher_html(self.branch, self.ym, emp, s, pay)

    def print_voucher(self):
        h = self._voucher()
        if h:
            print_preview(self, h)

    def pdf_voucher(self):
        h = self._voucher()
        if h:
            save_pdf(self, h, "سند_مرتب_%s_%s.pdf" % (self.code, self.ym))

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
