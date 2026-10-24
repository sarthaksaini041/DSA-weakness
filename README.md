# DSA Compass

An ES 335 project that uses Codeforces submission history to identify topics needing practice and
recommend problems. We compared Logistic Regression, Random Forest, and Gradient Boosting with an
acceptance-rate baseline.

The dataset has **120 users, 100,919 submissions, and 41,828 eligible first-attempt rows**.
Collection, features, and evaluation splits are complete. Baseline and three-model validation
comparisons and frozen final-test evaluation are complete. Offline topic analysis and practice
recommendations are implemented. The static website is implemented and locally browser-tested.
GitHub Pages publication and live handle support are pending.

## Project files

```text
proposal.md          Project question, methods, and evaluation plan
ai_usage.md          Required AI assistance disclosure
requirements.txt     Python dependencies
code/                Data collection, features, and checks
tests/               Automated tests
reports/             Course checklist, methods, and data report
website/             Static site, reviewed saved examples, and plots
  images/            Data plots
data/                Published snapshot and local working data
  raw_data.tar.gz    Raw captures and frozen split metadata
  raw_data.sha256    Archive checksum
  raw/               Captures, user selection, and source records
  processed/         Features and evaluation splits
```

`AGENTS.md` preserves the project rules and your Git authorship preference for coding assistants.
The course does not prescribe folder names; this layout supports its reproduction and submission
requirements.

## Run the project

Python 3.11+ is required. Collection and feature code use the standard library; plots use
matplotlib; model training uses scikit-learn.

```bash
python3 -m pip install -r requirements.txt
sha256sum -c data/raw_data.sha256
tar -xzf data/raw_data.tar.gz -C data
python3 code/select_users.py
python3 code/collect_data.py --batch-profiles
python3 code/make_features.py
python3 code/check_data.py
python3 code/train_models.py
python3 code/check_models.py
# For independent reproduction, preserve the checked-in final plan and results.
python3 code/test_models.py --freeze --output /tmp/dsa-final-reproduction
python3 code/test_models.py --output /tmp/dsa-final-reproduction
python3 -m unittest discover -s tests -v
```

Existing selection and captures are reused. Run only one collector at a time; requests are spaced by
at least 2.1 seconds. Public API access requires `codeforces.com` to be allowed in the cloud
environment. Fresh collections can differ from this snapshot.

For a fresh clone, the extraction step restores the original raw captures, candidate lists, and
frozen split metadata. The archive includes public Codeforces handles and submission records, with
minimized profile fields. It excludes credentials, temporary files, and generated feature tables.
Expanded `data/raw/` and `data/processed/` stay ignored; regenerate feature tables with
`make_features.py`.

The archive is compressed because one candidate JSON exceeds GitHub's per-file size limit. To
collect a different live snapshot instead, use a new output directory and record its new selection
and splits; do not overwrite the original dataset to change model results.

If profile checks flag stale rating groups, stop collection, run `python3 code/check_users.py`, and
resume. Replacements are recorded and originals retained for audit. Do not change selected users or
splits based on model results.

For an optional single-user inspection:

```bash
python3 code/get_data.py YOUR_HANDLE --max-pages 2
```

A bounded capture is incomplete and cannot establish first-ever attempts.

## Reports

- [Project proposal](proposal.md)
- [Course requirements and rubric checklist](reports/checklist.md)
- [Data collection and sampling](reports/sampling.md)
- [Features and evaluation splits](reports/features.md)
- [Data report and plots](reports/data_report.md)
- [Model validation comparison](reports/model_results.md)
- [Sensitivity, calibration, and error checks](reports/model_checks.md)
- [Final future-submission and unseen-user results](reports/test_results.md)
- [Topic evidence and practice recommendations](reports/recommendations.md)
- [Website preview, checks, and deployment](reports/website.md)

All coverage checks passed. The preselected Random Forest improves average log loss on both final
tests, but the 17-user unseen-test interval includes no improvement over baseline. See the final
report for uncertainty and subgroup limits. The final undergraduate deliverable will be a static
interactive website published on GitHub Pages, with the source link and required explanatory
sections.

## Try the offline recommender

```bash
python3 code/recommend.py ethanxupro
python3 code/recommend.py ethanxupro --topic graphs --min-rating 1000 --max-rating 1200
```

This uses saved cohort histories and writes `data/processed/recommendations.json`. Sparse histories
receive exploration suggestions without confident weakness labels. See the recommendation report for
evidence rules, limitations, and additional examples.

## Preview the website

```bash
python3 -m http.server 8000 --directory website
```

Open `http://localhost:8000`. The committed static site includes three saved examples; it requires
no model server. Rebuild the reviewed export with `python3 code/make_website_data.py` when needed.
GitHub Pages publishing is a separate manual workflow; see the website report.
