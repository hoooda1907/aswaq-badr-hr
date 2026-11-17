"""الاسم والشعار القابلان للتغيير من الواجهة (يُحفظان في قاعدة البيانات ويظهران في كل الشاشات والتقارير وسند المرتب)."""
import os

from . import APP_NAME as DEFAULT_NAME

LOGO_DIR = "brand"
LOGO_FILE = "logo.png"
_state = {"name": DEFAULT_NAME, "logo": None}


def name():
    return _state["name"]


def logo():
    """مسار الشعار المخصص أو None (فيُستخدم الشعار الافتراضي)."""
    p = _state["logo"]
    return p if p and os.path.exists(p) else None


def logo_target(data_dir):
    return os.path.join(data_dir, LOGO_DIR, LOGO_FILE)


def load(db, data_dir):
    _state["name"] = (db.get_setting("brand_name") or "").strip() or DEFAULT_NAME
    target = logo_target(data_dir)
    _state["logo"] = target if db.get_setting("brand_logo") and os.path.exists(target) else None


def set_name(db, text):
    text = " ".join((text or "").split())[:80]
    db.set_setting("brand_name", text)
    _state["name"] = text or DEFAULT_NAME


def set_logo(db, data_dir):
    """يُستدعى بعد حفظ ملف PNG الجديد في logo_target."""
    db.set_setting("brand_logo", LOGO_FILE)
    _state["logo"] = logo_target(data_dir)


def clear_logo(db, data_dir):
    db.set_setting("brand_logo", "")
    try:
        os.remove(logo_target(data_dir))
    except OSError:
        pass
    _state["logo"] = None


def reset(db, data_dir):
    set_name(db, "")
    clear_logo(db, data_dir)
