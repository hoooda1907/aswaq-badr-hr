import os, sys, tempfile, unittest
from datetime import datetime, date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from openpyxl import Workbook
from rmt_hr.attendance import build_days, summarize
from rmt_hr.db import Database
from rmt_hr.excel_reader import read_table, extract_punches_dir, detect_direction_col, dir_of
from rmt_hr.service import compute_all


def t(d, hm, m=10):
    return datetime(2026, m, d, int(hm[:2]), int(hm[3:]))


def P(*items):
    """P((1,'18:00','I'), ...) -> [(datetime, kind)]"""
    return [(t(d, hm), k) for d, hm, k in items]


class Directional(unittest.TestCase):
    def test_user_example_mon_tue_wed_thu(self):
        # دخول الإثنين 18:00 خروج الثلاثاء 04:00، دخول الأربعاء 18:00 خروج الخميس 04:00
        days = build_days(P((5, "18:00", "I"), (6, "04:00", "O"), (7, "18:00", "I"), (8, "04:00", "O")))
        self.assertEqual(sorted(days), [date(2026, 10, 5), date(2026, 10, 7)])
        self.assertNotIn(date(2026, 10, 6), days)                       # الثلاثاء راحة/غياب
        self.assertAlmostEqual(days[date(2026, 10, 5)].hours, 10)
        self.assertEqual(days[date(2026, 10, 5)].shift, "night")

    def test_orphan_morning_punch_means_day_off(self):
        # دخول 10 مساءً وخروج 11 صباحاً، لا دخول يوم 11، وبصمة يوم 12 الساعة 04:00 (يتيمة)
        days = build_days(P((10, "18:00", "I"), (11, "04:00", "O"), (12, "04:00", "O")))
        self.assertEqual(sorted(days), [date(2026, 10, 10)])
        self.assertEqual(list(days.orphans), [date(2026, 10, 11)])       # اليوم المعتبر راحة
        self.assertEqual(days.orphans[date(2026, 10, 11)], [t(12, "04:00")])
        s = summarize(days, "2026-10", 10, 20)
        self.assertEqual((s.present, s.missing_punches), (1, 0))         # لا تُحسب بصمة ناقصة

    def test_wrong_device_direction_is_corrected_by_time(self):
        # الجهاز سجّل «حضور» للبصمتين (حالة موظف 342 يوم 13/14)
        days = build_days(P((13, "20:47", "I"), (14, "03:42", "I"), (14, "20:56", "I"), (15, "03:58", "O")))
        self.assertEqual(sorted(days), [date(2026, 10, 13), date(2026, 10, 14)])
        self.assertEqual(days[date(2026, 10, 13)].out_dt, t(14, "03:42"))

    def test_changing_shift_with_morning_in_punches(self):
        # موظف 291: حضور 18:14 وانصراف 03:31، ثم حضور 11:53 وانصراف 03:34 (لا يُحسب 17.6 ساعة)
        days = build_days(P((6, "18:14", "I"), (7, "03:31", "O"), (7, "11:53", "I"), (8, "03:34", "O"),
                            (8, "11:23", "I"), (8, "18:41", "O")))
        self.assertAlmostEqual(days[date(2026, 10, 6)].hours, 9.28, places=1)
        self.assertEqual(days[date(2026, 10, 7)].in_dt, t(7, "11:53"))
        # يوم 8 فيه شيفت صباحي بعد خروج المسائي: يُحسب كيوم مستقل بدون فقد بصماته
        self.assertEqual(days[date(2026, 10, 8)].in_dt, t(8, "11:23"))
        self.assertEqual(days[date(2026, 10, 8)].shift, "day")
        self.assertEqual(days[date(2026, 10, 8)].change, "⇄ تحوّل إلى صباحي")

    def test_day_worker_double_in_flag_is_still_complete(self):
        days = build_days(P((1, "08:57", "I"), (1, "19:03", "I"), (2, "09:47", "I"), (2, "18:37", "O")))
        self.assertEqual((days[date(2026, 10, 1)].in_dt, days[date(2026, 10, 1)].out_dt), (t(1, "08:57"), t(1, "19:03")))
        self.assertTrue(all(d.shift == "day" for d in days.values()))

    def test_evening_out_flagged_wrongly_is_in(self):
        # 327 يوم 23: بصمة 17:12 اتسجلت انصراف وهي حضور
        days = build_days(P((22, "19:01", "I"), (23, "03:45", "O"), (23, "17:12", "O"), (24, "03:29", "O")))
        self.assertEqual(days[date(2026, 10, 23)].in_dt, t(23, "17:12"))
        self.assertEqual(days[date(2026, 10, 23)].out_dt, t(24, "03:29"))

    def test_duplicates_are_merged(self):
        days = build_days(P((1, "20:01", "I"), (1, "20:03", "I"), (2, "03:54", "O"), (2, "03:55", "O"), (2, "03:55", "I")))
        self.assertEqual(sorted(days), [date(2026, 10, 1)])
        self.assertEqual(days[date(2026, 10, 1)].out_dt, t(2, "03:54"))

    def test_first_morning_punch_of_data_is_not_a_warning(self):
        days = build_days(P((1, "03:54", "O"), (1, "20:01", "I"), (2, "04:06", "O")))
        self.assertEqual(days.orphans, {})
        self.assertEqual(sorted(days), [date(2026, 10, 1)])

    def test_last_shift_without_out_counts_as_missing(self):
        days = build_days(P((30, "20:00", "I"), (31, "03:30", "O"), (31, "22:38", "I")))
        s = summarize(days, "2026-10", 10, 20)
        self.assertEqual((s.in_punches, s.out_punches, s.missing_punches), (2, 1, 1))
        self.assertEqual(days[date(2026, 10, 31)].shift, "night")

    def test_forced_modes_ignore_direction(self):
        ps = P((1, "08:00", "I"), (1, "18:00", "O"))
        self.assertAlmostEqual(build_days(ps, "day")[date(2026, 10, 1)].hours, 10)

    def test_no_direction_falls_back_to_old_rule(self):
        # بدون اتجاه: نفس قاعدة الأوقات القديمة (مسائي بوجود بصمات بعد منتصف الليل)
        plain = [t(1, "18:00"), t(2, "04:00"), t(2, "18:00"), t(3, "04:00")]
        days = build_days(plain)
        self.assertEqual(sorted(days), [date(2026, 10, 1), date(2026, 10, 2)])
        self.assertAlmostEqual(days[date(2026, 10, 1)].hours, 10)
        day = build_days([t(1, "08:00"), t(1, "18:00"), t(2, "08:30"), t(2, "17:30")])
        self.assertAlmostEqual(day[date(2026, 10, 2)].hours, 9)

    def test_same_day_two_shifts_hours_are_summed(self):
        # صباحي 09:00-14:00 ثم مسائي 18:00 → 03:00 في نفس اليوم
        days = build_days(P((5, "09:00", "I"), (5, "14:00", "O"), (5, "18:00", "I"), (6, "03:00", "O")))
        self.assertAlmostEqual(days[date(2026, 10, 5)].hours, 14.0)
        self.assertIn("شيفت إضافي", days[date(2026, 10, 5)].note)


def sheet(rows, path=None):
    wb = Workbook(); ws = wb.active
    for r in rows:
        ws.append(r)
    p = path or os.path.join(tempfile.mkdtemp(), "p.xlsx"); wb.save(p)
    return read_table(p)


class DirectionColumn(unittest.TestCase):
    DATA = [(121, "أحمد", datetime(2026, 10, 1, 8, 0), "حضور"), (121, "أحمد", datetime(2026, 10, 1, 17, 0), "إنصراف"),
            (121, "أحمد", datetime(2026, 10, 2, 8, 5), "حضور"), (121, "أحمد", datetime(2026, 10, 2, 17, 5), "إنصراف"),
            (7, "منى", datetime(2026, 10, 1, 9, 0), "حضور"), (7, "منى", datetime(2026, 10, 1, 18, 0), "إنصراف")]

    def test_column_found_at_any_position(self):
        # الاتجاه في العمود الأخير / الأول / وسط أعمدة أخرى
        layouts = [lambda c, n, d, k: [c, n, d, k], lambda c, n, d, k: [k, c, n, d],
                   lambda c, n, d, k: [c, "", n, k, "x", d, ""]]
        for lay in layouts:
            rows = sheet([lay("الكود", "الاسم", "الميعاد", "نوع الحركة")] + [lay(*r) for r in self.DATA])
            out, cols = extract_punches_dir(rows)
            self.assertIsNotNone(cols[3])
            self.assertEqual(sorted({o[3] for o in out}), ["I", "O"])
            self.assertEqual(len(out), 6)
            self.assertEqual({o[0] for o in out}, {"121", "7"})

    def test_english_in_out_and_zk_numbers(self):
        rows = sheet([["ID", "Name", "Time", "State"]] + [(r[0], r[1], r[2], "C/In" if r[3] == "حضور" else "C/Out") for r in self.DATA])
        self.assertEqual(extract_punches_dir(rows)[1][3], 3)
        rows = sheet([["ID", "Name", "Time", "Status"]] + [(r[0], r[1], r[2], 0 if r[3] == "حضور" else 1) for r in self.DATA])
        out, cols = extract_punches_dir(rows)
        self.assertEqual(cols[3], 3)
        self.assertEqual(sorted({o[3] for o in out}), ["I", "O"])

    def test_missing_direction_column_continues_without_it(self):
        rows = sheet([["الكود", "الاسم", "الميعاد"]] + [r[:3] for r in self.DATA])
        out, cols = extract_punches_dir(rows)
        self.assertIsNone(cols[3])
        self.assertEqual({o[3] for o in out}, {""})

    def test_single_value_column_is_not_direction(self):
        rows = sheet([["الكود", "الاسم", "الميعاد", "نوع"]] + [r[:3] + ("حضور",) for r in self.DATA])
        self.assertIsNone(extract_punches_dir(rows)[1][3])

    def test_dir_of(self):
        self.assertEqual((dir_of("إنصراف"), dir_of("حضور"), dir_of(" In "), dir_of("OUT"), dir_of("بداية إضافي")),
                         ("O", "I", "I", "O", None))


class DbRoundTrip(unittest.TestCase):
    def test_kinds_stored_merged_and_used(self):
        db = Database(os.path.join(tempfile.mkdtemp(), "t.db"))
        items = [("5", "هدى", t(5, "18:00"), "I"), ("5", "هدى", t(6, "03:50"), "O"),
                 ("5", "هدى", t(6, "03:50"), "I"), ("5", "هدى", t(6, "03:50"), "I"),          # نفس البصمة باتجاهين = تعارض
                 ("5", "هدى", t(7, "18:10"), "I"), ("5", "هدى", t(8, "04:00"), "O")]
        db.replace_punches("ف", items)
        got = dict(db.punches_of("ف", "2026-10", "5", with_kind=True))
        self.assertEqual(got[t(6, "03:50")], "IO")
        self.assertEqual(len(got), 4)
        e = db.get_employee("ف", "2026-10", "5"); e["salary"] = 3100; db.save_employee(e)
        emp, days, s, pay = compute_all(db, "ف", "2026-10")[0]
        self.assertEqual(sorted(days), [date(2026, 10, 5), date(2026, 10, 7)])
        self.assertEqual((s.in_punches, s.out_punches, s.missing_punches), (2, 2, 0))

    def test_old_three_tuple_items_still_work(self):
        db = Database(os.path.join(tempfile.mkdtemp(), "t.db"))
        db.replace_punches("ف", [("1", "س", t(1, "08:00")), ("1", "س", t(1, "17:00"))])
        self.assertEqual(len(db.punches_of("ف", "2026-10", "1")), 2)

    def test_old_punches_table_is_migrated(self):
        import sqlite3
        path = os.path.join(tempfile.mkdtemp(), "old.db")
        c = sqlite3.connect(path)
        c.executescript("CREATE TABLE punches(branch TEXT, ym TEXT, code TEXT, ts TEXT);"
                        "INSERT INTO punches VALUES('b','2026-10','1','2026-10-01 08:00');")
        c.commit(); c.close()
        db = Database(path)
        self.assertEqual(db.punches_of("b", "2026-10", "1", with_kind=True), [(t(1, "08:00"), "")])


REAL = "/mnt/user-data/uploads/بصمة_شهر_10_حركات_الدخول_والخروج.xls"


@unittest.skipUnless(os.path.exists(REAL), "شيت البصمة الحقيقي غير موجود")
class RealSheet(unittest.TestCase):
    def test_real_sheet_numbers(self):
        db = Database(os.path.join(tempfile.mkdtemp(), "t.db"))
        out, cols = extract_punches_dir(read_table(REAL))
        self.assertEqual(cols[3], 4)
        db.replace_punches("ف", out)
        res = {e["code"]: (days, s) for e, days, s, _ in compute_all(db, "ف", "2026-10")}
        self.assertEqual(res["342"][1].missing_punches, 1)       # كانت 3
        self.assertEqual(res["327"][1].missing_punches, 1)       # كانت 3
        self.assertEqual(res["291"][1].missing_punches, 1)       # كانت 4
        self.assertEqual((res["110"][1].present, res["110"][1].missing_punches), (27, 5))   # النهاري كما كان
        self.assertEqual((res["306"][1].present, res["306"][1].missing_punches), (27, 2))
        d291 = res["291"][0]
        self.assertAlmostEqual(d291[date(2026, 10, 6)].hours, 9.28, places=1)               # كانت 17.6


if __name__ == "__main__":
    unittest.main()
