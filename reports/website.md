# Interactive website

The static site in `website/` is implemented and tested locally in Chromium. **GitHub Pages
publication and deployed-site verification remain pending.** It works without a Python or Node
backend: Python is used only to regenerate the saved data export.

## Preview

```bash
python3 -m http.server 8000 --directory website
```

Open `http://localhost:8000`. Opening `index.html` directly with a `file:` URL can block JSON
loading; use the HTTP preview command. The checked-in `data.json` and images make a fresh-clone
preview possible without training or downloading expanded raw data.

## Useful interactions

- Enter one of three saved handles, matched case-insensitively. Unknown handles show a clear error;
  no arbitrary live API lookup is claimed.
- Inspect topic counts, matched comparison evidence, relative gaps and descriptive rate intervals.
  Clicking a topic filters candidate problems.
- Change topic and minimum/maximum difficulty, reset filters, or show more problems. Filters operate
  on every exported candidate within that example's stated default difficulty window, not just the
  first ten recommendations. Out-of-window filters return no results rather than inventing data.
- Sparse histories show exploration only and withhold candidate probability estimates.
- Compare the three models and baseline on future submissions versus unseen users, using equal-user
  or equal-submission averaging. Results and uncertainty update with the selection.
- Inspect calibration plots, cohort coverage, real validation error examples, the study methods,
  limitations, reproduction steps, sources and AI disclosure.

The examples are `ethanxupro`, `BaJIuK`, and `rahma_hisham925`, all from saved 23 October 2026
captures. The latter two have no mature post-training evidence at their capture time and therefore
show exploration suggestions. A high rating alone does not establish sufficient recent topic
information. The page identifies these as saved examples, not a live analysis service.

## Regenerate the static data

After restoring the data and reproducing the frozen model artifact:

```bash
python3 code/make_website_data.py
```

The exporter verifies the frozen model through the recommendation loader, uses the existing final
results, and writes the three example summaries and candidates plus aggregate results to
`website/data.json`. It copies the two explanatory plots into `website/images/`. The export includes
public example handles, public problem links, pseudonymous diagnostic IDs and model evidence; it
does not include entire raw histories, profile locations, names, credentials or trained binaries.
Source/model/code hashes are included for traceability. No training or final-test scoring occurs.

## Checks performed

```bash
python3 -m unittest discover -s tests -q
node --check website/script.js
python3 tests/check_website.py
```

The optional browser check requires `playwright` (tested with Python package version 1.62.0) and
Chromium. It uses a local system `chromium` if available, otherwise Playwright's installed Chromium.
Install browser-test dependencies separately from model dependencies:

```bash
python3 -m pip install playwright==1.62.0
python3 -m playwright install chromium
```

Browser checks cover user selection, invalid handles, sparse-user fallback, topic/difficulty
filters, invalid ranges, empty results, pagination, population/averaging switches, JSON-load
failure, absence of JavaScript page errors, and no horizontal page overflow at a 390-pixel mobile
viewport. Desktop and mobile screenshots were inspected. Controls have labels, keyboard focus
styles, a skip link, semantic sections and table captions; this is not a comprehensive accessibility
certification.

The 42 existing Python tests also pass. Local browser success does not establish deployed-site
availability or live Codeforces access.

## Publish on GitHub Pages

The manual workflow `.github/workflows/website.yml` uploads only `website/` and deploys it as a
static Pages artifact. It does not run on every push and does not expose expanded raw/processed
working directories.

1. Push the reviewed project files and workflow to the repository.
2. Set the repository's **Settings → Pages → Source** to **GitHub Actions**.
3. Run **Actions → Publish website → Run workflow** on the intended branch.
4. Inspect the deployment output for the actual URL; verify navigation, saved examples, filters,
   results, images, external report links and mobile layout at that URL.
5. Record the verified live URL and submit both it and the source-repository link as required.

The expected project-site URL, once deployment succeeds, is
`https://sarthaksaini041.github.io/DSA-weakness/`. This is an expected URL, not a verified live
link. Student identities, contribution statements, defense preparation and portal submission remain
the team's responsibility and are not fabricated on the site.
