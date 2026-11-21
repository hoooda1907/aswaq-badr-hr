"""الحماية: نسخة تجريبية لمدة أسبوع، ثم تفعيل بكود مرتبط بتاريخ اليوم ومقيّد بجهاز واحد.

كود التفعيل = تاريخ يوم الإصدار (يوم شهر سنة) + 412022   مثال: 13 نوفمبر 2026 ← 13112026412022
كلمة السر الرئيسية 412022 تفعّل البرنامج لو فشل التفعيل بالكود.
بعد التفعيل يُحفظ توقيع مرتبط ببصمة الجهاز، فلا يعمل ملف الترخيص لو نُسخ إلى جهاز آخر.
الحالة تُحفظ في أكثر من مكان (ملف البيانات + ملف في AppData المحلي + سجل ويندوز + قاعدة البيانات) وموقَّعة بـ HMAC؛
ويُكتشف التلاعب بها وإرجاع ساعة الجهاز للوراء."""
import base64
import hashlib
import hmac
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta

from . import APP_ID

TRIAL_DAYS = 7
CODE_SUFFIX = "412022"
MASTER_PASSWORD = "412022"

_KEY = hashlib.sha256(("lic|%s|k9#Xv2!pQ7" % APP_ID).encode()).digest()


def expected_code(d=None):
    """كود التفعيل لتاريخ معيّن (الافتراضي اليوم)."""
    return (d or date.today()).strftime("%d%m%Y") + CODE_SUFFIX


def _sign(text):
    return hmac.new(_KEY, text.encode("utf-8"), hashlib.sha256).hexdigest()


def machine_id():
    """بصمة الجهاز: MachineGuid في ويندوز، وإلا عنوان MAC."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                            0, winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)) as k:
            return str(winreg.QueryValueEx(k, "MachineGuid")[0])
    except Exception:
        return "mac-%012x" % uuid.getnode()


def machine_token(mid=None):
    return _sign("machine|" + (mid or machine_id()))


def machine_short(mid=None):
    return hashlib.sha256((mid or machine_id()).encode()).hexdigest()[:12].upper()


# ------------------------------------------------------------------ التخزين
def _encode(rec):
    payload = base64.urlsafe_b64encode(json.dumps(rec, sort_keys=True).encode()).decode()
    return payload + "." + _sign(payload)


def _decode(blob):
    """يرجع dict أو None لو التوقيع غير صحيح."""
    try:
        payload, sig = blob.strip().rsplit(".", 1)
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        rec = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        datetime.strptime(rec["first"], "%Y-%m-%d")
        datetime.strptime(rec["last"], "%Y-%m-%d")
        return rec
    except Exception:
        return None


class _FileStore:
    def __init__(self, path):
        self.path = path

    def read(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None

    def write(self, blob):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(blob)


class _RegStore:
    path = r"Software\%s" % APP_ID

    def read(self):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.path, 0, winreg.KEY_READ) as k:
                return winreg.QueryValueEx(k, "lic")[0]
        except Exception:
            return None

    def write(self, blob):
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.path) as k:
            winreg.SetValueEx(k, "lic", 0, winreg.REG_SZ, blob)


class _DbStore:
    def __init__(self, db):
        self.db = db

    def read(self):
        return self.db.get_setting("lic")

    def write(self, blob):
        self.db.set_setting("lic", blob)


class License:
    def __init__(self, db=None, data_dir=None, today=None, machine=None, stores=None):
        self._today = today
        self._mid = machine
        if stores is not None:
            self.stores = stores
            return
        self.stores = []
        if data_dir:
            self.stores.append(_FileStore(os.path.join(data_dir, "lic.dat")))
        local = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
        self.stores.append(_FileStore(os.path.join(local, APP_ID, "sys.cfg")))
        if sys.platform.startswith("win"):
            self.stores.append(_RegStore())
        if db is not None:
            self.stores.append(_DbStore(db))

    @property
    def today(self):
        return self._today or date.today()

    def _token(self):
        return machine_token(self._mid)

    def _load(self):
        recs, tampered = [], False
        for st in self.stores:
            try:
                blob = st.read()
            except Exception:
                blob = None
            if not blob:
                continue
            rec = _decode(blob)
            if rec is None:
                tampered = True
            else:
                recs.append(rec)
        return recs, tampered

    def _save(self, rec):
        blob = _encode(rec)
        for st in self.stores:
            try:
                st.write(blob)
            except Exception:
                pass

    def status(self):
        """{'state': 'activated'|'trial'|'expired', 'days_left': int, 'reason': str}"""
        today = self.today
        recs, tampered = self._load()
        token = self._token()
        if any(r.get("act") == token for r in recs):
            first = min(r["first"] for r in recs)
            self._save({"v": 1, "first": first, "last": max(today.isoformat(), max(r["last"] for r in recs)),
                        "act": token})
            return {"state": "activated", "days_left": 0, "reason": ""}
        if not recs:
            if tampered:
                return {"state": "expired", "days_left": 0, "reason": "tamper"}
            self._save({"v": 1, "first": today.isoformat(), "last": today.isoformat(), "act": ""})
            return {"state": "trial", "days_left": TRIAL_DAYS, "reason": ""}
        first = datetime.strptime(min(r["first"] for r in recs), "%Y-%m-%d").date()
        last = datetime.strptime(max(r["last"] for r in recs), "%Y-%m-%d").date()
        if tampered:
            return {"state": "expired", "days_left": 0, "reason": "tamper"}
        if today < last - timedelta(days=1):
            return {"state": "expired", "days_left": 0, "reason": "clock"}
        used = (today - first).days
        self._save({"v": 1, "first": first.isoformat(), "last": max(today, last).isoformat(), "act": ""})
        if used >= TRIAL_DAYS:
            return {"state": "expired", "days_left": 0, "reason": "trial"}
        return {"state": "trial", "days_left": TRIAL_DAYS - used, "reason": ""}

    def activate(self, code="", master=""):
        """يرجع (نجح؟، رسالة). الكود يجب أن يطابق تاريخ اليوم؛ كلمة السر الرئيسية بديل عند فشل الكود."""
        code, master = (code or "").strip(), (master or "").strip()
        ok = False
        if code and hmac.compare_digest(code, expected_code(self.today)):
            ok = True
        elif master and hmac.compare_digest(_sign("master|" + master), _sign("master|" + MASTER_PASSWORD)):
            ok = True
        if not ok:
            return False, ("كود التفعيل غير صحيح أو منتهي (الكود صالح في يوم إصداره فقط)." if code
                           else "كلمة السر الرئيسية غير صحيحة." if master else "أدخل كود التفعيل.")
        recs, _ = self._load()
        first = min([r["first"] for r in recs] + [self.today.isoformat()])
        self._save({"v": 1, "first": first, "last": self.today.isoformat(), "act": self._token()})
        return True, "تم تفعيل البرنامج على هذا الجهاز بنجاح."


_current = None


def set_current(lic):
    global _current
    _current = lic


def current():
    return _current
