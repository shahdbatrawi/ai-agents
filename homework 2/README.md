# Homework 2 — Semantic Search and Safe Database Writes

This application extends my Homework 1 Flask resume agent with semantic
search, persistent embeddings, validated operations, and explicit approval
before deletion.

## Setup

Run these commands from the repository root:

```bash
python -m venv .venv
```

Activate the environment on Windows Git Bash:

```bash
source .venv/Scripts/activate
```

On Windows CMD:

```cmd
.venv\Scripts\activate
```

Install dependencies and enter the homework folder:

```bash
python -m pip install -r requirements.txt
cd "homework 2"
```

Create a local `.env` file in this folder using `.env.example` as a template.
Configure these settings privately:

- OPENROUTER_API_KEY
- OPENROUTER_CHAT_MODEL
- OPENROUTER_EMBEDDING_MODEL
- SEMANTIC_MIN_SCORE

Use the embedding model announced by the course team.
The chat model must support the structured JSON output used by this app.
Do not commit `.env` or API keys.

## Run the application

From `homework 2`:

```bash
python app.py
```

Open http://localhost:8080 and navigate to the resume chat.

Normal startup preserves existing resume records. Initial resume CSVs
load when their tables are first created. LLM role configuration reloads
on startup so prompt edits take effect without restoring deleted skills.

## Run all scenarios

From `homework 2`, with the environment activated:

```bash
python tests/run_scenarios.py
```

This command runs S1–S11, prints traces and individual PASS/FAIL results,
and returns a nonzero exit code if a scenario or test script fails.
Internet access and working OpenRouter settings are required.

The current development dataset is based on the original sample resume
and includes Machine Learning and Public Speaking. It is not verified
against the official Homework 2 fixtures. The observed development run
passed 11/11 scenarios.

The calibration database is stored at `tests/calibration.db`. Chat write
tests operate on temporary copies of that database. They do not change
the application's `resume.db`.

S5 checks the saved skill and embedding in a separate Python process.
S10 temporarily substitutes an invalid embedding model, checks that no
skill or embedding was saved, restores the environment, and verifies that
chat still works.

## Reset test data only

Stop any running test command first. From `homework 2`, run:

```bash
python -c "from pathlib import Path; Path('tests/calibration.db').unlink(missing_ok=True)"
python tests/run_scenarios.py
```

This removes only the development calibration database. The test runner
recreates it from `tests/sample_data` and adds the development category
skills. Embeddings are regenerated as needed.

Do not delete `flask_app/database/resume.db`: that is the application's
resume database.

## Search and approval behavior

Exact listings and counts use the Database Read Expert. Abbreviations
and skill categories use semantic search over relevant tables.

Semantic results include the source table, record ID, embedded text,
and cosine similarity score. The configured cutoff determines whether
a result is accepted. No accepted results produces an explicit
"No matching records found" reply.

Allowed writes are adding a skill, deleting matching skills, and deleting
all skills. Unsupported operations are rejected.

Deletion first displays the exact records and stores their snapshots
on the server. Only `yes` from the same client approves that pending
action. Approval executes the stored action without asking the model
to generate it again.

`no`, unclear replies such as `maybe`, a change of subject, or a
disconnect cancel the pending action. A later `yes` cannot approve it.
Associated embeddings are removed with approved skill deletions.

## Project files

- `flask_app/utils/llm.py`: routing, validated plans, read-only SQL.
- `flask_app/utils/semantic_search.py`: embeddings, storage, similarity.
- `flask_app/utils/semantic_routes.py`: semantic and dependent retrieval.
- `flask_app/utils/safe_writes.py`: validated writes and approval gate.
- `flask_app/utils/socket_events.py`: chat handling and request traces.
- `tests/run_scenarios.py`: single-command development scenario runner.
- `DESIGN_AND_TESTING.md`: architecture, decisions, evidence, limitations.