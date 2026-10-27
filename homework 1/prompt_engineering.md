### Prompt Engineering Concepts

# Homework 1: Prompt Engineering Concepts & Effectiveness
# Prompt Engineering Concepts

## 1. Role prompting (one template, four experts)
Every expert gets its system prompt from the same Jinja template, and only the
role, domain and instructions change. Telling the model "you are a Database Read
Expert, an expert in SQL query generation" made a real difference: it returned
plain SQL for questions and Python for writes, instead of chatty answers like in
Homework 0.

**Effectiveness:** High. The Read Expert reliably produced valid SELECT queries
(e.g. the join between `positions` and `institutions`), and the Content Expert
stayed grounded in the resume text.

## 2. Few-shot examples
Each expert has one example in its prompt showing the exact output shape. This
shaped the output more than the written instructions did. The Orchestrator's
plans came back as `handle_ai_chat_request(role=Content Expert, message=...)`
without quotes around the role, which is exactly how my example was written, even
though the instructions asked for quotes. The Write Expert also followed the
"check if it exists, then insert, then set `outcome`" pattern from its example.

**Effectiveness:** High, but the model copies the example's quirks too, so I had
to make my plan parser tolerant of the format the example taught.

## 3. Output format constraints and grounding
I told the experts "SQL only, no markdown", and gave them the database schema as
context so they wouldn't invent table names. The schema grounding worked well:
no wrong table or column names showed up. The "no markdown" rule worked less
well: the Orchestrator sometimes wrapped its plan in a ```python block anyway,
which broke `eval()`. I fixed that in code by stripping the fences before parsing.
Vague wording also caused trouble: for "most recent experience" the model once
sorted by `end_date` and once by `start_date`, so the skill landed on different
experiences.

**Effectiveness:** Schema grounding was very effective. Format rules helped but
can't be trusted alone, so I added code to enforce them. Being specific in the
request (naming the experience) gives more consistent results.