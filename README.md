# SmartIR: Smart Institutional Repository Prototype

SmartIR (Smart Institutional Repository Prototype) is a research-oriented repository system built using the University of Lagos (UNILAG) as a case study. It was created for a Master's research project on designing and implementing a smart institutional repository.

## Key features

Self-submission of theses, dissertations, and articles with PDF upload.
Live metadata quality checking using Dublin Core standards and university rules, with a quality score displayed as users type.
Duplicate detection that flags similar titles before submission.
Subject term suggestions from existing repository vocabulary.
Librarian review workflow with approval, return, withdrawal, normalization tools, and audit logs.
Full-text search across metadata and PDF contents with filtering options.
Access control supporting open, embargoed, and restricted items.
Citation export in APA 7 and BibTeX formats.
Analytics dashboard for views, downloads, searches, and metadata quality metrics.
OAI-PMH 2.0 interoperability for metadata harvesting via /oai.

## Run it on a laptop (Windows, macOS or Linux)

You need Python 3.10 or newer (python.org).

```
cd smart-ir
python -m venv .venv
.venv\Scripts\activate          (Windows)   or   source .venv/bin/activate   (macOS/Linux)
pip install -r requirements.txt
python seed.py
uvicorn app.main:app
```

Open https://smart-ir-xzzg.onrender.com in a browser.

### Demonstration accounts (password: Demo@2026)

| Role | Email |
|---|---|
| Depositor (student or staff) | depositor@demo.edu.ng |
| Librarian (repository manager) | librarian@demo.edu.ng |
| Administrator | admin@demo.edu.ng |

To start again with a clean database: `python seed.py --reset`

## Suggested demonstration (5 minutes)

1. Home page, then search "lagos" and use the faculty filter.
2. Open an item: Dublin Core record, citation export, related items.
3. Log in as depositor, open Submit work, type an author as `adebayo, k.o` and a date as `12/05/2025` to show the live quality check.
4. Type the title "Market Structure Paradigm and Institutional Settings in the Nigerian Electricity Industry" to show the duplicate warning.
5. Complete a good record and submit.
6. Log in as librarian, open the Review queue, approve it.
7. Open Metadata quality, choose "UNILAG records only" to show the audit of real records.
8. Open Analytics.
9. Open http://127.0.0.1:8000/oai?verb=ListRecords&metadataPrefix=oai_dc to show harvestable metadata.

## Deploy online (free, about 10 minutes)

1. Put this folder in a GitHub repository.
2. Sign in at render.com, choose New, then Blueprint, and select the repository. `render.yaml` configures everything.
3. Render gives a public address such as https://smartir.onrender.com.

On the free plan the database resets when the service restarts, which is fine for a demonstration. Docker users can run `docker build -t smartir . && docker run -p 8000:8000 smartir`.

## Tests

```
pip install -r requirements-dev.txt
python -m pytest tests -q                       # 48 functional test cases
python tests/audit_unilag.py                    # metadata audit of the UNILAG records
python tests/benchmark_performance.py 10000     # performance test with 10,000 synthetic records
```

Results are written to `tests/results/`.

## Data

`data/unilag_records.json` holds 15 records transcribed from public item pages of the University of Lagos Institutional Repository (ir.unilag.edu.ng) on 16 November 2026: 10 doctoral theses with full metadata and 5 recent staff publications. Synthetic records are created only by the performance test and are marked `origin = demo`.

## Project structure 

```
app/main.py        web routes, workflow, search, analytics
app/quality.py     metadata quality engine (DCMI and Bruce and Hillmann framework)
app/dedup.py       duplicate detection
app/oai.py         OAI-PMH 2.0 provider
app/citation.py    APA and BibTeX export
app/db.py          SQLite schema with FTS5 full-text index
app/templates/     pages
seed.py            database set-up and data loading
tests/             functional tests, audit, benchmark, screenshot capture
```
