"""Tests for plan.py, the step that turns prompt sets into a job matrix.

These run the script the way the workflow does (as a subprocess, with
GITHUB_OUTPUT set) and assert the contract: what gets rendered, how it is
sharded, and that a one-off never drags the whole library in with it.
"""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "plan.py"


def run_plan(tmp_path, **env):
    """Run plan.py. Returns (completed_process, matrix_or_None, github_output_path)."""
    gh_out = tmp_path / "gh_output.txt"
    e = dict(os.environ)
    for k in ("ADHOC", "ONLY", "SET", "SHARDS", "VARIANTS", "STEPS"):
        e.pop(k, None)
    e["GITHUB_OUTPUT"] = str(gh_out)
    for k, v in env.items():
        e[k] = str(v)
    p = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=REPO, env=e,
        capture_output=True, text=True,
    )
    matrix = None
    if p.returncode == 0 and p.stdout.strip():
        matrix = json.loads(p.stdout.splitlines()[0])
    return p, matrix, gh_out


def jobs_of(matrix):
    out = []
    for entry in matrix["include"]:
        out.extend(json.loads(base64.b64decode(entry["jobs"])))
    return out


def shards_of(matrix):
    return [json.loads(base64.b64decode(e["jobs"])) for e in matrix["include"]]


# ----------------------------------------------------------------- basics

def test_all_sets_are_planned(tmp_path):
    p, matrix, _ = run_plan(tmp_path, SET="all", VARIANT=1)
    assert p.returncode == 0, p.stderr
    jobs = jobs_of(matrix)
    kinds = {j["kind"] for j in jobs}
    assert kinds == {"portraits", "scenes"}, "every set in prompts/ must be planned"
    ids = {j["id"] for j in jobs}
    assert "portraits:marshal" in ids
    assert "scenes:kiln-district" in ids


def test_named_set_only(tmp_path):
    p, matrix, _ = run_plan(tmp_path, SET="scenes")
    assert p.returncode == 0, p.stderr
    jobs = jobs_of(matrix)
    assert jobs, "a named set must produce jobs"
    assert {j["kind"] for j in jobs} == {"scenes"}


def test_unknown_set_fails_loudly(tmp_path):
    p, matrix, _ = run_plan(tmp_path, SET="does-not-exist")
    assert p.returncode != 0
    assert "No prompt sets match" in (p.stderr + p.stdout)


def test_only_filters_to_the_named_items(tmp_path):
    p, matrix, _ = run_plan(tmp_path, SET="all", ONLY="marshal")
    assert p.returncode == 0, p.stderr
    jobs = jobs_of(matrix)
    assert len(jobs) == 2, "one item at the default two variants"
    assert all(j["key"] == "marshal" for j in jobs)


def test_only_with_no_match_fails(tmp_path):
    p, matrix, _ = run_plan(tmp_path, SET="all", ONLY="nobody")
    assert p.returncode != 0


# ----------------------------------------------------------------- variants and seeds

def test_variants_multiply_jobs_and_step_the_seed(tmp_path):
    p, matrix, _ = run_plan(tmp_path, SET="portraits", ONLY="marshal", VARIANTS=3)
    assert p.returncode == 0, p.stderr
    jobs = jobs_of(matrix)
    assert len(jobs) == 3
    seeds = sorted(j["seed"] for j in jobs)
    base = 1101
    assert seeds == [base, base + 1000, base + 2000], seeds


def test_every_variant_has_a_distinct_output_name(tmp_path):
    p, matrix, _ = run_plan(tmp_path, SET="portraits", ONLY="marshal", VARIANTS=2)
    jobs = jobs_of(matrix)
    names = {f"{j['kind']}-{j['key']}-s{j['seed']}" for j in jobs}
    assert len(names) == len(jobs), "two variants must not collide on one filename"


# ----------------------------------------------------------------- sharding

def test_shards_split_evenly_and_round_robin(tmp_path):
    p, matrix, _ = run_plan(tmp_path, SET="all", SHARDS=3)
    assert p.returncode == 0, p.stderr
    groups = shards_of(matrix)
    assert len(groups) == 3
    sizes = sorted(len(g) for g in groups)
    assert max(sizes) - min(sizes) <= 1, "shards must be balanced"


def test_shards_never_exceed_the_job_count(tmp_path):
    p, matrix, _ = run_plan(tmp_path, SET="portraits", ONLY="marshal", SHARDS=12, VARIANTS=1)
    assert p.returncode == 0, p.stderr
    assert len(matrix["include"]) == 1, "one job cannot be spread over twelve shards"


def test_every_job_carries_its_own_canvas_and_prompt(tmp_path):
    p, matrix, _ = run_plan(tmp_path, SET="all", VARIANTS=1)
    for j in jobs_of(matrix):
        assert j["w"] > 0 and j["h"] > 0
        assert j["prompt"].strip(), "a job with an empty prompt would render nonsense"
        assert j["steps"]


def test_shared_style_is_appended_to_every_line(tmp_path):
    p, matrix, _ = run_plan(tmp_path, SET="scenes", ONLY="kiln-district", VARIANTS=1)
    jobs = jobs_of(matrix)
    assert len(jobs) == 1
    style = json.loads((REPO / "prompts" / "scenes.json").read_text())["style"]
    assert style[:40] in jobs[0]["prompt"], "the set style must be part of the prompt"


# ----------------------------------------------------------------- ad-hoc

def adhoc_b64(name="probe", size=(512, 512), line="a hooded figure beside a forge"):
    payload = {
        "name": name, "size": list(size), "style": "oil painting",
        "items": {"probe": {"seed": 7, "line": line}},
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def test_adhoc_alone_does_not_render_the_library(tmp_path):
    """The bug this exists to prevent: a one-off prompt also queuing every committed set."""
    p, matrix, _ = run_plan(tmp_path, SET="all", ADHOC=adhoc_b64(), VARIANTS=1)
    assert p.returncode == 0, p.stderr
    jobs = jobs_of(matrix)
    assert len(jobs) == 1
    assert jobs[0]["kind"] == "probe"
    assert {j["kind"] for j in jobs} == {"probe"}, jobs


def test_adhoc_merges_when_a_set_is_named_explicitly(tmp_path):
    p, matrix, _ = run_plan(tmp_path, SET="portraits", ONLY="marshal", ADHOC=adhoc_b64(), VARIANTS=1)
    assert p.returncode == 0, p.stderr
    kinds = {j["kind"] for j in jobs_of(matrix)}
    assert kinds == {"portraits", "probe"}, "an explicit set plus a one-off renders both"


def test_adhoc_keeps_its_own_canvas(tmp_path):
    p, matrix, _ = run_plan(tmp_path, SET="all", ADHOC=adhoc_b64(size=(640, 384)), VARIANTS=1)
    j = jobs_of(matrix)[0]
    assert (j["w"], j["h"]) == (640, 384)


def test_malformed_adhoc_fails(tmp_path):
    p, matrix, _ = run_plan(tmp_path, SET="all", ADHOC="not-base64-json")
    assert p.returncode != 0


# ----------------------------------------------------------------- workflow contract

def test_github_output_has_matrix_and_count(tmp_path):
    p, matrix, gh_out = run_plan(tmp_path, SET="all", VARIANTS=1)
    assert p.returncode == 0, p.stderr
    text = gh_out.read_text()
    assert "matrix=" in text, "the render job needs the matrix from GITHUB_OUTPUT"
    assert "count=" in text, "the count is what the UI reports"


def test_matrix_entries_are_named_for_humans(tmp_path):
    p, matrix, _ = run_plan(tmp_path, SET="all", SHARDS=2)
    for entry in matrix["include"]:
        assert entry["name"].startswith("shard"), "job names must be readable in the Actions UI"
        assert "job(s)" in entry["name"]
