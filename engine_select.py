#!/usr/bin/env python3
"""
SUPERGROCK LOTO BONHEUR - PAIR PREDICTOR v5.4
Version Pydroid - Interaction en boucle
Sélection par NOM DE TIRAGE uniquement
"""

import re
import sys
from collections import defaultdict, Counter
from itertools import combinations
import warnings
warnings.filterwarnings('ignore')

# ====================== COLORAMA ======================
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False
    class Dummy:
        def __getattr__(self, name): return ""
    Fore = Style = Dummy()

def c(text, color):
    if HAS_COLOR:
        return f"{color}{text}{Style.RESET_ALL}"
    return text

# ====================== PARSING ======================
def parse_full_history(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    content = re.sub(r'\n\s*Tirage\s*:', '\n  Tirage :', content)
    content = re.sub(r'\nTirage\s*:', '\n  Tirage :', content)

    history = []
    current_jour = "Inconnu"
    idx = 0

    day_blocks = re.split(r'(?=Jour\s*:)', content)

    for block in day_blocks:
        if not block.strip():
            continue
        jour_match = re.search(r'Jour\s*:\s*(.+)', block)
        if jour_match:
            current_jour = jour_match.group(1).strip()

        tirage_matches = re.finditer(
            r'Tirage\s*:\s*(.+?)\n\s*Gagnants\s*:\s*([\d,\s]+)',
            block, re.DOTALL
        )
        for m in tirage_matches:
            nom = m.group(1).strip()
            nums_raw = m.group(2)
            nums = [int(x.strip()) for x in nums_raw.replace('\n', ' ').split(',') if x.strip().isdigit()]
            if len(nums) == 5 and all(1 <= n <= 90 for n in nums):
                history.append({
                    'jour': current_jour,
                    'tirage': nom,
                    'gagnants': sorted(nums),
                    'index': idx
                })
                idx += 1
    return history

# ====================== STATISTIQUES ======================
def compute_pair_stats(draws_list, window=None):
    data = draws_list[-window:] if window else draws_list
    pair_count = Counter()
    single_count = Counter()
    for d in data:
        for n in d:
            single_count[n] += 1
        for p in combinations(d, 2):
            pair_count[frozenset(p)] += 1
    return pair_count, single_count, len(data)

def geometric_affinity(a, b):
    diff = abs(a - b)
    score = 0.0
    if diff <= 5: score += 1.5
    if (a - 1) // 10 == (b - 1) // 10: score += 0.8
    if a % 2 == b % 2: score += 0.3
    if diff % 9 == 0: score += 0.4
    return score

def ghost_filter(pair_count, single_count, n_draws, threshold=0.12):
    freqs = {n: c / n_draws for n, c in single_count.items()}
    sorted_f = sorted(freqs.items(), key=lambda x: -x[1])
    ghosts = set()
    for n, f in sorted_f[:15]:
        if f > threshold:
            involvement = sum(1 for p in pair_count if n in p)
            if involvement > 35:
                ghosts.add(n)
    return ghosts

def score_pairs(draws_list, recent_window=80, mid_window=250):
    if len(draws_list) < 20:
        recent_window = max(10, len(draws_list) // 2)
        mid_window = len(draws_list)

    full_pairs, full_singles, n_full = compute_pair_stats(draws_list)
    recent_pairs, recent_singles, n_recent = compute_pair_stats(draws_list, recent_window)
    mid_pairs, _, n_mid = compute_pair_stats(draws_list, mid_window)

    ghosts = ghost_filter(full_pairs, full_singles, n_full)

    transition_boost = defaultdict(float)
    for i in range(len(draws_list) - 3):
        current = set(draws_list[i])
        next3 = set()
        for j in range(1, 4):
            next3.update(draws_list[i + j])
        for p in combinations(current, 2):
            fp = frozenset(p)
            if any(n in next3 for n in p):
                transition_boost[fp] += 0.7
            if fp.issubset(next3):
                transition_boost[fp] += 2.5

    max_t = max(transition_boost.values()) if transition_boost else 1.0
    for k in list(transition_boost.keys()):
        transition_boost[k] /= max_t

    scores = {}
    for a, b in combinations(range(1, 91), 2):
        fp = frozenset([a, b])
        rf = (recent_pairs.get(fp, 0) + 0.6) / (n_recent + 1)
        mf = (mid_pairs.get(fp, 0) + 0.4) / (n_mid + 1)
        ff = (full_pairs.get(fp, 0) + 0.15) / (n_full + 1)

        ghost_pen = 0.30 if (a in ghosts or b in ghosts) else 1.0
        geo = 1.0 + 0.20 * geometric_affinity(a, b)
        seq = 1.0 + 1.0 * transition_boost.get(fp, 0)

        sa = recent_singles.get(a, 0) / max(n_recent, 1)
        sb = recent_singles.get(b, 0) / max(n_recent, 1)
        balance = max(0.35, 1.0 - abs(sa - sb) * 2.8)

        score = (0.60 * rf + 0.27 * mf + 0.13 * ff) * ghost_pen * geo * seq * balance
        scores[fp] = score

    return scores, ghosts, n_recent

def select_top3_unique(scores):
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    selected = []
    used = set()
    for fp, sc in ranked:
        nums = list(fp)
        if nums[0] not in used and nums[1] not in used:
            selected.append((sorted(nums), sc))
            used.update(nums)
            if len(selected) == 3:
                break
    return selected

def calibrate_probs(selected, scores, draws_list, window=3):
    n = len(draws_list)
    emp = {}
    start = max(0, n - 400)
    for fp in scores:
        hits = 0
        total = 0
        for i in range(start, n - window):
            block = set()
            for j in range(window):
                block.update(draws_list[i + j])
            if fp.issubset(block):
                hits += 1
            total += 1
        emp[fp] = hits / total if total else 0.01

    raw = [s[1] for s in selected]
    emp_vals = [emp.get(frozenset(s[0]), 0.015) for s in selected]
    total_raw = sum(raw) + 1e-9
    blended = [0.65 * (r / total_raw) + 0.35 * e for r, e in zip(raw, emp_vals)]
    max_b = max(blended) + 1e-9
    scale = 0.20 / max_b
    probs = [max(2.0, min(24.0, b * scale * 100)) for b in blended]
    return probs

