import os, sys, unittest
from datetime import datetime, date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rmt_hr.attendance import build_days, detect_mode, summarize


def dt(d, hm):
    return datetime(2026, 10, d, int(hm[:2]), int(hm[3:]))


class NightShift(unittest.TestCase):
    def test_user_example_auto(self):
        # دخول 1 الساعة 18:00 - خروج 2 الساعة 04:00 - دخول 2 الساعة 18:00 - خروج 3 الساعة 04:00
        ps = [dt(1, "18:00"), dt(2, "04:00"), dt(2, "18:00"), dt(3, "04:00")]
        self.assertEqual(detect_mode(ps), "night")
        days = build_days(ps)
        self.assertEqual(sorted(days), [date(2026, 10, 1), date(2026, 10, 2)])
        self.assertAlmostEqual(days[date(2026, 10, 1)].hours, 10)
        self.assertEqual(days[date(2026, 10, 1)].in_dt, dt(1, "18:00"))
        self.assertEqual(days[date(2026, 10, 1)].out_dt, dt(2, "04:00"))
        self.assertAlmostEqual(days[date(2026, 10, 2)].hours, 10)

    def test_20_to_11(self):
        days = build_days([dt(5, "20:00"), dt(6, "11:00")], "night")
        self.assertAlmostEqual(days[date(2026, 10, 5)].hours, 15)

    def test_duplicates_and_orphan_first_morning(self):
        ps = [dt(1, "03:50"),                      # خروج شيفت الشهر السابق: يُهمل
              dt(1, "18:00"), dt(1, "18:02"),      # تكرار دخول
              dt(2, "03:00"), dt(2, "04:05"),      # آخر بصمة صباحية هي الخروج
              dt(2, "18:10")]                      # دخول بدون خروج
        days = build_days(ps, "night")
        self.assertEqual(sorted(days), [date(2026, 10, 1), date(2026, 10, 2)])
        self.assertEqual(days[date(2026, 10, 1)].in_dt, dt(1, "18:00"))
        self.assertEqual(days[date(2026, 10, 1)].out_dt, dt(2, "04:05"))
        self.assertIsNone(days[date(2026, 10, 2)].out_dt)
        self.assertIn("بصمة ناقصة", days[date(2026, 10, 2)].note)

    def test_month_summary_counts_each_shift_once(self):
        ps = []
        for d in range(1, 11):
            ps += [dt(d, "18:00"), dt(d + 1, "04:00")] if d < 10 else [dt(d, "18:00"), dt(11, "04:00")]
        s = summarize(build_days(ps), "2026-10", 10, 20)
        self.assertEqual(s.present, 10)
        self.assertAlmostEqual(s.total_hours, 100)
        self.assertAlmostEqual(s.ot_hours, 0)

    def test_day_worker_unchanged(self):
        ps = [dt(1, "08:00"), dt(1, "18:00"), dt(2, "08:30"), dt(2, "17:30")]
        self.assertEqual(detect_mode(ps), "day")
        days = build_days(ps)
        self.assertAlmostEqual(days[date(2026, 10, 1)].hours, 10)
        self.assertAlmostEqual(days[date(2026, 10, 2)].hours, 9)

    def test_day_worker_single_late_punch_not_night(self):
        ps = [dt(1, "08:00"), dt(1, "18:00"), dt(2, "00:30"), dt(2, "08:00"), dt(2, "18:00"),
              dt(3, "08:00"), dt(3, "18:00"), dt(4, "08:00"), dt(4, "18:00")]
        self.assertEqual(detect_mode(ps), "day")


if __name__ == "__main__":
    unittest.main()


class MixedShifts(unittest.TestCase):
    def _mixed(self):
        ps = []
        for d in range(1, 11):                       # 1-10 صباحي 08:00 - 18:00
            ps += [dt(d, "08:00"), dt(d, "18:00")]
        for d in range(11, 21):                      # 11-20 مسائي 18:00 - 04:00
            ps += [dt(d, "18:00"), dt(d + 1, "04:00")]
        return ps

    def test_day_to_night_change(self):
        days = build_days(self._mixed())             # auto
        self.assertEqual(sorted(days)[0], date(2026, 10, 1))
        for d in range(1, 11):
            self.assertEqual(days[date(2026, 10, d)].shift, "day")
            self.assertAlmostEqual(days[date(2026, 10, d)].hours, 10)
        for d in range(11, 21):
            self.assertEqual(days[date(2026, 10, d)].shift, "night")
            self.assertAlmostEqual(days[date(2026, 10, d)].hours, 10)
        self.assertEqual(days[date(2026, 10, 11)].change, "⇄ تحوّل إلى مسائي")
        self.assertEqual(days[date(2026, 10, 12)].change, "")
        self.assertEqual(days[date(2026, 10, 5)].change, "")
        self.assertNotIn(date(2026, 10, 21), days)   # بصمة 04:00 ليست يوماً جديداً

    def test_night_to_day_change(self):
        ps = []
        for d in range(1, 6):
            ps += [dt(d, "18:00"), dt(d + 1, "04:00")]
        for d in range(8, 12):
            ps += [dt(d, "08:00"), dt(d, "18:00")]
        days = build_days(ps)
        self.assertEqual(days[date(2026, 10, 5)].shift, "night")
        self.assertNotIn(date(2026, 10, 6), days)
        self.assertEqual(days[date(2026, 10, 8)].shift, "day")
        self.assertEqual(days[date(2026, 10, 8)].change, "⇄ تحوّل إلى صباحي")
        self.assertAlmostEqual(days[date(2026, 10, 8)].hours, 10)

    def test_summary_counts_and_labels(self):
        s = summarize(build_days(self._mixed()), "2026-10", 10, 20)
        self.assertEqual((s.in_punches, s.out_punches, s.missing_punches), (20, 20, 0))
        self.assertEqual((s.day_shifts, s.night_shifts), (10, 10))
        self.assertEqual(s.shift_label, "متغيّر (الآن مسائي)")
        d = summarize(build_days([dt(1, "08:00"), dt(1, "18:00")]), "2026-10", 10, 20)
        self.assertEqual(d.shift_label, "صباحي")

    def test_pure_night_label_and_last_shift_without_out(self):
        ps = [dt(1, "18:00"), dt(2, "04:00"), dt(2, "18:00"), dt(3, "04:00"), dt(3, "18:00")]
        s = summarize(build_days(ps), "2026-10", 10, 20)
        self.assertEqual(s.shift_label, "مسائي")
        self.assertEqual((s.in_punches, s.out_punches, s.missing_punches), (3, 2, 1))

    def test_missing_in_punch_midmonth(self):
        # نسي يبصم دخول يوم 2 لكن بصم خروجه صباح 3
        ps = [dt(1, "18:00"), dt(2, "04:00"), dt(3, "04:30"), dt(3, "18:00"), dt(4, "04:00"),
              dt(4, "18:00"), dt(5, "04:00")]
        days = build_days(ps, "night")
        self.assertIsNone(days[date(2026, 10, 2)].in_dt)
        self.assertEqual(days[date(2026, 10, 2)].out_dt, dt(3, "04:30"))
        self.assertIn("بصمة دخول ناقصة", days[date(2026, 10, 2)].note)
        s = summarize(days, "2026-10", 10, 20)
        self.assertEqual((s.in_punches, s.out_punches, s.missing_punches), (3, 4, 1))

    def test_explicit_modes_have_single_shift(self):
        d = build_days(self._mixed(), "day")
        self.assertTrue(all(r.shift == "day" and not r.change for r in d.values()))
