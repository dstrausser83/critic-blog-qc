#!/usr/bin/env python3
"""Integration tests against the LIVE critic-qc judge.

Runs scripts/judge_files.py as a subprocess on the fixtures and asserts the
verdict semantics:
  pass.md  (kind=qc)   -> exit 0, verdict PASS
  fail.md  (kind=qc)   -> exit 1, verdict FAIL
  spam.txt (kind=spam) -> exit 1, verdict SPAM
Requires QC_SECRET in env or ~/.config/critic-qc/qc-secret.txt.
Note: the judge caches verdicts by text hash (~24h), so re-runs are stable.
"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "..", "scripts", "judge_files.py")

CASES = [
    ("pass.md", "qc", 0, "PASS"),
    ("fail.md", "qc", 1, "FAIL"),
    ("spam.txt", "spam", 1, "SPAM"),
]

def main():
    failures = 0
    for fixture, kind, want_rc, want_word in CASES:
        path = os.path.join(HERE, "fixtures", fixture)
        r = subprocess.run([sys.executable, RUNNER, "--kind", kind, path],
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        ok = (r.returncode == want_rc) and (want_word in out)
        print(f"[{'PASS' if ok else 'FAIL'}] {fixture} kind={kind} "
              f"exit={r.returncode} (want {want_rc})")
        for line in out.splitlines():
            print(f"    judge> {line}")
        if not ok:
            failures += 1
    print(f"tests: {len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
