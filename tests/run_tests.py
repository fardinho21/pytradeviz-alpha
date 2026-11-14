"""Run the test modules in parallel, one unittest process per module.

Usage (from the repository root):

    python3 tests/run_tests.py                 # every test module
    python3 tests/run_tests.py test_zoom       # selected modules
    python3 tests/run_tests.py -j 2            # limit the number of workers

Each module runs in its own interpreter, so Tk windows and module-level state
never collide. Output from a module is only printed when that module fails.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, NamedTuple

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
RAN_PATTERN = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)


class ModuleResult(NamedTuple):
    name: str
    returncode: int
    seconds: float
    output: str
    tests_run: int


def discover_modules(names: List[str]) -> List[str]:
    if names:
        return [name[:-3] if name.endswith(".py") else name for name in names]
    return sorted(path.stem for path in TESTS.glob("test_*.py"))


def default_jobs() -> int:
    # Logical CPUs overstate capacity: Tk drawing goes through one X server, and
    # hyperthreaded cores share execution units, so more workers stop helping.
    return max(1, (os.cpu_count() or 2) // 2)


def run_module(name: str) -> ModuleResult:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(TESTS), str(ROOT), env.get("PYTHONPATH", "")) if part
    )
    started = time.monotonic()
    # Run from the repository root: some tests use paths relative to it.
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", name],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    seconds = time.monotonic() - started
    output = completed.stdout
    match = RAN_PATTERN.search(output)
    return ModuleResult(name, completed.returncode, seconds, output,
                        int(match.group(1)) if match else 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("modules", nargs="*", help="test module names, e.g. test_zoom")
    parser.add_argument("-j", "--jobs", type=int, default=default_jobs(),
                        help="number of modules to run at once (default: half the CPU count)")
    args = parser.parse_args()

    modules = discover_modules(args.modules)
    if not modules:
        print("No test modules found.")
        return 1

    started = time.monotonic()
    results: List[ModuleResult] = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = [pool.submit(run_module, name) for name in modules]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status = "ok" if result.returncode == 0 else "FAILED"
            print("{:<4} {:<36} {:>4} tests  {:>6.1f}s".format(
                status, result.name, result.tests_run, result.seconds), flush=True)

    failed = [result for result in results if result.returncode != 0]
    for result in sorted(failed, key=lambda item: item.name):
        print("\n" + "=" * 70 + "\n" + result.name + "\n" + "=" * 70)
        print(result.output.rstrip())

    total = sum(result.tests_run for result in results)
    print("\nRan {} tests in {} modules in {:.1f}s (wall clock)".format(
        total, len(results), time.monotonic() - started))
    if failed:
        print("FAILED modules: " + ", ".join(sorted(result.name for result in failed)))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
