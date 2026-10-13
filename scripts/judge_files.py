#!/usr/bin/env python3
"""critic-blog-qc — local CLI runner for the critic-qc judge Worker.

Sends each draft file's text to the judge and reports PASS/FAIL per file.
Same verdict semantics as the GitHub Action (action.yml calls this script).

Judge contract (verified live 2026-10-13):
  POST https://critic-qc.dstrausser83.workers.dev/judge
  headers: x-swarm-secret: <QC_SECRET>, Content-Type: application/json
  body:    {"text": "...", "kind": "qc"}     <-- kind ONLY.
  A separate "rubric" field diverts the Worker into article-SUMMARY output
  (its source picks `rubric || RUBRICS[kind]`), so NEVER send one.
  Response JSON: {"kind": ..., "verdict": ..., "notes": ..., "raw": ...}

Verdicts: qc -> PASS / FAIL | spam -> NOT_SPAM / SPAM | trend -> GO / NO-GO.
The first-listed verdict for each kind is the passing one.
Exit codes: 0 = every file passed | 1 = at least one file failed its verdict
            2 = judge unreachable / auth / usage error (NEVER a silent pass)

Secret handling: read from $QC_SECRET, else from ~/.config/critic-qc/qc-secret.txt
(read in-process; the value is never printed, logged, or passed on a command line).
"""
import argparse, glob, json, os, sys, urllib.request, urllib.error

DEFAULT_JUDGE_URL = "https://critic-qc.dstrausser83.workers.dev/judge"
PASS_VERDICT = {"qc": "PASS", "spam": "NOT_SPAM", "trend": "GO"}
# The judge Worker's own cap; longer texts are truncated the same way it would.
MAX_TEXT = 4000
# Cloudflare's edge rejects the default Python User-Agent (error 1010);
# a browser UA is required for the request to reach the Worker at all.
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def load_secret(explicit_file=None):
    env = os.environ.get("QC_SECRET") or os.environ.get("QC_SECRET_INPUT")
    if env:
        return env.strip()
    path = explicit_file or os.path.expanduser("~/.config/critic-qc/qc-secret.txt")
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    return None


def extract_text(path):
    """Plain text for .md/.txt; for blog-draft JSON, title + md/text fields."""
    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    if path.endswith(".json"):
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        parts = []
        for key in ("title", "text", "reply_text", "md", "body", "caption"):
            v = d.get(key)
            if isinstance(v, str) and v.strip():
                parts.append(v)
        return "\n\n".join(parts) if parts else raw
    return raw


def judge(text, kind, secret, judge_url):
    body = json.dumps({"text": text[:MAX_TEXT], "kind": kind}).encode()
    req = urllib.request.Request(judge_url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "x-swarm-secret": secret,
        "User-Agent": UA,
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser(description="Judge draft files with critic-qc.")
    ap.add_argument("files", nargs="+", help="files or glob patterns")
    ap.add_argument("--kind", default="qc", choices=sorted(PASS_VERDICT),
                    help="judge rubric kind (default: qc)")
    ap.add_argument("--judge-url", default=DEFAULT_JUDGE_URL)
    ap.add_argument("--secret-file", default=None,
                    help="secret file path (default: ~/.config/critic-qc/qc-secret.txt)")
    args = ap.parse_args()

    secret = load_secret(args.secret_file)
    if not secret:
        print("ERROR: QC_SECRET is not set and no secret file was found. "
              "Set the QC_SECRET env var or place the secret at "
              "~/.config/critic-qc/qc-secret.txt", file=sys.stderr)
        return 2

    paths = []
    for pat in args.files:
        hits = sorted(glob.glob(pat))
        paths.extend(hits if hits else [pat])
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        print(f"ERROR: file(s) not found: {', '.join(missing)}", file=sys.stderr)
        return 2

    want = PASS_VERDICT[args.kind]
    failed = 0
    for p in paths:
        text = extract_text(p)
        if not text.strip():
            print(f"FAIL {p} — empty text, nothing to judge")
            failed += 1
            continue
        try:
            res = judge(text, args.kind, secret, args.judge_url)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:200]
            print(f"ERROR: judge unreachable/auth for {p}: HTTP {e.code} {detail}",
                  file=sys.stderr)
            return 2
        except Exception as e:
            print(f"ERROR: judge unreachable for {p}: {e}", file=sys.stderr)
            return 2
        verdict = str(res.get("verdict", "")).upper()
        notes = res.get("notes", "")
        if verdict == want:
            print(f"PASS {p} — {notes}")
        else:
            print(f"FAIL {p} — verdict {verdict or '(none)'}: {notes}")
            failed += 1
    print(f"critic-qc: {len(paths) - failed}/{len(paths)} file(s) passed (kind={args.kind})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
