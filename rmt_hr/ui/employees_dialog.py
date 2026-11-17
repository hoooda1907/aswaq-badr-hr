from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
                               QPushButton, QLabel, QInputDialog, QFileDialog, QAbstractItemView)

from .. import templates
from ..employee_import import parse_employee_sheet, apply_to_master, to_num
from ..excel_reader import read_table, ReadError
from .common import warn, info, ask

HEADS = ["الكود", "الاسم", "الراتب الأساسي", "البدلات", "خصم التأمينات", "رصيد الإجازات السنوية (يوم)"]


class EmployeesListDialog(QDialog):
    """القائمة الدائمة للموظفين: تُملأ تلقائياً من البصمات وشيت المرتبات، وتُستخدم في كل الشهور القادمة.
    تحتفظ بالكود والاسم والراتب والبدلات والتأمينات + رصيد الإجازة السنوية (الافتراضي 21)."""

    def __init__(self, db, branch, parent=None):
        super().__init__(parent)
        self.db, self.branch = db, branch
        self.setWindowTitle("قائمة الموظفين — " + branch)
        self.resize(900, 600)
        lay = QVBoxLayout(self)
        note = QLabel("هذه البيانات محفوظة بصفة دائمة وتُرحَّل تلقائياً للشهور الجديدة. الجزاءات والسلف والإضافي لا تُحفظ هنا. "
                      "عدّل الخلايا مباشرة ثم اضغط «حفظ».")
        note.setWordWrap(True)
        note.setStyleSheet("color:#666;")
        lay.addWidget(note)
        self.tbl = QTableWidget(0, len(HEADS))
        self.tbl.setHorizontalHeaderLabels(HEADS)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        lay.addWidget(self.tbl, 1)
        row = QHBoxLayout()
        for text, fn, name in (("إضافة موظف", self.add, None), ("حذف من القائمة", self.delete, "danger"),
                               ("حفظ", self.save, None), ("استيراد من شيت", self.import_sheet, "secondary"),
                               ("تصدير القائمة", self.export_sheet, "secondary")):
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
        rows = self.db.master_list(self.branch)
        self.tbl.setRowCount(len(rows))
        for r, m in enumerate(rows):
            vals = [m["code"], m["name"], m["salary"], m["allowances"], m["insurance"], m["annual_days"]]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(("%g" % v) if isinstance(v, float) else str(v))
                it.setTextAlignment(Qt.AlignCenter if c != 1 else Qt.AlignVCenter | Qt.AlignRight)
                if c == 0:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.tbl.setItem(r, c, it)

    def add(self):
        code, ok = QInputDialog.getText(self, "إضافة موظف", "الكود:")
        code = (code or "").strip()
        if not ok or not code:
            return
        if self.db.master_get(self.branch, code):
            return warn(self, "هذا الكود موجود بالفعل")
        name, ok = QInputDialog.getText(self, "إضافة موظف", "الاسم:")
        if not ok:
            return
        self.db.master_upsert(self.branch, code, name=(name or "").strip() or code)
        self.reload()

    def delete(self):
        r = self.tbl.currentRow()
        if r < 0:
            return warn(self, "اختر موظفاً أولاً")
        code = self.tbl.item(r, 0).text()
        if ask(self, "حذف الموظف %s من القائمة الدائمة؟\n(بيانات الشهور السابقة لا تتأثر)" % code):
            self.db.master_delete(self.branch, code)
            self.reload()

    def save(self):
        updates = []
        for r in range(self.tbl.rowCount()):
            code = self.tbl.item(r, 0).text()
            nums = []
            for c in (2, 3, 4, 5):
                v, ok = to_num(self.tbl.item(r, c).text())
                if not ok or (v is not None and v < 0):
                    return warn(self, "قيمة غير صحيحة في الصف %d (%s): «%s»" % (r + 1, code, HEADS[c]))
                nums.append(v)
            updates.append((code, self.tbl.item(r, 1).text().strip(), nums))
        for code, name, (sal, alw, ins, ann) in updates:
            self.db.master_upsert(self.branch, code, name=name or code, salary=sal or 0.0, allowances=alw or 0.0,
                                  insurance=ins or 0.0, annual_days=21.0 if ann is None else ann, commit=False)
        self.db.conn.commit()
        info(self, "تم حفظ قائمة الموظفين (%d موظف)" % len(updates))

    def import_sheet(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختر شيت المرتبات والبدلات", "",
                                              "ملفات Excel (*.xlsx *.xls *.csv);;كل الملفات (*)")
        if not path:
            return
        try:
            cols, recs, warns = parse_employee_sheet(read_table(path))
        except ReadError as e:
            return warn(self, str(e))
        except Exception as e:
            return warn(self, "تعذر قراءة الملف:\n%s" % e)
        added, updated = apply_to_master(self.db, self.branch, cols, recs)
        self.reload()
        info(self, "تم التحديث: %d موظف جديد، %d موظف محدّث.\n(يُطبَّق على الشهور القادمة؛ لتطبيقه على شهر حالي استخدم «استيراد بيانات الموظفين»)%s"
             % (added, updated, ("\n" + "\n".join(warns[:5])) if warns else ""))

    def export_sheet(self):
        path, _ = QFileDialog.getSaveFileName(self, "تصدير قائمة الموظفين", "قائمة_الموظفين.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            templates.export_master_sheet(path, self.db.master_list(self.branch))
            info(self, "تم التصدير:\n" + path)
        except Exception as e:
            warn(self, "تعذر التصدير: %s" % e)
