"""Resolve a render job matrix from prompt sets and/or an ad-hoc payload.

Every job is fully resolved here (prompt text, size, seed), then carried to the
render jobs base64-encoded. That is what lets one-off prompts run without ever
being committed to the repository.

Inputs (env):
  SET       name of a file in prompts/ (without .json), or "all"   default "all"
  ONLY      comma-separated item ids to keep                        default: all
  SHARDS    number of parallel jobs (one model download each)       default 8
  VARIANTS  seeds per item                                          default 2
  STEPS     sampling steps                                          default 4
  ADHOC     base64 JSON of an extra set, merged in:
            {"name","size":[w,h],"style","items":{id:{seed,line}}}
Output: matrix JSON to stdout and to $GITHUB_OUTPUT as matrix=<json>.
"""
import base64, glob, json, os, sys

SET = os.environ.get("SET", "all").strip() or "all"
ONLY = {s.strip() for s in os.environ.get("ONLY", "").split(",") if s.strip()}
SHARDS = max(1, int(os.environ.get("SHARDS", "8") or 8))
VARIANTS = max(1, int(os.environ.get("VARIANTS", "2") or 2))
STEPS = str(os.environ.get("STEPS", "4") or 4)
MAX_STEPS = max(1, int(os.environ.get("MAX_STEPS", "50") or 50))
PAGE = 100
# Explicit page marker keeps each item's prompt from being re-derived anywhere else.
MARK = "\x00"

if not STEPS.isdigit():
    sys.exit(f"STEPS must be a whole number, got {STEPS!r}")
if int(STEPS) > MAX_STEPS:
    sys.exit(f"STEPS={STEPS} exceeds MAX_STEPS={MAX_STEPS}; a typo here burns hours of runner time")

sets = []
for path in sorted(glob.glob("prompts/*.json")):
    name = os.path.basename(path)[:-5]
    if SET != "all" and name != SET:
        continue
    with open(path) as f:
        d = json.load(f)
    d.setdefault("size", [768, 1024])
    # (name, set, subject_to_only_filter)
    sets.append((name, d, True))

adhoc = os.environ.get("ADHOC", "").strip()
if adhoc:
    d = json.loads(base64.b64decode(adhoc))
    d.setdefault("size", [768, 1024])
    # An ad-hoc payload is a one-off. On its own it means "render only this",
    # never "render this AND every set committed to the repository" — a one-off
    # prompt must not silently queue the whole library. It is also exempt from
    # ONLY: the caller chose its items outright.
    if SET == "all":
        sets = []
    sets.append((d.get("name", "adhoc"), d, False))

if not sets:
    sys.exit(f"No prompt sets match SET={SET!r} (have: {[os.path.basename(p)[:-5] for p in glob.glob('prompts/*.json')]})")

jobs = []
for name, d, filter_by_only in sets:
    w, h = d["size"]
    style = (d.get("style") or "").strip()
    for key, e in d["items"].items():
        if ONLY and filter_by_only and key not in ONLY:
            continue
        for v in range(VARIANTS):
            seed = int(e["seed"]) + v * 1000
            prompt = (e["line"].strip() + " " + style).strip()
            jobs.append({"id": f"{name}:{key}", "kind": name, "key": key,
                         "prompt": prompt, "w": w, "h": h, "seed": seed, "steps": STEPS})

if not jobs:
    sys.exit(f"No items match ONLY={sorted(ONLY)}")

# A shard renders its items one after another, so an unbounded shard can outlive
# the runner's time limit. Raise the shard count until every shard fits the cap.
MAX_PER_SHARD = max(1, int(os.environ.get("MAX_PER_SHARD", "6") or 6))
min_shards = -(-len(jobs) // MAX_PER_SHARD)  # ceiling division
shards = min(max(SHARDS, min_shards), len(jobs))
if shards > SHARDS:
    print(
        f"plan: raised shards {SHARDS} -> {shards} so every shard holds "
        f"at most {MAX_PER_SHARD} job(s)",
        file=sys.stderr,
    )
groups = [jobs[i::shards] for i in range(shards)]
out = json.dumps({"include": [
    {"shard": i, "name": f"shard {i} ({len(g)} job(s))",
     "jobs": base64.b64encode(json.dumps(g).encode()).decode()}
    for i, g in enumerate(groups)
]})
print(out)
print(f"plan: {len(jobs)} job(s) across {shards} shard(s)", file=sys.stderr)
with open(os.environ["GITHUB_OUTPUT"], "a") as f:
    f.write(f"matrix={out}\n")
    f.write(f"count={len(jobs)}\n")
