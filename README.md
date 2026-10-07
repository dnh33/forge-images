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

The model files are four lines of `env:` in the workflow. Swap them and the pipeline renders something else;
no code moves.

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

An `adhoc` input accepts a base64-encoded set. It is merged into the run and **never committed** — for a quick
idea that does not deserve a file. The desktop app uses this for interactive work.

```bash
python3 - <<'PY' | base64 -w0
import json
print(json.dumps({"name":"adhoc","size":[768,1024],"style":"cinematic, 35mm","items":{"a":{"seed":1,"line":"a lighthouse in a storm"}}}))
PY
```

## How it works

1. **plan** — `scripts/plan.py` resolves every job (prompt text, size, seed, steps) and shards them.
2. **render** — `scripts/render.py` renders each shard. Shards run in parallel; the model is downloaded once per shard.
3. **publish** — artifacts are merged onto the `renders` branch, contact sheets are rebuilt, and the index page is written.

## Cost and speed

Free. The trade is time: CPU rendering means roughly a minute or two per image on a runner, versus a few seconds
on a GPU. Sharding is how a batch finishes in reasonable wall-clock time. For interactive work, run the same
prompts locally on a GPU (ComfyUI); this pipeline is for the batch.

## Driving it from the desktop app

[forge-studio](https://github.com/dnh33/forge-studio) is a Tauri desktop app that writes sets, dispatches the
workflow, streams the run's status via the GitHub API, previews the renders and offers to download them.

## License

Apache-2.0. Model weights are Apache-2.0 (FLUX.1-schnell); the runtime is MIT.
