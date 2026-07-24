#!/usr/bin/env python3
import base64
import json
import os
import urllib.error

os.environ.setdefault("DIFY_KEY", "test")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE", "https://example.com/openai/v1")

import hqbot_api as h

assert h.OPENAI == "https://example.com/openai/v1/chat/completions"
assert h._body_type("脾虚") == "脾虚湿困型"
assert h._body_type("气血两虚型") == "气血两虚型"
assert h._body_type("宫寒气滞型") == "寒凝气滞型"
assert h._body_type("寒凝") == "寒凝气滞型"
assert h._body_type("未明确") == ""
for profile in h.BODY_MAP.values():
    assert len(h._product_details(profile["products"])) == len(profile["products"])
assert not any(word in product["benefit"] for product in h.PRODUCT_CATALOG.values()
               for word in ("治疗", "燃脂翻倍", "控糖稳血糖", "改善睡眠"))
assert all(not h._has_gender_assumption(product["benefit"]) for product in h.PRODUCT_CATALOG.values())
assert not {"氣恤寶", "双花燕窝阿胶姜桂膏", "經舒寶"} & set(h.AUTO_IMAGE_PRODUCT_KEYS)

def assert_neutral(value):
    text = json.dumps(value, ensure_ascii=False)
    assert not h._has_gender_assumption(text), text

neutral_details = {key: "看不清" for key, _ in h.TONGUE_FIELDS}
for body_type, profile in h.BODY_MAP.items():
    product_details = h._product_details(profile["products"])
    assert all(product["key"] in h.AUTO_IMAGE_PRODUCT_KEYS for product in product_details)
    assert_neutral({
        "body_type": body_type,
        "symptoms": profile["symptoms"],
        "products": profile["products"],
        "product_details": product_details,
        "answer": h._tongue_answer("舌象可见", body_type, profile, neutral_details, product_details),
    })

jpg = base64.b64encode(b"\xff\xd8\xfftest").decode()
webp = base64.b64encode(b"RIFF1234WEBPtest").decode()
assert h._image_url(jpg).startswith("data:image/jpeg;base64,")
assert h._image_url(webp).startswith("data:image/webp;base64,")

h._vision = lambda *args, **kwargs: {
    "type": "tongue",
    "observation": "舌体偏胖，舌色偏淡，边缘可见齿痕，舌苔白且偏厚",
    "body_type": "脾虚",
    "tongue_details": {
        "tongue_body": "偏胖",
        "tongue_color": "偏淡",
        "tooth_marks": "有",
        "coating_color": "白",
        "coating_thickness": "偏厚",
        "coating_texture": "略腻",
        "coating_amount": "偏多",
        "moisture": "偏润",
        "fissures": "看不清",
    },
    "quality_issues": [],
}
tongue = h.analyze_image(jpg)
assert tongue["body_type"] == "脾虚湿困型"
assert tongue["symptoms"] and tongue["products"]
assert tongue["tongue_details"]["tooth_marks"] == "有"
assert len(tongue["product_details"]) == 3
assert tongue["product_details"][0]["ingredients"]
assert tongue["product_details"][0]["benefit"]
assert tongue["tip"] == tongue["answer"]
assert_neutral(tongue)
assert all(text in tongue["answer"] for text in (
    "初步舌象", "舌象细节", "舌苔厚薄：偏厚", "常见表现，请你核对",
    "管理重点", "今天可以先做", "下一步", "这些不是照片能够直接证明的症状",
    "用白话说", "候选产品资料（非食用建议）", "主要成分", "日常支持方向",
    "本次初步倾向：脾虚湿困型",
    "不构成疾病诊断", "拨打120",
))
assert not any(word in tongue["answer"] for word in ("治疗痛经", "燃脂翻倍", "控糖稳血糖"))
assert "完成体测、过敏、基础病、用药和其他特殊情况核对前，请勿据此开始食用" in tongue["answer"]

h._vision = lambda *args, **kwargs: {
    "type": "tongue",
    "observation": "舌色淡紫，女性可能月经量少",
    "body_type": "宫寒气滞型",
    "tongue_details": {
        "tongue_body": "偏胖",
        "tongue_color": "淡紫",
        "moisture": "经期偏干",
    },
    "quality_issues": ["疑似女性特征"],
}
neutral_tongue = h.analyze_image(jpg)
assert neutral_tongue["body_type"] == "寒凝气滞型"
assert neutral_tongue["products"] == [] and neutral_tongue["product_details"] == []
assert "本次不展示候选产品" in neutral_tongue["answer"]
assert neutral_tongue["tongue_details"]["moisture"] == "看不清"
assert_neutral(neutral_tongue)

h._vision = lambda *args, **kwargs: {
    "type": "tongue_unclear",
    "observation": "舌体可见，但舌缘模糊",
    "tongue_details": {"tongue_body": "看不清", "tongue_color": "偏淡"},
    "quality_issues": ["舌缘未完整入镜"],
}
unclear = h.analyze_image(jpg)
assert unclear["is_tongue"] and unclear["body_type"] == "未明确"
assert unclear["products"] == [] and unclear["product_details"] == []
assert "为避免误判，本次不强行归入某一体质" in unclear["answer"]
assert "舌缘未完整入镜" in unclear["answer"]

real_chat = h.chat
h._vision = lambda *args, **kwargs: {
    "type": "report",
    "metric_items": [
        {"name": "体重", "display_value": "41.9kg", "status_text": "偏瘦",
         "reference_text": "", "change_text": "较上次-0.5kg"},
        {"name": "BMI", "display_value": "16.57", "status_text": "偏瘦",
         "reference_text": "女性18.5-23.9，男性18.5-23.9", "change_text": ""},
        {"name": "女性参考值", "display_value": "18-24", "status_text": "",
         "reference_text": "", "change_text": ""},
    ],
    "trend": "体重较上次下降0.5kg",
}
report_queries = []
def fake_chat(query, user, conv):
    report_queries.append(query)
    return {"answer": ("女性可能同时出现月经量少。\n报告标注BMI偏瘦，建议先稳定三餐。\n\n### 产品建议\n"
                       "必颐堂·青稞匀浆膳可以治疗问题。\n推荐产品：必颐堂·青稞匀浆膳"),
            "conversation_id": "report"}
h.chat = fake_chat
report = h.analyze_image(jpg)
assert report["is_report"]
assert report["metrics"] == {"体重": "41.9kg", "BMI": "16.57"}
assert report["metric_items"][0]["status_text"] == "偏瘦"
assert report["metric_items"][1]["name"] == "BMI"
assert report["metric_items"][1]["reference_text"] == ""
assert report["products"] == ["青稞匀浆膳"]
assert report["product_details"][0]["ingredients"]
assert_neutral(report)
assert "产品主要成分与日常支持方向" in report["answer"]
assert "可以治疗问题" not in report["answer"]
assert "体重：41.9kg（报告标注：偏瘦；报告变化：较上次-0.5kg）" in report["answer"]
assert "重要提示" in report["answer"]
assert "报告标注为" in report_queries[0]
assert "不要自行补充正常范围" in report_queries[0]
assert h._mentioned_products("不建议使用必颐堂·青稞匀浆膳") == []
assert h._mentioned_products("推荐产品：暂不推荐") == []
assert h._mentioned_products(
    "推荐产品: 左旋肉碱绿茶控能片、必颐堂·青稞匀浆膳"
) == ["左旋肉碱绿茶控能片", "青稞匀浆膳"]
assert h._without_model_product_copy(
    "重点关注内容\n### 产品建议\n未经核实的产品功效\n推荐产品：必颐堂·青稞匀浆膳"
) == "重点关注内容"
for heading in ("4. 产品建议", "四、产品建议", "### 产品推荐"):
    assert h._without_model_product_copy(
        f"重点关注内容\n{heading}\n可以治疗问题\n推荐产品：必颐堂·青稞匀浆膳"
    ) == "重点关注内容"
assert h._without_model_product_copy(
    "重点关注内容\n必颐堂·青稞匀浆膳可以治疗问题\n推荐产品：必颐堂·青稞匀浆膳"
) == "重点关注内容"
assert h._neutral_generated_text(
    "报告标注体重偏低\n女性可能月经量少\n建议规律三餐"
) == "报告标注体重偏低\n建议规律三餐"
for unsafe in ("月經量少", "月 经 量 少", "经量偏少", "月事不调",
               "menstrual flow is low", "女子"):
    assert h._has_gender_assumption(unsafe)
    assert h._neutral_generated_text(f"安全内容\n{unsafe}") == "安全内容"
assert h._neutral_generated_text("安全内容\n月\n經\n量少") == ""
assert "上传报告中清晰可见的原文数据" in report["answer"]
assert "当前舌照可见特征" not in report["answer"]

def failed_chat(*args):
    raise RuntimeError("dify down")
h.chat = failed_chat
degraded = h.analyze_image(jpg)
assert degraded["is_report"] and degraded["metric_items"]
assert degraded["products"] == []
assert "综合解读服务暂时繁忙" in degraded["answer"]
h._vision = lambda *args, **kwargs: {
    "type": "other",
    "summary": "图片中是一张舌照\n根据外观判断为女性，月经量少",
}
other = h.analyze_image(jpg)
assert other["tip"] == "图片中是一张舌照"
assert_neutral(other)
h.chat = real_chat

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
