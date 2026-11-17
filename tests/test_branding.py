import os, sys, tempfile, unittest
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rmt_hr import APP_NAME, branding, reports
from rmt_hr.db import Database
from rmt_hr.service import compute_all


def mk():
    d = tempfile.mkdtemp()
    return Database(os.path.join(d, "t.db")), d


class Branding(unittest.TestCase):
    def tearDown(self):
        branding._state.update(name=APP_NAME, logo=None)

    def test_default_then_custom_name_persists(self):
        db, d = mk()
        branding.load(db, d)
        self.assertEqual((branding.name(), branding.logo()), (APP_NAME, None))
        branding.set_name(db, "  شركة   النور  للتجارة ")
        self.assertEqual(branding.name(), "شركة النور للتجارة")
        branding._state.update(name=APP_NAME)                       # محاكاة إعادة تشغيل البرنامج
        branding.load(db, d)
        self.assertEqual(branding.name(), "شركة النور للتجارة")
        branding.set_name(db, "   ")                                # فارغ = الافتراضي
        self.assertEqual(branding.name(), APP_NAME)

    def test_logo_set_clear_and_survives_restart(self):
        db, d = mk()
        target = branding.logo_target(d)
        os.makedirs(os.path.dirname(target)); open(target, "wb").write(b"png")
        branding.set_logo(db, d)
        self.assertEqual(branding.logo(), target)
        branding._state.update(logo=None)
        branding.load(db, d)
        self.assertEqual(branding.logo(), target)
        os.remove(target)                                           # الملف اتمسح: يرجع للافتراضي بدون خطأ
        branding.load(db, d)
        self.assertIsNone(branding.logo())
        open(target, "wb").write(b"png"); branding.set_logo(db, d)
        branding.clear_logo(db, d)
        self.assertEqual((branding.logo(), os.path.exists(target)), (None, False))

    def test_reset(self):
        db, d = mk()
        branding.set_name(db, "X")
        branding.reset(db, d)
        self.assertEqual(branding.name(), APP_NAME)

    def test_name_appears_in_voucher_punches_table_and_xlsx(self):
        db, d = mk()
        db.replace_punches("ف", [("5", "هدى", datetime(2026, 10, i, h)) for i in range(1, 10) for h in (8, 17)])
        e = db.get_employee("ف", "2026-10", "5"); e["salary"] = 3100; db.save_employee(e)
        emp, days, s, pay = compute_all(db, "ف", "2026-10")[0]
        branding.set_name(db, "شركة <النور> & أولاده")
        for html in (reports.voucher_html("ف", "2026-10", emp, s, pay),
                     reports.punches_html("ف", "2026-10", emp, days, s),
                     reports.employees_table_html("ف", "2026-10", [(emp, days, s, pay)])):
            self.assertIn("شركة &lt;النور&gt; &amp; أولاده", html)       # اسم مخصص ومُهرَّب
            self.assertNotIn(APP_NAME + " —", html)
        branding.set_name(db, "")
        self.assertIn(APP_NAME, reports.voucher_html("ف", "2026-10", emp, s, pay))

    def test_logo_image_has_no_fixed_height_so_wide_logos_keep_ratio(self):
        db, d = mk()
        db.replace_punches("ف", [("5", "هدى", datetime(2026, 10, 1, 8)), ("5", "هدى", datetime(2026, 10, 1, 17))])
        emp, days, s, pay = compute_all(db, "ف", "2026-10")[0]
        h = reports.voucher_html("ف", "2026-10", emp, s, pay)
        self.assertIn("<img src='logo' width='90'>", h)


if __name__ == "__main__":
    unittest.main()
