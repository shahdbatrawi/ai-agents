# Homework 1 — AI Agents

Implementation follows the supplied Homework 1 steps, extending Jamal's Homework 0.
All four roles use `openai/gpt-4o-mini` through OpenRouter.

## Run

Install the repository requirements, enter your own OpenRouter key in a local
`.env` file using `.env.example`, then from `homework 1` run `python app.py`.
The assignment uses port 8080. Its default Socket.IO setup uses the installed
async backend. The pinned eventlet dependency is incompatible with Python 3.13;
use a compatible Python environment for the handout's unchanged startup code.

Startup uses `db.createTables(purge=True)` exactly as the handout specifies.
A browser reload preserves added rows; restarting the server resets the database.
The Orchestrator uses the supplied `eval` and regex parser, and generated writes
use `exec`. These retain the classroom design and its documented limitations.

## Local verification

From `homework 1`: `python -X utf8 -m unittest discover -s tests -v`.
The test harness selects threading only during tests to avoid the local eventlet
compatibility problem; the delivered application factory follows the handout.
Tests use temporary SQLite and mocked model outputs, with no live API requests.
Live API behavior and prompt experiments remain unverified due to the key limit.
See the demo checklist and fill in actual results in `prompt_engineering.md`.
