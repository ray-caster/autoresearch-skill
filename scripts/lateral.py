# /// script
# requires-python = ">=3.10"
# ///
"""Lateral-thinking briefs for the autoresearch researcher.

When a branch closes (and at the start of a run, or when the idea list is used up) the driver asks this module
for a brief: ONE technique from autoresearch/lateral_techniques.json plus ONE random stimulus of that
technique's kind (a knowledge-base card from a near, middle or far field, a book, an unused dataset field, a
pooled alpha to invert, a provocation, a random cell of the design space...). The researcher must turn it into
a few tagged ideas ("technique", "stimulus") before reading the history, using a fixed protocol: abstract the
problem, plan five distinct directions, map by function, check field names, then de-duplicate.

Which techniques work is LEARNED: an idea's outcome (kept / falsified / tried, and whether its branch joined the
pool) is credited to its technique, and the next technique is drawn by Thompson sampling on those counts, so
productive techniques come up more often while every technique keeps some chance.

    uv run --python 3.12 autoresearch/lateral.py --sample            # print a brief for the current state
    uv run --python 3.12 autoresearch/lateral.py --sample --technique book_lens
    uv run --python 3.12 autoresearch/lateral.py --stats             # outcome table (also runs/lateral_stats.md)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(os.environ.get("AR_ROOT") or Path(__file__).resolve().parent.parent)
AR = ROOT / "autoresearch"
RUNS = AR / "runs"
DEFAULTS = {"enabled": True, "deck": "autoresearch/lateral_techniques.json", "books": "autoresearch/lateral_books.md",
            "kb": r"C:\ClaudeWork\Research\kb.sqlite", "fields": "reference/fields.tsv", "n_ideas": 3,
            "forced_seed_every": 2, "distance_weights": {"near": 0.25, "mid": 0.35, "far": 0.40}}
NEAR = ("Quant/", "Personal/finance")
MID = ("Maths/", "Computing/artificial-intelligence", "Computing/computational-theory", "Engineering/systems")
SKIP_TOPICS = ("Quant/brain",)  # the loop's own notes are not a stimulus
ID_RE = re.compile(r"\[(I\d+)\]")


def settings(cfg: dict | None) -> dict:
    out = {**DEFAULTS, **((cfg or {}).get("lateral") or {})}
    out["distance_weights"] = {**DEFAULTS["distance_weights"], **(out.get("distance_weights") or {})}
    return out


def load_deck(lc: dict) -> dict:
    return json.loads((ROOT / lc["deck"]).read_text(encoding="utf-8-sig"))


# ---------------------------------------------------------------- outcomes per technique
def all_ideas() -> dict[str, dict]:
    """Every idea ever listed (archive first, then the live list, so a later tag wins)."""
    ideas: dict[str, dict] = {}
    arch = RUNS / "ideas_archive.jsonl"
    if arch.exists():
        for line in arch.read_text(encoding="utf-8").splitlines():
            try:
                i = json.loads(line)
                ideas[str(i["id"])] = {**ideas.get(str(i["id"]), {}), **i}
            except (ValueError, KeyError, TypeError):
                pass
    try:
        for i in json.loads((RUNS / "ideas.json").read_text(encoding="utf-8-sig")):
            if isinstance(i, dict) and i.get("id"):
                ideas[str(i["id"])] = {**ideas.get(str(i["id"]), {}), **i}
    except (OSError, ValueError):
        pass
    return ideas


def outcomes(state: dict, deck: dict) -> dict[str, Counter]:
    ideas = all_ideas()
    status = state.get("idea_status", {})
    pooled_seeds = {m for b in state.get("branches", []) if b.get("status") == "pooled"
                    for m in ID_RE.findall(str(b.get("seed", "")))}
    out = {t["id"]: Counter() for t in deck["techniques"]}
    for iid, i in ideas.items():
        tech = i.get("technique")
        if tech not in out:
            continue
        c = out[tech]
        c["ideas"] += 1
        c[status.get(iid, "untried")] += 1
        if iid in pooled_seeds:
            c["pooled"] += 1
    return out


def choose_technique(deck: dict, state: dict, rng: random.Random, last: str | None) -> dict:
    """Thompson sampling: Beta(1 + kept + 2*pooled, 1 + falsified + 0.5*tried) per technique."""
    oc = outcomes(state, deck)
    best, best_draw = None, -1.0
    for t in deck["techniques"]:
        c = oc[t["id"]]
        draw = rng.betavariate(1 + c["kept"] + 2 * c["pooled"], 1 + c["falsified"] + 0.5 * c["tried"])
        if t["id"] == last:
            draw *= 0.5  # avoid the same technique twice in a row unless it is clearly the best
        if draw > best_draw:
            best, best_draw = t, draw
    return best


# ---------------------------------------------------------------- stimuli
def distance_class(topic: str) -> str:
    if topic.startswith(NEAR):
        return "near"
    if topic.startswith(MID):
        return "mid"
    return "far"


def kb_card(lc: dict, rng: random.Random) -> tuple[str, str, dict]:
    w = lc["distance_weights"]
    dist = rng.choices(list(w), weights=list(w.values()))[0]
    con = sqlite3.connect(f"file:{lc['kb']}?mode=ro", uri=True, timeout=30)
    try:
        rows = con.execute("SELECT id, topic FROM docs WHERE kind = 'card' AND summary IS NOT NULL").fetchall()
        pick = [r for r in rows if not str(r[1]).startswith(SKIP_TOPICS) and distance_class(str(r[1])) == dist]
        cid, topic = rng.choice(pick or rows)
        title, summary = con.execute("SELECT title, summary FROM docs WHERE id = ?", (cid,)).fetchone()
    finally:
        con.close()
    text = f"Knowledge-base card #{cid} ({topic}, a {dist} field): {title}\n{(summary or '').strip()[:900]}"
    return text, f"kb #{cid} {title[:60]}", {"distance": dist, "ref": f"kb card #{cid}"}


def book(lc: dict, rng: random.Random) -> tuple[str, str, dict]:
    titles = []
    p = ROOT / lc["books"]
    if p.exists():
        titles = [l[2:].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.startswith("- ") and l[2:].strip()]
    kb_titles = []
    if rng.random() < 0.3 or not titles:  # sometimes a textbook from the user's own library
        try:
            con = sqlite3.connect(f"file:{lc['kb']}?mode=ro", uri=True, timeout=30)
            kb_titles = [f"{t} (a textbook in the user's library, #{i}, topic {tp})"
                         for i, t, tp in con.execute("SELECT id, title, topic FROM docs WHERE kind = 'paper'")
                         if not str(tp).startswith(SKIP_TOPICS)]
            con.close()
        except sqlite3.Error:
            pass
    title = rng.choice(kb_titles or titles)
    dist = "near" if re.search(r"invest|stock|market|financ|value|trad|money|crowd|bubble|alchemy|short", title, re.I) else "far"
    return f"Book: {title}", title[:70], {"distance": dist, "ref": title[:120]}


def unused_field(lc: dict, rng: random.Random) -> tuple[str, str, dict]:
    rows = list(csv.DictReader((ROOT / lc["fields"]).open(encoding="utf-8-sig"), delimiter="\t"))
    used_text = (AR / "results.tsv").read_text(encoding="utf-8", errors="replace") if (AR / "results.tsv").exists() else ""
    used_fields = set(re.findall(r"[a-z][a-z0-9_]{2,}", used_text))
    by_ds: dict[str, list[dict]] = {}
    for r in rows:
        try:
            cov = float(r.get("coverage") or 0)
        except ValueError:
            cov = 0.0
        if r.get("type") == "MATRIX" and cov >= 0.5:
            by_ds.setdefault(r["dataset"], []).append(r)
    usage = {ds: sum(1 for r in fs if r["id"] in used_fields) for ds, fs in by_ds.items()}
    least = min(usage.values())
    ds = rng.choice([d for d, u in usage.items() if u <= least + 1])
    fresh = [r for r in by_ds[ds] if r["id"] not in used_fields] or by_ds[ds]
    r = rng.choice(fresh)
    text = (f"Field `{r['id']}` (dataset {ds}, coverage {r['coverage']}, {r['type']}): {r.get('description', '')}\n"
            f"Dataset {ds} has {len(by_ds[ds])} well-covered fields; this run has used {usage[ds]} of them so far.")
    return text, f"{r['id']} ({ds})", {"distance": "near", "ref": r["id"]}


def pool_alpha(state: dict, rng: random.Random) -> tuple[str, str, dict]:
    pool = state.get("pool") or []
    if not pool:
        return "No pooled alpha yet: use the current best idea of the run instead.", "current best", {"distance": "near"}
    p = rng.choice(pool)
    idea = re.sub(r"\[own idea[^\]]*\]\s*", "", str(p.get("idea", "")))
    return (f"Pooled alpha {p['branch']} (score {p.get('score')}): {idea[:600]}", f"pool {p['branch']}",
            {"distance": "near", "ref": p["branch"]})


FALLBACK = {"field": "kb_card", "kb_card": "provocation", "book": "provocation", "pool_alpha": "assumption"}


def stimulus(kind: str, lc: dict, deck: dict, state: dict, rng: random.Random) -> tuple[str, str, dict]:
    """A stimulus of this kind, or of the next kind in FALLBACK when its source (knowledge base, fields file,
    pool, deck list) is missing in this project."""
    for _ in range(4):
        try:
            out = _stimulus(kind, lc, deck, state, rng)
            if out[1] != "-":
                return out
        except (OSError, sqlite3.Error, KeyError, IndexError, ValueError):
            pass
        kind = FALLBACK.get(kind, "provocation")
    return "(no stimulus available: apply the technique to the program's current best idea)", "-", {}


def _stimulus(kind: str, lc: dict, deck: dict, state: dict, rng: random.Random) -> tuple[str, str, dict]:
    if kind == "kb_card":
        if not Path(lc["kb"]).exists():
            raise OSError("no knowledge base")
        return kb_card(lc, rng)
    if kind == "book":
        return book(lc, rng)
    if kind == "field":
        return unused_field(lc, rng)
    if kind == "pool_alpha":
        if not state.get("pool"):
            raise KeyError("no pool yet")
        return pool_alpha(state, rng)
    if kind == "field" and not (ROOT / lc["fields"]).exists():
        raise OSError("no fields file")
    if kind == "provocation":
        s = rng.choice(deck["provocations"])
        return s, s[4:60], {"distance": "mid"}
    if kind == "assumption":
        s = rng.choice(deck["assumptions"])
        return f"Assumption to break: {s}", s[:60], {"distance": "near"}
    if kind == "persona":
        s = rng.choice(deck["personas"])
        return f"Persona: {s}", s[:60], {"distance": "far"}
    if kind == "triz":
        a, b = rng.sample(deck["triz"], 2)
        return f"TRIZ principles: {a}; {b}", f"{a} + {b}", {"distance": "mid"}
    if kind == "morph_cell":
        cell = {k: rng.choice(v) for k, v in deck["morph"].items()}
        return ("Design-space cell: " + "; ".join(f"{k} = {v}" for k, v in cell.items()),
                " / ".join(cell.values())[:80], {"distance": "near", "cell": cell})
    return "(no stimulus)", "-", {}


# ---------------------------------------------------------------- the brief
def brief(cfg: dict, state: dict, rnd: int, reason: str, technique: str | None = None) -> tuple[str, dict]:
    lc = settings(cfg)
    deck = load_deck(lc)
    rng = random.Random(f"{state.get('started', '')}|{rnd}|{reason}|{len(state.get('branches', []))}")
    last = (state.get("lateral_log") or [{}])[-1].get("technique")
    t = next((x for x in deck["techniques"] if x["id"] == technique), None) or choose_technique(deck, state, rng, last)
    s_text, s_short, s_meta = stimulus(t["stimulus"], lc, deck, state, rng)
    n_branch = len(state.get("branches", []))
    forced = reason == "branch" and lc["forced_seed_every"] and n_branch % int(lc["forced_seed_every"]) == 0
    rank_rule = ("This branch is a LATERAL branch: rank your best lateral idea FIRST, so it becomes the next seed "
                 "(unless it cannot be expressed with existing fields; then say so in the notes)." if forced else
                 "Rank them on evidence against the other ideas, but put at least one in the top 3.")
    text = "\n".join([
        "", f"===== LATERAL STEP: technique `{t['id']}` ({t['name']}) =====",
        *deck["protocol"], "",
        f"Technique: {t['steps']}", f"(Why this technique: {t['source']})", "",
        f"Stimulus:\n{s_text}", "",
        f"Produce at least {lc['n_ideas']} ideas from this step, tagged \"technique\": \"{t['id']}\". {rank_rule}",
        "===== end of lateral step =====", ""])
    meta = {"round": rnd, "reason": reason, "technique": t["id"], "stimulus": s_short, "forced": bool(forced), **s_meta}
    return text, meta


def record(state: dict, meta: dict, new_ideas: list[dict]) -> None:
    meta = {**meta, "n_ideas": sum(1 for i in new_ideas if i.get("technique") == meta["technique"]),
            "ids": [i["id"] for i in new_ideas if i.get("technique") == meta["technique"]]}
    state.setdefault("lateral_log", []).append(meta)


def stats_table(cfg: dict, state: dict) -> str:
    lc = settings(cfg)
    deck = load_deck(lc)
    oc = outcomes(state, deck)
    briefs = Counter(m.get("technique") for m in state.get("lateral_log", []))
    lines = ["# Lateral techniques: outcomes so far", "",
             "Credited by idea tag. Thompson sampling favours rows with more kept/pooled ideas.", "",
             "| technique | briefs | ideas | kept | pooled | falsified | tried | untried |", "|---|---|---|---|---|---|---|---|"]
    for t in deck["techniques"]:
        c = oc[t["id"]]
        lines.append(f"| {t['id']} | {briefs[t['id']]} | {c['ideas']} | {c['kept']} | {c['pooled']} | {c['falsified']} | "
                     f"{c['tried']} | {c['untried']} |")
    recent = state.get("lateral_log", [])[-10:]
    if recent:
        lines += ["", "Recent briefs:"] + [f"- round {m['round']} ({m['reason']}{', forced seed' if m.get('forced') else ''}): "
                                           f"{m['technique']} / {m.get('stimulus')} -> {m.get('n_ideas', '?')} ideas "
                                           f"{' '.join(m.get('ids', []))}" for m in recent]
    return "\n".join(lines) + "\n"


def write_stats(cfg: dict, state: dict) -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / "lateral_stats.md").write_text(stats_table(cfg, state), encoding="utf-8")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--technique")
    ap.add_argument("--reason", default="branch")
    ap.add_argument("--round", type=int)
    a = ap.parse_args()
    cfg = json.loads((AR / "config.json").read_text(encoding="utf-8-sig"))
    st = json.loads((AR / "state.json").read_text(encoding="utf-8-sig")) if (AR / "state.json").exists() else {}
    if a.sample:
        txt, m = brief(cfg, st, a.round if a.round is not None else random.randrange(10**6), a.reason, a.technique)
        print(txt)
        print(json.dumps(m, ensure_ascii=False))
    if a.stats or not a.sample:
        print(stats_table(cfg, st))
