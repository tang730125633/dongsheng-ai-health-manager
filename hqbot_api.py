#!/usr/bin/env python3
"""东晟时代统一后端服务。监听 :8093。密钥读 /opt/zhipu.key(视觉) 和 /opt/dify.key(问答)。
接口:
  POST /api/tongue   {"image":"<base64>"} → 舌诊结构化结果；非舌照自动尝试识别体测报告→解读+产品推荐(tip字段)
  POST /api/chat     {"query":..,"user":..,"conversation_id":..(可选)} → {answer, conversation_id}
  GET  /health
"""
import json, urllib.request, http.server, socketserver

ZHIPU_KEY = open("/opt/zhipu.key").read().strip()
DIFY_KEY = open("/opt/dify.key").read().strip()
ZHIPU = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DIFY = "http://127.0.0.1/v1/chat-messages"   # Dify 就在本机
TIP = "初步参考，建议结合AI智能体测+专业导师确认"

# ── 舌诊：体质 → 固定症状/产品（模型只判体质，症状产品查表，永不错配） ──
BODY_MAP = {
    "痰湿蕴盛型": {"symptoms": ["身体沉重", "大便黏马桶", "困倦嗜睡", "面部出油", "痰多"],
                "products": ["五指毛桃茯苓营养膏", "果燃畅通", "颐纤芋芸益生菌"]},
    "脾虚湿困型": {"symptoms": ["肉松软无力", "气短懒言", "食欲一般", "易水肿", "乏力"],
                "products": ["青稞匀浆膳", "果燃畅通", "左旋肉碱绿茶控能片"]},
    "气血两虚型": {"symptoms": ["面色淡白", "头晕心悸", "疲倦乏力", "月经量少", "易脱发"],
                "products": ["氣恤寶", "颜润堂PQQ", "双花燕窝阿胶姜桂膏"]},
    "宫寒气滞型": {"symptoms": ["怕冷手脚凉", "痛经", "经血有块", "小腹发凉", "情绪易郁"],
                "products": ["双花燕窝阿胶姜桂膏", "經舒寶", "氣恤寶"]},
}
TONGUE_SYS = """你是"东晟时代"AI舌诊助手。观察舌头照片，抓主要特征，按规则判定"四大减脂体质"之一。不追求医学精确。
【观察4点】舌体(正常/胖大)、齿痕(无/有)、舌苔(薄白/白腻厚/少苔)、舌色(淡红/偏淡白/淡紫暗)
【规则】胖大+齿痕+白腻厚苔+舌色偏淡→痰湿蕴盛型；淡胖+齿痕+薄白苔+舌色更淡→脾虚湿困型；舌色淡白+胖嫩+齿痕浅→气血两虚型；舌色淡紫或青暗→宫寒气滞型
【只输出JSON，body_type必须是上面四个之一】{"is_tongue":true,"observation":"一句话舌象","body_type":"xx型"}
若不是舌头或看不清:{"is_tongue":false}"""



def _vision(system, image_b64, max_tokens=400):
    content = [{"type": "text", "text": "分析这张图片，只输出JSON。"},
               {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + image_b64}}]
    body = json.dumps({"model": "glm-4v-plus", "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": content}],
        "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(ZHIPU, data=body, headers={
        "Authorization": "Bearer " + ZHIPU_KEY, "Content-Type": "application/json"})
    txt = (json.load(urllib.request.urlopen(req, timeout=120))["choices"][0]["message"].get("content") or "").strip()
    if txt.startswith("```"):
        txt = txt.split("```")[1].lstrip("json").strip()
    return json.loads(txt)


REPORT_SYS = """你是健康报告识别助手。判断图片是否为体测/体脂/健康检测报告（含体重、体脂率、BMI、内脏脂肪等指标的截图或照片）。
是报告→提取图中能看清的指标，只输出JSON:{"is_report":true,"metrics":{"体重":"105.2公斤","BMI":"31.76","体脂率":"31.27%"},"trend":"若图中有前后对比，用一句话说明主要变化，无则空字符串"}
不是报告→{"is_report":false}"""


def analyze_report(image_b64, user=""):
    """非舌照时的第二次识别：体测报告→提指标→交给 Dify 解读+推荐产品。不是报告返回 None。"""
    try:
        r = _vision(REPORT_SYS, image_b64, max_tokens=600)
    except Exception:
        return None
    if not r.get("is_report"):
        return None
    m = r.get("metrics") or {}
    q = "用户发来一份体测报告，指标：" + "、".join(f"{k} {v}" for k, v in m.items())
    if r.get("trend"):
        q += "。前后变化：" + r["trend"]
    q += "。请用亲切易懂的语气解读这份报告（重点讲需要注意的指标），并推荐适合的产品和使用建议。话术自然亲切，不要提到资料、context、知识库等字眼。"
    a = chat(q, user or "report-user", "")
    return {"is_tongue": False, "is_report": True, "metrics": m,
            "tip": a["answer"] or ("报告已收到，" + TIP)}


UNIFIED_SYS = """你是"东晟时代"AI健康助手的图片识别器。判断图片类型并按对应规则输出，只输出JSON。
【若是舌头照片】观察4点：舌体(正常/胖大)、齿痕(无/有)、舌苔(薄白/白腻厚/少苔)、舌色(淡红/偏淡白/淡紫暗)。
规则：胖大+齿痕+白腻厚苔+舌色偏淡→痰湿蕴盛型；淡胖+齿痕+薄白苔+舌色更淡→脾虚湿困型；舌色淡白+胖嫩+齿痕浅→气血两虚型；舌色淡紫或青暗→宫寒气滞型。
输出：{"type":"tongue","observation":"一句话舌象","body_type":"必须是上面四个之一"}
舌头但看不清：{"type":"tongue_unclear"}
【若是体测/体脂/健康检测报告】必须清晰含有体重/体脂率/BMI/内脏脂肪等身体成分数字指标才算；海报、广告、聊天截图、文档一律不算。提取图中能看清的指标：
{"type":"report","metrics":{"指标名":"图中真实数值+单位"},"trend":"若有前后对比，一句话主要变化，无则空字符串"}。metrics只能填图中真实出现的数字，一个都不许编造；图中没有身体指标数字就是other
【都不是】{"type":"other"}"""


def analyze_image(image_b64, user=""):
    """一次视觉调用完成分类：舌照→体质查表；报告→Dify解读推荐；其他→引导语。"""
    r = _vision(UNIFIED_SYS, image_b64, max_tokens=600)
    t = r.get("type", "other")
    if t == "tongue":
        bt = r.get("body_type", "")
        if bt not in BODY_MAP:
            return {"is_tongue": True, "observation": r.get("observation", ""), "body_type": bt or "未明确",
                    "symptoms": [], "products": [], "tip": "舌象不够典型，" + TIP}
        m = BODY_MAP[bt]
        return {"is_tongue": True, "observation": r.get("observation", ""), "body_type": bt,
                "symptoms": m["symptoms"], "products": m["products"], "tip": TIP}
    if t == "report":
        m = r.get("metrics") or {}
        BODY_KEYS = ("体重", "BMI", "体脂", "内脏脂肪", "肌肉", "基础代谢", "骨骼肌", "水分", "蛋白")
        if not any(bk in k for k in m for bk in BODY_KEYS):
            return {"is_tongue": False, "tip": "这张看不清舌头，请对着光、正对镜头再拍一张伸舌照"}
        q = "用户发来一份体测报告，指标：" + "、".join(f"{k} {v}" for k, v in m.items())
        if r.get("trend"):
            q += "。前后变化：" + r["trend"]
        q += ("。请解读这份报告（重点讲需要注意的指标），并推荐适合的产品。"
              "要求：口语化、亲切、200字以内、不用markdown标题和分隔线，不要提到资料、context、知识库等字眼。")
        a = chat(q, user or "report-user", "")
        return {"is_tongue": False, "is_report": True, "metrics": m,
                "tip": a["answer"] or ("报告已收到，" + TIP)}
    return {"is_tongue": False, "tip": "这张看不清舌头，请对着光、正对镜头再拍一张伸舌照"}


def analyze_tongue(image_b64):
    content = [{"type": "text", "text": "分析这张舌头照片，只输出JSON。"},
               {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + image_b64}}]
    body = json.dumps({"model": "glm-4v-plus", "messages": [
        {"role": "system", "content": TONGUE_SYS}, {"role": "user", "content": content}],
        "max_tokens": 400}).encode()
    req = urllib.request.Request(ZHIPU, data=body, headers={
        "Authorization": "Bearer " + ZHIPU_KEY, "Content-Type": "application/json"})
    txt = (json.load(urllib.request.urlopen(req, timeout=120))["choices"][0]["message"].get("content") or "").strip()
    if txt.startswith("```"):
        txt = txt.split("```")[1].lstrip("json").strip()
    r = json.loads(txt)
    if not r.get("is_tongue"):
        return {"is_tongue": False, "tip": "这张看不清舌头，请对着光、正对镜头再拍一张伸舌照"}
    bt = r.get("body_type", "").strip()
    if bt not in BODY_MAP:
        return {"is_tongue": True, "observation": r.get("observation", ""), "body_type": bt or "未明确",
                "symptoms": [], "products": [], "tip": "舌象不够典型，" + TIP}
    m = BODY_MAP[bt]
    return {"is_tongue": True, "observation": r.get("observation", ""), "body_type": bt,
            "symptoms": m["symptoms"], "products": m["products"], "tip": TIP}


def chat(query, user, conv):
    b = {"inputs": {}, "query": query, "response_mode": "blocking", "user": user or "h5user"}
    if conv:
        b["conversation_id"] = conv
    req = urllib.request.Request(DIFY, data=json.dumps(b).encode(), headers={
        "Authorization": "Bearer " + DIFY_KEY, "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=120))
    return {"answer": d.get("answer", ""), "conversation_id": d.get("conversation_id", "")}


class H(http.server.BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(b)

    def do_OPTIONS(self):
        self._send({"ok": True})

    def do_GET(self):
        self._send({"ok": True} if self.path == "/health" else {"ok": False}, 200 if self.path == "/health" else 404)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n)) if n else {}
            if self.path == "/api/tongue":
                import time as _t
                t0 = _t.time()
                res = analyze_image(data["image"], data.get("user", ""))
                kind = "tongue" if res.get("is_tongue") else ("report" if res.get("is_report") else "other")
                print(f"[img] kind={kind} {_t.time()-t0:.1f}s", flush=True)
                self._send({"ok": True, **res})
            elif self.path == "/api/chat":
                self._send({"ok": True, **chat(data.get("query", ""), data.get("user", ""), data.get("conversation_id", ""))})
            else:
                self._send({"ok": False, "error": "not found"}, 404)
        except Exception as e:
            import traceback
            print(f"[err] {self.path}: {e}", flush=True)
            traceback.print_exc()
            self._send({"ok": False, "error": str(e)[:200]}, 500)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", 8093), H) as srv:
        print("hqbot_api listening on 127.0.0.1:8093", flush=True)
        srv.serve_forever()
