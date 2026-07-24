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

h._vision = lambda *args, **kwargs: {
    "type": "tongue",
    "observation": "舌体偏胖，舌苔偏白",
    "body_type": "脾虚",
}
tongue = h.analyze_image(jpg)
assert tongue["body_type"] == "脾虚湿困型"
assert tongue["symptoms"] and tongue["products"]
assert all(text in tongue["answer"] for text in (
    "初步舌象", "常见表现，请你核对", "管理重点", "今天可以先做", "下一步",
    "这些不是照片能够直接证明的症状", "用白话说", "产品匹配",
    "单张舌照阶段不作个性化产品推荐", "本次初步倾向：脾虚湿困型",
    "不构成疾病诊断", "拨打120",
))

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
