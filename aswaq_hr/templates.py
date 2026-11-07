"""تصدير شيتات فارغة (بيانات الموظفين / البصمات) بالشكل الذي يتعرف عليه البرنامج."""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

from .employee_import import FIELDS

_HEAD_FILL = PatternFill("solid", fgColor="1B9E4B")


def _style_head(ws, ncol):
    for c in ws[1][:ncol]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = _HEAD_FILL
        c.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "A2"
    ws.sheet_view.rightToLeft = True


def _notes(wb, title, lines):
    ws = wb.create_sheet(title)
    ws.sheet_view.rightToLeft = True
    for ln in lines:
        ws.append([ln])
    ws.column_dimensions["A"].width = 110
    ws["A1"].font = Font(bold=True, size=13)


def export_employee_template(path):
    wb = Workbook()
    ws = wb.active
    ws.title = "بيانات الموظفين"
    ws.append([f[1] for f in FIELDS])
    _style_head(ws, len(FIELDS))
    for col, w in zip("ABCDEFGHIJ", [10, 28, 16, 12, 12, 16, 12, 30, 10, 14]):
        ws.column_dimensions[col].width = w
    _notes(wb, "تعليمات", [
        "طريقة تعبئة شيت بيانات الموظفين",
        "1) املأ الشيت الأول فقط (بيانات الموظفين) صفاً لكل موظف، ولا تغيّر عناوين الأعمدة ولا تحذف عمود الكود.",
        "2) الكود هو المعامل: يجب أن يطابق كود الموظف في شيت البصمة تماماً.",
        "3) الخلية الفارغة في أعمدة (البدلات - الجزاءات - خصم التأمينات - السلف - غياب - إجازة بإذن) تعني صفراً.",
        "4) الخلية الفارغة في (الراتب الأساسي - الاسم - ملاحظات) تُبقي القيمة الموجودة في البرنامج كما هي.",
        "5) الغياب = أيام الشهر − الحضور − الراحة − الإجازة. المعتمد دائماً حساب البرنامج، ولو كتبت «غياب» مختلفاً سيُنبّهك البرنامج.",
        "6) يمكنك حذف أي عمود لا تريده (ما عدا الكود) وسيتجاهله البرنامج ولا يغيّر بياناته.",
        "7) جزاء نسيان البصمة يُحسب تلقائياً من قواعد البرنامج ويظهر منفصلاً في سند المرتب، ولا تكتبه هنا.",
        "8) بعد الاستيراد افتح شيت الموظف لتعديل أو حذف أي بند قبل الاعتماد.",
    ])
    wb.save(path)


def export_punch_template(path, rows=3000):
    wb = Workbook()
    ws = wb.active
    ws.title = "البصمات"
    ws.append(["الكود", "الاسم", "التاريخ والوقت"])
    _style_head(ws, 3)
    for col, w in zip("ABC", [10, 30, 22]):
        ws.column_dimensions[col].width = w
    for r in range(2, rows + 2):
        ws.cell(r, 3).number_format = "dd/mm/yyyy hh:mm"
    _notes(wb, "تعليمات", [
        "طريقة تعبئة شيت البصمات",
        "1) كل صف = بصمة واحدة: كود الموظف، اسمه، ثم التاريخ والوقت (مثال: 05/10/2026 18:00).",
        "2) لا يهم الترتيب ولا عدد البصمات في اليوم، والبرنامج يحدد الدخول والخروج والشيفت المسائي تلقائياً.",
        "3) اكتب الشهر كاملاً، وللشيفت المسائي أضف بصمات أول يوم في الشهر التالي ليكتمل آخر شيفت.",
        "4) الشيت الذي يصدّره جهاز البصمة (xls/xlsx/csv) يُستورد مباشرة بدون هذا القالب.",
    ])
    wb.save(path)
