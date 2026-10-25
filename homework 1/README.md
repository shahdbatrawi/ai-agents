# Homework 1 — Multi-expert resume agent

Jamal's Homework 0 resume now uses Database Read, Database Write, Content,
and Orchestrator roles. All share `openai/gpt-4o-mini` through OpenRouter;
their prompts are configured in the `llm_roles` table.

## Run

Install the unchanged requirements from the repository root, preferably in a
virtual environment: `pip install -r requirements.txt`. Then:

```sh
cd "homework 1"
# Copy .env.example to .env and enter your OPENROUTER_API_KEY.
python app.py
```

Open http://localhost:8080/resume. Live chat needs an OpenRouter key with access
and credits for the configured model. Keep the terminal visible to see plans,
SELECT statements, generated Python, and ordered expert execution.

Database changes survive page reloads and server restarts (`purge=False`).
To reset Homework 1, stop the app, delete only its
`flask_app/database/resume.db`, and restart. Homework 0 is separate.

## Tests and demonstration

From `homework 1`, run `python -m unittest discover -s tests -v`.
Tests use temporary SQLite databases and mocked model outputs; they execute
actual SQL, generated Python fixtures, and Socket.IO handlers without API costs.
They do not measure live model quality. Follow `documentation/demo_checklist.md`
to record the required live video and complete the live prompt comparisons in
`prompt_engineering.md`.

The plan parser uses `ast.literal_eval` and validated AST calls instead of
`eval`, handling quoted messages and rejecting invalid plans before execution.
Earlier results are passed to later experts to support conditional requests.
The Write Expert still uses `exec` as required by the classroom exercise;
this local app is not a production code-execution sandbox.

Socket.IO uses threading mode to support Python 3.13 with the existing pinned
dependencies; no requirements were added or changed.
