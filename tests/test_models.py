"""Model-family tests: the pipeline must be able to swap models from env alone.

FLUX.1 takes a CLIP-L + T5 pair; FLUX.2 and Z-Image take a single `--llm` text
encoder plus flags that matter on a memory-tight CPU host. Both must work from
configuration, with no code change.
"""
import json

from test_render import one_job, run_render


def test_llm_text_encoder_is_passed_through(tmp_path):
    calls, p, _ = run_render(
        tmp_path, one_job(),
        env={"LLM": "Qwen3-4B-Q4_K_M.gguf", "CLIP_L": "", "T5XXL": ""},
    )
    assert p.returncode == 0, p.stderr
    cmd = calls[0]
    assert cmd[cmd.index("--llm") + 1].endswith("Qwen3-4B-Q4_K_M.gguf")
    assert "--t5xxl" not in cmd and "--clip_l" not in cmd, \
        "the FLUX.1 encoders must not be sent to a model that does not take them"


def test_extra_flags_are_appended_verbatim(tmp_path):
    calls, _, _ = run_render(
        tmp_path, one_job(),
        env={"EXTRA": "--offload-to-cpu --diffusion-fa"},
    )
    cmd = calls[0]
    assert "--offload-to-cpu" in cmd
    assert "--diffusion-fa" in cmd


def test_threads_is_passed_to_the_runtime(tmp_path):
    calls, _, _ = run_render(tmp_path, one_job(), env={"THREADS": "4"})
    cmd = calls[0]
    assert cmd[cmd.index("-t") + 1] == "4"


def test_a_z_image_style_invocation_is_well_formed(tmp_path):
    """The exact shape the stable-diffusion.cpp docs give for Z-Image-Turbo."""
    calls, p, _ = run_render(
        tmp_path,
        one_job(steps="8"),
        env={
            "DIFFUSION": "z_image_turbo-Q3_K.gguf",
            "VAE": "ae.safetensors",
            "LLM": "Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
            "CLIP_L": "",
            "T5XXL": "",
            "CFG": "1.0",
            "EXTRA": "--offload-to-cpu --diffusion-fa",
            "MODEL_NAME": "Z-Image-Turbo Q3_K (Apache-2.0)",
        },
    )
    assert p.returncode == 0, p.stderr
    cmd = calls[0]
    joined = " ".join(cmd)
    assert "z_image_turbo-Q3_K.gguf" in joined
    assert "Qwen3-4B-Instruct-2507-Q4_K_M.gguf" in joined
    assert cmd[cmd.index("--steps") + 1] == "8"
    assert cmd[cmd.index("--cfg-scale") + 1] == "1.0"
    assert "--vae-tiling" in cmd


def test_the_sidecar_names_the_model_that_actually_ran(tmp_path):
    _, _, out = run_render(
        tmp_path, one_job(),
        env={"MODEL_NAME": "Z-Image-Turbo Q3_K (Apache-2.0)",
             "DIFFUSION": "z_image_turbo-Q3_K.gguf", "CLIP_L": "", "T5XXL": "",
             "LLM": "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"},
    )
    side = json.loads((out / "portraits-marshal-s1101.json").read_text())
    assert side["model"] == "Z-Image-Turbo Q3_K (Apache-2.0)"
