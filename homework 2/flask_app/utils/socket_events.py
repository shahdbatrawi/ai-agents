"""Chat routing, approval handling, and request tracing."""

import json
from threading import RLock
from uuid import uuid4

from flask import current_app, request
from flask_socketio import emit

from flask_app import socketio
from flask_app.utils.llm import handle_ai_chat_request
from flask_app.utils.safe_writes import SafeWrites


_writer_lock = RLock()


def get_writer():
    """Keep one approval manager per application."""
    with _writer_lock:
        if "safe_writes" not in current_app.extensions:
            current_app.extensions["safe_writes"] = SafeWrites(
                current_app.db
            )

        return current_app.extensions["safe_writes"]


@socketio.on("send_message")
def handle_message(data):
    request_id = uuid4().hex[:12]
    client_id = request.sid

    def trace(event, **details):
        record = {
            "request_id": request_id,
            "event": event,
            **details,
        }
        print(
            json.dumps(record, ensure_ascii=False),
            flush=True,
        )

    if not isinstance(data, dict):
        trace(
            "finished",
            approval="none",
            outcome="invalid_message",
        )
        emit(
            "receive_message",
            {"response": "Please send a text message."},
        )
        return

    message = data.get("message")

    if not isinstance(message, str) or not message.strip():
        trace(
            "finished",
            approval="none",
            outcome="empty_message",
        )
        return

    message = message.strip()

    try:
        writer = get_writer()

        # Every new message consumes or cancels an older pending action.
        approval = writer.answer(client_id, message)
        normalized = message.lower()

        if approval is not None:
            trace(
                "approval",
                route="confirmation",
                reason="A pending action was answered.",
                approval=approval["state"],
                outcome=approval["reply"],
            )

            if normalized in {"yes", "no", "maybe", "hmm"}:
                reply = approval["reply"]

                trace(
                    "finished",
                    approval=approval["state"],
                    outcome=reply,
                )
                emit("receive_message", {"response": reply})
                return

            # A different request cancels the old action,
            # then continues through the Orchestrator.
            prefix = "Previous pending action cancelled.\n"
        else:
            prefix = ""

        if normalized in {"yes", "no", "maybe", "hmm"}:
            reply = "There is no pending action to approve."

            trace(
                "finished",
                route="confirmation",
                reason="No action is waiting.",
                approval="none",
                outcome=reply,
            )
            emit("receive_message", {"response": reply})
            return

        if len(message) > 8000:
            raise ValueError(
                "Message is too long. Please shorten it."
            )

        trace(
            "started",
            route="orchestrator",
            reason="Route the new user request.",
            approval="none",
        )

        reply = handle_ai_chat_request(
            current_app.db,
            role="Orchestrator",
            message=message,
            writer=writer,
            client_id=client_id,
            trace=trace,
        )

        reply = prefix + reply

        # The write event records waiting/approved/cancelled states.
        trace("finished", outcome="reply_sent")

    except (ValueError, RuntimeError) as error:
        reply = str(error)
        trace(
            "finished",
            outcome="request_failed",
            error=reply,
        )

    except Exception as error:
        # Log only the exception type, never credentials or headers.
        trace(
            "finished",
            outcome="unexpected_error",
            error_type=type(error).__name__,
        )
        reply = "Something went wrong. Please try again."

    emit("receive_message", {"response": reply})


@socketio.on("disconnect")
def handle_disconnect(reason=None):
    get_writer().cancel(request.sid)