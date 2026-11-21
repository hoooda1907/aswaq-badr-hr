#!/usr/bin/env python3
"""مولّد أكواد التفعيل وكلمات المرور — للمطوّر فقط (لا يُسلَّم للعميل).

  python keygen.py                      واجهة رسومية
  python keygen.py code [YYYY-MM-DD]    كود تفعيل لتاريخ (الافتراضي اليوم)
  python keygen.py pass [الطول]         كلمة مرور عشوائية

كود التفعيل = تاريخ اليوم (يوم شهر سنة) + 412022   مثال: 13 نوفمبر 2026 ← 13112026412022
"""
import secrets
import string
import sys
from datetime import date, datetime

SUFFIX = "412022"
MASTER_PASSWORD = "412022"
AMBIGUOUS = set("O0oIl1|")


def activation_code(d=None):
    return (d or date.today()).strftime("%d%m%Y") + SUFFIX


def generate_password(length=12, upper=True, lower=True, digits=True, symbols=False, avoid_ambiguous=True):
    pools = []
    for on, chars in ((lower, string.ascii_lowercase), (upper, string.ascii_uppercase),
                      (digits, string.digits), (symbols, "!@#$%&*?-_+=")):
        if on:
            pools.append("".join(c for c in chars if not (avoid_ambiguous and c in AMBIGUOUS)))
    pools = pools or [string.ascii_lowercase]
    length = max(length, len(pools))
    out = [secrets.choice(p) for p in pools]
    allc = "".join(pools)
    out += [secrets.choice(allc) for _ in range(length - len(out))]
    secrets.SystemRandom().shuffle(out)
    return "".join(out)


def _gui():
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("مولّد الأكواد")
    root.geometry("460x360")
    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=8, pady=8)

    def copy(var):
        root.clipboard_clear()
        root.clipboard_append(var.get())

    # --- كود التفعيل
    f1 = ttk.Frame(nb, padding=14)
    nb.add(f1, text="كود التفعيل")
    ttk.Label(f1, text="التاريخ (YYYY-MM-DD):").pack(anchor="e")
    dv = tk.StringVar(value=date.today().isoformat())
    ttk.Entry(f1, textvariable=dv, justify="center", font=("Consolas", 13)).pack(fill="x", pady=4)
    cv = tk.StringVar(value=activation_code())
    ttk.Entry(f1, textvariable=cv, justify="center", font=("Consolas", 18, "bold"), state="readonly").pack(fill="x", pady=10)
    msg = ttk.Label(f1, text="الكود صالح في تاريخه فقط ويعمل على جهاز واحد", foreground="#666")
    msg.pack()

    def make_code(*_):
        try:
            cv.set(activation_code(datetime.strptime(dv.get().strip(), "%Y-%m-%d").date()))
            msg.config(text="الكود صالح في تاريخه فقط ويعمل على جهاز واحد", foreground="#666")
        except ValueError:
            msg.config(text="صيغة التاريخ غير صحيحة", foreground="#c0392b")

    bf = ttk.Frame(f1)
    bf.pack(pady=8)
    ttk.Button(bf, text="توليد", command=make_code).pack(side="left", padx=4)
    ttk.Button(bf, text="اليوم", command=lambda: (dv.set(date.today().isoformat()), make_code())).pack(side="left", padx=4)
    ttk.Button(bf, text="نسخ", command=lambda: copy(cv)).pack(side="left", padx=4)
    ttk.Label(f1, text="كلمة السر الرئيسية (عند فشل الكود): " + MASTER_PASSWORD, foreground="#666").pack(pady=10)

    # --- كلمات المرور
    f2 = ttk.Frame(nb, padding=14)
    nb.add(f2, text="مولّد كلمات المرور")
    ln = tk.IntVar(value=12)
    up, lo, di, sy = tk.BooleanVar(value=True), tk.BooleanVar(value=True), tk.BooleanVar(value=True), tk.BooleanVar(value=False)
    row = ttk.Frame(f2)
    row.pack(fill="x")
    ttk.Label(row, text="الطول:").pack(side="right")
    ttk.Spinbox(row, from_=6, to=40, textvariable=ln, width=5).pack(side="right", padx=6)
    for text, v in (("حروف كبيرة", up), ("حروف صغيرة", lo), ("أرقام", di), ("رموز", sy)):
        ttk.Checkbutton(f2, text=text, variable=v).pack(anchor="e")
    pv = tk.StringVar()
    ttk.Entry(f2, textvariable=pv, justify="center", font=("Consolas", 15), state="readonly").pack(fill="x", pady=10)

    def make_pw():
        pv.set(generate_password(int(ln.get()), up.get(), lo.get(), di.get(), sy.get()))

    bf2 = ttk.Frame(f2)
    bf2.pack()
    ttk.Button(bf2, text="توليد", command=make_pw).pack(side="left", padx=4)
    ttk.Button(bf2, text="نسخ", command=lambda: copy(pv)).pack(side="left", padx=4)
    make_pw()
    root.mainloop()


def main(argv):
    if len(argv) >= 2 and argv[1] == "code":
        d = datetime.strptime(argv[2], "%Y-%m-%d").date() if len(argv) > 2 else None
        print(activation_code(d))
    elif len(argv) >= 2 and argv[1] == "pass":
        print(generate_password(int(argv[2]) if len(argv) > 2 else 12))
    else:
        _gui()


if __name__ == "__main__":
    main(sys.argv)
