"""Tests for bench_report.py, which turns sidecars into a comparison table."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "bench_report.py"


def write_sidecar(dirpath, name, model, seconds, size=(768, 1024), steps=4):
    out = dirpath / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps({
        "model": model, "seconds": seconds, "steps": steps, "size": list(size),
    }))


def run(tmp_path):
    summary = tmp_path / "summary.md"
    p = subprocess.run(
        [sys.executable, str(SCRIPT), str(summary)],
        cwd=tmp_path, capture_output=True, text=True,
    )
    return p, (summary.read_text() if summary.exists() else "")


def test_table_lists_every_sidecar(tmp_path):
    write_sidecar(tmp_path, "a.json", "Model A (Apache-2.0)", 2702)
    write_sidecar(tmp_path, "b.json", "Model B (Apache-2.0)", 900)
    p, text = run(tmp_path)
    assert p.returncode == 0, p.stderr
    assert "Model A (Apache-2.0)" in text and "2702" in text
    assert "Model B (Apache-2.0)" in text and "900" in text
    assert text.count("| --- |") == 1, "one header, one separator"


def test_no_sidecars_is_not_a_crash(tmp_path):
    p, text = run(tmp_path)
    assert p.returncode == 0, p.stderr
    assert "model" in text, "the header is still emitted so the summary reads correctly"


def test_a_corrupt_sidecar_is_skipped(tmp_path):
    write_sidecar(tmp_path, "good.json", "Good Model", 10)
    (tmp_path / "out" / "bad.json").write_text("{ not json")
    p, text = run(tmp_path)
    assert p.returncode == 0, p.stderr
    assert "Good Model" in text
