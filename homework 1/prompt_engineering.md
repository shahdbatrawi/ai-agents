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
`outcome`, and a valid quoted list of expert calls. These examples demonstrate
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

## Live experiment results

Live API comparisons have not been run. Before the demo, record for each concept:
date/model, exact prompt/config change, actual outputs, repeated trial results,
and whether the technique helped or failed. Do not describe mocked tests as live
prompt experiments. Output instructions improve consistency but cannot guarantee
correctness; raw generated Python execution is suitable only for this exercise.
