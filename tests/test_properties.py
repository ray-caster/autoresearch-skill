"""Property-based tests (Hypothesis) for the driver's pure decision helpers: better(), parse_eval(), is_editable().

These decide what is kept and what counts as tampering, so they must hold for every input, not just the
examples in run_tests.py. Tests marked xfail(strict=True) document a known gap (README "Known gaps"); when the
gap is fixed they start passing and strict xfail turns that into a failure, so remove the mark then.

    uv run -q --python 3.12 --with pytest --with hypothesis pytest -q tests/test_properties.py
"""
import json
import math
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import driver  # noqa: E402

finite = st.floats(allow_nan=False, allow_infinity=False, width=64, min_value=-1e12, max_value=1e12)
delta = st.floats(min_value=0.0, max_value=1e6, allow_nan=False)
direction = st.sampled_from(["min", "max"])
SET = settings(max_examples=500, deadline=None)


# ------------------------------------------------------------------ better(): the keep rule
@SET
@given(finite, finite, direction, delta)
def test_better_is_never_mutual(a, b, d, dl):
    assert not (driver.better(a, b, d, dl) and driver.better(b, a, d, dl))


@SET
@given(finite, direction, delta)
def test_equal_score_is_never_better(a, d, dl):
    assert not driver.better(a, a, d, dl)


@SET
@given(finite, finite, delta)
def test_min_is_mirror_of_max(a, b, dl):
    assert driver.better(a, b, "min", dl) == driver.better(-a, -b, "max", dl)


@SET
@given(finite, finite, direction, delta, delta)
def test_bigger_delta_keeps_less(a, b, d, d1, d2):
    lo, hi = sorted((d1, d2))
    if driver.better(a, b, d, hi):
        assert driver.better(a, b, d, lo)


@SET
@given(finite, direction, delta)
def test_first_version_of_a_branch_is_kept(a, d, dl):
    assert driver.better(a, None, d, dl)


@pytest.mark.xfail(strict=True, reason="known gap: an inf/-inf score (e.g. a Sharpe with zero std) is kept and "
                                       "then can never be beaten")
@SET
@given(st.sampled_from([math.inf, -math.inf, math.nan]), finite, direction, delta)
def test_non_finite_score_is_never_kept(bad, best, d, dl):
    score, _, _ = driver.parse_eval(json.dumps({"score": bad}))
    assert not driver.better(score, best, d, dl)


# ------------------------------------------------------------------ parse_eval(): reading the evaluator
json_safe_text = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=60)
noise_line = json_safe_text.filter(lambda s: "\n" not in s and "\r" not in s)


@SET
@given(st.lists(noise_line, max_size=8), finite, st.booleans(),
       st.dictionaries(st.text(max_size=8), finite, max_size=3))
def test_parse_eval_reads_the_final_score_line(junk, score, ok, metrics):
    out = "\n".join(junk + [json.dumps({"score": score, "pass": ok, "metrics": metrics})])
    s, p, m = driver.parse_eval(out)
    assert s == score and p == ok and m == metrics


@SET
@given(finite, finite)
def test_parse_eval_last_score_line_wins(first, last):
    s, _, _ = driver.parse_eval(json.dumps({"score": first}) + "\n" + json.dumps({"score": last}) + "\n")
    assert s == last


@SET
@given(st.lists(noise_line.filter(lambda s: "score" not in s), max_size=8))
def test_parse_eval_refuses_output_without_a_score(junk):
    with pytest.raises(ValueError):
        driver.parse_eval("\n".join(junk))


# ------------------------------------------------------------------ is_editable(): the tamper check
segment = st.text(alphabet="abcdefghijklmnopqrstuvwxyz_.-0123456789", min_size=1, max_size=10).filter(
    lambda s: s not in (".", ".."))
rel_path = st.lists(segment, min_size=1, max_size=4).map("/".join)


@SET
@given(rel_path, rel_path)
def test_exact_glob_matches_only_itself(glob, path):
    """brain-alpha's config lists exact files ("alpha.json"): nothing else may count as editable."""
    if any(c in glob for c in "*?["):
        return
    assert driver.is_editable(path, [glob]) == (path.lower() == glob.lower())


@SET
@given(rel_path)
def test_backslash_paths_match_like_slash_paths(path):
    assert driver.is_editable(path.replace("/", "\\"), [path]) == driver.is_editable(path, [path])


@pytest.mark.xfail(strict=True, reason="known gap: fnmatch's * crosses '/', so a glob like 'src/*.py' also "
                                       "makes src/sub/evaluate.py editable (no live config uses such a glob)")
@SET
@given(segment, st.lists(segment, min_size=1, max_size=3))
def test_star_does_not_cross_directories(top, sub):
    deep = "/".join([top] + sub) + ".py"
    assert not driver.is_editable(deep, [f"{top}/*.py"]) or len(sub) == 1
