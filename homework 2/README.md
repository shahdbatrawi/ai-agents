# CSE 491 — Homework 2: Resume Agent with Memory, Search by Meaning and Safe Writes

A Flask chat app on top of a resume database. It keeps its data between restarts, finds records by meaning (embeddings), routes each question to the right expert, and asks for a `yes` before any delete or overwrite.

All commands below are run from the `homework 2/` folder.

## Setup

1. Create and activate a virtual environment, then install the requirements (the `requirements.txt` is in the repository root):
   ```
   pip install -r ../requirements.txt
   ```
2. Copy `.env.example` to `.env` (put it in `homework 2/`) and fill in your key:
   ```
   cp .env.example .env
   ```

| Setting | What it is |
|---|---|
| `OPENROUTER_API_KEY` | Your OpenRouter key (required). Never commit `.env`. |
| `EMBEDDING_MODEL` | Model used for embeddings. Default in `.env.example`: `nvidia/nemotron-3-embed-1b:free` (free). |
| `SEARCH_MIN_SCORE` | Minimum similarity for a search result to count (`0.20`). This number belongs to the embedding model: if you change `EMBEDDING_MODEL`, re-measure with `python tests/probe_scores.py "your query"` and update it. |
| `RESUME_DB_PATH` | Optional. Database file; leave it out to use `flask_app/database/resume.db`. |

## Run the app

```
python app.py
```
 Open http://localhost:5000. 
 (The line printed in the terminal says 8080; that text comes from the provided `app.py`. The server really listens on port 5000.)
 The first start loads the resume CSVs once and creates the embeddings. After that, your data (including anything added through the chat) is kept between restarts. Each message prints a trace in the terminal (`[req N] ...`).

## Run the tests (one command)

```
python tests/run_scenarios.py
```
This prints PASS / FAIL for S1–S11 (plus U1, U2, which need no key). It builds a **separate** test database (`tests/.test_resume.db`) from the course test data (`fixtures/` if present, otherwise `tests/test_data/`), so your own resume is never touched. Scenarios marked `[API]` call the real models and need your key; without a key they are printed as SKIP.

## Reset the data

- **Test data:** nothing to do. The test command deletes and rebuilds its own database on every run.
- **Your app data:** stop the app, delete `flask_app/database/resume.db`, and start the app again. It reloads the CSVs and re-creates the embeddings.

## Where things are

| File | What it does |
|---|---|
| `flask_app/utils/database.py` | Tables, loading data once, embeddings sync, and `apply_operation` (the only place the AI's changes are written, with the approval check inside) |
| `flask_app/utils/write_ops.py` | The fixed list of allowed write operations and their checks |
| `flask_app/utils/embeddings.py`, `semantic_search.py` | Embedding API call and search by meaning |
| `flask_app/utils/llm.py` | Orchestrator plan (JSON, validated), Read/Content experts, search expert |
| `flask_app/utils/chat_flow.py` | One chat session, including the yes/no approval step |
| `flask_app/utils/trace.py` | The per-message trace |
| `flask_app/database/initial_data/llm_roles.csv` | The experts' prompts (re-synced at every start) |
| `tests/run_scenarios.py` | The one-command scenario tests |
| `tests/probe_scores.py` | Prints raw search scores, used to choose `SEARCH_MIN_SCORE` |

## Approval rule

A delete or overwrite never runs on the first request. The chat shows the exact action and waits. `yes` runs exactly that action; `no`, any unclear reply, or a new request cancels it. A pending action expires after 5 minutes, and a later `yes` cannot approve an old action.

See `DESIGN_AND_TESTING.md` for the design decisions, test results and known limits.