import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aswaq_hr.db import Database
from aswaq_hr.auth import verify
from aswaq_hr.excel_reader import read_table, extract_punches
from aswaq_hr.service import compute_all
from aswaq_hr import reports

d = tempfile.mkdtemp()
db = Database(os.path.join(d, "x.db"))
assert verify(db, "Mahmoud", "4482975")["is_admin"]
assert verify(db, "mahmoud", "bad") is None
assert db.user_count() == 0          # الحساب المدمج غير مخزن في الجدول
db.set_user("admin", "123"); assert verify(db, "ADMIN", "123") and not verify(db, "admin", "1")
items, _ = extract_punches(read_table(sys.argv[1]))
months = db.replace_punches("فرع المساكن", items)
print(months, db.months("فرع المساكن"))
e = db.get_employee("فرع المساكن", "2026-10", "121"); e["salary"] = 6200; e["advance"] = 500; e["leave_days"] = 2
db.save_employee(e)
res = compute_all(db, "فرع المساكن", "2026-10")
print(len(res), [r[3]["net"] for r in res[:4]])
html = reports.voucher_html("فرع المساكن", "2026-10", *[x for x in res if x[0]["code"] == "121"][0][0:1], res[3][2], res[3][3])
reports.export_summary_xlsx(os.path.join(d, "s.xlsx"), "فرع المساكن", "2026-10", res)
print(len(html), os.path.getsize(os.path.join(d, "s.xlsx")), reports.totals_of(res)["net"])
# إعادة الاستيراد تحافظ على بيانات الموظف
db.replace_punches("فرع المساكن", items)
assert db.get_employee("فرع المساكن", "2026-10", "121")["salary"] == 6200
print("OK")
