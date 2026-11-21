"""مولّد كلمات المرور (عشوائي آمن)."""
import secrets
import string

AMBIGUOUS = set("O0oIl1|")


def generate_password(length=12, upper=True, lower=True, digits=True, symbols=False, avoid_ambiguous=True):
    pools = []
    for on, chars in ((lower, string.ascii_lowercase), (upper, string.ascii_uppercase),
                      (digits, string.digits), (symbols, "!@#$%&*?-_+=")):
        if on:
            c = "".join(ch for ch in chars if not (avoid_ambiguous and ch in AMBIGUOUS))
            pools.append(c)
    if not pools:
        pools = [string.ascii_lowercase]
    length = max(length, len(pools))
    chars = [secrets.choice(p) for p in pools]            # حرف على الأقل من كل نوع مختار
    allc = "".join(pools)
    chars += [secrets.choice(allc) for _ in range(length - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)
