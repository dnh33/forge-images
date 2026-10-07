"""Support harness for the render.py tests.

render.py executes stable-diffusion.cpp through subprocess.run, so the test needs
to see the exact argv it builds without a real diffusion build present. This
script patches subprocess.run, imports render.py, and reports the argv it was
handed. Run it with:  python tests/_render_harness.py <path-to-render.py>
"""
import base64
import importlib.util
import json
import os
import subprocess
import sys


class _Result:
    def __init__(self, returncode):
        self.returncode = returncode


def main():
    script = sys.argv[1]
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        failing = os.environ.get("STUB_FAIL") == "1"
        if not failing:
            out = cmd[cmd.index("-o") + 1]
            with open(out, "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n")
        return _Result(1 if failing else 0)

    subprocess.run = fake_run  # patch before render.py imports it

    spec = importlib.util.spec_from_file_location("render_under_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with open("calls.json", "w") as fh:
        json.dump(calls, fh)


if __name__ == "__main__":
    main()
