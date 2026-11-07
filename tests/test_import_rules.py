import os, sys, tempfile, unittest
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from openpyxl import Workbook, load_workbook
from aswaq_hr.db import Database
from aswaq_hr.service import compute_all, compute_employee
from aswaq_hr.payroll import fp_days
from aswaq_hr.constants import DEFAULT_FP_RULES
from aswaq_hr.excel_reader import read_table, extract_punches
from aswaq_hr.employee_import import parse_employee_sheet, apply_employee_data
from aswaq_hr.templates import export_employee_template, export_punch_template
from aswaq_hr import reports

BR, YM = "فرع المساكن", "2026-10"


def mkdb():
    return Database(os.path.join(tempfile.mkdtemp(), "t.db"))


def day_punches(code, name, days, forget=0):
    """صباحي 08:00-18:00 لكل يوم، وأول `forget` أيام تنقصها بصمة الخروج."""
    out = []
    for i, d in enumerate(days):
        out.append((code, name, datetime(2026, 10, d, 8, 0)))
        if i >= forget:
            out.append((code, name, datetime(2026, 10, d, 18, 0)))
    return out


class FpRules(unittest.TestCase):
    def test_tiers(self):
        r = DEFAULT_FP_RULES
        got = {n: fp_days(n, r) for n in (0, 2, 3, 10, 11, 20, 21, 40)}
        self.assertEqual(got, {0: 0, 2: 0, 3: 1, 10: 1, 11: 5, 20: 5, 21: 7, 40: 7})

    def test_custom_rules(self):
        r = dict(DEFAULT_FP_RULES, d0=0.25, d1=1.5, t1=2)
        self.assertEqual(fp_days(1, r), 0.25)
        self.assertEqual(fp_days(2, r), 1.5)

    def test_rules_saved_in_db_and_applied(self):
        db = mkdb()
        self.assertEqual(db.fp_rules(), DEFAULT_FP_RULES)
        db.replace_punches(BR, day_punches("5", "هدى", range(1, 25), forget=4))   # 4 بصمات منسية
        e = db.get_employee(BR, YM, "5"); e["salary"] = 3100; db.save_employee(e)
        _, s, pay = compute_all(db, BR, YM)[0][1:]
        self.assertEqual((s.missing_punches, pay["fp_days"], pay["fp_amount"]), (4, 1.0, 100.0))   # 3100/31
        db.set_fp_rules(dict(DEFAULT_FP_RULES, d1=1.5))
        self.assertEqual(compute_all(db, BR, YM)[0][3]["fp_amount"], 150.0)

    def test_manual_override_and_delete(self):
        db = mkdb()
        db.replace_punches(BR, day_punches("5", "هدى", range(1, 25), forget=12))  # 12 بصمة -> 5 أيام
        e = db.get_employee(BR, YM, "5"); e["salary"] = 3100; db.save_employee(e)
        base = compute_all(db, BR, YM)[0][3]
        self.assertEqual(base["fp_amount"], 500.0)
        e["fp_manual"] = 0.0; db.save_employee(e)            # حذف الجزاء
        p0 = compute_all(db, BR, YM)[0][3]
        self.assertEqual((p0["fp_amount"], p0["fp_edited"]), (0.0, True))
        self.assertAlmostEqual(p0["net"] - base["net"], 500.0)
        e["fp_manual"] = 120.0; db.save_employee(e)          # تعديل المبلغ
        self.assertEqual(compute_all(db, BR, YM)[0][3]["fp_amount"], 120.0)
        e["fp_manual"] = None; db.save_employee(e)           # رجوع للتلقائي
        self.assertEqual(compute_all(db, BR, YM)[0][3]["fp_amount"], 500.0)

    def test_old_db_gets_migrated(self):
        import sqlite3
        path = os.path.join(tempfile.mkdtemp(), "old.db")
        c = sqlite3.connect(path)
        c.executescript("CREATE TABLE payroll(branch TEXT, ym TEXT, code TEXT, name TEXT, salary REAL DEFAULT 0,"
                        "allowances REAL DEFAULT 0, penalties REAL DEFAULT 0, insurance REAL DEFAULT 0,"
                        "advance REAL DEFAULT 0, leave_days INTEGER DEFAULT 0, req_hours REAL DEFAULT 10,"
                        "grace_min INTEGER DEFAULT 20, ot_rate REAL DEFAULT 1, ot_manual REAL,"
                        "shift_mode TEXT DEFAULT 'auto', leave_paid INTEGER DEFAULT 1, deduct_short INTEGER DEFAULT 0,"
                        "notes TEXT DEFAULT '', PRIMARY KEY(branch, ym, code));"
                        "INSERT INTO payroll(branch,ym,code,name,salary) VALUES('b','2026-10','1','x',5000);")
        c.commit(); c.close()
        db = Database(path)
        self.assertEqual(db.get_employee("b", YM, "1")["salary"], 5000)
        self.assertIsNone(db.get_employee("b", YM, "1")["fp_manual"])

    def test_voucher_shows_fp_and_notes(self):
        db = mkdb()
        db.replace_punches(BR, day_punches("5", "هدى", range(1, 25), forget=4))
        e = db.get_employee(BR, YM, "5"); e["salary"] = 3100; e["notes"] = "ملاحظة اختبار"; db.save_employee(e)
        emp, days, s, pay = compute_all(db, BR, YM)[0]
        h = reports.voucher_html(BR, YM, emp, s, pay)
        self.assertIn("جزاء نسيان البصمة (4 بصمة منسية = 1 يوم)", h)
        self.assertIn("ملاحظة اختبار", h)
        t = reports.totals_of([(emp, days, s, pay)])
        self.assertEqual(t["penalties_total"], 100.0)


class ImportEmployees(unittest.TestCase):
    def _sheet(self, rows, headers=None):
        wb = Workbook(); ws = wb.active
        ws.append(headers or ["الكود", "الاسم", "الراتب الأساسي", "البدلات", "الجزاءات", "خصم التأمينات", "السلف",
                              "ملاحظات", "غياب", "إجازة بإذن"])
        for r in rows:
            ws.append(r)
        p = os.path.join(tempfile.mkdtemp(), "e.xlsx"); wb.save(p)
        return read_table(p)

    def test_full_import_by_code(self):
        db = mkdb()
        items = day_punches("121", "أحمد", range(1, 25)) + day_punches("7", "منى", range(1, 13))
        db.replace_punches(BR, items)
        rows = self._sheet([[121.0, "أحمد علي", 6200, 300, 150, 100, 500, "حافز", 0, 1],
                            ["7", "منى", 4000, None, None, 50, None, "", 3, 2],
                            [999, "موظف جديد", 3000, 0, 0, 0, 0, "", 0, 0],
                            [None, "الإجمالي", 13200, None, None, None, None, None, None, None]])
        cols, recs, warns = parse_employee_sheet(rows)
        self.assertEqual(len(recs), 3)
        rep = apply_employee_data(db, BR, YM, cols, recs)
        self.assertEqual((rep["updated"], rep["created"]), (2, 1))
        self.assertEqual(rep["no_punches"], ["999"])
        e = db.get_employee(BR, YM, "121")
        self.assertEqual((e["name"], e["salary"], e["allowances"], e["penalties"], e["insurance"], e["advance"],
                          e["notes"], e["leave_days"]), ("أحمد علي", 6200, 300, 150, 100, 500, "حافز", 1))
        m = db.get_employee(BR, YM, "7")
        self.assertEqual((m["allowances"], m["advance"], m["leave_days"]), (0, 0, 2))
        # أيام الموظف 121: حضور 24 + راحة 4 + إجازة 1 + غياب 2 = 31
        _, s, pay = compute_employee(db, BR, YM, e)
        self.assertEqual((s.present, s.rest, pay["leave"], pay["absent"]), (24, 4, 1, 2))
        # غياب الشيت لموظف 7 (3) لا يطابق حساب البرنامج
        self.assertTrue(any(c == "7" for c, *_ in rep["mismatch"]))
        # الجزاء والملاحظات تظهر في سند المرتب
        emp, days, s, pay = [x for x in compute_all(db, BR, YM) if x[0]["code"] == "121"][0]
        h = reports.voucher_html(BR, YM, emp, s, pay)
        self.assertIn("حافز", h); self.assertIn("150.00", h)

    def test_blank_rules_and_partial_columns(self):
        db = mkdb()
        db.replace_punches(BR, day_punches("1", "س", range(1, 10)))
        e = db.get_employee(BR, YM, "1"); e.update(salary=5000, advance=200, notes="قديمة"); db.save_employee(e)
        rows = self._sheet([["1", "", None, None, None, None, 75, ""]],
                           headers=["رقم الموظف", "الاسم", "المرتب", "بدل", "جزاءات", "التأمينات", "سلفة", "ملاحظات"])
        cols, recs, _ = parse_employee_sheet(rows)
        apply_employee_data(db, BR, YM, cols, recs)
        e = db.get_employee(BR, YM, "1")
        self.assertEqual((e["salary"], e["advance"], e["notes"], e["name"]), (5000, 75, "قديمة", "س"))
        # عمود واحد فقط (الكود + السلف): باقي البيانات لا تتغير
        cols, recs, _ = parse_employee_sheet(self._sheet([["1", 10]], headers=["الكود", "السلف"]))
        apply_employee_data(db, BR, YM, cols, recs)
        e = db.get_employee(BR, YM, "1")
        self.assertEqual((e["salary"], e["advance"]), (5000, 10))

    def test_only_absent_column_derives_leave(self):
        db = mkdb()
        db.replace_punches(BR, day_punches("1", "س", range(1, 25)))     # حضور 24 + راحة 4 -> متبقي 3
        cols, recs, _ = parse_employee_sheet(self._sheet([["1", 1]], headers=["الكود", "غياب"]))
        rep = apply_employee_data(db, BR, YM, cols, recs)
        e = db.get_employee(BR, YM, "1")
        self.assertEqual(e["leave_days"], 2)
        self.assertEqual(rep["mismatch"], [])

    def test_leave_larger_than_remaining_is_clipped(self):
        db = mkdb()
        db.replace_punches(BR, day_punches("1", "س", range(1, 25)))
        cols, recs, _ = parse_employee_sheet(self._sheet([["1", 9]], headers=["الكود", "إجازة بإذن"]))
        rep = apply_employee_data(db, BR, YM, cols, recs)
        self.assertEqual(db.get_employee(BR, YM, "1")["leave_days"], 3)
        self.assertEqual(len(rep["clipped"]), 1)

    def test_bad_sheet_errors(self):
        from aswaq_hr.excel_reader import ReadError
        with self.assertRaises(ReadError):
            parse_employee_sheet([["الاسم", "الراتب"], ["أ", 100]])


class Templates(unittest.TestCase):
    def test_employee_template_roundtrip(self):
        p = os.path.join(tempfile.mkdtemp(), "t.xlsx")
        export_employee_template(p)
        wb = load_workbook(p)
        self.assertEqual(wb.sheetnames, ["بيانات الموظفين", "تعليمات"])
        ws = wb.active
        ws.append(["3", "علي", 1000, 1, 2, 3, 4, "ن", 0, 0]); wb.save(p)
        cols, recs, _ = parse_employee_sheet(read_table(p))
        self.assertEqual(cols, ["code", "name", "salary", "allowances", "penalties", "insurance", "advance",
                                "notes", "absent", "leave"])
        self.assertEqual((recs[0]["code"], recs[0]["advance"]), ("3", 4.0))

    def test_empty_punch_template_has_no_data_and_filled_one_imports(self):
        p = os.path.join(tempfile.mkdtemp(), "p.xlsx")
        export_punch_template(p)
        wb = load_workbook(p); ws = wb.active
        self.assertEqual([c.value for c in ws[1]], ["الكود", "الاسم", "التاريخ والوقت"])
        self.assertIsNone(ws["A2"].value)
        for i, (code, h) in enumerate([(1, 8), (1, 18), (2, 9), (2, 17)], start=2):
            ws.cell(i, 1, code); ws.cell(i, 2, "م%d" % code); ws.cell(i, 3, datetime(2026, 10, 1, h, 0))
        wb.save(p)
        items, cols = extract_punches(read_table(p))
        self.assertEqual(len(items), 4)


if __name__ == "__main__":
    unittest.main()
