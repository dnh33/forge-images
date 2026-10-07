"""Tests for render.py, the step that actually invokes stable-diffusion.cpp.

The argv matters: it is the whole contract with the runtime, and a wrong flag
means a wasted 45-minute job. These tests pin the argv, the metadata sidecar and
the failure path.
"""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RENDER = REPO / "scripts" / "render.py"
HARNESS = Path(__file__).resolve().parent / "_render_harness.py"


def run_render(tmp_path, jobs, env=None, fail=False):
    """Render `jobs` with a stubbed runtime. Returns (calls, process, out_dir)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    out_dir = tmp_path / "out"
    e = dict(os.environ)
    e["JOBS"] = base64.b64encode(json.dumps(jobs).encode()).decode()
    e["MODELS"] = "models"
    e["SD_BIN"] = "./sd/sd-cli"
    if fail:
        e["STUB_FAIL"] = "1"
    for k, v in (env or {}).items():
        e[k] = str(v)
    p = subprocess.run(
        [sys.executable, str(HARNESS), str(RENDER)],
        cwd=tmp_path, env=e, capture_output=True, text=True,
    )
    calls = None
    calls_file = tmp_path / "calls.json"
    if calls_file.exists():
        calls = json.loads(calls_file.read_text())
    return calls, p, out_dir


def one_job(**over):
    job = {
        "id": "portraits:marshal", "kind": "portraits", "key": "marshal",
        "prompt": "a hooded figure beside a forge", "w": 768, "h": 1024,
        "seed": 1101, "steps": "4",
    }
    job.update(over)
    return [job]


# ----------------------------------------------------------------- argv

def test_argv_carries_the_model_stack(tmp_path):
    calls, p, _ = run_render(tmp_path, one_job())
    assert p.returncode == 0, p.stderr
    assert len(calls) == 1
    cmd = calls[0]
    joined = " ".join(cmd)
    assert "--diffusion-model" in cmd and "flux.gguf" in joined
    assert "--vae" in cmd and "ae.safetensors" in joined
    assert "--clip_l" in cmd and "clip_l.safetensors" in joined
    assert "--t5xxl" in cmd and "t5.gguf" in joined
    assert "--vae-tiling" in cmd, "tiling is what keeps a 16 GB runner from swapping"


def test_argv_carries_canvas_seed_and_sampling(tmp_path):
    calls, _, _ = run_render(tmp_path, one_job(w=640, h=384, seed=42, steps="6"))
    cmd = calls[0]
    assert cmd[cmd.index("-W") + 1] == "640"
    assert cmd[cmd.index("-H") + 1] == "384"
    assert cmd[cmd.index("--seed") + 1] == "42"
    assert cmd[cmd.index("--steps") + 1] == "6"
    assert cmd[cmd.index("--cfg-scale") + 1] == "1.0"
    assert cmd[cmd.index("--sampling-method") + 1] == "euler"
    assert cmd[cmd.index("-p") + 1].startswith("a hooded figure")


def test_output_path_names_the_item_and_seed(tmp_path):
    calls, _, _ = run_render(tmp_path, one_job())
    out = calls[0][calls[0].index("-o") + 1]
    assert out == "out/portraits-marshal-s1101.png"


def test_one_invocation_per_job(tmp_path):
    jobs = one_job() + one_job(id="scenes:kiln", kind="scenes", key="kiln", seed=2102)
    calls, _, _ = run_render(tmp_path, jobs)
    assert len(calls) == 2
    outs = {c[c.index("-o") + 1] for c in calls}
    assert len(outs) == 2, "each job must write its own file"


# ----------------------------------------------------------------- model swapping

def test_optional_model_files_can_be_switched_off(tmp_path):
    """Swapping the model is four env vars; an empty one must drop its flag."""
    calls, _, _ = run_render(tmp_path, one_job(), env={"T5XXL": "", "CLIP_L": "", "VAE": ""})
    cmd = calls[0]
    assert "--t5xxl" not in cmd
    assert "--clip_l" not in cmd
    assert "--vae" not in cmd
    assert "--diffusion-model" in cmd, "the diffusion model itself is never optional"


def test_model_and_sampler_are_overridable(tmp_path):
    calls, _, _ = run_render(
        tmp_path, one_job(),
        env={"DIFFUSION": "other.gguf", "CFG": "3.5", "SAMPLER": "dpm++2m"},
    )
    cmd = calls[0]
    assert "other.gguf" in " ".join(cmd)
    assert cmd[cmd.index("--cfg-scale") + 1] == "3.5"
    assert cmd[cmd.index("--sampling-method") + 1] == "dpm++2m"


# ----------------------------------------------------------------- sidecar

def test_sidecar_records_how_the_image_was_made(tmp_path):
    _, _, out = run_render(tmp_path, one_job())
    side = json.loads((out / "portraits-marshal-s1101.json").read_text())
    assert side["kind"] == "portraits"
    assert side["id"] == "marshal"
    assert side["seed"] == 1101
    assert side["size"] == [768, 1024]
    assert side["steps"] == 4
    assert isinstance(side["seconds"], int), "the timing must be recorded, not guessed"
    assert side["prompt"].startswith("a hooded figure")
    assert side["model"], "provenance: which model produced this file"
    assert side["runner"], "provenance: which platform produced this file"


def test_sidecar_uses_the_configured_model_name(tmp_path):
    _, _, out = run_render(tmp_path, one_job(), env={"MODEL_NAME": "Some Model (Apache-2.0)"})
    side = json.loads((out / "portraits-marshal-s1101.json").read_text())
    assert side["model"] == "Some Model (Apache-2.0)"


# ----------------------------------------------------------------- failure path

def test_a_failed_render_writes_no_sidecar_and_is_reported(tmp_path):
    _, p, out = run_render(tmp_path, one_job(), fail=True)
    assert not (out / "portraits-marshal-s1101.json").exists(), \
        "a failure must not leave metadata claiming an image exists"
    assert "failed" in (p.stdout + p.stderr).lower()
    assert "::error" in p.stdout, "failures must surface as a GitHub annotation"


def test_one_failure_does_not_stop_the_rest_of_the_shard(tmp_path):
    """A shard is a batch; one bad item must not discard the others."""
    jobs = one_job() + one_job(id="portraits:builder", key="builder", seed=1102)
    _, p, _ = run_render(tmp_path, jobs)
    assert p.returncode == 0, "a per-item failure is reported, not fatal to the shard"
    assert "shard done" in p.stdout
