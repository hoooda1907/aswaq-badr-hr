import os, sys, tempfile, unittest
from datetime import datetime, date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from openpyxl import Workbook
from rmt_hr.db import Database
from rmt_hr.excel_reader import read_table
from rmt_hr.employee_import import parse_employee_sheet, apply_employee_data, apply_to_master
from rmt_hr.service import compute_all, compute_employee
from rmt_hr.templates import export_master_sheet

B = "ف"


def mkdb():
    return Database(os.path.join(tempfile.mkdtemp(), "t.db"))


def pun(code, name, m, d, h, mi=0, k=""):
    return (code, name, datetime(2026, m, d, h, mi), k)


def sheet(headers, rows):
    wb = Workbook(); ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    p = os.path.join(tempfile.mkdtemp(), "s.xlsx"); wb.save(p)
    return read_table(p)


class Master(unittest.TestCase):
    def test_first_import_creates_master_with_default_annual_21(self):
        db = mkdb()
        db.replace_punches(B, [pun("5", "هدى", 10, 1, 8), pun("5", "هدى", 10, 1, 17)])
        m = db.master_get(B, "5")
        self.assertEqual((m["name"], m["salary"], m["annual_days"]), ("هدى", 0, 21))

    def test_next_month_inherits_pay_but_not_one_off_items(self):
        db = mkdb()
        db.replace_punches(B, [pun("5", "هدى", 10, 1, 8), pun("5", "هدى", 10, 1, 17)])
        e = db.get_employee(B, "2026-10", "5")
        e.update(salary=4000, allowances=300, insurance=120, penalties=50, advance=700, ot_manual=3.0,
                 notes="ملاحظة", leave_days=2, fp_manual=10.0)
        db.save_employee(e)
        db.replace_punches(B, [pun("5", "هدى", 11, 2, 8), pun("5", "هدى", 11, 2, 17)])
        n = db.get_employee(B, "2026-11", "5")
        self.assertEqual((n["salary"], n["allowances"], n["insurance"], n["name"]), (4000, 300, 120, "هدى"))
        self.assertEqual((n["penalties"], n["advance"], n["leave_days"], n["notes"]), (0, 0, 0, ""))
        self.assertIsNone(n["ot_manual"]); self.assertIsNone(n["fp_manual"])

    def test_salary_sheet_updates_master_and_next_month(self):
        db = mkdb()
        db.replace_punches(B, [pun("5", "هدى", 10, 1, 8), pun("5", "هدى", 10, 1, 17)])
        cols, recs, _ = parse_employee_sheet(sheet(["الكود", "الاسم", "الراتب الأساسي", "البدلات", "خصم التأمينات", "رصيد الإجازات السنوية"],
                                                  [["5", "هدى علي", 5000, 400, 150, 18]]))
        self.assertIn("annual", cols); self.assertNotIn("leave", cols)       # العمود لا يختلط بـ «إجازة بإذن»
        apply_employee_data(db, B, "2026-10", cols, recs)
        m = db.master_get(B, "5")
        self.assertEqual((m["name"], m["salary"], m["allowances"], m["insurance"], m["annual_days"]), ("هدى علي", 5000, 400, 150, 18))
        db.replace_punches(B, [pun("5", "5", 11, 2, 8), pun("5", "5", 11, 2, 17)])      # الشيت يعطي الكود كاسم
        n = db.get_employee(B, "2026-11", "5")
        self.assertEqual((n["name"], n["salary"], n["allowances"], n["insurance"]), ("هدى علي", 5000, 400, 150))

    def test_editing_latest_month_updates_master_old_month_does_not(self):
        db = mkdb()
        db.replace_punches(B, [pun("5", "هدى", 10, 1, 8), pun("5", "هدى", 10, 1, 17),
                               pun("5", "هدى", 11, 2, 8), pun("5", "هدى", 11, 2, 17)])
        old = db.get_employee(B, "2026-10", "5"); old["salary"] = 1111; db.save_employee(old)
        self.assertEqual(db.master_get(B, "5")["salary"], 0)                 # شهر قديم: لا يغيّر الافتراضي
        new = db.get_employee(B, "2026-11", "5"); new["salary"] = 2222; db.save_employee(new)
        self.assertEqual(db.master_get(B, "5")["salary"], 2222)

    def test_apply_to_master_keeps_blank_and_counts(self):
        db = mkdb()
        db.master_upsert(B, "7", name="منى", salary=3000, allowances=100, insurance=50, annual_days=21)
        cols, recs, _ = parse_employee_sheet(sheet(["الكود", "الراتب الأساسي"], [["7", 3500], ["8", 2000]]))
        added, updated = apply_to_master(db, B, cols, recs)
        self.assertEqual((added, updated), (1, 1))
        m = db.master_get(B, "7")
        self.assertEqual((m["name"], m["salary"], m["allowances"]), ("منى", 3500, 100))
        self.assertEqual(db.master_get(B, "8")["annual_days"], 21)

    def test_real_name_from_punch_sheet_updates_master_but_code_does_not(self):
        db = mkdb()
        db.master_upsert(B, "9", name="سعيد محمد")
        db.replace_punches(B, [pun("9", "9", 10, 1, 8), pun("9", "9", 10, 1, 17)])
        self.assertEqual(db.master_get(B, "9")["name"], "سعيد محمد")
        self.assertEqual(db.get_employee(B, "2026-10", "9")["name"], "سعيد محمد")
        db.replace_punches(B, [pun("9", "سعيد م.", 10, 1, 8), pun("9", "سعيد م.", 10, 1, 17)])
        self.assertEqual(db.master_get(B, "9")["name"], "سعيد م.")

    def test_export_master_sheet_roundtrip(self):
        db = mkdb()
        db.master_upsert(B, "1", name="أ", salary=100, allowances=5, insurance=2, annual_days=21)
        db.master_upsert(B, "2", name="ب", salary=200, annual_days=15)
        p = os.path.join(tempfile.mkdtemp(), "m.xlsx")
        export_master_sheet(p, db.master_list(B))
        cols, recs, _ = parse_employee_sheet(read_table(p))
        db2 = mkdb()
        apply_to_master(db2, B, cols, recs)
        self.assertEqual([(m["code"], m["salary"], m["annual_days"]) for m in db2.master_list(B)], [("1", 100, 21), ("2", 200, 15)])


class PunchEdits(unittest.TestCase):
    def setUp(self):
        self.db = mkdb()
        # موظف متغيّر: بصمة صباحية زائدة 11:53 تكسر شيفت 6 المسائي (الحالة الحقيقية في الشيت)
        self.db.replace_punches(B, [pun("291", "م", 10, 6, 18, 14, "I"), pun("291", "م", 10, 7, 3, 31, "O"),
                                    pun("291", "م", 10, 7, 11, 53, "I"), pun("291", "م", 10, 8, 3, 34, "O")])

    def days(self):
        return compute_all(self.db, B, "2026-10")[0][1]

    def test_delete_punch_changes_calculation_and_restore(self):
        base = self.days()
        self.assertEqual(base[date(2026, 10, 7)].in_dt, datetime(2026, 10, 7, 11, 53))
        self.db.punch_delete(B, "291", datetime(2026, 10, 7, 11, 53))
        self.assertEqual(len(self.db.punches_of(B, "2026-10", "291")), 3)
        self.assertNotIn(date(2026, 10, 7), self.days())
        self.assertEqual(self.db.punch_edit_count(B, "2026-10", "291"), 1)
        self.db.punch_restore(B, "291", datetime(2026, 10, 7, 11, 53))
        self.assertEqual(len(self.db.punches_of(B, "2026-10", "291")), 4)
        self.assertEqual(self.db.punch_edit_count(B, "2026-10", "291"), 0)

    def test_modify_time_and_kind(self):
        self.db.punch_modify(B, "291", datetime(2026, 10, 7, 11, 53), datetime(2026, 10, 7, 18, 0), "I")
        rows = {r["dt"]: r for r in self.db.punch_rows(B, "2026-10", "291")}
        self.assertEqual(rows[datetime(2026, 10, 7, 18, 0)]["state"], "mod")
        self.assertEqual(rows[datetime(2026, 10, 7, 18, 0)]["orig"], datetime(2026, 10, 7, 11, 53))
        self.assertNotIn(datetime(2026, 10, 7, 11, 53), rows)
        d = self.days()[date(2026, 10, 7)]
        self.assertEqual((d.in_dt, d.out_dt), (datetime(2026, 10, 7, 18, 0), datetime(2026, 10, 8, 3, 34)))
        # تعديل ثانٍ لنفس البصمة يبقى تعديلاً واحداً، والرجوع للأصل يلغيه
        self.db.punch_modify(B, "291", datetime(2026, 10, 7, 18, 0), datetime(2026, 10, 7, 19, 0))
        self.assertEqual(self.db.punch_edit_count(B, "2026-10", "291"), 1)
        self.db.punch_modify(B, "291", datetime(2026, 10, 7, 19, 0), datetime(2026, 10, 7, 11, 53))
        self.assertEqual(self.db.punch_edit_count(B, "2026-10", "291"), 0)

    def test_add_missing_punch_completes_shift(self):
        self.db.replace_punches(B, [pun("5", "س", 10, 1, 18, 0, "I")])           # خروج ناقص
        self.assertEqual(self.db.get_employee(B, "2026-10", "5") is not None, True)
        self.db.punch_add(B, "5", datetime(2026, 10, 2, 4, 0), "O")
        d = compute_all(self.db, B, "2026-10")
        d5 = [x for x in d if x[0]["code"] == "5"][0][1]
        self.assertTrue(d5[date(2026, 10, 1)].complete)
        self.assertAlmostEqual(d5[date(2026, 10, 1)].hours, 10)
        # حذف البصمة المضافة يلغي الإضافة
        self.db.punch_delete(B, "5", datetime(2026, 10, 2, 4, 0))
        self.assertEqual(self.db.punch_edit_count(B, "2026-10", "5"), 0)

    def test_edits_survive_reimport_of_sheet(self):
        self.db.punch_delete(B, "291", datetime(2026, 10, 7, 11, 53))
        self.db.punch_add(B, "291", datetime(2026, 10, 20, 8, 0), "I")
        self.db.replace_punches(B, [pun("291", "م", 10, 6, 18, 14, "I"), pun("291", "م", 10, 7, 3, 31, "O"),
                                    pun("291", "م", 10, 7, 11, 53, "I"), pun("291", "م", 10, 8, 3, 34, "O")])
        eff = [dt for dt, _ in self.db.punches_of(B, "2026-10", "291", with_kind=True)]
        self.assertNotIn(datetime(2026, 10, 7, 11, 53), eff)
        self.assertIn(datetime(2026, 10, 20, 8, 0), eff)

    def test_deleted_rows_still_listed_for_editor_and_clear(self):
        self.db.punch_delete(B, "291", datetime(2026, 10, 7, 11, 53))
        states = {r["dt"]: r["state"] for r in self.db.punch_rows(B, "2026-10", "291")}
        self.assertEqual(states[datetime(2026, 10, 7, 11, 53)], "del")
        self.db.punch_edits_clear(B, "291", "2026-10")
        self.assertEqual(self.db.punch_edit_count(B, "2026-10", "291"), 0)

    def test_delete_employee_removes_edits(self):
        self.db.punch_delete(B, "291", datetime(2026, 10, 7, 11, 53))
        self.db.delete_employee(B, "2026-10", "291")
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM punch_edits").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
