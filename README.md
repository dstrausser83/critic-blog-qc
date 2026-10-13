# critic-blog-qc

A GitHub Action that gates blog drafts on the **critic-qc judge** — a
Cloudflare Worker that reads a draft and returns a verdict. Wire it into a
drafts repo's pull requests and a bad draft fails its check before a human
ever sees it, with the judge's notes right in the Actions log.

The judge lives at `https://critic-qc.dstrausser83.workers.dev`
(`GET /health`, `POST /judge`), runs on Workers AI, and caches verdicts by
text hash, so re-running a check on unchanged text is fast and stable.

## What it does

For each file you give it, the action extracts the text (raw for
`.md`/`.txt`; `title` + `md`/`text` fields for blog-draft JSON), sends it to
the judge, and prints one line per file:

```
PASS drafts/my-post.md — Informative, specific, follows the requested voice.
FAIL drafts/hype-post.md — verdict FAIL: Contains misinformation (guaranteed returns).
```

Exit-code semantics — three distinct outcomes, never a silent pass:

| exit | meaning |
|------|---------|
| 0 | every file passed its verdict |
| 1 | at least one file **failed** (a real content verdict) |
| 2 | judge unreachable / unauthorized / bad input — an infrastructure failure, reported as `result=error`, **not** a content verdict |

## The kind-only rule (read this before touching the request)

The judge is invoked with **kind only**:

```json
POST /judge
{"text": "<draft text>", "kind": "qc"}
```

`kind` is one of `qc`, `spam`, `trend` and selects the rubric by itself.
**Never add a `rubric` field** — the Worker resolves its prompt as
`rubric || RUBRICS[kind]`, so a stray `rubric` silently diverts it into
article-summary output instead of a verdict. `scripts/judge_files.py` owns
the request shape; both the Action and the local CLI go through it.

Verdicts per kind — the first is the passing one:

| kind | pass | fail |
|------|------|------|
| `qc` | `PASS` | `FAIL` |
| `spam` | `NOT_SPAM` | `SPAM` |
| `trend` | `GO` | `NO-GO` |

Practical notes: texts are judged at up to 4,000 characters (the Worker's
own cap; longer drafts are truncated the same way the Worker would). The
judge is a small model — treat a FAIL as "a human should look," not gospel;
its notes occasionally over-describe. Verdicts are the gate; notes are hints.

## Setup

1. **Add the secret.** In the repo that will run the check:
   *Settings → Secrets and variables → Actions → New repository secret*
   - Name: `QC_SECRET`
   - Value: the shared secret for the judge Worker.

   The value's custody stays with Rock (it matches the `QC_SECRET` secret
   on the critic-qc Worker). It is never committed anywhere — the Action
   reads it from the environment only, and this repo contains no credential
   values.

2. **Add the workflow** (below). That's it — no other dependencies;
   `python3` is preinstalled on GitHub runners.

## Adopt it

As an Action step in any workflow:

```yaml
- uses: actions/checkout@v4
- name: Critic QC on changed drafts
  uses: dstrausser83/critic-blog-qc@v1
  with:
    files: "drafts/*.md"
    kind: qc
    qc-secret: ${{ secrets.QC_SECRET }}
```

Or via the reusable workflow in this repo
(`.github/workflows/critic-qc.yml`), which is the same thing wrapped for
`workflow_call`:

```yaml
jobs:
  critic:
    uses: dstrausser83/critic-blog-qc/.github/workflows/critic-qc.yml@v1
    with:
      files: "drafts/*.md"
    secrets:
      QC_SECRET: ${{ secrets.QC_SECRET }}
```

The workflow file also documents a `pull_request` variant that judges only
the drafts a PR actually changed.

## Run it locally

The same check, no GitHub involved:

```sh
# secret from ~/.config/critic-qc/qc-secret.txt (read in-process, never echoed)
# or from the QC_SECRET environment variable
python3 scripts/judge_files.py drafts/*.md
python3 scripts/judge_files.py --kind spam inbox/message.txt
```

Same output, same exit codes as the Action.

## Tests

Integration tests against the **live** judge (fixtures: one clean draft,
one hype/scam draft, one prize-phish message):

```sh
python3 tests/run_tests.py
```

Expected: 3/3 — `pass.md` → PASS (exit 0), `fail.md` → FAIL (exit 1),
`spam.txt` → SPAM (exit 1).

## Layout

```
action.yml                        the composite Action (calls the runner)
.github/workflows/critic-qc.yml   reusable-workflow adoption example
scripts/judge_files.py            the one implementation: Action + local CLI
tests/fixtures/                   pass / fail / spam fixtures
tests/run_tests.py                live-judge integration tests
```
