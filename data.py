"""Données : lecture, validation, sauvegarde et ajout dans loto_bonheur.txt (format inchangé)."""
import os, re, shutil
from datetime import datetime

JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def _date(day):
    try:
        return datetime.strptime(day.split()[-1], "%d/%m/%Y")
    except Exception:
        return None


def parse_lines(lines):
    out, day, name, cur = [], None, None, None
    for raw in lines:
        s = raw.strip()
        if s.startswith("Jour :"):
            day, name, cur = s[6:].strip(), None, None
        elif s.startswith("Tirage :"):
            name, cur = s[8:].strip(), None
        elif s.startswith("Gagnants :") and day and name:
            cur = {"day": day, "date": _date(day), "name": name,
                   "g": [int(x) for x in re.findall(r"\d+", s)], "m": []}
            out.append(cur)
        elif s.startswith("Machines :") and cur is not None:
            cur["m"] = [int(x) for x in re.findall(r"\d+", s)]
            cur = None
    return out


def load(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return parse_lines(f.readlines())


def ok5(x):
    return len(x) == 5 and len(set(x)) == 5 and all(1 <= n <= 90 for n in x)


def to_vip(draws):
    return [{"date": d["date"], "day": d["day"], "name": d["name"], "g": d["g"], "m": d["m"]}
            for d in draws if len(d["g"]) == 5 and len(d["m"]) == 5
            and all(1 <= n <= 90 for n in d["g"] + d["m"])]


def to_select(draws):
    return [{"tirage": d["name"], "gagnants": sorted(d["g"])}
            for d in draws if len(d["g"]) == 5 and all(1 <= n <= 90 for n in d["g"])]


def validate(d, known_names):
    if d.get("date") is None:
        return "date invalide"
    if d["name"] not in known_names:
        return f"nom de tirage inconnu : {d['name']}"
    if not ok5(d["g"]):
        return "Gagnants : il faut 5 numéros différents entre 1 et 90"
    if d["m"] and not ok5(d["m"]):
        return "Machines : il faut 5 numéros différents entre 1 et 90 (ou vide)"
    return None


def _block(d):
    m = ", ".join(map(str, d["m"]))
    return (f"  Tirage : {d['name']}\n    Gagnants : {', '.join(map(str, d['g']))}\n"
            f"    Machines : {m}\n")


def append_new(path, new, known_names):
    """Ajoute les tirages valides et nouveaux. Retourne (ajoutés, refusés[(tirage, raison)])."""
    existing = load(path)
    seen = {(d["date"], d["name"]) for d in existing}
    last_day = existing[-1]["day"] if existing else None
    good, bad = [], []
    for d in new:
        d = dict(d)
        d["date"] = d.get("date") or _date(d.get("day", ""))
        why = validate(d, known_names)
        if why:
            bad.append((f"{d.get('day')} {d.get('name')}", why))
        elif (d["date"], d["name"]) in seen:
            bad.append((f"{d['day']} {d['name']}", "déjà présent"))
        else:
            seen.add((d["date"], d["name"]))
            good.append(d)
    if not good:
        return [], bad
    good.sort(key=lambda d: d["date"])  # tri stable : l'ordre dans la journée est conservé
    folder = os.path.join(os.path.dirname(os.path.abspath(path)), "sauvegardes")
    os.makedirs(folder, exist_ok=True)
    shutil.copy2(path, os.path.join(folder, datetime.now().strftime("loto_%Y%m%d_%H%M%S.txt")))
    text = open(path, encoding="utf-8", errors="ignore").read()
    if not text.endswith("\n"):
        text += "\n"
    days = {}
    for d in good:
        days.setdefault(d["date"], []).append(d)
    for date, items in days.items():
        head = f"Jour : {JOURS[date.weekday()]} {date:%d/%m/%Y}"
        same = last_day is not None and last_day.split()[-1] == f"{date:%d/%m/%Y}"
        text += ("\n" if same else f"\n\n{head}\n") + "\n".join(_block(i) for i in items)
        last_day = head
    tmp = path + ".tmp"
    open(tmp, "w", encoding="utf-8").write(text)
    os.replace(tmp, path)
    return good, bad
