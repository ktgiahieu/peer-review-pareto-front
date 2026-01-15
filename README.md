# ICLR Review Data Extraction

This notebook downloads ICLR 2024 and ICLR 2025 submission and review data from OpenReview, extracts specific review scores, and consolidates them into a pandas DataFrame.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install openreview-py tqdm pandas
```

## Usage

1. Open the Jupyter notebook: `Plot_Human_Review_Scores_(Pareto_front)_(from_openreview).ipynb`
2. Run all cells in order
3. When prompted, enter your OpenReview username and password
4. Wait for the data extraction to complete (this may take several minutes)
5. The final cell will display:
   - DataFrame head (first 5 rows)
   - DataFrame info (data types, non-null counts)
   - DataFrame shape (number of rows and columns)

## Extracted Data

The DataFrame contains the following columns:
- `conference`: Conference name (ICLR2024 or ICLR2025)
- `submission_id`: OpenReview submission ID
- `review_id`: OpenReview review ID
- `soundness`: Soundness score from review
- `presentation`: Presentation score from review
- `contribution`: Contribution score from review
- `rating`: Overall rating from review
- `confidence`: Reviewer confidence score
- `status`: Submission status (accept/reject)

## Notes

- The data will be saved locally in a `data/` directory (though the current version extracts directly to DataFrame)
- You need a valid OpenReview account to access the data
- The extraction process may take 10-30 minutes depending on your connection speed

