"""The owner gate is executable, so test it as code, not as YAML text.

A gate nobody has watched fail is not a gate: these run scripts/gate.py as a
subprocess with a forged ACTOR against a temporary facts file and check the
exit status — the whole contract the workflow depends on.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATE = REPO / "scripts" / "gate.py"

OWNER = "the-owner"


def run_gate(actor, owner=OWNER, facts=None):
    env = dict(os.environ, ACTOR=actor)
    if owner is None:
        env["FACTS"] = str(Path(os.environ.get("TMPDIR", "/tmp")) / "missing-facts.json")
    else:
        path = Path(env.get("TMPDIR", "/tmp")) / f"facts-{owner}-{actor}.json"
        path.write_text(
            json.dumps(facts if facts is not None else {"owner": owner}),
            encoding="utf-8",
        )
        env["FACTS"] = str(path)
    return subprocess.run(
        [sys.executable, str(GATE)], env=env, capture_output=True, text=True, timeout=30
    )


def test_gate_passes_for_the_owner():
    r = run_gate(OWNER)
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert OWNER in r.stdout


def test_gate_fails_for_a_non_owner():
    r = run_gate("not-the-owner")
    assert r.returncode != 0, "a non-owner must be refused"
    assert "not-the-owner" in r.stderr and OWNER in r.stderr


def test_gate_is_case_insensitive():
    # GitHub logins are case-insensitive; a cased actor must not be locked out.
    r = run_gate(OWNER.upper())
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)


def test_gate_fails_closed_when_the_facts_file_is_unreadable():
    # No file, no owner, no run: the gate must refuse rather than allow.
    r = run_gate(OWNER, owner=None)
    assert r.returncode != 0, "a missing facts file must fail closed"


def test_gate_fails_closed_when_owner_is_blank_or_missing():
    for facts in ({"owner": ""}, {"owner": "   "}, {"note": "no owner field"}):
        r = run_gate(OWNER, facts=facts)
        assert r.returncode != 0, f"must refuse with facts={facts}"


def test_the_committed_facts_file_names_the_real_owner():
    # The workflow reads the committed file; it must carry a usable owner.
    facts = json.loads((REPO / "context" / "facts.json").read_text(encoding="utf-8"))
    assert isinstance(facts.get("owner"), str) and facts["owner"].strip()
