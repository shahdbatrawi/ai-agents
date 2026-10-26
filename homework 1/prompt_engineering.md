# Prompt engineering concepts and evaluation

## 1. Role prompting and grounding

The shared Jinja2 template supplies each expert's role, domain, instructions,
context, and examples. The Read Expert gets the database schema and a SELECT-only
instruction; the Content Expert gets fresh resume text and must use only that.

Comparison: ask "What is this page about?" with `role=None` and then through the
Orchestrator. Compare whether answers reference Jamal's actual projects. Ask
about a fact absent from the resume and check whether the answer avoids guessing.

Local automated evidence verifies that actual resume text reaches the Content
Expert and blank template sections disappear. It does not measure live adherence.

## 2. Few-shot prompting and explicit output formats

The CSV includes a valid SELECT, duplicate-check/insertion Python with exact
`outcome`, and an example list of expert calls from the handout. The supplied example omits inner quotes around role/message values, even though the instructions and regex require them. These examples demonstrate
syntax alongside instructions. The context specifies dict rows and Python None.

Comparison: temporarily clear only the Read Expert's `few_shot_examples` in
SQLite and repeat the same question. Restore the example and repeat. Compare
SQL validity, exact institution matching, and unwanted explanation. Also repeat
a skill insertion and inspect the different insert/duplicate outcome messages.
Keep all other settings fixed; repeat trials because model output varies.

Local automated evidence verifies the role configs load and action fixtures
insert once and return a duplicate message on repetition. Live improvement from
the examples remains to be measured with an actual model.

## 3. Task decomposition and ordered coordination

The Orchestrator breaks "Does he know Rust? If not, add it to AI Agents & Prompt
Engineering" into a read followed by a conditional write. The write checks the database again before inserting. A final
model call synthesizes the expert results.

Comparison: send the conditional request directly to the Write Expert, then
through the Orchestrator. Compare correctness with Rust absent and already
present. Inspect the plan and execution order. A two-expert plan takes four
model calls (plan, read, write, synthesis), increasing latency and cost.

Local automated evidence verifies actual read/write handlers run in order,
duplicates are prevented. This tests
coordination with model fixtures, not live planning quality.

## Observed live results — 2026-10-26

These observations come from the actual terminal logs supplied by the student,
not mocked tests. They are not a controlled before/after prompt experiment.

- **Role prompting and grounding:** In one free-router run, the Orchestrator
  selected Content Expert, and that expert described the actual UCAS studies,
  SPOCs training, NASA Orbit X, SQL/database project, and Python/Blender work.
  This shows relevant resume grounding for that individual expert response.
  The final UI response was reported as `User Safety: safe`, so the complete
  content workflow did not pass. The log did not identify the final model;
  attributing the bad synthesis to a particular model would be speculation.
- **Few-shot output formatting:** Another real plan omitted inner quotes and
  included a trailing Markdown fence. The handout parser rejected it. A later
  plan used escaped double quotes correctly and was executed. This shows that
  format instructions/examples did not guarantee consistent valid plans.
  The handout's Orchestrator example itself omits inner quotes, while its
  instructions and parser require them. No controlled example-on/example-off
  comparison has been completed, so improvement cannot be quantified.
- **Task decomposition:** A one-step Content Expert plan executed in a real
  run. The required two-step Read -> Write workflow has passed local fixture
  tests only. Its live effectiveness remains unverified.

Current configuration: `qwen/qwen3-coder:free`. On 2026-10-26 a direct
OpenRouter authentication check returned HTTP 401, `User not found.`. No resume
content was sent in that check. Live experiments were stopped rather than
fabricating results or repeatedly requesting inference with a rejected key.

## Still required before submission

Run the three comparisons described above after installing a valid key. Record
exact prompts, configuration changes, actual outputs, model, and repeated trials.
Complete all four live application flows and record the demonstration. Current
observations and local tests do not establish full rubric compliance.
