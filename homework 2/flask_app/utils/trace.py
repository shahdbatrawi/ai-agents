"""
trace.py — the per-message trace. Every line starts with the request id, e.g.
    [req 3] step 1/2: Semantic Search Expert | reason: ...
Lines are printed in the terminal. The API key is never passed to log().
"""

import itertools
import threading

_counter = itertools.count(1)
_state = threading.local()
CAPTURE = None          # tests set this to a list to collect the lines


def new_request(text=""):
    _state.request_id = next(_counter)
    log(f"request: {text!r}")
    return _state.request_id


def log(message):
    line = f"[req {getattr(_state, 'request_id', '-')}] {message}"
    print(line)
    if CAPTURE is not None:
        CAPTURE.append(line)


def one_line(text, limit=300):
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[:limit] + "..."