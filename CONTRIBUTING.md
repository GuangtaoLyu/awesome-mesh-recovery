# Contribution and maintenance

This repository is **fully auto-updated every Monday at 09:00 UTC**. A paper
does **not** need to have been accepted by a conference or journal. Relevant
arXiv-only preprints are included as "arXiv preprint (year)".

## What appears on the README?

An Awesome List is a browsable index, not an annotated survey. Each paper is
**one line only**:

```markdown
- **VideoMimic** (CoRL 2025) — [Paper](...) · [Code](...)
- **ExMR** (arXiv 2026) — [Paper](...) · [Code (demo)](...)
- **VideoManip** (arXiv 2026) — [Paper](...) · [Code (partial)](...)
- **Hand2Robot** (arXiv 2026) — [Paper](...)
```

No abstract, detailed methods, citation metrics, reviewer scores, real-robot
claims or repetitive task tags in every entry. Scope is explained by the
section headings.

## Automatic data sources and publication rules

| Source | Role |
| --- | --- |
| `data/papers.json` | Broad human, hand, body and face recovery index |
| `data/embodied.json` | Recovery → robot, retargeting and tracking papers; shown **first** |
| `data/ignored.json` | Optional list of excluded paper identifiers |
| `config.json` | Queries, scope filters, caps and classification |
| `README.md` | Generated; **never** the paper database |

The automated pipeline searches arXiv, DBLP, Semantic Scholar and Crossref.
A paper's publication status does **not** determine eligibility. Instead,
the title and (when available) abstract must establish relevance to the
selected track. The narrow "recovery-to-robot" bridge excludes generic VLA
and unrelated robotics work.

New works enter their track **automatically**. Papers from different sources
are deduplicated by normalized title, arXiv ID or DOI. Existing editorial
labels are preserved, and published venue claims are only promoted when
the new source has consistent year information. Older papers remain indexed.

## Code and link policy

- Always link a verifiable primary paper: official arXiv or publisher/DOI.
- Add `[Code]` only when a GitHub repository can be found in author-supplied
  paper metadata (abstract/comment) and the repository exists.
- A repository link **does not mean complete code is released**.
- Existing explicitly verified `partial` / `demo` labels are preserved;
  new public repositories receive the neutral `Code` label.
- If no code is verified, **omit the Code link**. Missing a link does not
  mean the work is closed source. Do not claim "not released" as a fact.
- Project pages or model links are optional and included only when known.

## Updates and tests

- Weekly: `.github/workflows/update.yml`
- PR tests: `.github/workflows/ci.yml`
- Offline rebuild: `python scripts/pipeline.py --render-only`
- Offline validation: `python -m unittest discover -s tests -v`

Any GitHub Actions update first regenerates the README, then tests it.
It commits only changed JSON data and README files. A missing source
file or complete core-search outage blocks publishing instead of erasing data.
The discovery window is deliberately limited for scheduled updates; historical
works do not expire.

Issues and pull requests for corrections are welcome, but **routine maintenance
requires no human approval or manual review queue**.
