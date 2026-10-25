"""Route every chat message through the Orchestrator."""
from flask import current_app
from flask_socketio import emit
from flask_app import socketio
from flask_app.utils.llm import handle_ai_chat_request


@socketio.on('send_message')
def handle_message(data):
    user_message = data.get('message', '').strip()
    if not user_message:
        return
    try:
        db = current_app.db
        ai_response = handle_ai_chat_request(db, role="Orchestrator", message=user_message)
    except Exception as error:
        print(f"LLM error: {error}")
        ai_response = "Sorry, something went wrong answering that."
    emit('receive_message', {'response': ai_response})
