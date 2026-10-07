"""Tests for sheet.py, the step that turns a run's artifacts into something a
human can actually look at: one contact sheet per set, plus an index page.
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "sheet.py"


def make_image(path, size=(64, 96), colour=(120, 40, 20)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colour).save(path)


def make_sidecar(path, **over):
    meta = {
        "kind": "portraits", "id": "marshal", "seed": 1101, "steps": 4,
        "size": [64, 96], "seconds": 2702, "prompt": "a hooded figure",
        "model": "FLUX.1-schnell Q4_K_S GGUF (Apache-2.0)", "runner": "Linux/X64",
    }
    meta.update(over)
    path.write_text(json.dumps(meta))


def run_sheet(tmp_path):
    return subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=tmp_path,
        capture_output=True, text=True,
    )


def test_sheet_and_index_are_built_for_a_set(tmp_path):
    make_image(tmp_path / "renders" / "portraits" / "portraits-marshal-s1101.png")
    make_sidecar(tmp_path / "renders" / "portraits" / "portraits-marshal-s1101.json")
    p = run_sheet(tmp_path)
    assert p.returncode == 0, p.stderr
    assert (tmp_path / "renders" / "sheets" / "portraits.jpg").exists()
    index = (tmp_path / "renders" / "README.md").read_text()
    assert "portraits" in index
    assert "sheets/portraits.jpg" in index, "the sheet must be embedded in the index"


def test_index_row_carries_the_settings_that_made_the_image(tmp_path):
    make_image(tmp_path / "renders" / "portraits" / "portraits-marshal-s1101.png")
    make_sidecar(tmp_path / "renders" / "portraits" / "portraits-marshal-s1101.json")
    run_sheet(tmp_path)
    index = (tmp_path / "renders" / "README.md").read_text()
    assert "1101" in index, "seed"
    assert "2702" in index, "the measured render time"
    assert "portraits/portraits-marshal-s1101.png" in index, "a link to the image itself"


def test_multiple_sets_each_get_a_sheet(tmp_path):
    for kind, item in (("portraits", "marshal"), ("scenes", "kiln-district")):
        base = f"{kind}-{item}-s1101"
        make_image(tmp_path / "renders" / kind / f"{base}.png")
        make_sidecar(tmp_path / "renders" / kind / f"{base}.json", kind=kind, id=item)
    p = run_sheet(tmp_path)
    assert p.returncode == 0, p.stderr
    assert (tmp_path / "renders" / "sheets" / "portraits.jpg").exists()
    assert (tmp_path / "renders" / "sheets" / "scenes.jpg").exists()


def test_an_empty_set_is_skipped_not_crashed(tmp_path):
    (tmp_path / "renders" / "empty").mkdir(parents=True)
    make_image(tmp_path / "renders" / "portraits" / "portraits-marshal-s1101.png")
    make_sidecar(tmp_path / "renders" / "portraits" / "portraits-marshal-s1101.json")
    p = run_sheet(tmp_path)
    assert p.returncode == 0, p.stderr
    assert not (tmp_path / "renders" / "sheets" / "empty.jpg").exists()


def test_nothing_to_do_is_not_an_error(tmp_path):
    (tmp_path / "renders").mkdir(parents=True)
    p = run_sheet(tmp_path)
    assert p.returncode == 0, p.stderr


def test_a_corrupt_sidecar_does_not_break_the_index(tmp_path):
    make_image(tmp_path / "renders" / "portraits" / "portraits-marshal-s1101.png")
    make_sidecar(tmp_path / "renders" / "portraits" / "portraits-marshal-s1101.json")
    bad = tmp_path / "renders" / "portraits" / "portraits-broken-s9.json"
    bad.write_text("{ this is not json")
    p = run_sheet(tmp_path)
    assert p.returncode == 0, "one unreadable sidecar must not lose the whole index"
    index = (tmp_path / "renders" / "README.md").read_text()
    assert "marshal" in index


def test_derived_layers_are_not_mistaken_for_renders(tmp_path):
    """cut/depth/glow layers live beside the render; the sheet shows the render."""
    make_image(tmp_path / "renders" / "portraits" / "portraits-marshal-s1101.png")
    make_sidecar(tmp_path / "renders" / "portraits" / "portraits-marshal-s1101.json")
    make_image(tmp_path / "renders" / "portraits" / "portraits-marshal-s1101.depth.png")
    p = run_sheet(tmp_path)
    assert p.returncode == 0, p.stderr
    index = (tmp_path / "renders" / "README.md").read_text()
    assert index.count("marshal") >= 1
