"""Run S1-S11 using the existing development integration tests."""

import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RESULTS = {
    f"S{number}": False
    for number in range(1, 12)
}

ENVIRONMENT = os.environ.copy()
ENVIRONMENT["PYTHONIOENCODING"] = "utf-8"
ENVIRONMENT["PYTHONUNBUFFERED"] = "1"


def run_script(filename, markers=None):
    """Stream actual test output and record explicit PASS markers."""
    print(f"\n=== Running {filename} ===", flush=True)

    process = subprocess.Popen(
        [sys.executable, "-u", str(ROOT / filename)],
        cwd=str(ROOT),
        env=ENVIRONMENT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    detected = set()

    try:
        for line in process.stdout:
            print(line, end="", flush=True)

            for pattern, scenario in (markers or {}).items():
                if re.fullmatch(pattern, line.strip()):
                    detected.add(scenario)
    finally:
        process.stdout.close()

    return_code = process.wait()

    for scenario in detected:
        RESULTS[scenario] = True

    if return_code:
        print(
            f"\n{filename} exited with code {return_code}.",
            flush=True,
        )

    return return_code == 0


def main():
    print(
        "HW2 integration scenarios — REAL OpenRouter API calls.\n"
        "Data: development sample data, not verified course fixtures.\n"
        "Tests use calibration.db and temporary database copies.",
        flush=True,
    )

    setup_ok = run_script("tests/calibrate_search.py")
    scripts_ok = setup_ok

    if setup_ok:
        jobs = [
            (
                "tests/test_routing.py",
                {
                    r"D1: PASS": "S1",
                    r"D2: PASS": "S2",
                    r"D3: PASS": "S3",
                    r"D4: PASS": "S4",
                    r"D5: PASS": "S11",
                },
            ),
            (
                "tests/test_chat_safety.py",
                {
                    r"S6 DEVELOPMENT: PASS": "S6",
                    r"S7 DEVELOPMENT: PASS": "S7",
                    r"S8 DEVELOPMENT: PASS": "S8",
                    r"S9 DEVELOPMENT: PASS": "S9",
                },
            ),
            (
                "tests/test_embedding_writes.py",
                {
                    r"S5 DEVELOPMENT: PASS": "S5",
                    r"S10 DEVELOPMENT: PASS.*": "S10",
                },
            ),
        ]

        for filename, markers in jobs:
            succeeded = run_script(filename, markers)
            scripts_ok = succeeded and scripts_ok

    print("\n=== Development scenario summary ===", flush=True)

    for scenario, passed in RESULTS.items():
        status = "PASS" if passed else "FAIL"
        print(f"{scenario}: {status}", flush=True)

    total = sum(RESULTS.values())
    print(f"\nDevelopment scenarios: {total}/11 PASS", flush=True)

    if not scripts_ok:
        print(
            "At least one script failed. Review its output above.",
            flush=True,
        )

    return 0 if scripts_ok and all(RESULTS.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())