# OpenReview multi-venue extraction

`extract_openreview_reviews.py` downloads review data from OpenReview for ICLR, NeurIPS, and ICML, with **dynamic score columns** so different venues/years (different criteria and scales) are supported in one CSV.

## Setup

```bash
conda activate all_purpose
# Ensure OPENREVIEW_USERNAME and OPENREVIEW_PASSWORD are set (e.g. in .env or export)
pip install openreview-py python-dotenv tqdm  # if not already installed
```

## Usage

- **Test with one submission per venue** (recommended first run):
  ```bash
  python extract_openreview_reviews.py --limit 1 --output data/openreview_reviews_sample.csv
  ```
- **Single venue**:
  ```bash
  python extract_openreview_reviews.py --venues ICLR2024 --limit 5
  ```
- **Full run** (all configured venues):
  ```bash
  python extract_openreview_reviews.py --output data/openreview_reviews.csv
  ```
- **Dry run** (list venue config only):
  ```bash
  python extract_openreview_reviews.py --dry-run
  ```

## Output

- **CSV**: Columns `venue`, `submission_id`, `review_id`, `status`, plus **dynamic score columns** (e.g. `rating`, `confidence`, `soundness`, `presentation`, `contribution`). Rows for venues that don’t use a given criterion have empty cells.
- **Metadata JSON** (`--output-meta`): For each venue, `score_fields` and `scale_notes` (scale and criteria by year).

## Venues and API versions

- **API v1** (`api.openreview.net`): ICLR 2022–2023, NeurIPS 2021–2023. Uses `Blind_Submission` (or `Submission` for single-blind).
- **API v2** (`api2.openreview.net`): ICLR 2024–2026, NeurIPS 2024–2025, ICML 2025.

If a venue returns 0 submissions (e.g. wrong invitation), adjust `submission_invitation` in `VENUE_CONFIG` (e.g. switch between `Blind_Submission` and `Submission`).

## Scales (reference)

- **Rating**: usually 1–10 (1 = Trivial/wrong, 10 = Top 5%).
- **Confidence**: usually 1–5.
- **ICLR 2024+**: soundness, presentation, contribution often 1–5 each.
- **ICML 2025**: overall score only (form may differ; raw values are kept).
