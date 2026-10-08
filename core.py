"""Logique de l'application, sans interface (testable sur ordinateur)."""
import io, re, contextlib
import data, updater
import engine_select as S
import engine_vip as V

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def select_text(draws, nom):
    hist = [h["gagnants"] for h in data.to_select(draws) if h["tirage"] == nom]
    scores, _, _ = S.score_pairs(hist)
    top = S.select_top3_unique(scores)
    probs = S.calibrate_probs(top, scores, hist, window=3)
    lines = [f"MOTEUR SELECT - {nom} ({len(hist)} tirages)", ""]
    for i, ((a, b), sc) in enumerate(top):
        lines.append(f"RANG {i+1} :  {a:02d} - {b:02d}   proba calibrée {probs[i]:.1f} %   score {sc:.6f}")
    lines += ["", "Hasard pur (paire, 3 tirages de Gagnants) : environ 2,6 %"]
    return "\n".join(lines)


def vip_text(draws):
    dv = V.clean_draws(data.to_vip(draws))
    preds = V.forecast(dv)
    lines = [f"MOTEUR VIP ({len(dv)} tirages G+M)", ""]
    for i, p in enumerate(preds):
        a, b = p["pair"]
        lines.append(f"RANG {i+1} :  {a:02d} - {b:02d}   proba {p['probability']*100:.1f} %   score {p['score']:.4f}")
    lines += ["", "Hasard pur (paire, bloc de 3 tirages G+M) : environ 10 %"]
    return "\n".join(lines)


def backtest_text(draws):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        V.backtest(V.clean_draws(data.to_vip(draws)))
    return ANSI.sub("", buf.getvalue()) + "\nHasard pur : environ 10 % par paire."


def auto_update(path, draws):
    names = {d["name"] for d in draws}
    try:
        new = updater.fetch_new_draws(max(d["date"] for d in draws if d["date"]))
        ok, bad = data.append_new(path, new, names)
        return f"Mise à jour : {len(ok)} ajoutés, {len(bad)} refusés."
    except updater.NotConfigured as e:
        return "Mise à jour automatique indisponible : " + str(e)
    except Exception as e:
        return f"Mise à jour impossible ({type(e).__name__}). Le fichier local est utilisé."
