"""
chat_flow.py — one chat conversation, including the yes/no approval step.

Rules for a destructive change (a delete or an overwrite):
  1. The Write Expert asks for it -> database.apply_operation raises ApprovalRequired
     BEFORE anything is changed. We save the exact operation as "pending" and ask.
  2. The very next message decides:
        "yes"  -> run exactly that saved operation (and only that one)
        "no"   -> cancel
        anything else (maybe, a new question, ...) -> cancel too. Nothing is deleted
        unless the user clearly said yes.
  3. A pending change expires after `ttl` seconds, and it is cleared after any answer,
     so a later "yes" can never approve an old action.
"""

import re
import time

from flask_app.utils.database import ApprovalRequired
from flask_app.utils.llm import handle_ai_chat_request

YES = {"yes", "y", "confirm"}
NO = {"no", "n", "cancel"}


def _answer(text):
    word = re.sub(r"[^\w]+", " ", text.lower()).strip()
    return "yes" if word in YES else "no" if word in NO else "unclear"


class ChatSession:
    def __init__(self, db, ttl=300, clock=time.time):
        self.db = db
        self.ttl = ttl
        self.clock = clock
        self.pending = None          # {"operation", "preview", "asked_at"} or None

    def handle(self, text):
        text = text.strip()
        if self.pending:
            return self._handle_answer(text)
        try:
            reply = handle_ai_chat_request(self.db, role="Orchestrator", message=text)
            print("[trace] approval: none")
            return reply
        except ApprovalRequired as needed:
            self.pending = {"operation": needed.operation, "preview": needed.preview,
                            "asked_at": self.clock()}
            print(f"[trace] approval: waiting | {needed.operation}")
            return f"{needed.preview} Nothing has been changed yet. Reply yes to confirm or no to cancel."
        except Exception as error:
            print(f"LLM error: {error}")
            return "Sorry, something went wrong answering that."

    def _handle_answer(self, text):
        pending, self.pending = self.pending, None      # always cleared after one answer
        if self.clock() - pending["asked_at"] > self.ttl:
            print("[trace] approval: cancelled (expired)")
            return "That confirmation expired, so nothing was changed. Please ask again."
        answer = _answer(text)
        if answer == "yes":
            print(f"[trace] approval: approved | {pending['operation']}")
            try:
                return self.db.apply_operation(pending["operation"],
                                               approved_operation=pending["operation"])
            except Exception as error:
                print(f"Approved change failed: {error}")
                return "Sorry, that change failed and nothing was modified."
        print(f"[trace] approval: cancelled ({answer})")
        return "Cancelled. Nothing was changed. Send your request again if you still want it."