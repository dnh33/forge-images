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
