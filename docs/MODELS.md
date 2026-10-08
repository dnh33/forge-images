# Swapping the model

The pipeline is not married to FLUX.1. A model is five `env:` lines in the
workflow (`render.yml`) plus a `benchmark` run to prove it. No Python changes.

## The two families

`stable-diffusion.cpp` takes text encoders in two shapes. The pipeline supports
both from environment variables.

**FLUX.1 shape** — a CLIP-L plus a T5-XXL:

| var | file | meaning |
|---|---|---|
| `DIFFUSION` | `flux.gguf` | the diffusion model |
| `CLIP_L` | `clip_l.safetensors` | small text encoder |
| `T5XXL` | `t5.gguf` | large text encoder |
| `VAE` | `ae.safetensors` | decoder |
| `LLM` | *(empty)* | not used |

**FLUX.2 / Z-Image shape** — one text encoder passed as `--llm`:

| var | file | meaning |
|---|---|---|
| `DIFFUSION` | `diff.gguf` | the diffusion model |
| `LLM` | `llm.gguf` | the single text encoder |
| `CLIP_L` | *(empty)* | must be empty; the model does not take it |
| `T5XXL` | *(empty)* | must be empty |
| `VAE` | `ae.safetensors` | decoder |

Leaving a variable **empty removes its flag entirely**, so a FLUX.1 model never
receives `--llm` and a Z-Image model never receives `--t5xxl`. That behaviour is
pinned by `tests/test_models.py`.

## The other knobs

| var | default | meaning |
|---|---|---|
| `CFG` | `1.0` | guidance scale. Both Z-Image and FLUX.2 want `1.0` |
| `SAMPLER` | `euler` | sampling method |
| `STEPS` | `4` | sampling steps (schnell is built for 4, Z-Image for 8) |
| `THREADS` | *(unset)* | passed as `-t` when set |
| `EXTRA` | *(unset)* | free-form flags. FLUX.2 and Z-Image want `--offload-to-cpu --diffusion-fa` on a CPU host |
| `MODEL_NAME` | FLUX.1-schnell | recorded verbatim in every sidecar, so provenance is honest |

`--vae-tiling` is always passed: it is what keeps a memory-tight runner from
swapping.

## Verified file locations

These were checked against the Hugging Face API, not assumed:

| model | repo | file |
|---|---|---|
| FLUX.1-schnell Q4_K_S | `city96/FLUX.1-schnell-gguf` | `flux1-schnell-Q4_K_S.gguf` |
| T5-XXL encoder Q4_K_M | `city96/t5-v1_1-xxl-encoder-gguf` | `t5-v1_1-xxl-encoder-Q4_K_M.gguf` |
| CLIP-L | `comfyanonymous/flux_text_encoders` | `clip_l.safetensors` |
| FLUX VAE | `Comfy-Org/Lumina_Image_2.0_Repackaged` | `split_files/vae/ae.safetensors` |
| Z-Image-Turbo Q3_K | `leejet/Z-Image-Turbo-GGUF` | `z_image_turbo-Q3_K.gguf` |
| Qwen3-4B encoder Q4_K_M | `unsloth/Qwen3-4B-Instruct-2507-GGUF` | `Qwen3-4B-Instruct-2507-Q4_K_M.gguf` |
| FLUX.2-klein-4B Q4_0 | `leejet/FLUX.2-klein-4B-GGUF` | `flux-2-klein-4b-Q4_0.gguf` |

Note: the runtime's own docs name the FLUX.2 decoder `flux2_ae.safetensors`, but
the file published in `black-forest-labs/FLUX.2-dev` is `ae.safetensors`. Check
the repository, not the doc.

## Proving a swap before adopting it

Do not adopt a model on a hunch. Run the benchmark, which renders the same
prompt on the same canvas once per profile and reports the measured seconds:

```
Actions -> benchmark -> Run workflow
```

Each profile's `out/*.json` sidecar carries `seconds`, and the run summary gets a
comparison table. Then set the winner as the default in `render.yml` and record
the number in the README, as the FLUX.1 timing already is.

## Cost of being wrong

A CPU runner renders one 768x1024 image in the tens of minutes. A model that
does not load, or a step count that is a typo, does not fail fast: it burns a job
slot. Two guards exist for that reason:

- `MAX_STEPS` (default 50) refuses a step count above the limit before any job
  is planned.
- The model download step verifies every file is present and non-empty, and
  fails loudly rather than starting a render against a truncated model.
