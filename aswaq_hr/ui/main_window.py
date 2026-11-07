from collections import Counter

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
                               QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMenu,
                               QToolButton, QDialog, QFormLayout, QAbstractItemView)

from .. import APP_NAME, reports
from ..excel_reader import read_table, extract_punches, ReadError
from ..employee_import import parse_employee_sheet, apply_employee_data, report_text
from .. import templates
from ..service import compute_all
from .common import logo_label, signature_label, info, warn, ask, print_preview
from .employee_dialog import EmployeeDialog
from .summary_dialog import SummaryDialog
from .login import ChangePasswordDialog, UsersDialog
from .rules_dialog import FpRulesDialog

COLS = ["الكود", "الاسم", "الشيفت", "أيام الحضور", "بصمات الدخول", "بصمات الخروج", "بصمات ناقصة", "الراحة", "إجازة", "غياب", "إجمالي الساعات", "متوسط الساعات", "صافي المرتب"]


class AddEmployeeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إضافة موظف")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.code, self.name = QLineEdit(), QLineEdit()
        form.addRow("الكود", self.code)
        form.addRow("الاسم", self.name)
        lay.addLayout(form)
        b = QPushButton("إضافة")
        b.clicked.connect(self._ok)
        lay.addWidget(b)

    def _ok(self):
        if not self.code.text().strip() or not self.name.text().strip():
            return warn(self, "اكتب الكود والاسم")
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, db, user, branch, on_switch):
        super().__init__()
        self.db, self.user, self.branch, self.on_switch = db, user, branch, on_switch
        self.items = []
        self.setWindowTitle("%s — %s" % (APP_NAME, branch))
        self.resize(1200, 760)

        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        top = QHBoxLayout()
        top.addWidget(logo_label(56))
        title = QLabel("<span style='font-size:17pt;color:#1b9e4b'><b>%s</b></span><br>الفرع: <b>%s</b>   |   المستخدم: %s"
                       % (APP_NAME, branch, user["username"]))
        top.addWidget(title)
        top.addStretch()
        top.addWidget(QLabel("الشهر:"))
        self.cmb = QComboBox()
        self.cmb.setMinimumWidth(170)
        self.cmb.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.cmb)
        root.addLayout(top)

        bar = QHBoxLayout()
        def mk(text, fn, obj=""):
            b = QPushButton(text)
            if obj:
                b.setObjectName(obj)
            b.clicked.connect(fn)
            bar.addWidget(b)
            return b
        mk("استيراد شيت البصمة", self.import_sheet)
        mk("استيراد بيانات الموظفين", self.import_employees)
        tb = QToolButton()
        tb.setText("تصدير شيت فارغ ▾")
        tb.setPopupMode(QToolButton.InstantPopup)
        tm = QMenu(tb)
        tm.addAction("شيت بيانات الموظفين (فارغ)", self.export_employee_template)
        tm.addAction("شيت البصمات (فارغ)", self.export_punch_template)
        tb.setMenu(tm)
        bar.addWidget(tb)
        mk("قواعد نسيان البصمة", self.open_fp_rules, "secondary")
        mk("إجمالي المرتبات", self.open_summary)
        mk("طباعة كل السندات", self.print_all, "secondary")
        mk("إضافة موظف", self.add_employee, "secondary")
        mk("حذف الموظف المحدد", self.delete_employee, "danger")
        bar.addStretch()
        mk("تغيير الفرع", self.switch_branch, "secondary")
        st = QToolButton()
        st.setText("الإعدادات ▾")
        st.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(st)
        menu.addAction("تغيير كلمة المرور", self.change_password)
        if user.get("is_admin"):
            menu.addAction("إدارة المستخدمين", lambda: UsersDialog(self.db).exec())
        menu.addAction("حول البرنامج", self.about)
        st.setMenu(menu)
        bar.addWidget(st)
        root.addLayout(bar)

        self.search = QLineEdit()
        self.search.setPlaceholderText("بحث بالاسم أو الكود...")
        self.search.textChanged.connect(self.apply_filter)
        root.addWidget(self.search)

        self.tbl = QTableWidget(0, len(COLS))
        self.tbl.setHorizontalHeaderLabels(COLS)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.cellDoubleClicked.connect(self.open_employee)
        root.addWidget(self.tbl, 1)

        self.status = QLabel("")
        root.addWidget(self.status)
        root.addWidget(signature_label())

        self.load_months()

    # ------------------------------------------------------------ الشهور
    @property
    def ym(self):
        return self.cmb.currentData()

    def load_months(self, select=None):
        self.cmb.blockSignals(True)
        self.cmb.clear()
        for ym in self.db.months(self.branch):
            self.cmb.addItem(reports.month_label(ym), ym)
        if select:
            i = self.cmb.findData(select)
            if i >= 0:
                self.cmb.setCurrentIndex(i)
        self.cmb.blockSignals(False)
        self.refresh()

    # ------------------------------------------------------------ الجدول
    def refresh(self, *_):
        self.tbl.setRowCount(0)
        self.items = []
        if not self.ym:
            self.status.setText("لا توجد بيانات لهذا الفرع بعد — اضغط «استيراد شيت البصمة».")
            return
        self.items = compute_all(self.db, self.branch, self.ym)
        self.tbl.setRowCount(len(self.items))
        for r, (emp, days, s, pay) in enumerate(self.items):
            vals = [emp["code"], emp["name"], s.shift_label, s.present, s.in_punches, s.out_punches,
                    s.missing_punches, s.rest, pay["leave"], pay["absent"],
                    reports.hrs(s.total_hours), reports.hrs(s.avg_hours), reports.money(pay["net"])]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setTextAlignment(Qt.AlignCenter if c != 1 else Qt.AlignVCenter | Qt.AlignRight)
                if c == 2 and s.last_shift:
                    mixed = bool(s.day_shifts and s.night_shifts)
                    it.setBackground(QColor("#fdebd0" if mixed else "#d6eaf8" if s.last_shift == "night" else "#fef9e7"))
                if c == 6 and v:
                    it.setBackground(QColor("#fff3cd"))
                self.tbl.setItem(r, c, it)
        self.apply_filter()
        self.status.setText("عدد الموظفين: %d   |   اضغط مرتين على الموظف لعرض الحضور والمرتب" % len(self.items))

    def apply_filter(self, *_):
        q = self.search.text().strip().lower()
        for r in range(self.tbl.rowCount()):
            txt = (self.tbl.item(r, 0).text() + " " + self.tbl.item(r, 1).text()).lower()
            self.tbl.setRowHidden(r, bool(q) and q not in txt)

    def _selected_code(self):
        r = self.tbl.currentRow()
        if r < 0:
            return None
        return self.tbl.item(r, 0).text()

    # ------------------------------------------------------------ الإجراءات
    def import_sheet(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختر شيت البصمة", "",
                                              "ملفات الحضور (*.xls *.xlsx *.csv);;كل الملفات (*)")
        if not path:
            return
        try:
            punches, cols = extract_punches(read_table(path))
        except ReadError as e:
            return warn(self, str(e))
        except Exception as e:
            return warn(self, "تعذر قراءة الملف:\n%s" % e)
        months = Counter(d.strftime("%Y-%m") for _, _, d in punches)
        codes = {c for c, _, _ in punches}
        exist = [m for m in months if self.db.month_has_punches(self.branch, m)]
        msg = "تم التعرف على %d موظف و %d حركة بصمة.\nالشهور: %s" % (
            len(codes), len(punches), "، ".join(reports.month_label(m) for m in sorted(months)))
        if exist:
            msg += "\n\nتنبيه: توجد بصمات محفوظة لنفس الشهر وسيتم استبدالها (بيانات الرواتب تبقى كما هي)."
        if not ask(self, msg + "\n\nهل تريد المتابعة؟", "استيراد الشيت"):
            return
        self.db.replace_punches(self.branch, punches)
        self.load_months(select=months.most_common(1)[0][0])
        info(self, "تم استيراد الشيت بنجاح")

    def import_employees(self):
        if not self.ym:
            return warn(self, "استورد شيت البصمة أولاً لتحديد الشهر")
        path, _ = QFileDialog.getOpenFileName(self, "اختر شيت بيانات الموظفين", "",
                                              "ملفات Excel (*.xlsx *.xls *.csv);;كل الملفات (*)")
        if not path:
            return
        try:
            cols, recs, warns = parse_employee_sheet(read_table(path))
        except ReadError as e:
            return warn(self, str(e))
        except Exception as e:
            return warn(self, "تعذر قراءة الملف:\n%s" % e)
        label = reports.month_label(self.ym)
        if not ask(self, "تم التعرف على %d موظف.\nسيتم تطبيق البيانات على شهر %s — فرع %s.\n"
                         "(الأعمدة غير الموجودة في الشيت لن تتغير)\n\nهل تريد المتابعة؟" % (len(recs), label, self.branch),
                   "استيراد بيانات الموظفين"):
            return
        try:
            rep = apply_employee_data(self.db, self.branch, self.ym, cols, recs)
        except Exception as e:
            return warn(self, "حدث خطأ أثناء الاستيراد:\n%s" % e)
        self.refresh()
        info(self, report_text(label, cols, rep, warns))

    def _save_template(self, title, default, fn):
        path, _ = QFileDialog.getSaveFileName(self, title, default, "Excel (*.xlsx)")
        if not path:
            return
        try:
            fn(path)
            info(self, "تم التصدير:\n" + path)
        except Exception as e:
            warn(self, "تعذر التصدير: %s" % e)

    def export_employee_template(self):
        self._save_template("تصدير شيت بيانات الموظفين", "شيت_بيانات_الموظفين.xlsx", templates.export_employee_template)

    def export_punch_template(self):
        self._save_template("تصدير شيت البصمات", "شيت_البصمات.xlsx", templates.export_punch_template)

    def open_fp_rules(self):
        if FpRulesDialog(self.db, self).exec() == QDialog.Accepted:
            self.refresh()

    def open_employee(self, row, _col):
        code = self.tbl.item(row, 0).text()
        EmployeeDialog(self.db, self.branch, self.ym, code, self).exec()
        self.refresh()

    def open_summary(self):
        if not self.ym:
            return warn(self, "استورد شيت البصمة أولاً")
        SummaryDialog(self.db, self.branch, self.ym, self).exec()

    def print_all(self):
        if not self.items:
            return warn(self, "لا توجد بيانات للطباعة")
        print_preview(self, reports.vouchers_html(self.branch, self.ym, self.items))

    def add_employee(self):
        if not self.ym:
            return warn(self, "استورد شيت البصمة أولاً لتحديد الشهر")
        d = AddEmployeeDialog(self)
        if d.exec() == QDialog.Accepted:
            code = d.code.text().strip()
            if self.db.get_employee(self.branch, self.ym, code):
                return warn(self, "هذا الكود موجود بالفعل")
            self.db.ensure_employee(self.branch, self.ym, code, d.name.text().strip())
            self.refresh()

    def delete_employee(self):
        code = self._selected_code()
        if not code:
            return warn(self, "اختر موظفاً من الجدول أولاً")
        if ask(self, "حذف الموظف %s وكل بصماته وبياناته في هذا الشهر؟" % code):
            self.db.delete_employee(self.branch, self.ym, code)
            self.refresh()

    def change_password(self):
        if self.user.get("is_admin"):
            return info(self, "كلمة مرور مدير النظام ثابتة داخل البرنامج ولا يمكن تغييرها.")
        ChangePasswordDialog(self.db, self.user).exec()

    def about(self):
        info(self, "%s\nالإصدار 1.0.0\n\nتصميم وتطوير: Mahmoud Thabet" % APP_NAME)

    def switch_branch(self):
        QTimer.singleShot(0, self.on_switch)
