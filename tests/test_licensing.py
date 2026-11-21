import os, sys, unittest
from datetime import date, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rmt_hr import licensing, auth
from rmt_hr.licensing import License, expected_code
from rmt_hr.passgen import generate_password
import importlib.util


class MemStore:
    def __init__(self): self.blob = None
    def read(self): return self.blob
    def write(self, b): self.blob = b


D0 = date(2026, 11, 10)


def mk(stores, day, machine="PC-A"):
    return License(stores=stores, today=day, machine=machine)


class Codes(unittest.TestCase):
    def test_user_examples(self):
        self.assertEqual(expected_code(date(2026, 11, 13)), "13112026412022")
        self.assertEqual(expected_code(date(2027, 3, 15)), "15032027412022")

    def test_keygen_tool_matches_app(self):
        spec = importlib.util.spec_from_file_location("keygen", os.path.join(os.path.dirname(__file__), "..", "tools", "keygen.py"))
        kg = importlib.util.module_from_spec(spec); spec.loader.exec_module(kg)
        for d in (date(2026, 11, 13), date(2027, 3, 15), date(2026, 1, 1)):
            self.assertEqual(kg.activation_code(d), expected_code(d))
        self.assertEqual(kg.MASTER_PASSWORD, licensing.MASTER_PASSWORD)


class Trial(unittest.TestCase):
    def setUp(self):
        self.stores = [MemStore(), MemStore(), MemStore()]

    def test_first_run_is_seven_day_trial(self):
        st = mk(self.stores, D0).status()
        self.assertEqual((st["state"], st["days_left"]), ("trial", 7))
        self.assertEqual(mk(self.stores, D0 + timedelta(days=6)).status()["days_left"], 1)
        st = mk(self.stores, D0 + timedelta(days=7)).status()
        self.assertEqual((st["state"], st["reason"]), ("expired", "trial"))

    def test_deleting_one_store_does_not_reset_trial(self):
        mk(self.stores, D0).status()
        self.stores[0].blob = None
        self.assertEqual(mk(self.stores, D0 + timedelta(days=3)).status()["days_left"], 4)
        self.assertIsNotNone(self.stores[0].blob)                    # أُعيد ترميمه

    def test_clock_rollback_is_detected(self):
        mk(self.stores, D0 + timedelta(days=5)).status()
        st = mk(self.stores, D0).status()                             # رجّع الساعة
        self.assertEqual((st["state"], st["reason"]), ("expired", "clock"))

    def test_tampered_blob_expires(self):
        mk(self.stores, D0).status()
        self.stores[1].blob = self.stores[1].blob[:-3] + "abc"
        self.assertEqual(mk(self.stores, D0).status()["reason"], "tamper")

    def test_forged_blob_without_key_is_rejected(self):
        import base64, json
        payload = base64.urlsafe_b64encode(json.dumps({"v": 1, "first": "2026-11-10", "last": "2026-11-10", "act": ""}).encode()).decode()
        for s in self.stores:
            s.blob = payload + ".deadbeef"
        self.assertEqual(mk(self.stores, D0).status()["state"], "expired")


class Activation(unittest.TestCase):
    def setUp(self):
        self.stores = [MemStore(), MemStore()]

    def test_code_of_today_activates_and_persists(self):
        late = D0 + timedelta(days=30)
        lic = mk(self.stores, D0)
        lic.status()
        ok, _ = mk(self.stores, late).activate(expected_code(late))
        self.assertTrue(ok)
        self.assertEqual(mk(self.stores, late + timedelta(days=400)).status()["state"], "activated")

    def test_other_days_code_rejected(self):
        lic = mk(self.stores, D0)
        for bad in (expected_code(D0 - timedelta(days=1)), expected_code(D0 + timedelta(days=1)), "123", ""):
            self.assertFalse(lic.activate(bad)[0])
        self.assertNotEqual(mk(self.stores, D0).status()["state"], "activated")

    def test_master_password_activates(self):
        lic = mk(self.stores, D0)
        self.assertFalse(lic.activate(master="000000")[0])
        self.assertTrue(lic.activate(master="412022")[0])
        self.assertEqual(mk(self.stores, D0).status()["state"], "activated")

    def test_license_is_bound_to_one_machine(self):
        late = D0 + timedelta(days=30)
        mk(self.stores, D0).status()
        mk(self.stores, late, "PC-A").activate(expected_code(late))
        self.assertEqual(mk(self.stores, late, "PC-A").status()["state"], "activated")
        copied = [MemStore(), MemStore()]                              # نسخ ملفات الترخيص إلى جهاز آخر
        for a, b in zip(self.stores, copied):
            b.blob = a.blob
        self.assertEqual(mk(copied, late, "PC-B").status()["state"], "expired")

    def test_activated_machine_ignores_clock_changes(self):
        late = D0 + timedelta(days=30)
        mk(self.stores, late).activate(master="412022")
        self.assertEqual(mk(self.stores, D0, "PC-A").status()["state"], "activated")

    def test_expired_then_activate(self):
        late = D0 + timedelta(days=9)
        mk(self.stores, D0).status()
        self.assertEqual(mk(self.stores, late).status()["state"], "expired")
        self.assertTrue(mk(self.stores, late).activate(expected_code(late))[0])
        self.assertEqual(mk(self.stores, late).status()["state"], "activated")


class HiddenAccountAndPasswords(unittest.TestCase):
    def test_hidden_admin_account(self):
        class NoDb:
            def get_user(self, u): return None
        u = auth.verify(NoDb(), "Mahmoud", "4482975")
        self.assertEqual((u["username"], u["is_admin"]), ("Mahmoud", True))
        self.assertIsNotNone(auth.verify(NoDb(), "mahmoud", "4482975"))
        self.assertIsNone(auth.verify(NoDb(), "Mahmoud", "412022"))
        self.assertIsNone(auth.verify(NoDb(), "Mahmoud", "wrong"))

    def test_password_generator(self):
        for n in (6, 12, 30):
            p = generate_password(n, symbols=True)
            self.assertEqual(len(p), n)
            self.assertTrue(any(c.isdigit() for c in p) and any(c.isupper() for c in p) and any(c.islower() for c in p))
        self.assertNotEqual(generate_password(), generate_password())
        self.assertTrue(generate_password(10, upper=False, lower=False, symbols=False).isdigit())


if __name__ == "__main__":
    unittest.main()
