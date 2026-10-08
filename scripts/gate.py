"""Owner gate for the Render workflow.

The allowed actor is data, not code: it lives in context/facts.json, so a copy
generated from this template edits one JSON field and never the workflow. The
workflow runs this before anything expensive; the exit status is the whole
contract. Failure text goes through ::error:: so it surfaces on the run page.
"""
import json
import os
import sys
from pathlib import Path

FACTS = Path(
    os.environ.get("FACTS")
    or Path(__file__).resolve().parents[1] / "context" / "facts.json"
)


def main() -> int:
    try:
        facts = json.loads(FACTS.read_text(encoding="utf-8"))
        owner = facts["owner"]
        if not isinstance(owner, str) or not owner.strip():
            raise ValueError("owner must be a non-empty string")
    except Exception as exc:
        print(f"::error::owner gate: cannot read the owner from {FACTS}: {exc}",
              file=sys.stderr)
        return 2

    actor = os.environ.get("ACTOR", "").strip().lower()
    owner = owner.strip().lower()
    if actor == owner:
        print(f"owner gate: {actor} is the repository owner, proceeding")
        return 0

    print(f"::error::owner gate: actor '{actor}' is not the repository owner "
          f"'{owner}'; refusing to render", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
