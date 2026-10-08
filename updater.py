"""Mise à jour automatique depuis lotobonheur.ci.
Il reste UNE chose à brancher : l'adresse du service qui renvoie les résultats.
Tant qu'elle n'est pas renseignée, l'application fonctionne avec le fichier local."""
import json, urllib.request
from datetime import datetime

# Exemple de forme attendue : "https://.../resultats?year={year}&month={month}"
URL_TEMPLATE = None


class NotConfigured(Exception):
    pass


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_response(payload):
    """À écrire quand on aura un exemple de réponse du site.
    Doit renvoyer une liste de {"day": "Jeudi 24/09/2026", "name": "Digital Reveil 7h", "g": [...], "m": [...]}"""
    raise NotImplementedError("Format de réponse du site pas encore branché.")


def fetch_new_draws(last_date):
    if not URL_TEMPLATE:
        raise NotConfigured("Adresse du service de résultats non configurée (updater.py).")
    out, now = [], datetime.now()
    y, m = last_date.year, last_date.month
    while (y, m) <= (now.year, now.month):
        out += parse_response(_get_json(URL_TEMPLATE.format(year=y, month=m)))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out
