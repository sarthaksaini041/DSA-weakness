# Project instructions

- Follow `reports/checklist.md` and `proposal.md` throughout development. The intended deliverable
  is the ES 335 interactive static website on GitHub Pages.
- Keep prediction-time information explicit, prevent temporal and preprocessing leakage, compare all
  three models with a meaningful baseline, and reserve final test data from tuning.
- Never claim live API access, model quality, or learning improvement without supporting validation.
  Distinguish offline tests from live checks.
- Do not add the assistant, Codex, OpenAI, or an AI identity as a commit author or co-author. Do not
  add AI co-author trailers. Preserve the user's configured Git identity; do not invent or replace
  an identity. If committing is requested and no suitable user identity is configured, ask for it.
- The course requires disclosure of AI assistance in project materials. Keep that disclosure
  separate from Git authorship.
- The dataset must include varied users. Follow `reports/sampling.md`: cover unrated and multiple
  rating bands, audit activity/history diversity and prolific-user dominance, and keep smoke-test
  data separate. Never claim planned coverage has already been collected.
- Follow `reports/checklist.md` for ES 335 deliverables. Keep unfinished rubric evidence marked
  pending; the final website must be static and work on GitHub Pages. Maintain `ai_usage.md` and the
  course-required disclosure without adding AI Git authorship.
- Check generalization with both future submissions and user-disjoint evaluation, keeping test
  results out of tuning. Audit split subgroup counts before fitting. Follow the feature allowlist
  and availability limits in `reports/features.md`.
- Use the simple student project layout in README.md: `code/`, `tests/`, `reports/`, and `data/`.
  Avoid adding duplicate phase reports, retired datasets, or empty placeholder folders.

- The user explicitly authorized publishing raw data. Track only the reviewed `data/raw_data.tar.gz`
  snapshot and its checksum; keep expanded raw/processed data, caches, and secrets ignored. Preserve
  public-data minimization and the frozen splits.
