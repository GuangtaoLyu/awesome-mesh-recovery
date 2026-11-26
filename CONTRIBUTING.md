# Contribution and maintenance

This repository is **fully auto-updated every Monday at 09:00 UTC**. A paper
does **not** need to have been accepted by a conference or journal. Relevant
arXiv-only preprints are included as "arXiv 2026" (year follows the source metadata).

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
The primary contribution should be human/hand mesh, shape or motion recovery
(or a concrete human-motion-to-robot pipeline for the embodied section);
pure pose-only studies, camera calibration, biomedical meshes and papers
that merely *use* an HMR model for an unrelated application are excluded.
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
- Add `[Code]` only when a public GitHub repository is explicitly
  identified as code/implementation in the paper's metadata, and the
  repository exists. A bare GitHub URL or a cited dependency does not qualify.
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


## Discovery quality and fully automatic evidence checks

The search process is deliberately broader than the publication policy:

1. **Weekly incremental discovery:** arXiv requests are ordered by their
   last updated timestamp. DBLP, Semantic Scholar and Crossref broaden
   coverage and fill verified metadata.
2. **Monthly deep backfill:** the first scheduled Monday in each month runs
   a larger, submitted-date search across the same 3-year discovery horizon.
   This is also available as `python scripts/pipeline.py --backfill` and in
   the manual GitHub Actions form.
3. **Two-step task evidence:** explicit mesh, shape or motion recovery and
   direct human/video-to-robot papers publish automatically. Borderline
   titles are checked against abstracts and an additional bounded arXiv
   metadata lookup; no editor or LLM approval is needed.
4. **Machine-only deferral:** inconclusive candidates are retained in
   `data/pending.json` and automatically re-assessed on later runs; they
   never appear in README until there is enough evidence.
5. **No silent paper limits:** unexpected spikes in auto-admission cause
   the scheduled job to fail safely rather than quietly discard titles
   late in the alphabet. All JSON/README writes happen after checks.
6. **Quality regression:** `python scripts/evaluate_selection.py --strict`
   reports selection precision, recall and category accuracy on a fixed
   representative offline fixture. This is a regression guard, **not** an
   unbiased statistical estimate of the accuracy of live weekly searches.

Routine updates remain fully automatic, including arXiv-only work. Only the
automatically generated sources and the compact README are published.
