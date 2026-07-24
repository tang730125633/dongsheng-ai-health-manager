#!/usr/bin/env python3
import base64
import os
import urllib.error

os.environ.setdefault("DIFY_KEY", "test")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE", "https://example.com/openai/v1")

import hqbot_api as h

assert h.OPENAI == "https://example.com/openai/v1/chat/completions"
assert h._body_type("脾虚") == "脾虚湿困型"
assert h._body_type("气血两虚型") == "气血两虚型"
assert h._body_type("未明确") == ""
jpg = base64.b64encode(b"\xff\xd8\xfftest").decode()
webp = base64.b64encode(b"RIFF1234WEBPtest").decode()
assert h._image_url(jpg).startswith("data:image/jpeg;base64,")
assert h._image_url(webp).startswith("data:image/webp;base64,")

calls = []
def fake_dify(body):
    calls.append(dict(body))
    if len(calls) == 1:
        raise urllib.error.HTTPError("http://dify", 400, "old config", {}, None)
    return {"answer": "ok", "conversation_id": "new"}

h._dify = fake_dify
assert h.chat("hi", "test", "old") == {"answer": "ok", "conversation_id": "new"}
assert calls == [
    {"inputs": {}, "query": "hi", "response_mode": "blocking", "user": "test", "conversation_id": "old"},
    {"inputs": {}, "query": "hi", "response_mode": "blocking", "user": "test"},
]
print("ok")
