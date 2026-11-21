import os, sys, tempfile, unittest
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rmt_hr import constants, db as dbmod


def mk(mode):
    constants.BRANCH_MODE = mode
    dbmod.BRANCH_MODE = mode
    return dbmod.Database(os.path.join(tempfile.mkdtemp(), "t.db"))


class Branches(unittest.TestCase):
    def tearDown(self):
        constants.BRANCH_MODE = "fixed"; dbmod.BRANCH_MODE = "fixed"

    def test_fixed_mode_uses_constant_list(self):
        self.assertEqual(mk("fixed").branches(), constants.BRANCHES)

    def test_dynamic_default_add_rename(self):
        db = mk("dynamic")
        self.assertEqual(db.branches(), [constants.DEFAULT_BRANCH_NAME])
        self.assertTrue(db.add_branch("  فرع   جديد ")[0])
        self.assertEqual(db.branches(), [constants.DEFAULT_BRANCH_NAME, "فرع جديد"])
        self.assertFalse(db.add_branch("فرع جديد")[0])
        self.assertFalse(db.add_branch("   ")[0])
        db.replace_punches(constants.DEFAULT_BRANCH_NAME, [("1", "س", datetime(2026, 10, 1, 8, 0)), ("1", "س", datetime(2026, 10, 1, 17, 0))])
        self.assertTrue(db.rename_branch(constants.DEFAULT_BRANCH_NAME, "المقر")[0])
        self.assertEqual(db.branches(), ["المقر", "فرع جديد"])
        self.assertEqual(len(db.punches_of("المقر", "2026-10", "1")), 2)             # البيانات انتقلت للاسم الجديد
        self.assertIsNotNone(db.get_employee("المقر", "2026-10", "1"))
        self.assertEqual(db.punches_of(constants.DEFAULT_BRANCH_NAME, "2026-10", "1"), [])
        self.assertFalse(db.rename_branch("المقر", "فرع جديد")[0])                   # اسم مكرر
        self.assertFalse(db.rename_branch("غير موجود", "x")[0])


if __name__ == "__main__":
    unittest.main()
