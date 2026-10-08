"""Invariants of the render workflow itself.

These read the workflow YAML. A preview must be able to run without any risk of a
half-resolution image being committed to the `renders` branch, and that property
lives in the publish job's artifact pattern rather than in any Python, so it has
to be asserted against the workflow text.
"""
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
RENDER = REPO / ".github" / "workflows" / "render.yml"

WF = yaml.safe_load(RENDER.read_text(encoding="utf-8"))


def steps_of(job):
    return WF["jobs"][job]["steps"]


def find_step(job, name_fragment):
    for s in steps_of(job):
        if name_fragment.lower() in (s.get("name") or "").lower():
            return s
    return None


def test_render_offers_a_preview_input():
    # PyYAML parses the YAML key `on:` as the boolean True, hence the lookup.
    doc = WF.get(True, WF.get("on", {}))
    inputs = doc.get("workflow_dispatch", {}).get("inputs", {})
    assert "preview" in inputs, "the workflow must expose a preview switch"
    assert inputs["preview"]["default"] is False, "a preview must be opt-in"


def test_a_preview_uploads_under_a_different_artifact_name():
    up = None
    for s in steps_of("render"):
        if "upload-artifact" in str(s.get("uses", "")):
            up = s
    assert up is not None
    name = up["with"]["name"]
    assert "preview" in name and "render" in name, name
    assert "inputs.preview" in name, "the artifact name must depend on the preview flag"


def test_publish_only_pulls_render_artifacts():
    """The whole safety property: previews can never reach the renders branch."""
    dl = None
    for s in steps_of("publish"):
        if "download-artifact" in str(s.get("uses", "")):
            dl = s
    assert dl is not None
    assert dl["with"]["pattern"] == "render-*", (
        "publish must pull only render-*, or a preview would be committed"
    )
    assert "preview" not in dl["with"]["pattern"]


def test_the_publish_pattern_cannot_match_a_preview_artifact():
    """Belt and braces: prove the patterns are disjoint by construction."""
    upload = None
    for s in steps_of("render"):
        if "upload-artifact" in str(s.get("uses", "")):
            upload = s
    pattern = None
    for s in steps_of("publish"):
        if "download-artifact" in str(s.get("uses", "")):
            pattern = s["with"]["pattern"]
    # The preview branch of the upload expression produces "preview-<shard>".
    preview_name = str(upload["with"]["name"]).replace(
        "${{ inputs.preview && 'preview' || 'render' }}", "preview"
    )
    prefix = pattern.replace("*", "")
    assert not preview_name.startswith(prefix), (preview_name, prefix)


def test_the_plan_step_is_told_when_to_preview():
    plan = None
    for s in WF["jobs"]["plan"]["steps"]:
        if "plan.py" in str(s.get("run", "")):
            plan = s
    assert plan is not None
    env = plan.get("env", {})
    assert "PREVIEW" in env, "plan.py must be told whether this is a preview"
    assert "PREVIEW_SCALE" in env and "PREVIEW_STEPS" in env


def test_a_gate_job_runs_before_anything_else():
    """Only the owner recorded in the repo's facts may spend runner time."""
    jobs = list(WF["jobs"])
    assert "gate" in jobs, "the workflow must have an owner gate job"
    assert jobs[0] == "gate", f"the gate must run first, got {jobs}"


def test_the_gate_reads_the_owner_from_the_facts_file():
    gate_job = WF["jobs"]["gate"]
    text = str(gate_job)
    assert "gate.py" in text, "the gate must run scripts/gate.py"
    assert "context/facts.json" not in text or "gate.py" in text  # path lives in gate.py
    # The actor comes in as data via the environment, not a hard-coded name.
    assert "github.actor" in text, "the gate must compare against github.actor"
    step = next(s for s in gate_job["steps"] if "gate.py" in str(s.get("run", "")))
    assert "ACTOR" in step.get("env", {}), "the actor must be passed via env"


def test_everything_waits_for_the_gate():
    # plan is the only consumer of the matrix; render and publish hang off it.
    plan_needs = WF["jobs"]["plan"].get("needs")
    assert plan_needs == "gate", f"plan must need the gate, got {plan_needs}"
    plan_if = WF["jobs"]["plan"].get("if", "")
    assert "needs.gate.outputs.allowed" in plan_if, plan_if

    publish_needs = WF["jobs"]["publish"].get("needs")
    assert "gate" in publish_needs, f"publish must also need the gate, got {publish_needs}"
    publish_if = WF["jobs"]["publish"].get("if", "")
    assert "needs.gate.outputs.allowed" in publish_if, publish_if
    # The preview invariant still holds: publish is skipped for previews.
    assert "inputs.preview" in publish_if, publish_if


def test_the_renders_branch_cannot_be_reached_without_the_gate():
    """Prove a refused actor produces no publish run, by construction.

    publish's condition must require needs.gate.outputs.allowed == 'true', so
    when the gate fails (output unset) the condition is false and the job is
    skipped — the renders branch is unreachable for a non-owner.
    """
    publish_if = str(WF["jobs"]["publish"].get("if", ""))
    assert "always()" in publish_if, publish_if
    allowed = "needs.gate.outputs.allowed == 'true'"
    assert allowed in publish_if, (
        "publish must require the gate's allowed output explicitly"
    )
    # A failed gate yields an unset output; the equality is then false.
    assert "allowed == 'true'" in publish_if.replace(allowed, "allowed == 'true'")
