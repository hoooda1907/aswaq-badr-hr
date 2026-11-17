import json
import os
import sqlite3
from datetime import datetime

from .auth import hash_password
from .constants import (DEFAULT_REQ_HOURS, DEFAULT_GRACE_MIN, DEFAULT_FP_RULES, BRANCHES, BRANCH_MODE,
                        DEFAULT_BRANCH_NAME)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY COLLATE NOCASE, salt TEXT, hash TEXT);
CREATE TABLE IF NOT EXISTS punches(branch TEXT, ym TEXT, code TEXT, ts TEXT, kind TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_p ON punches(branch, ym, code);
CREATE TABLE IF NOT EXISTS payroll(
  branch TEXT, ym TEXT, code TEXT, name TEXT,
  salary REAL DEFAULT 0, allowances REAL DEFAULT 0, penalties REAL DEFAULT 0,
  insurance REAL DEFAULT 0, advance REAL DEFAULT 0, leave_days INTEGER DEFAULT 0,
  req_hours REAL DEFAULT 10, grace_min INTEGER DEFAULT 20, ot_rate REAL DEFAULT 1,
  ot_manual REAL, shift_mode TEXT DEFAULT 'auto', leave_paid INTEGER DEFAULT 1,
  deduct_short INTEGER DEFAULT 0, notes TEXT DEFAULT '', fp_manual REAL,
  PRIMARY KEY(branch, ym, code));
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS employees_master(branch TEXT, code TEXT, name TEXT DEFAULT '', salary REAL DEFAULT 0,
  allowances REAL DEFAULT 0, insurance REAL DEFAULT 0, annual_days REAL DEFAULT 21, PRIMARY KEY(branch, code));
CREATE TABLE IF NOT EXISTS punch_edits(id INTEGER PRIMARY KEY AUTOINCREMENT, branch TEXT, code TEXT, op TEXT,
  ts TEXT, new_ts TEXT, kind TEXT DEFAULT '');
"""

# يُرحَّل من الشهر السابق: الراتب والبدلات والتأمينات + إعدادات الموظف الفنية.
# لا يُرحَّل: الجزاءات والسلف والإضافي اليدوي والملاحظات والإجازات (تُدخل كل شهر).
CARRY = ("salary", "allowances", "insurance", "req_hours", "grace_min",
         "ot_rate", "shift_mode", "leave_paid", "deduct_short")
DEFAULT_ANNUAL_DAYS = 21


def _code_key(c):
    return (0, int(c), c) if str(c).isdigit() else (1, 0, str(c))


class Database:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(payroll)")}
        if "fp_manual" not in cols:          # ترقية قواعد البيانات القديمة
            self.conn.execute("ALTER TABLE payroll ADD COLUMN fp_manual REAL")
        pcols = {r[1] for r in self.conn.execute("PRAGMA table_info(punches)")}
        if "kind" not in pcols:
            self.conn.execute("ALTER TABLE punches ADD COLUMN kind TEXT DEFAULT ''")
        self.conn.commit()

    # ---------------- الإعدادات
    def get_setting(self, key, default=None):
        r = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r[0] if r else default

    def set_setting(self, key, value):
        self.conn.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, value))
        self.conn.commit()

    # ---------------- الفروع
    def branches(self):
        if BRANCH_MODE != "dynamic":
            return list(BRANCHES)
        try:
            lst = json.loads(self.get_setting("branches") or "[]")
        except ValueError:
            lst = []
        return lst or [DEFAULT_BRANCH_NAME]

    def _save_branches(self, lst):
        self.set_setting("branches", json.dumps(lst, ensure_ascii=False))

    @staticmethod
    def _clean_branch(name):
        return " ".join((name or "").split())[:60]

    def add_branch(self, name):
        """يرجع (نجح؟، رسالة)."""
        name = self._clean_branch(name)
        if not name:
            return False, "اكتب اسم الفرع"
        lst = self.branches()
        if name in lst:
            return False, "هذا الفرع موجود بالفعل"
        self._save_branches(lst + [name])
        return True, name

    def rename_branch(self, old, new):
        new = self._clean_branch(new)
        if not new:
            return False, "اكتب اسم الفرع"
        lst = self.branches()
        if old not in lst:
            return False, "الفرع غير موجود"
        if new == old:
            return True, new
        if new in lst:
            return False, "هذا الاسم مستخدم لفرع آخر"
        self.conn.execute("UPDATE punches SET branch=? WHERE branch=?", (new, old))
        self.conn.execute("UPDATE payroll SET branch=? WHERE branch=?", (new, old))
        self._save_branches([new if b == old else b for b in lst])
        self.conn.commit()
        return True, new

    def fp_rules(self):
        rules = dict(DEFAULT_FP_RULES)
        try:
            rules.update(json.loads(self.get_setting("fp_rules") or "{}"))
        except ValueError:
            pass
        return rules

    def set_fp_rules(self, rules):
        self.set_setting("fp_rules", json.dumps({k: rules[k] for k in DEFAULT_FP_RULES}))

    # ---------------- المستخدمون
    def user_count(self):
        return self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def get_user(self, username):
        return self.conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

    def list_users(self):
        return [r["username"] for r in self.conn.execute("SELECT username FROM users ORDER BY username")]

    def set_user(self, username, password):
        salt, h = hash_password(password)
        self.conn.execute("INSERT OR REPLACE INTO users VALUES(?,?,?)", (username.strip(), salt, h))
        self.conn.commit()

    def delete_user(self, username):
        self.conn.execute("DELETE FROM users WHERE username=?", (username,))
        self.conn.commit()

    # ---------------- الشهور والبصمات
    def months(self, branch):
        q = """SELECT ym FROM (SELECT ym FROM punches WHERE branch=? UNION SELECT ym FROM payroll WHERE branch=?)
               ORDER BY ym DESC"""
        return [r[0] for r in self.conn.execute(q, (branch, branch))]

    def replace_punches(self, branch, items):
        """items: [(code, name, datetime)] أو [(code, name, datetime, kind)] حيث kind = I/O/'' (اتجاه الجهاز).
        تُستبدل بيانات كل شهر موجود في الشيت. يرجع قائمة الشهور."""
        by_month = {}
        for it in items:
            code, name, dt = it[0], it[1], it[2]
            kind = it[3] if len(it) > 3 else ""
            by_month.setdefault(dt.strftime("%Y-%m"), []).append((code, name, dt, kind or ""))
        for ym, rows in by_month.items():
            self.conn.execute("DELETE FROM punches WHERE branch=? AND ym=?", (branch, ym))
            uniq = {}
            for c, _, d, k in rows:                       # دمج الصفوف المكررة (نفس البصمة بأكثر من اتجاه = IO)
                key = (c, d.strftime("%Y-%m-%d %H:%M"))
                uniq[key] = "".join(sorted(set(uniq.get(key, "")) | set(k)))
            self.conn.executemany(
                "INSERT INTO punches(branch, ym, code, ts, kind) VALUES(?,?,?,?,?)",
                [(branch, ym, c, ts, k) for (c, ts), k in uniq.items()])
            names = {}
            for c, n, _, _ in rows:
                names[c] = n
            for c, n in names.items():
                self.ensure_employee(branch, ym, c, n, commit=False)
        self.conn.commit()
        return sorted(by_month, reverse=True)

    def month_has_punches(self, branch, ym):
        return self.conn.execute("SELECT 1 FROM punches WHERE branch=? AND ym=? LIMIT 1", (branch, ym)).fetchone() is not None

    def punches_by_code(self, branch, ym):
        out = {}
        for r in self.conn.execute("SELECT code, ts FROM punches WHERE branch=? AND ym=?", (branch, ym)):
            out.setdefault(r["code"], []).append(datetime.strptime(r["ts"], "%Y-%m-%d %H:%M"))
        return out

    # ---------------- البصمات (مع التعديلات اليدوية)
    @staticmethod
    def _fmt(dt):
        return dt.strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def _parse(ts):
        return datetime.strptime(ts, "%Y-%m-%d %H:%M")

    def punch_rows(self, branch, ym, code):
        """البصمات الفعلية للشهر (مع أول يوم من الشهر التالي) بعد تطبيق التعديلات اليدوية، وتشمل المحذوفة.
        كل عنصر: dict(dt, kind, state, orig) حيث state: raw (أصلية) / mod (معدّلة) / add (مضافة) / del (محذوفة)."""
        y, m = int(ym[:4]), int(ym[5:7])
        nxt = "%04d-%02d" % ((y + 1, 1) if m == 12 else (y, m + 1))
        rows = {}
        for r in self.conn.execute("SELECT ts, kind FROM punches WHERE branch=? AND code=? AND ym IN (?,?)",
                                   (branch, code, ym, nxt)):
            dt = self._parse(r["ts"])
            rows[dt] = {"dt": dt, "kind": r["kind"] or "", "state": "raw", "orig": dt}
        for e in self.conn.execute("SELECT * FROM punch_edits WHERE branch=? AND code=? ORDER BY id", (branch, code)):
            ts = self._parse(e["ts"])
            if e["op"] == "del":
                if ts in rows and rows[ts]["state"] == "raw":
                    rows[ts]["state"] = "del"
            elif e["op"] == "mod":
                if ts in rows and rows[ts]["state"] == "raw":
                    row = rows.pop(ts)
                    new = self._parse(e["new_ts"])
                    row.update(dt=new, state="mod", orig=ts)
                    if e["kind"]:
                        row["kind"] = "" if e["kind"] == "U" else e["kind"]
                    rows[new] = row
            elif e["op"] == "add":
                rows[ts] = {"dt": ts, "kind": "" if e["kind"] == "U" else (e["kind"] or ""), "state": "add", "orig": None}
        out = [r for r in rows.values() if r["dt"].strftime("%Y-%m") == ym or (r["dt"].strftime("%Y-%m") == nxt and r["dt"].day == 1)]
        out.sort(key=lambda r: r["dt"])
        return out

    def punches_of(self, branch, ym, code, with_kind=False):
        """بصمات الموظف الفعّالة (بدون المحذوفة) — تشمل أول يوم من الشهر التالي ليكتمل الشيفت المسائي."""
        return [(r["dt"], r["kind"]) if with_kind else r["dt"]
                for r in self.punch_rows(branch, ym, code) if r["state"] != "del"]

    def punch_edit_count(self, branch, ym, code):
        return sum(1 for r in self.punch_rows(branch, ym, code) if r["state"] != "raw")

    def punch_delete(self, branch, code, dt):
        ts = self._fmt(dt)
        r = self.conn.execute("SELECT id FROM punch_edits WHERE branch=? AND code=? AND op='add' AND ts=?", (branch, code, ts)).fetchone()
        if r:                                                    # بصمة مضافة يدوياً: يُلغى إضافتها
            self.conn.execute("DELETE FROM punch_edits WHERE id=?", (r["id"],))
        else:
            m = self.conn.execute("SELECT id, ts FROM punch_edits WHERE branch=? AND code=? AND op='mod' AND new_ts=?",
                                  (branch, code, ts)).fetchone()
            if m:                                                # معدّلة: تُحذف الأصلية
                self.conn.execute("DELETE FROM punch_edits WHERE id=?", (m["id"],))
                self.conn.execute("INSERT INTO punch_edits(branch, code, op, ts) VALUES(?,?,'del',?)", (branch, code, m["ts"]))
            else:
                self.conn.execute("INSERT INTO punch_edits(branch, code, op, ts) VALUES(?,?,'del',?)", (branch, code, ts))
        self.conn.commit()

    def punch_modify(self, branch, code, old_dt, new_dt, kind=None):
        """تعديل توقيت بصمة (وكذلك اتجاهها لو kind = I/O/U)."""
        old, new = self._fmt(old_dt), self._fmt(new_dt)
        a = self.conn.execute("SELECT id FROM punch_edits WHERE branch=? AND code=? AND op='add' AND ts=?", (branch, code, old)).fetchone()
        if a:
            self.conn.execute("UPDATE punch_edits SET ts=?, kind=COALESCE(?, kind) WHERE id=?", (new, kind, a["id"]))
        else:
            m = self.conn.execute("SELECT id, ts FROM punch_edits WHERE branch=? AND code=? AND op='mod' AND new_ts=?",
                                  (branch, code, old)).fetchone()
            if m and m["ts"] == new and not kind:                # رجوع للتوقيت الأصلي
                self.conn.execute("DELETE FROM punch_edits WHERE id=?", (m["id"],))
            elif m:
                self.conn.execute("UPDATE punch_edits SET new_ts=?, kind=COALESCE(?, kind) WHERE id=?", (new, kind, m["id"]))
            else:
                self.conn.execute("INSERT INTO punch_edits(branch, code, op, ts, new_ts, kind) VALUES(?,?,'mod',?,?,?)",
                                  (branch, code, old, new, kind or ""))
        self.conn.commit()

    def punch_add(self, branch, code, dt, kind=""):
        ts = self._fmt(dt)
        d = self.conn.execute("SELECT id FROM punch_edits WHERE branch=? AND code=? AND op='del' AND ts=?", (branch, code, ts)).fetchone()
        if d:                                                    # كانت محذوفة: تُسترجع
            self.conn.execute("DELETE FROM punch_edits WHERE id=?", (d["id"],))
        elif not self.conn.execute("SELECT 1 FROM punch_edits WHERE branch=? AND code=? AND op='add' AND ts=?", (branch, code, ts)).fetchone():
            self.conn.execute("INSERT INTO punch_edits(branch, code, op, ts, kind) VALUES(?,?,'add',?,?)", (branch, code, ts, kind or ""))
        self.conn.commit()

    def punch_restore(self, branch, code, dt):
        """يلغي كل تعديل على هذه البصمة (محذوفة/معدّلة/مضافة) ويرجعها كما في الشيت."""
        ts = self._fmt(dt)
        self.conn.execute("DELETE FROM punch_edits WHERE branch=? AND code=? AND "
                          "((op='del' AND ts=?) OR (op='mod' AND (ts=? OR new_ts=?)) OR (op='add' AND ts=?))",
                          (branch, code, ts, ts, ts, ts))
        self.conn.commit()

    def punch_edits_clear(self, branch, code, ym):
        self.conn.execute("DELETE FROM punch_edits WHERE branch=? AND code=? AND (ts LIKE ? OR new_ts LIKE ?)",
                          (branch, code, ym + "%", ym + "%"))
        self.conn.commit()

    # ---------------- الموظفون وبيانات المرتب
    def ensure_employee(self, branch, ym, code, name, commit=True):
        """ينشئ سجل الموظف للشهر. الاسم والراتب والبدلات والتأمينات تُؤخذ من القائمة الدائمة (أو من الشهر السابق)."""
        real_name = bool(name) and str(name).strip() != str(code)
        cur = self.conn.execute("SELECT * FROM payroll WHERE branch=? AND ym=? AND code=?", (branch, ym, code)).fetchone()
        master = self.master_get(branch, code)
        if cur:
            use = name if real_name or not (master and master["name"]) else master["name"]
            self.conn.execute("UPDATE payroll SET name=? WHERE branch=? AND ym=? AND code=?", (use, branch, ym, code))
        else:
            prev = self.conn.execute(
                "SELECT * FROM payroll WHERE branch=? AND code=? AND ym<? ORDER BY ym DESC LIMIT 1",
                (branch, code, ym)).fetchone()
            vals = {k: prev[k] for k in CARRY} if prev else {
                "req_hours": DEFAULT_REQ_HOURS, "grace_min": DEFAULT_GRACE_MIN}
            if master:                                   # القائمة الدائمة هي المرجع للأجر
                for k in ("salary", "allowances", "insurance"):
                    vals[k] = master[k]
            use = name if real_name or not (master and master["name"]) else master["name"]
            cols = ["branch", "ym", "code", "name"] + list(vals)
            self.conn.execute(
                "INSERT INTO payroll(%s) VALUES(%s)" % (",".join(cols), ",".join("?" * len(cols))),
                [branch, ym, code, use] + list(vals.values()))
        if not master:                                   # أول ظهور للموظف: يُحفظ في القائمة الدائمة
            row = self.conn.execute("SELECT name, salary, allowances, insurance FROM payroll WHERE branch=? AND ym=? AND code=?",
                                    (branch, ym, code)).fetchone()
            self.master_upsert(branch, code, name=row["name"], salary=row["salary"], allowances=row["allowances"],
                               insurance=row["insurance"], commit=False)
        elif real_name and master["name"] != name:
            self.master_upsert(branch, code, name=name, commit=False)
        if commit:
            self.conn.commit()

    # ---------------- القائمة الدائمة للموظفين (الكود، الاسم، الراتب، البدلات، التأمينات، رصيد الإجازة السنوية)
    def master_get(self, branch, code):
        r = self.conn.execute("SELECT * FROM employees_master WHERE branch=? AND code=?", (branch, code)).fetchone()
        return dict(r) if r else None

    def master_list(self, branch):
        rows = [dict(r) for r in self.conn.execute("SELECT * FROM employees_master WHERE branch=?", (branch,))]
        rows.sort(key=lambda r: _code_key(r["code"]))
        return rows

    def master_upsert(self, branch, code, name=None, salary=None, allowances=None, insurance=None,
                      annual_days=None, commit=True):
        """يضيف الموظف أو يحدّث الحقول المرسلة فقط (None = بدون تغيير)."""
        if not self.master_get(branch, code):
            self.conn.execute("INSERT INTO employees_master(branch, code, name, annual_days) VALUES(?,?,?,?)",
                              (branch, code, str(code), DEFAULT_ANNUAL_DAYS))
        for col, val in (("name", name), ("salary", salary), ("allowances", allowances),
                         ("insurance", insurance), ("annual_days", annual_days)):
            if val is not None:
                self.conn.execute("UPDATE employees_master SET %s=? WHERE branch=? AND code=?" % col, (val, branch, code))
        if commit:
            self.conn.commit()

    def master_delete(self, branch, code):
        self.conn.execute("DELETE FROM employees_master WHERE branch=? AND code=?", (branch, code))
        self.conn.commit()

    def employees(self, branch, ym):
        rows = [dict(r) for r in self.conn.execute("SELECT * FROM payroll WHERE branch=? AND ym=?", (branch, ym))]
        rows.sort(key=lambda r: _code_key(r["code"]))
        return rows

    def get_employee(self, branch, ym, code):
        r = self.conn.execute("SELECT * FROM payroll WHERE branch=? AND ym=? AND code=?", (branch, ym, code)).fetchone()
        return dict(r) if r else None

    def save_employee(self, e):
        keys = ["name", "salary", "allowances", "penalties", "insurance", "advance", "leave_days", "req_hours",
                "grace_min", "ot_rate", "ot_manual", "shift_mode", "leave_paid", "deduct_short", "notes", "fp_manual"]
        self.conn.execute(
            "UPDATE payroll SET %s WHERE branch=? AND ym=? AND code=?" % ",".join(k + "=?" for k in keys),
            [e.get(k) for k in keys] + [e["branch"], e["ym"], e["code"]])
        months = self.months(e["branch"])
        if months and e["ym"] >= months[0]:              # تعديل أحدث شهر يصبح هو الافتراضي للشهور القادمة
            self.master_upsert(e["branch"], e["code"], name=e.get("name"), salary=e.get("salary"),
                               allowances=e.get("allowances"), insurance=e.get("insurance"), commit=False)
        self.conn.commit()

    def delete_employee(self, branch, ym, code):
        self.conn.execute("DELETE FROM payroll WHERE branch=? AND ym=? AND code=?", (branch, ym, code))
        self.conn.execute("DELETE FROM punches WHERE branch=? AND ym=? AND code=?", (branch, ym, code))
        self.conn.execute("DELETE FROM punch_edits WHERE branch=? AND code=? AND (ts LIKE ? OR new_ts LIKE ?)",
                          (branch, code, ym + "%", ym + "%"))
        self.conn.commit()
