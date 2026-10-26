# Validation status — 2026-10-26

Current branch: Jamal_HM1. Current model: qwen/qwen3-coder:free.

| Check | Result | Evidence |
| --- | --- | --- |
| Local application startup | Passed | Python 3.12, native eventlet, resume HTTP 200 |
| Local regression suite | Passed | Eight tests with mocked model outputs and temporary SQLite |
| Four role configurations | Passed locally | Table created/seeded and role-name assertion |
| Current OpenRouter authentication | Blocked | Direct auth endpoint returned HTTP 401, User not found. |
| Live database read | Not verified | Authentication must succeed first |
| Live database write and browser refresh | Not verified | Fixture writes/reloads are not a real-model demo |
| Live compound Read -> Write | Not verified | Only fixture coordination passed |
| Live content answer | Partial historical evidence | Content Expert response was grounded, final UI response failed |
| Three controlled prompt experiments | Incomplete | Observations documented in prompt_engineering.md; comparisons pending |
| Demo recording and submission | Pending student | Requires the student's name, voice, visible console and browser |

No live test or experiment is reported as passed merely because source code or
mocked tests exist. The current blocker is authentication, not demonstrated
model reasoning or planning quality. Replace the key locally in the root .env
and restart; never put keys or .env contents in the recording or repository.

The script `scripts/check_connection.py` provides a small authenticated probe
without sending the resume. Run it from `homework 1` using the root venv.
