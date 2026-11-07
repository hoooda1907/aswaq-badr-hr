import json
import os
import sqlite3
from datetime import datetime

from .auth import hash_password
from .constants import DEFAULT_REQ_HOURS, DEFAULT_GRACE_MIN, DEFAULT_FP_RULES

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY COLLATE NOCASE, salt TEXT, hash TEXT);
CREATE TABLE IF NOT EXISTS punches(branch TEXT, ym TEXT, code TEXT, ts TEXT);
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
"""

CARRY = ("salary", "allowances", "insurance", "advance", "req_hours", "grace_min",
         "ot_rate", "shift_mode", "leave_paid", "deduct_short")


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
        self.conn.commit()

    # ---------------- الإعدادات
    def get_setting(self, key, default=None):
        r = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r[0] if r else default

    def set_setting(self, key, value):
        self.conn.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, value))
        self.conn.commit()

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
        """items: [(code, name, datetime)] — تُستبدل بيانات كل شهر موجود في الشيت. يرجع قائمة الشهور."""
        by_month = {}
        for code, name, dt in items:
            by_month.setdefault(dt.strftime("%Y-%m"), []).append((code, name, dt))
        for ym, rows in by_month.items():
            self.conn.execute("DELETE FROM punches WHERE branch=? AND ym=?", (branch, ym))
            self.conn.executemany(
                "INSERT INTO punches VALUES(?,?,?,?)",
                [(branch, ym, c, d.strftime("%Y-%m-%d %H:%M")) for c, _, d in rows])
            names = {}
            for c, n, _ in rows:
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

    def punches_of(self, branch, ym, code):
        # يشمل أول يوم من الشهر التالي ليكتمل الشيفت المسائي في آخر يوم من الشهر
        y, m = int(ym[:4]), int(ym[5:7])
        nxt = "%04d-%02d" % ((y + 1, 1) if m == 12 else (y, m + 1))
        res = []
        for r in self.conn.execute(
                "SELECT ts FROM punches WHERE branch=? AND code=? AND ym IN (?,?)", (branch, code, ym, nxt)):
            dt = datetime.strptime(r["ts"], "%Y-%m-%d %H:%M")
            if dt.strftime("%Y-%m") == ym or dt.day == 1:
                res.append(dt)
        return res

    # ---------------- الموظفون وبيانات المرتب
    def ensure_employee(self, branch, ym, code, name, commit=True):
        cur = self.conn.execute("SELECT 1 FROM payroll WHERE branch=? AND ym=? AND code=?", (branch, ym, code))
        if cur.fetchone():
            self.conn.execute("UPDATE payroll SET name=? WHERE branch=? AND ym=? AND code=?", (name, branch, ym, code))
        else:
            prev = self.conn.execute(
                "SELECT * FROM payroll WHERE branch=? AND code=? AND ym<? ORDER BY ym DESC LIMIT 1",
                (branch, code, ym)).fetchone()
            vals = {k: prev[k] for k in CARRY} if prev else {
                "req_hours": DEFAULT_REQ_HOURS, "grace_min": DEFAULT_GRACE_MIN}
            cols = ["branch", "ym", "code", "name"] + list(vals)
            self.conn.execute(
                "INSERT INTO payroll(%s) VALUES(%s)" % (",".join(cols), ",".join("?" * len(cols))),
                [branch, ym, code, name] + list(vals.values()))
        if commit:
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
        self.conn.commit()

    def delete_employee(self, branch, ym, code):
        self.conn.execute("DELETE FROM payroll WHERE branch=? AND ym=? AND code=?", (branch, ym, code))
        self.conn.execute("DELETE FROM punches WHERE branch=? AND ym=? AND code=?", (branch, ym, code))
        self.conn.commit()
