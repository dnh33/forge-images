"""Render one shard's jobs with stable-diffusion.cpp. Writes PNG + JSON metadata to out/.

Everything is resolved by plan.py, so this script reads no prompt files: JOBS is a
base64-encoded JSON list of {id, kind, key, prompt, w, h, seed, steps}.
"""
import base64, json, os, subprocess, time

JOBS = json.loads(base64.b64decode(os.environ["JOBS"]))
SD = os.environ.get("SD_BIN", "./sd/sd-cli")
M = os.environ.get("MODELS", "models")
DEFAULT_STEPS = os.environ.get("STEPS", "4")

# Model files, overridable so the pipeline can swap models without touching code.
# Two families are supported: the CLIP-L + T5 pair that FLUX.1 uses, and the
# single `--llm` text encoder that FLUX.2 and Z-Image use.
DIFFUSION = os.environ.get("DIFFUSION", "flux.gguf")
VAE = os.environ.get("VAE", "ae.safetensors")
CLIP_L = os.environ.get("CLIP_L", "clip_l.safetensors")
T5XXL = os.environ.get("T5XXL", "t5.gguf")
LLM = os.environ.get("LLM", "")
CFG = os.environ.get("CFG", "1.0")
SAMPLER = os.environ.get("SAMPLER", "euler")
THREADS = os.environ.get("THREADS", "")
# Free-form extra flags, e.g. "--offload-to-cpu --diffusion-fa", which both
# FLUX.2 and Z-Image want on a memory-tight CPU host.
EXTRA = os.environ.get("EXTRA", "")
MODEL_NAME = os.environ.get("MODEL_NAME", "FLUX.1-schnell Q4_K_S GGUF (Apache-2.0)")

os.makedirs("out", exist_ok=True)


def build_cmd(job):
    name = f"out/{job['kind']}-{job['key']}-s{job['seed']}"
    cmd = [SD, "-p", job["prompt"], "-W", str(job["w"]), "-H", str(job["h"]),
           "--seed", str(job["seed"]), "-o", name + ".png", "--vae-tiling"]
    if DIFFUSION:
        cmd += ["--diffusion-model", os.path.join(M, DIFFUSION)]
    if VAE:
        cmd += ["--vae", os.path.join(M, VAE)]
    if CLIP_L:
        cmd += ["--clip_l", os.path.join(M, CLIP_L)]
    if T5XXL:
        cmd += ["--t5xxl", os.path.join(M, T5XXL)]
    if LLM:
        # The single text encoder that FLUX.2 and Z-Image take.
        cmd += ["--llm", os.path.join(M, LLM)]
    if CFG:
        cmd += ["--cfg-scale", CFG]
    if SAMPLER:
        cmd += ["--sampling-method", SAMPLER]
    if THREADS:
        cmd += ["-t", THREADS]
    cmd += ["--steps", str(job.get("steps", DEFAULT_STEPS))]
    if EXTRA:
        cmd += EXTRA.split()
    return name, cmd


failed = 0
for job in JOBS:
    name, cmd = build_cmd(job)
    t = time.time()
    print(f"::group::{job['id']} seed {job['seed']} ({job['w']}x{job['h']})", flush=True)
    r = subprocess.run(cmd)
    dt = round(time.time() - t)
    print("::endgroup::", flush=True)
    if r.returncode != 0 or not os.path.exists(name + ".png"):
        print(f"::error file={name}.png::{job['id']} seed {job['seed']} failed (exit {r.returncode})")
        failed += 1
        continue
    json.dump({"kind": job["kind"], "id": job["key"], "seed": job["seed"],
               "steps": int(job.get("steps", DEFAULT_STEPS)), "size": [job["w"], job["h"]],
               "seconds": dt, "prompt": job["prompt"], "model": MODEL_NAME,
               "preview": bool(job.get("preview", False)),
               "runner": os.environ.get("RUNNER_OS", "") + "/" + os.environ.get("RUNNER_ARCH", "")},
              open(name + ".json", "w"), indent=1)
    print(f"{job['id']} seed {job['seed']}: {dt}s", flush=True)
print(f"shard done: {len(JOBS) - failed} ok, {failed} failed")
