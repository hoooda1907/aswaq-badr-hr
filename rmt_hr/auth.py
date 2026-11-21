"""المصادقة. حساب مدير النظام مدمج داخل البرنامج (بصيغة تجزئة)، لا يظهر في أي قائمة ولا يمكن حذفه."""
import hashlib
import hmac
import os

_ITER = 200_000
_ADMIN_USER = "mahmoud"
_ADMIN_SALT = bytes.fromhex("a3f1c97d5e2b4a80b6d1093c7e58f2a4")
_ADMIN_HASH = "bfd6a9df70b03157b71c3354339701ade80306ee45aa340a8a37dfe5b9f6b7f5"


def hash_password(password, salt=None):
    salt = salt or os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITER)
    return salt.hex(), h.hex()


def _check(password, salt_hex, hash_hex):
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), _ITER).hex()
    return hmac.compare_digest(h, hash_hex)


def verify(db, username, password):
    """يرجع dict {username, is_admin} أو None."""
    u = (username or "").strip()
    if u.lower() == _ADMIN_USER:
        if _check(password, _ADMIN_SALT.hex(), _ADMIN_HASH):
            return {"username": "Mahmoud", "is_admin": True}
        return None
    row = db.get_user(u)
    if row and _check(password, row["salt"], row["hash"]):
        return {"username": row["username"], "is_admin": False}
    return None
