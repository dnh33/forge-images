"""Append one benchmark row per rendered sidecar to the GitHub step summary.

Kept as a file rather than an inline heredoc because the workflow already buries
this in enough quoting. Usage: bench_report.py <path-to-summary-file>
"""
import glob
import json
import sys


def rows(paths):
    yield "| model | canvas | steps | seconds |"
    yield "| --- | --- | --- | --- |"
    for path in sorted(paths):
        try:
            d = json.load(open(path))
        except Exception:
            continue
        size = d.get("size") or [0, 0]
        yield "| {} | {}x{} | {} | {} |".format(
            d.get("model", "?"), size[0], size[1], d.get("steps", "?"), d.get("seconds", "?")
        )


def main():
    target = sys.argv[1]
    paths = glob.glob("out/*.json")
    text = "\n".join(rows(paths))
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
