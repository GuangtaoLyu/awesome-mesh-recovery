# Contributing & Maintenance

This is an **awesome list**, not a general robotics paper feed. The front-page
embodied section is a deliberate bridge from **human / hand recovery** to
**retargeting and robot-executable motion**, while the rest remains a focused
index of 3D human and hand **mesh, pose-and-shape, and motion recovery**.

## Where to make changes

| File | Role | Maintainer action |
| --- | --- | --- |
| `data/papers.json` | Accepted HMR papers (existing historical records preserved) | Normally automatic; manually verified additions can be approved from the queue |
| `data/embodied.md` | Curated robotics bridge; displayed **first** | Edit only after checking the actual paper and release status |
| `data/review_queue.json` | Unpublished discovery suggestions | Review, approve or reject; **not** rendered as papers |
| `data/ignored.json` | Rejected titles / arXiv IDs / DOIs | Generated when rejecting; prevents repeats |
| `config.json` | Discovery queries, eligibility phrases, queue limits, taxonomy | Tune with a focused change and tests |
| `README.md` | Generated view from accepted papers plus curated section | **Do not directly add papers here** |

## Weekly update (Monday 09:00 UTC)

1. Query arXiv, DBLP, Semantic Scholar and Crossref, restricted to the recent
   discovery window in `config.json` (currently three publication years).
   Older papers already in the index remain untouched.
2. Merge cross-source duplicates by normalized title, arXiv ID and DOI.
   Existing titles, categories and editorial decisions take precedence; newly
   available identifiers or publication venues may fill missing metadata.
3. **Auto-accept only specific recovery titles** (e.g., Human Mesh Recovery,
   Human Pose and Shape Estimation, Hand Mesh Reconstruction).
   Broader 3D pose, world-grounded motion, hand reconstruction or SMPL-related
   leads require review. Other topics are ignored.
4. Discover plausible *embodied* follow-up papers using separate robot/video
   queries. **Never insert them automatically** into the curated front section.
   A paper on robot tracking alone is not automatically a mesh-recovery paper.
5. Save limited, deduplicated suggestions in `data/review_queue.json`
   (currently max 80 total; up to 8 new leads per track each run).
6. Generate the README **only from accepted + curated sources**, run offline
   tests, and push only if content actually changed. Dates alone do not produce
   commits. Failed queries are reported; total core-source failure blocks the
   update. Missing curated data fails loudly instead of deleting the section.

## Review workflow

Run these commands locally (or via GitHub's code editor when editing the
curated Markdown manually):

```bash
python scripts/review_candidates.py list
python scripts/review_candidates.py approve 3 --category "Hand, Face & Expressive Mesh"
python scripts/review_candidates.py reject 5
python scripts/pipeline.py --render-only
python -m unittest discover -s tests -v
```

The list command shows stable **1-based indices at the time of listing**;
list again after approving or rejecting because indices shift.

- **Core recovery:** Approve after verifying that the paper actually predicts
  a human / hand mesh, shape parameters or relevant 3D motion; choose the
  closest category. Review must not be confused with automatic acceptance.
- **Embodied:** Verify the connection to recovery, then add one concise entry
  to `data/embodied.md` under the appropriate full-body or hand section.
  Include `[Paper]`, `[Code]`, `[Project]` only when confirmed. Prefer the
  original article URL and official repository. Do **not** approve embodied
  proposals into the generic auto-index; when the entry is in the curated
  file, the next update automatically removes matching leads.
- **Rejected:** Reject low-quality, unrelated, duplicate or misleading leads.
  The queue removes them, and the stable identifiers in `data/ignored.json`
  prevent the same paper from reappearing under another provider URL.
- **Manual addition:** To insert an older seminal paper that discovery no
  longer scans, add it directly to `data/papers.json` with the correct category
  (or to curated embodied Markdown), then run the offline generator and tests.

## Scope and evidence rules

**Embodied groups:** Whole-Body Recovery → Humanoid Robots; Hand-Object
Recovery → Dexterous Robots; Reusable Retargeting Toolkit.

- **Vision → Robot:** Has a concrete perception/reconstruction and
  retargeting/execution path.
- **Recovery:** A perception backbone. Do not claim robot execution merely
  because downstream adaptation is possible.
- **Retargeting / Teleoperation:** Translates human motion to robot
  references; XR/MoCap systems must be labeled as such.
- **Tracking / Control:** Executes or stabilizes robot references. It is a
  downstream component, not a mesh estimator.
- **Code status:** Link the verified public repository and specify whether
  it includes reconstruction, retargeting, training, real deployment, only a
  demo, or merely pretrained weights. Do not infer complete release from a
  GitHub link. For example, VideoManip currently releases the reconstruction
  pathway, not all grasping/manipulation-policy stages.

Preserve the curated section at the start of the table of contents **and**
body. When editing an item, use accurate venue/year/link information and
avoid redundant entries in both the curated and auto-indexed collections.

## Reliability and recovery

- Manual rendering (no internet): `python scripts/pipeline.py --render-only`
- Local validation: `python -m unittest discover -s tests -v`
- Automatic update: `.github/workflows/update.yml` (scheduled and manual;
  manual dispatch has a `render_only` checkbox)
- PR validation: `.github/workflows/ci.yml` (offline only)
- There is **no automatic deletion** of old accepted papers or manually
  curated robotics papers. Tune the selection phrases in config and add tests
  instead of weakening admission rules to chase citation counts.
