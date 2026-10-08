# forge-images

A free, public batch image pipeline: write prompt sets as JSON, run a workflow, get contact sheets back.

No API keys, no credits, no GPU. The images are rendered on GitHub-hosted runners, which are free for public
repositories, by a small open model.

## The stack

| | |
|---|---|
| **Model** | [FLUX.1-schnell](https://huggingface.co/black-forest-labs/FLUX.1-schnell) by Black Forest Labs, Apache-2.0, as a Q4_K_S GGUF ([city96](https://huggingface.co/city96/FLUX.1-schnell-gguf)) |
| **Runtime** | [stable-diffusion.cpp](https://github.com/leejet/stable-diffusion.cpp) (MIT), CPU only |
| **Compute** | GitHub-hosted `ubuntu-latest` runners — free for public repositories |
| **Output** | the `renders` branch (PNG + a JSON sidecar per image, contact sheets in `renders/sheets/`) and the run's artifacts |

The model files are a few lines of `env:` in the workflow. Swap them and the pipeline renders something else;
no code moves. Which variables a given model needs, and how to prove a swap with a measured run, is in
[docs/MODELS.md](docs/MODELS.md).

## Run it

**Actions → _Render_ → Run workflow.** Choose a set (`all`, or a file in `prompts/` without `.json`), optionally
a comma-separated list of item ids, and the number of seeds per item.

## Prompt sets

One JSON file per set in `prompts/`. The file is self-describing:

```json
{
  "name": "Portraits",
  "size": [768, 1024],
  "style": "One shared style block, appended to every item line.",
  "items": {
    "forgemaster": { "seed": 1103, "line": "The subject of this image." }
  }
}
```

- `size` — the canvas, `[width, height]`.
- `style` — shared text appended to each item, so a set is stylistically coherent.
- `items` — one entry per image. `seed` is fixed so a re-run is reproducible; each added variant uses `seed + n*1000`.

## One-off prompts

An `adhoc` input accepts a base64-encoded set. It is **never committed** — for a quick idea that does not
deserve a file. When `set` is left at `all` (the default), an ad-hoc payload renders **only** that payload:
it is not merged into the committed sets, so a one-off prompt never silently queues the whole library.
Name a set explicitly if you want that set *and* the ad-hoc items in the same run.

```bash
python3 - <<'PY' | base64 -w0
import json
print(json.dumps({"name":"adhoc","size":[768,1024],"style":"cinematic, 35mm","items":{"a":{"seed":1,"line":"a lighthouse in a storm"}}}))
PY
```

## How it works

1. **plan** — `scripts/plan.py` resolves every job (prompt text, size, seed, steps) and shards them.
2. **render** — `scripts/render.py` renders each shard. Shards run in parallel; the model is cached between runs.
   A shard holds at most six images (`MAX_PER_SHARD`), so no shard can outlive the job timeout.
3. **publish** — artifacts are merged onto the `renders` branch, contact sheets are rebuilt, and the index page is written.

## Tests

```bash
python3 -m pytest tests -q     # no network, no GPU
```

The suite runs on every push (`.github/workflows/ci.yml`). It pins the job-matrix contract, the exact argv handed to
the runtime, the ad-hoc rules, the sharding guards and the sidecar provenance. It finishes in seconds because it
stubs the runtime instead of rendering: a test that needed a 45-minute render would not be run.

## Cost and speed

Free. The trade is time, and the trade is steep — measured, not estimated:

| | |
|---|---|
| one 768x1024 image, 4 steps, FLUX.1-schnell Q4_K_S | **2702 s (45 min)** on a free `ubuntu-latest` runner (4 vCPU) |
| the same render on a mid-range desktop GPU | a few seconds |

That number is recorded in every image's JSON sidecar (`seconds`), so it can be checked rather than
trusted. Two independent runs measured **2702 s** and **2699 s** for the same prompt and canvas, so the
figure reproduces to within 0.1%. Plan for it: a single image is an hour-class job, which is exactly why
the pipeline shards a batch across parallel jobs — a shard only pays the model download once, and
wall-clock falls as you add shards. Keep each shard to a small number of images so it stays inside the
job timeout.

Which model is the default is a measurement, not a preference. `benchmark.yml` renders one image per
model profile on the same canvas and records the seconds in each sidecar; the run summary carries the
comparison table. See [docs/MODELS.md](docs/MODELS.md) for the profiles, the measured table, and how to
add one. The short version: Z-Image-Turbo is quicker per step and slightly more detailed, but it needs
eight steps against schnell's four, making it 74% slower to a finished image (4689 s against 2699 s).
The default stays schnell.

For interactive work, run the same prompts locally on a GPU (ComfyUI). This pipeline is for the batch
that can wait.

## Driving it from the desktop app

[forge-studio](https://github.com/dnh33/forge-studio) is a Tauri desktop app that writes sets, dispatches the
workflow, streams the run's status via the GitHub API, previews the renders and offers to download them.

## License

Apache-2.0. Model weights are Apache-2.0 (FLUX.1-schnell); the runtime is MIT.
