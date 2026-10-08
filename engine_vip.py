import re
import os
import math
import itertools
from collections import Counter
from datetime import datetime

import numpy as np

# ============================================================
# THE FORECASTER SHARP TWO
# TRUE WINDOW 3
# ============================================================

FILE = "/storage/emulated/0/Script Loto /loto_bonheur.txt"

# Si tu utilises le fichier 2026 :
# FILE = "/storage/emulated/0/Script Loto /tirages-2026.txt"

MAX_HISTORY = 300

# Nombre de tirages récents utilisés comme mémoire immédiate
SOURCE_DRAWS = 6

# T+1, T+2, T+3
HORIZONS = (1, 2, 3)

# Pondérations temporelles
HORIZON_WEIGHT = {
    1: 1.00,
    2: 0.72,
    3: 0.48
}

# Gagnants plus importants que Machines
ROLE_WEIGHT = {
    "G": 1.00,
    "M": 0.62
}

# Glissements
TRANSFORMS = (-2, -1, 1, 2)

# Poids des glissements
TRANSFORM_WEIGHT = 0.045

# Pondération du passé
DECAY_TRANSITION = 55.0
DECAY_RECENT = 4.0
DECAY_BLOCK_PROB = 80.0

# Nombre minimum de tirages nécessaires
MIN_HISTORY = 50

# Backtest
BACKTEST_ENABLED = True
BACKTEST_MAX = 180
BACKTEST_STEP = 5


# ============================================================
# COULEURS
# ============================================================

try:
    from colorama import Fore, Style, init
    init(autoreset=True)
except Exception:
    class Dummy:
        def __getattr__(self, name):
            return ""
    Fore = Style = Dummy()


# ============================================================
# LECTURE DU FICHIER
# ============================================================

def load_draws(path):

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"\nFichier introuvable :\n{path}\n"
        )

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    draws = []

    current_day = None
    current_name = None
    current_g = None

    for line in lines:

        s = line.strip()

        if s.startswith("Jour :"):
            current_day = s[7:].strip()

        elif s.startswith("Tirage :"):
            current_name = s[8:].strip()
            current_g = None

        elif s.startswith("Gagnants :"):
            nums = [int(x) for x in re.findall(r"\d+", s)]

            if len(nums) == 5:
                current_g = nums

        elif s.startswith("Machines :"):

            nums = [int(x) for x in re.findall(r"\d+", s)]

            if (
                current_day
                and current_name
                and current_g
                and len(current_g) == 5
                and len(nums) == 5
            ):

                try:
                    date_obj = datetime.strptime(
                        current_day.split()[-1],
                        "%d/%m/%Y"
                    )
                except Exception:
                    date_obj = None

                draws.append({
                    "date": date_obj,
                    "day": current_day,
                    "name": current_name,
                    "g": current_g,
                    "m": nums
                })

    return draws


# ============================================================
# NORMALISATION
# ============================================================

def clean_draws(draws):

    result = []

    for d in draws:

        g = [
            x for x in d["g"]
            if 1 <= x <= 90
        ]

        m = [
            x for x in d["m"]
            if 1 <= x <= 90
        ]

        if len(g) == 5 and len(m) == 5:
            result.append({
                "date": d["date"],
                "day": d["day"],
                "name": d["name"],
                "g": g,
                "m": m
            })

    return result


# ============================================================
# PRESENCE D'UNE PAIRE DANS UN BLOC DE 3
# ============================================================

def pair_in_block(pair, draws):

    a, b = pair

    for d in draws:

        vals = set(d["g"])
        vals.update(d["m"])

        if a in vals and b in vals:
            return True

    return False


# ============================================================
# CONSTRUCTION DU MOTEUR
# ============================================================

def build_engine(draws, current_index):

    start = max(0, current_index - MAX_HISTORY)

    history_end = current_index - 3

    if history_end <= start:
        return None

    history = draws[start:history_end]

    # --------------------------------------------------------
    # TRANSITION :
    #
    # [role][position][source_number][target_number]
    #
    # role 0 = Gagnants
    # role 1 = Machines
    # --------------------------------------------------------

    transition = np.zeros(
        (2, 5, 91, 91),
        dtype=np.float64
    )

    source_total = np.zeros(
        (2, 5, 91),
        dtype=np.float64
    )

    # --------------------------------------------------------
    # PAIRS OBSERVEES DANS LES BLOCS DE 3
    # --------------------------------------------------------

    pair_matrix = np.zeros(
        (91, 91),
        dtype=np.float64
    )

    block_weight_total = 0.0

    # Fréquence de présence d'un numéro dans les blocs
    block_number_weight = np.zeros(91)

    # --------------------------------------------------------
    # APPRENTISSAGE HISTORIQUE
    # --------------------------------------------------------

    for local_j, j in enumerate(
        range(start, history_end)
    ):

        age = current_index - 1 - j

        temporal_weight = math.exp(
            -age / DECAY_TRANSITION
        )

        # -----------------------------
        # BLOC T+1 / T+2 / T+3
        # -----------------------------

        future_numbers = []

        for h in HORIZONS:

            future_draw = draws[j + h]

            hw = HORIZON_WEIGHT[h]

            for role_name, role_index, role_weight in [
                ("G", 0, ROLE_WEIGHT["G"]),
                ("M", 1, ROLE_WEIGHT["M"])
            ]:

                arr = (
                    future_draw["g"]
                    if role_name == "G"
                    else future_draw["m"]
                )

                for y in arr:

                    future_numbers.append(
                        (
                            y,
                            temporal_weight
                            * hw
                            * role_weight
                        )
                    )

        # ----------------------------------------------------
        # MEMOIRE POSITIONNELLE
        # ----------------------------------------------------

        for role_name, role_index in [
            ("G", 0),
            ("M", 1)
        ]:

            arr = (
                draws[j]["g"]
                if role_name == "G"
                else draws[j]["m"]
            )

            rw = ROLE_WEIGHT[role_name]

            for position, x in enumerate(arr):

                if not (1 <= x <= 90):
                    continue

                source_total[
                    role_index,
                    position,
                    x
                ] += temporal_weight * rw

                for y, fw in future_numbers:

                    transition[
                        role_index,
                        position,
                        x,
                        y
                    ] += temporal_weight * rw * fw

        # ----------------------------------------------------
        # CO-OCCURRENCE DES NUMEROS DANS LE BLOC DE 3
        # ----------------------------------------------------

        future_set = set()

        for h in HORIZONS:

            future_set.update(
                draws[j + h]["g"]
            )

            future_set.update(
                draws[j + h]["m"]
            )

        future_set = sorted(future_set)

        block_weight_total += temporal_weight

        for x in future_set:
            block_number_weight[x] += temporal_weight

        for a, b in itertools.combinations(
            future_set, 2
        ):

            pair_matrix[a, b] += temporal_weight
            pair_matrix[b, a] += temporal_weight

    # --------------------------------------------------------
    # PROBABILITE MARGINALE DANS LE BLOC DE 3
    # --------------------------------------------------------

    marginal = (
        block_number_weight
        / max(block_weight_total, 1e-12)
    )

    return {
        "start": start,
        "transition": transition,
        "source_total": source_total,
        "pair_matrix": pair_matrix,
        "block_weight_total": block_weight_total,
        "marginal": marginal
    }


# ============================================================
# SCORE DES NUMEROS
# ============================================================

def score_numbers(draws, current_index, engine):

    transition = engine["transition"]
    source_total = engine["source_total"]

    scores = np.zeros(91)

    recent_support = np.zeros(91)

    start = max(
        0,
        current_index - SOURCE_DRAWS
    )

    # --------------------------------------------------------
    # MEMOIRE DES DERNIERS TIRAGES
    # --------------------------------------------------------

    for j in range(start, current_index):

        age = current_index - 1 - j

        recent_weight = math.exp(
            -age / 2.2
        )

        # -----------------------------------------------
        # GAGNANTS
        # -----------------------------------------------

        for position, x in enumerate(
            draws[j]["g"]
        ):

            if not 1 <= x <= 90:
                continue

            denom = source_total[
                0,
                position,
                x
            ]

            if denom > 0:

                distribution = (
                    transition[
                        0,
                        position,
                        x
                    ] / denom
                )

                scores += (
                    recent_weight
                    * ROLE_WEIGHT["G"]
                    * distribution
                )

            recent_support[x] += (
                recent_weight
                * ROLE_WEIGHT["G"]
            )

        # -----------------------------------------------
        # MACHINES
        # -----------------------------------------------

        for position, x in enumerate(
            draws[j]["m"]
        ):

            if not 1 <= x <= 90:
                continue

            denom = source_total[
                1,
                position,
                x
            ]

            if denom > 0:

                distribution = (
                    transition[
                        1,
                        position,
                        x
                    ] / denom
                )

                scores += (
                    recent_weight
                    * ROLE_WEIGHT["M"]
                    * distribution
                )

            recent_support[x] += (
                recent_weight
                * ROLE_WEIGHT["M"]
            )

    # --------------------------------------------------------
    # GLISSEMENTS
    # --------------------------------------------------------

    for j in range(start, current_index):

        age = current_index - 1 - j

        w = math.exp(
            -age / DECAY_RECENT
        )

        for role_name in ["g", "m"]:

            for x in draws[j][role_name]:

                for delta in TRANSFORMS:

                    y = x + delta

                    if 1 <= y <= 90:

                        scores[y] += (
                            w
                            * TRANSFORM_WEIGHT
                        )

                # miroir 91 - x
                y = 91 - x

                if 1 <= y <= 90:

                    scores[y] += (
                        w
                        * TRANSFORM_WEIGHT
                    )

    # --------------------------------------------------------
    # SUPPORT RECENT
    # --------------------------------------------------------

    if recent_support.max() > 0:

        recent_norm = (
            recent_support
            / recent_support.max()
        )

        scores += (
            0.10 * recent_norm
        )

    scores[0] = 0

    return scores


# ============================================================
# FILTRE ANTI-NUMERO FANTOME
# ============================================================

def ghost_filter(scores):

    result = scores.copy()

    positive = result[1:]

    if np.max(positive) <= 0:
        return result

    # Seuil de saturation
    cap = np.quantile(
        positive,
        0.85
    )

    if cap <= 0:
        return result

    # On empêche un seul numéro de monopoliser
    # toute la masse de prédiction.
    for n in range(1, 91):

        if result[n] > cap:

            excess = result[n] - cap

            result[n] = (
                cap
                + 0.30 * excess
            )

    return result


# ============================================================
# SCORE DES PAIRES
# ============================================================

def rank_pairs(
    draws,
    current_index,
    engine,
    number_scores
):

    pair_matrix = engine["pair_matrix"]
    marginal = engine["marginal"]
    total = engine["block_weight_total"]

    # Nettoyage anti-fantôme
    number_scores = ghost_filter(
        number_scores
    )

    mean_score = np.mean(
        number_scores[1:]
    )

    # --------------------------------------------------------
    # NORMALISATION
    # --------------------------------------------------------

    if np.max(number_scores[1:]) > 0:

        ns = (
            number_scores
            / np.max(number_scores[1:])
        )

    else:

        ns = number_scores.copy()

    candidates = []

    for a, b in itertools.combinations(
        range(1, 91),
        2
    ):

        # ---------------------------------------------
        # FORCE INDIVIDUELLE
        # ---------------------------------------------

        base = ns[a] * ns[b]

        # ---------------------------------------------
        # CO-OCCURRENCE OBSERVEE
        # ---------------------------------------------

        observed = (
            pair_matrix[a, b]
            / max(total, 1e-12)
        )

        # ---------------------------------------------
        # ATTENDU SI LES DEUX NUMEROS ETAIENT
        # INDEPENDANTS
        # ---------------------------------------------

        expected = (
            marginal[a]
            * marginal[b]
        )

        # ---------------------------------------------
        # CORRELATION CROISEE
        #
        # Ceci casse le monopole des numéros
        # très fréquents individuellement.
        # ---------------------------------------------

        lift = (
            (observed + 0.0005)
            / (expected + 0.0005)
        )

        interaction = math.tanh(
            math.log(max(lift, 1e-6))
        )

        # ---------------------------------------------
        # SATURATION INDIVIDUELLE
        # ---------------------------------------------

        cap_a = min(
            ns[a],
            0.80
        )

        cap_b = min(
            ns[b],
            0.80
        )

        individual = (
            cap_a + cap_b
        )

        # ---------------------------------------------
        # SCORE FINAL
        # ---------------------------------------------

        score = (
            1.00
            * math.log1p(
                60.0 * max(base, 0)
            )
            +
            0.90
            * interaction
            +
            0.25
            * math.tanh(
                individual
                / max(
                    mean_score,
                    1e-9
                )
            )
        )

        candidates.append(
            (
                score,
                (a, b)
            )
        )

    candidates.sort(
        reverse=True,
        key=lambda x: x[0]
    )

    # --------------------------------------------------------
    # TOP 3 100 % DISJOINT
    # --------------------------------------------------------

    selected = []
    used = set()

    for score, pair in candidates:

        a, b = pair

        if a in used or b in used:
            continue

        selected.append(
            (
                pair,
                score
            )
        )

        used.add(a)
        used.add(b)

        if len(selected) == 3:
            break

    return selected


# ============================================================
# PROBABILITE EMPIRIQUE SUR BLOC DE 3
# ============================================================

def empirical_probability(
    draws,
    current_index,
    pair
):

    start = max(
        0,
        current_index - MAX_HISTORY
    )

    end = current_index - 3

    if end <= start:
        return 0.0, 0, 0

    hit_weight = 0.0
    total_weight = 0.0

    a, b = pair

    for j in range(start, end):

        age = current_index - 1 - j

        w = math.exp(
            -age / DECAY_BLOCK_PROB
        )

        total_weight += w

        future = set()

        for h in HORIZONS:

            future.update(
                draws[j + h]["g"]
            )

            future.update(
                draws[j + h]["m"]
            )

        if a in future and b in future:

            hit_weight += w

    # --------------------------------------------------------
    # LISSAGE BETA CONSERVATEUR
    # --------------------------------------------------------

    alpha = 1.0
    beta = 20.0

    probability = (
        hit_weight + alpha
    ) / (
        total_weight
        + alpha
        + beta
    )

    return (
        probability,
        hit_weight,
        total_weight
    )


# ============================================================
# PREDICTION
# ============================================================

def forecast(draws, index=None):

    if index is None:
        index = len(draws)

    if index < MIN_HISTORY + 3:

        raise ValueError(
            "Pas assez d'historique."
        )

    engine = build_engine(
        draws,
        index
    )

    numbers = score_numbers(
        draws,
        index,
        engine
    )

    pairs = rank_pairs(
        draws,
        index,
        engine,
        numbers
    )

    result = []

    for rank, (pair, score) in enumerate(
        pairs,
        start=1
    ):

        prob, hitw, totalw = (
            empirical_probability(
                draws,
                index,
                pair
            )
        )

        result.append({
            "rank": rank,
            "pair": pair,
            "score": score,
            "probability": prob,
            "historical_weighted_hits": hitw,
            "historical_weight": totalw
        })

    return result


# ============================================================
# BACKTEST TEMPOREL
# ============================================================

def backtest(draws):

    if len(draws) < MIN_HISTORY + 10:
        return

    last_start = max(
        MIN_HISTORY + 3,
        len(draws) - BACKTEST_MAX
    )

    tests = []
    pair_hits = Counter()

    print()
    print(
        Fore.CYAN
        + "=" * 72
    )
    print(
        Fore.CYAN
        + "BACKTEST WALK-FORWARD — TRUE WINDOW 3"
    )
    print(
        Fore.CYAN
        + "=" * 72
    )

    for index in range(
        last_start,
        len(draws) - 3,
        BACKTEST_STEP
    ):

        try:

            predictions = forecast(
                draws,
                index
            )

        except Exception:
            continue

        future = draws[
            index:index + 3
        ]

        hit_count = 0

        for p in predictions:

            pair = p["pair"]

            hit = pair_in_block(
                pair,
                future
            )

            if hit:
                hit_count += 1
                pair_hits[pair] += 1

        tests.append(
            {
                "index": index,
                "hits": hit_count,
                "any": hit_count > 0
            }
        )

    if not tests:
        print(
            Fore.RED
            + "Backtest impossible."
        )
        return

    total = len(tests)

    any_rate = (
        sum(x["any"] for x in tests)
        / total
        * 100
    )

    pair_rate = (
        sum(x["hits"] for x in tests)
        / (total * 3)
        * 100
    )

    print(
        f"Tests effectués : {total}"
    )

    print(
        f"Au moins 1 paire touchée : "
        f"{any_rate:.2f}%"
    )

    print(
        f"Taux moyen par paire : "
        f"{pair_rate:.2f}%"
    )

    # --------------------------------------------------------
    # TOP DES PAIRES QUI ONT LE PLUS SOUVENT VALIDÉ
    # --------------------------------------------------------

    print()
    print(
        Fore.YELLOW
        + "PAIRES HISTORIQUEMENT LES PLUS VALIDÉES"
    )

    for pair, hits in pair_hits.most_common(10):

        rate = (
            hits / total * 100
        )

        print(
            f"{pair[0]:02d}-{pair[1]:02d}"
            f"   {hits:3d}/{total}"
            f"   {rate:6.2f}%"
        )


# ============================================================
# AFFICHAGE FINAL
# ============================================================

def show_forecast(
    draws,
    predictions
):

    last = draws[-1]

    print()
    print(
        Fore.CYAN
        + "=" * 72
    )

    print(
        Fore.CYAN
        + "THE FORECASTER SHARP TWO"
    )

    print(
        Fore.CYAN
        + "TRUE WINDOW 3"
    )

    print(
        Fore.CYAN
        + "=" * 72
    )

    print()
    print(
        f"Dernier tirage connu : "
        f"{last['day']} — {last['name']}"
    )

    print(
        "Bloc cible : "
        "les 3 prochains tirages chronologiques"
    )

    print(
        "Source : Gagnants + Machines"
    )

    print()
    print(
        Fore.YELLOW
        + "TOP 3 VIP — PAIRES 100 % UNIQUES"
    )

    print(
        Fore.YELLOW
        + "-" * 72
    )

    for p in predictions:

        a, b = p["pair"]

        print()

        print(
            Fore.GREEN
            + f"RANG {p['rank']} : "
            + Fore.WHITE
            + f"{a:02d} - {b:02d}"
        )

        print(
            f"Score moteur : "
            f"{p['score']:.5f}"
        )

        print(
            f"Probabilité empirique bloc 3 : "
            f"{p['probability'] * 100:.2f}%"
        )

        print(
            f"Validation historique pondérée : "
            f"{p['historical_weighted_hits']:.2f}"
        )

    print()

    # Vérification unicité
    all_numbers = []

    for p in predictions:
        all_numbers.extend(
            p["pair"]
        )

    unique = (
        len(all_numbers)
        == len(set(all_numbers))
    )

    print(
        "Contrôle unicité : "
        + (
            Fore.GREEN
            + "OK — 6 numéros différents"
            if unique
            else
            Fore.RED
            + "ERREUR"
        )
    )

    print(
        Fore.CYAN
        + "=" * 72
    )


