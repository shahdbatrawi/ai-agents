"""
llm.py — sends messages to an AI language model via the OpenRouter API.

This file is the bridge between your Flask app and an AI model (GPT-3.5).
When a student types a message in the chat, it travels here, gets sent to
OpenRouter, and the AI's reply comes back.

KEY CONCEPTS:
  - API (Application Programming Interface): a way for two programs to talk
    to each other over the internet. OpenRouter exposes an API we can call.
  - HTTP POST request: sending data to a server (like submitting a form).
    We POST the conversation to OpenRouter and it POSTs back the AI reply.
  - System prompt: instructions given to the AI before the conversation starts.
    Think of it as the AI's job description.
"""

import json
import os
import requests
import re

from flask_app.utils.embeddings import EmbeddingError
from flask_app.utils.database import EMBED_SOURCES
from flask_app.utils.semantic_search import search_by_meaning
from flask_app.utils.write_ops import parse_operation
from flask_app.utils.trace import log, one_line




# The URL we send our messages to.
# OpenRouter acts as a single gateway to many different AI models.
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Which AI model to use. OpenRouter supports many models.
# Models with ':free' suffix are free to use — no API credits needed.
# See all available models at: https://openrouter.ai/models
# QUESTION: What would change if you switched to a different model?
#           Try 'google/gemma-2-9b-it:free' or 'mistralai/mistral-7b-instruct:free'.
DEFAULT_MODEL = "openai/gpt-4o-mini"
from jinja2 import Template

MASTER_TEMPLATE = Template("""\
You are a {{ role }}, an expert in {{ domain }}.
{{ specific_instructions }}
{% if background_context %}
Context:
{{ background_context }}
{% endif %}
{% if few_shot_examples %}
Examples:
{{ few_shot_examples }}
{% endif %}
Request: {{ request }}""", trim_blocks=True, lstrip_blocks=True)



def fill_template(role, domain, specific_instructions, request,
                   background_context="", few_shot_examples=""):
    """
    Render MASTER_TEMPLATE into one expert's full system prompt.
    background_context and few_shot_examples are optional: the {% if %}
    blocks above drop the whole section — header included — when the
    argument is empty, instead of lingering a dangling "Context:" with
    nothing underneath it.
    """
    return MASTER_TEMPLATE.render(
        role=role,
        domain=domain,
        specific_instructions=specific_instructions,
        background_context=background_context,
        few_shot_examples=few_shot_examples,
        request=request,
    ).strip()


def send_message(user_message, system_prompt="You are a helpful assistant."):
    """
    Send a message to the AI and return its response as a string.

    Args:
        user_message  (str): The message the user typed in the chat.
        system_prompt (str): Instructions that define how the AI should behave.
                             This is sent before the user message, every time.

    Returns:
        str: The AI's reply text, or an error message if something went wrong.

    HOW IT WORKS:
        We build a 'messages' list with two entries:
          1. system — gives the AI its instructions (the resume context)
          2. user   — the student's actual question
        We send this list to OpenRouter, which forwards it to the AI model
        and returns the generated reply.

    # NOTE: This function has no memory — each call starts fresh.
    #       Every message includes the full system prompt but no chat history.
    # QUESTION: How would you modify this to remember previous messages?
    #           Hint: you would need to store past messages and include them
    #           in the 'messages' list between the system and user entries.
    """
    api_key = os.getenv('OPENROUTER_API_KEY')

    # If the .env file is missing or the key was not filled in, tell the user
    # immediately rather than making a doomed API call that will just hang.
    if not api_key or api_key == 'paste-your-key-here':
        return "⚠️ No API key found. Add your OpenRouter key to the .env file and restart the app."

    # The Authorization header tells OpenRouter who we are.
    # "Bearer" is just a standard prefix for API key authentication.
    # NEVER hardcode the api_key here — always load it from the .env file.
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8080"   # identifies our app to OpenRouter
    }

    # The messages list defines the conversation context for the AI.
    # 'system' sets the AI's role and knowledge before it sees our question.
    # 'user' is the message the student actually typed.
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message}
    ]

    # Send the HTTP POST request to OpenRouter.
    # timeout=30 means: give up if we don't hear back within 30 seconds.
    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json={"model": DEFAULT_MODEL, "messages": messages},
        timeout=30
    )

    result = response.json()

    # OpenRouter sometimes returns HTTP 200 but with an 'error' field instead
    # of 'choices' — this happens with a bad API key or an invalid request.
    # QUESTION: Print result here and see what OpenRouter actually sends back.
    if 'error' in result:
        error_message = result['error'].get('message', 'Unknown API error')
        return f"⚠️ OpenRouter error: {error_message}"

    if 'choices' not in result:
        return f"⚠️ Unexpected response from OpenRouter: {result}"

    return result['choices'][0]['message']['content']



# Experts the Orchestrator is allowed to call. Anything else in a plan is rejected.
ALLOWED_EXPERTS = {
    "Semantic Search Expert",
    "Database Read Expert",
    "Database Write Expert",
    "Content Expert",
}
MAX_PLAN_STEPS = 4


def handle_ai_chat_request(db, role, message, context="", tables=None):
    """
    Route a chat message to the named expert. role=None keeps Homework 0's
    original single-prompt behavior as a fallback.

    context: results of earlier plan steps (used by the Read/Write experts, so a
             second step can use exactly what the first step found).
    tables:  only used by the Semantic Search Expert (which tables to search).
    """
    if role is None:
        return send_message(message)

    # The Semantic Search Expert makes no model call: it embeds the query and
    # compares it with the stored embeddings (see semantic_search.py).
    if role == "Semantic Search Expert":
        return run_semantic_search(db, message, tables)

    config = db.getLLMRoles()[role]
    background_context = config['background_context'] or ""
    if role == "Content Expert":
        # No page-scraping in this stack -- "current page content" is the
        # resume data itself, fetched fresh on every request.
        background_context += "\n" + db.getResumeText()
    if context and role in ("Database Read Expert", "Database Write Expert"):
        background_context += "\n" + context

    system_prompt = fill_template(
        role=config['role'],
        domain=config['domain'],
        specific_instructions=config['specific_instructions'],
        background_context=background_context,
        few_shot_examples=config['few_shot_examples'] or "",
        request=message,
    )
    output = send_message(message, system_prompt).strip()
    log(f"{role} generated: {one_line(output)}")

    if role == "Database Read Expert":
        return execute_read_query(db, output)
    if role == "Database Write Expert":
        return execute_write_action(db, output)
    if role == "Orchestrator":
        return run_orchestrator_plan(db, message, output)
    return output   # Content Expert -- output is already the final answer


def run_semantic_search(db, query, tables=None):
    """
    Search by meaning and return a plain-text list of ranked matches. The text
    starts with "NO MATCH" or "SEARCH FAILED" when there is nothing usable, so
    later code (and the final reply) can say so honestly instead of guessing.
    """
    cutoff = os.getenv("SEARCH_MIN_SCORE") or "0.0"
    scope = ", ".join(tables) if tables else "all tables"
    try:
        results = search_by_meaning(db, query, tables=tables)
    except EmbeddingError as error:
        log(f"Semantic Search Expert: embedding failed: {error}")
        return f"SEARCH FAILED: the search is unavailable right now ({error})."
    except ValueError as error:
        log(f"Semantic Search Expert: bad request: {error}")
        return f"SEARCH FAILED: {error}"

    log(f"Semantic Search Expert: query={query!r} tables={scope} cutoff={cutoff}")
    for r in results:
        log(f"    score {r['score']:.3f}  {r['table']}#{r['id']}  {r['text'][:70]}")

    if not results:
        log("    NO MATCH: nothing above the relevance cutoff")
        return (f"NO MATCH: nothing relevant to '{query}' was found in {scope} "
                f"(relevance cutoff {cutoff}).")
    return "\n".join(
        f"{r['table']} #{r['id']} name='{r['name']}' score={r['score']:.3f} text='{r['text']}'"
        for r in results
    )


def execute_read_query(db, sql):
    """
    Run the Database Read Expert's generated SQL. We refuse anything that
    isn't a SELECT -- this expert is read-only by design, so there's never
    a legitimate reason to run anything else, even if a user's message
    somehow tricks the model into generating something else.
    """
    if not sql.strip().upper().startswith("SELECT"):
        return "Sorry, I couldn't safely answer that question."
    try:
        return str(db.query(sql))
    except Exception as error:
        log(f"Read Expert query failed: {error}")
        return "Sorry, that question couldn't be answered."


def execute_write_action(db, output):
    """
    Turn the Database Write Expert's output into ONE allowed operation (JSON, see
    write_ops.py) and apply it. Nothing the model wrote is executed.

    A destructive operation raises ApprovalRequired from db.apply_operation. We let
    it travel up to chat_flow.py, which asks the user yes/no. Nothing has been
    changed at that point.
    """
    try:
        operation = parse_operation(output)
    except ValueError as error:
        log(f"write request refused: {error}")
        return "I couldn't turn that into an allowed change, so nothing was modified."
    log(f"write operation: {operation}")
    return db.apply_operation(operation)


def parse_plan(plan_text):
    """
    Read the Orchestrator's plan as DATA (JSON) and check it. Raises ValueError if
    anything is wrong. Nothing from the model is ever executed here.

    Expected: a JSON list of steps, each like
        {"expert": "<allowed expert>", "message": "...", "reason": "...",
         "tables": ["skills"]}            <- tables only for the Semantic Search Expert
    """
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", plan_text.strip())
    try:
        plan = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"the plan is not valid JSON ({error.msg})")
    if isinstance(plan, dict) and "steps" in plan:
        plan = plan["steps"]
    if not isinstance(plan, list) or not plan:
        raise ValueError("the plan must be a non-empty list of steps")
    if len(plan) > MAX_PLAN_STEPS:
        raise ValueError(f"the plan has more than {MAX_PLAN_STEPS} steps")

    steps = []
    for number, step in enumerate(plan, 1):
        if not isinstance(step, dict):
            raise ValueError(f"step {number} is not an object")
        expert, message = step.get("expert"), step.get("message")
        if expert not in ALLOWED_EXPERTS:
            raise ValueError(f"step {number} uses an unknown expert: {expert!r}")
        if not isinstance(message, str) or not message.strip():
            raise ValueError(f"step {number} has no message")
        tables = step.get("tables")
        if tables is not None:
            if (not isinstance(tables, list) or not tables
                    or not all(t in EMBED_SOURCES for t in tables)):
                raise ValueError(f"step {number} has invalid tables: {tables!r}")
        steps.append({
            "expert": expert,
            "message": message.strip(),
            "tables": tables,
            "reason": str(step.get("reason", "")).strip()[:200],
        })
    return steps


def _earlier_results_context(results):
    """Turn the results of earlier steps into context for the next step."""
    if not results:
        return ""
    lines = "\n".join(f"[{expert}] {response}" for expert, _, response in results)
    return ("Results of earlier steps. Use the exact names shown here (the "
            "name='...' values) in your SQL; do not guess names:\n" + lines)


def run_orchestrator_plan(db, original_request, plan_text):
    """Run the experts in the Orchestrator's plan, in order, and summarize results."""
    try:
        steps = parse_plan(plan_text)
    except ValueError as error:
        log(f"invalid plan: {error} | received: {one_line(plan_text, 150)}")
        return "Sorry, I couldn't plan a response to that."

    log("route: " + " -> ".join(step["expert"] for step in steps))
    results = []
    for number, step in enumerate(steps, 1):
        log(f"step {number}/{len(steps)}: {step['expert']} | reason: {step['reason'] or '-'}")
        response = handle_ai_chat_request(
            db, step["expert"], step["message"],
            context=_earlier_results_context(results),
            tables=step["tables"],
        )
        results.append((step["expert"], step["message"], response))

        # If the search found nothing usable, later steps depend on it: stop here.
        if (step["expert"] == "Semantic Search Expert"
                and str(response).startswith(("NO MATCH", "SEARCH FAILED"))
                and number < len(steps)):
            log("the search found nothing usable: skipping the remaining steps")
            break

    steps_summary = "\n".join(
        f"{expert}: {response}" for expert, message, response in results
    )

    synthesis_prompt = (
        f'The user asked: "{original_request}"\n\n'
        f"Expert results:\n{steps_summary}\n\n"
        "Give one short, clear reply based ONLY on the expert results. Rules: "
        "If a Database Write Expert returned the exact success or already-exists "
        "message, reuse it verbatim. "
        "If a result starts with NO MATCH, say you could not find anything matching "
        "the request, and do not guess. "
        "If a result starts with SEARCH FAILED, say the search is unavailable right "
        "now, and do not guess. "
        "When records were found, name them exactly as shown. "
        "Never mention scores, SQL, experts or internal steps. "
        "Do not invent resume information or claim a change succeeded if it failed."
    )

    return send_message(original_request, synthesis_prompt)