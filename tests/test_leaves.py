import os, sys, tempfile, unittest
from datetime import datetime, date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rmt_hr.attendance import build_days
from rmt_hr.db import Database
from rmt_hr.leaves import build_plan, month_dates
from rmt_hr.service import compute_all, compute_employee, ledger
from rmt_hr import reports

B, YM = "ف", "2026-10"


def D(d, m=10):
    return date(2026, m, d)


def day_shift_days(day_list, m=10):
    ps = []
    for d in day_list:
        ps += [datetime(2026, m, d, 8), datetime(2026, m, d, 17)]
    return build_days(ps)


def mkdb(present_days=range(1, 21), salary=3100):
    db = Database(os.path.join(tempfile.mkdtemp(), "t.db"))
    db.replace_punches(B, [("5", "هدى", datetime(2026, 10, d, h)) for d in present_days for h in (8, 17)])
    e = db.get_employee(B, YM, "5"); e["salary"] = salary; db.save_employee(e)
    return db


def calc(db):
    emp, days, s, pay = compute_all(db, B, YM)[0]
    return emp, days, s, pay


class PlanLogic(unittest.TestCase):
    def test_default_matches_legacy_counts(self):
        days = day_shift_days(range(1, 21))                         # 20 حضور → راحة 3
        plan = build_plan(YM, days, allowed_rest=3, legacy_leave=2)
        self.assertEqual(plan.counts, {"rest": 3, "annual": 0, "unpaid": 0, "leave": 2, "absent": 6, "comp": 0})
        self.assertEqual(20 + sum(plan.counts.values()), 31)         # المجموع = أيام الشهر

    def test_explicit_choices_and_total_always_equals_month(self):
        days = day_shift_days(range(1, 21))
        ex = {D(21): "annual", D(22): "annual", D(23): "unpaid", D(24): "absent", D(25): "comp", D(5): "annual"}  # 5 حضور = يُتجاهل
        plan = build_plan(YM, days, 3, 0, explicit=ex)
        self.assertEqual((plan.counts["annual"], plan.counts["unpaid"], plan.counts["comp"]), (2, 1, 1))
        self.assertNotIn(D(5), plan.statuses)
        self.assertEqual(20 + sum(plan.counts.values()), 31)
        self.assertEqual(plan.dates_of("annual"), [D(21), D(22)])

    def test_explicit_rest_reduces_auto_rest_and_excess_is_reported(self):
        days = day_shift_days(range(1, 13))                          # 12 حضور → المستحق 2
        ex = {D(13): "rest", D(14): "rest", D(15): "rest", D(16): "rest"}
        plan = build_plan(YM, days, 2, 0, explicit=ex)
        self.assertEqual(plan.counts["rest"], 4)
        self.assertEqual(plan.rest_excess, 2)                        # زيادة عن المسموح
        plan2 = build_plan(YM, days, 2, 0, explicit={D(13): "rest"})
        self.assertEqual((plan2.counts["rest"], plan2.rest_excess), (2, 0))   # الباقي يُكمل تلقائياً

    def test_holidays_worked_vs_not_worked(self):
        days = day_shift_days([7])                                   # اشتغل 7 فقط
        hol = [{"day": D(7), "name": "عيد", "mult": 1.5}, {"day": D(25), "name": "ثورة", "mult": 2.0}]
        plan = build_plan(YM, days, 0, 0, holidays=hol, explicit={D(25): "annual"})
        self.assertEqual(plan.holiday_pay_days, 1.5)                 # 25 إجازة = لا مقابل
        self.assertEqual([r["worked"] for r in plan.holidays], [True, False])
        plan = build_plan(YM, days, 0, 0, holidays=hol, choices={D(7): "comp"})
        self.assertEqual((plan.holiday_pay_days, plan.comp_credit), (0.0, 1.0))
        plan = build_plan(YM, days, 0, 0, holidays=[{"day": D(7), "name": "", "mult": 0}])
        self.assertEqual(plan.holiday_pay_days, 0.0)                 # «لا يحتسب»


class PayWithStatuses(unittest.TestCase):
    def test_pay_effects(self):
        db = mkdb()                                                  # راتب 3100 → اليوم 100
        base = calc(db)[3]
        self.assertEqual((base["rest_n"], base["absent"], base["net"]), (3, 8, 2300.0))
        for day, st in ((21, "annual"), (22, "annual"), (23, "comp"), (24, "unpaid"), (25, "absent")):
            db.set_day_status(B, "5", D(day), st)
        p = calc(db)[3]
        # سنوية×2 + خصم رصيد×1 لا يخصمان؛ بدون أجر×1 وغياب يخصمان. الراحة المستحقة (3) تتوزع تلقائياً
        # على أول أيام غير محددة (26-28) والباقي 29-31 غياب + يوم 25 المختار = 4 غياب
        self.assertEqual((p["annual"], p["comp_days"], p["unpaid"], p["absent"], p["rest_n"]), (2, 1, 1, 4, 3))
        self.assertEqual(p["absence_ded"], 400.0)
        self.assertEqual(p["leave_ded"], 100.0)                      # بدون أجر دائماً تُخصم
        self.assertEqual(p["net"], 3100 - 400 - 100)
        self.assertEqual(20 + p["rest_n"] + p["annual"] + p["leave"] + p["absent"] + p["comp_days"], 31)
        db.set_day_status(B, "5", D(21), None)                       # رجوع للتلقائي
        self.assertEqual(calc(db)[3]["annual"], 1)

    def test_legacy_leave_counter_still_works(self):
        db = mkdb()
        e = db.get_employee(B, YM, "5"); e["leave_days"] = 3; e["leave_paid"] = 1; db.save_employee(e)
        p = calc(db)[3]
        self.assertEqual((p["leave"], p["absent"], p["leave_ded"]), (3, 5, 0.0))     # مدفوعة كما كانت
        e["leave_paid"] = 0; db.save_employee(e)
        self.assertEqual(calc(db)[3]["leave_ded"], 300.0)

    def test_holiday_pay_added_and_choice_to_comp(self):
        db = mkdb()
        db.set_holiday(B, D(7), "عيد", 1.5)
        db.set_holiday(B, D(25), "ثورة", 2.0)                        # 25 غياب → لا مقابل
        p = calc(db)[3]
        self.assertEqual((p["holiday_pay_days"], p["holiday_pay"]), (1.5, 150.0))
        self.assertEqual(p["net"], 2300 + 150)
        db.set_holiday_choice(B, "5", D(7), "comp")                  # إلغاء الأجر مقابل بدل إجازة
        p = calc(db)[3]
        self.assertEqual((p["holiday_pay"], p["comp_credit"], p["net"]), (0.0, 1.0, 2300.0))
        db.set_holiday_choice(B, "5", D(7), "pay")
        self.assertEqual(calc(db)[3]["holiday_pay"], 150.0)
        db.delete_holiday(B, D(7))
        self.assertEqual(calc(db)[3]["holiday_pay"], 0.0)

    def test_holidays_are_per_month(self):
        db = mkdb()
        db.set_holiday(B, D(7), "a", 1); db.set_holiday(B, date(2026, 11, 7), "b", 1)
        self.assertEqual([h["name"] for h in db.holidays_of(B, YM)], ["a"])


class LedgerTests(unittest.TestCase):
    def test_annual_balance_and_year_dates_across_months(self):
        db = Database(os.path.join(tempfile.mkdtemp(), "t.db"))
        items = [("5", "هدى", datetime(2026, m, d, h)) for m in (9, 10) for d in range(1, 21) for h in (8, 17)]
        db.replace_punches(B, items)
        db.set_day_status(B, "5", date(2026, 9, 25), "annual")
        db.set_day_status(B, "5", D(22), "annual")
        db.set_day_status(B, "5", D(24), "unpaid")
        db.set_day_status(B, "5", D(26), "unpaid")
        led = ledger(db, B, "5", YM)
        self.assertEqual((led["entitlement"], led["annual_used"], led["annual_left"]), (21.0, 2, 19.0))
        self.assertEqual(led["year_dates"]["annual"], [date(2026, 9, 25), D(22)])
        self.assertEqual(led["month_dates"]["annual"], [D(22)])
        self.assertEqual(led["year_dates"]["unpaid"], [D(24), D(26)])
        db.master_upsert(B, "5", annual_days=15)                     # الرصيد قابل للتعديل
        self.assertEqual(ledger(db, B, "5", YM)["annual_left"], 13.0)
        self.assertEqual(ledger(db, B, "5", "2026-09")["annual_used"], 1)   # حتى الشهر المحدد فقط

    def test_year_resets_in_new_year(self):
        db = Database(os.path.join(tempfile.mkdtemp(), "t.db"))
        db.replace_punches(B, [("5", "هدى", datetime(2026, 12, d, h)) for d in range(1, 10) for h in (8, 17)]
                              + [("5", "هدى", datetime(2027, 1, d, h)) for d in range(1, 10) for h in (8, 17)])
        db.set_day_status(B, "5", date(2026, 12, 20), "annual")
        self.assertEqual(ledger(db, B, "5", "2027-01")["annual_used"], 0)

    def test_comp_balance_accumulates_and_is_debited(self):
        db = Database(os.path.join(tempfile.mkdtemp(), "t.db"))
        items = [("5", "هدى", datetime(2026, m, d, h)) for m in (9, 10) for d in range(1, 21) for h in (8, 17)]
        db.replace_punches(B, items)
        db.set_holiday(B, date(2026, 9, 7), "عيد", 1.0)
        db.set_holiday_choice(B, "5", date(2026, 9, 7), "comp")           # +1 بدل إجازة
        e = db.get_employee(B, "2026-09", "5"); e["comp_added"] = 2; db.save_employee(e)   # +2 يدوي
        db.set_day_status(B, "5", D(23), "comp")                           # -1 خصم من الرصيد (أكتوبر)
        self.assertEqual(ledger(db, B, "5", "2026-09")["comp_balance"], 3.0)
        self.assertEqual(ledger(db, B, "5", YM)["comp_balance"], 2.0)

    def test_voucher_shows_new_rows(self):
        db = mkdb()
        db.set_day_status(B, "5", D(21), "annual"); db.set_holiday(B, D(7), "عيد", 2.0)
        emp, days, s, pay = calc(db)
        h = reports.voucher_html(B, YM, emp, s, pay, ledger=ledger(db, B, "5", YM))
        for txt in ("إجازة سنوية", "رصيد الإجازة السنوية المتبقي (من 21 يوم)", "رصيد بدلات الإجازة", "أجر العمل في الأجازات الرسمية (2 يوم)"):
            self.assertIn(txt, h)
        ph = reports.punches_html(B, YM, emp, days, s, plan=pay["plan"])
        self.assertIn("إجازة سنوية", ph)

    def test_delete_employee_clears_statuses(self):
        db = mkdb()
        db.set_day_status(B, "5", D(21), "annual"); db.set_holiday_choice(B, "5", D(7), "comp")
        db.delete_employee(B, YM, "5")
        self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM day_status").fetchone()[0], 0)
        self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM holiday_choice").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
