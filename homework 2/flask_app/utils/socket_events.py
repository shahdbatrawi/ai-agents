"""
socket_events.py — handles real-time chat messages using WebSockets.

The browser emits 'send_message'; we answer with 'receive_message'. Each browser
connection gets its own ChatSession (chat_flow.py), so one user's pending
"yes/no" question can never be answered by someone else.
"""

from flask import current_app, request
from flask_socketio import emit
from flask_app import socketio
from flask_app.utils.chat_flow import ChatSession

SESSIONS = {}   # connection id -> ChatSession


@socketio.on('send_message')
def handle_message(data):
    user_message = data.get('message', '').strip()
    if not user_message:
        return

    session = SESSIONS.get(request.sid)
    if session is None:
        session = SESSIONS[request.sid] = ChatSession(current_app.db)

    emit('receive_message', {'response': session.handle(user_message)})


@socketio.on('disconnect')
def handle_disconnect():
    SESSIONS.pop(request.sid, None)