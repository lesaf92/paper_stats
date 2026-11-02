# Changelog

All notable changes to this project. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Read-only mode for public deployments. On Vercel (`VERCEL=1`) or with `READ_ONLY=1`, the run and save buttons are hidden, POST requests get 403, and the committed results are served.
- `.vercelignore` and README instructions for publishing on Vercel.
- Offline Flask route checks for read-only behavior and configuration bounds.

### Changed
- `results.json` is committed, because it is what the website serves.
- Crossref publication dates now prefer online, print, published, and issued fields; metadata creation dates are not treated as publication dates.
- Configuration inputs are bounded, and completed results replace the previous JSON file atomically.
- Clarify that the arXiv-to-publication proxy has no fixed direction relative to review time.

## [0.2.0] - 2026-10-18

### Added
- **Real review times.** Each paper now gets its received and accepted dates from the journal itself:
  - Crossref article history, deposited by Springer and Wiley (Autonomous Robots, Journal of Intelligent & Robotic Systems, Journal of Field Robotics, ...).
  - The "Manuscript received ...; accepted ..." footnote on the first page of the arXiv PDF, which covers many IEEE papers (T-RO, RA-L, IEEE Access, ...).
- **Venue check.** Crossref's container title has to match the journal name. arXiv's `jr:` search matches phrases, so a query for *Robotics and Autonomous Systems* used to pull in *Annual Review of Control, Robotics, and Autonomous Systems*, and *Autonomous Robots* pulled in conference papers.
- **Proxy metric kept separate.** "arXiv v1 → journal publication" is still computed but plotted and summarized next to the measured review time, never mixed into it.
- Summary table per journal: papers, measured papers, median review time, IQR, median proxy, sorted fastest first.
- CSV export of every paper (`/results.csv`).
- Background analysis with real progress (`/status`), replacing the simulated progress bar and the request that blocked for the whole run.
- Results saved to `results.json`, so the last run is shown after a restart.
- `cache.json`: Crossref and PDF lookups are cached per arXiv id, so later runs are fast and send fewer requests to arXiv.
- Configuration option `mine_pdfs` to turn PDF reading on or off.
- `test_collector.py`: offline checks for date parsing, footnote matching, venue matching and statistics.
- `README.md`, `CHANGELOG.md`, `requirements.txt`.

### Changed
- Data collection moved from `server.py` to `collector.py`, which runs without Flask.
- The year range now filters on the **journal publication year**. It used to filter on the arXiv last-updated year.
- arXiv is queried over HTTPS and sorted by submission date. PDFs come from `export.arxiv.org`, the mirror arXiv asks programmatic clients to use.
- Box plots are horizontal and grouped (measured and proxy), with every paper shown as a point and its title on hover.
- Paper tables are rendered on the server, with a source badge per paper (`crossref`, `pdf`, `proxy`).
- `algorithm.md` describes the new pipeline. The duplicate, unfenced second flowchart was removed.
- The page is titled "Paper Stats", matching the project name.

### Fixed
- XSS: paper titles from arXiv were inserted with `innerHTML`. Templates now auto-escape them.
- The Flask secret key was hard-coded. It now comes from `SECRET_KEY` or is random per process.
- The server ran with the Werkzeug debugger on `0.0.0.0`, which let anyone on the network run code. It now listens on `127.0.0.1` with debug off by default (`HOST`, `FLASK_DEBUG` to override).
- Config, journal and results files are found relative to the script, not the current directory.
- Saving a config with a start year after the end year, or zero papers, is rejected.

### Removed
- `test_pdf_miner.py`: its regex approach is now `collector.dates_from_text`, covered by `test_collector.py`.
- The "Scrapling" progress text and unused CSS.

## [0.1.0] - 2026-03-04

### Added
- Flask app that queries arXiv by journal reference for each journal in `list_of_journals.txt`.
- Review time approximated as the arXiv first-version date to last-update date.
- Plotly box plot per journal, per-journal paper tables, configuration tab (`config.json`).
- Retry with backoff on HTTP 429/503 and a 3-second delay between arXiv requests.
- `algorithm.md` flowchart for the methodology section.
- `test_pdf_miner.py` experiment for reading dates out of arXiv PDFs.
