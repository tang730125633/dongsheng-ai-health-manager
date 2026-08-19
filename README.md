# 东晟 AI 健康管家

<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="东晟 AI 健康管家：将文字问题、图片可见信息和受控资料匹配置于明确安全护栏内的日常健康信息服务">
</p>

## 价值

这是一个本地运行的日常健康与体重管理信息服务。它接收文字问题，或观察上传图片中**清晰可见**的信息，再在资料和风险条件允许时给出日常管理方向与受控产品资料。

它不做疾病诊断、处方或治疗，不应替代医生、药师或紧急医疗服务。

## 代码与测试证据

当前仓库的 [`test_hqbot_api.py`](test_hqbot_api.py) 是可直接执行的断言检查，覆盖的范围包括：

- JPEG、PNG、WebP 的图片输入校验，以及舌照、报告、截图/海报等来源区分。
- 对图像不清、没有稳定可见细节或不匹配时，不展示候选产品的分支。
- 对孕哺、儿童、过敏、慢病、用药和紧急症状等风险信息的安全回复与本地兜底。
- 图像上下文的一次性使用、用户绑定、过期和并发占用处理；以及文字会话的短期进程内记忆。
- 用户主动开启的 7 天文字记忆：加密令牌、最近 4 轮、抽取式整理、过期、篡改、绑定、整组作废和故障隔离。
- 上游文字模型或 Dify 超时、错误时，回复本地安全兜底而非上游错误内容。

运行检查：

```sh
cd dongsheng-ai-health-manager
OPENAI_API_KEY=test \
OPENAI_BASE=https://example.com/openai/v1 \
python3 test_hqbot_api.py
```

这项检查以本地桩替代外部模型调用；它验证代码分支，不证明任何生产环境、模型供应商或线上服务已经可用。

## 接口与受控机制

服务默认只监听 `127.0.0.1:8093`，提供六个 JSON 接口：

- `GET /health`：本地健康检查。
- `POST /api/chat`：接收 `query`，可附带 `user`、`conversation_id` 或一次性 `context_id`。
- `POST /api/chat/memory`：只供用户主动开启 7 天文字记忆时调用；旧 `/api/chat` 不读取该记忆。
- `POST /api/chat/memory/compact`：使用一次性票据在后台整理旧文字，不阻塞当前回答。
- `POST /api/chat/memory/revoke`：作废当前记忆链的全部副本，提交成功后客户端才能显示“已清除”。
- `POST /api/tongue`：接收 base64 的 JPEG、PNG 或 WebP 图片，可附带 `user`；返回图片类别、可见信息及（仅在条件满足时）受控资料。

### 最小请求与响应

以下健康检查由当前代码实现确认，不访问上游模型：

```sh
curl -s http://127.0.0.1:8093/health
```

```json
{"ok": true}
```

`/api/chat` 的成功响应在 `ok` 之外带有 `answer`、`conversation_id`、`fast_path` 和 `mode`。带图上下文的请求只能被同一 `user` 领取一次；占用中返回 `409 context_in_use`，失效或不匹配返回 `410 context_unavailable`。

### 护栏如何介入

1. 图片路径只转写或描述画面中可稳定辨认的内容；截图、海报和不清晰图片不当作直接舌照。
2. 文字和图片结果都附带医疗边界；急症提示立即拨打 `120`，而不是继续给建议。
3. 产品资料来自代码内的受控目录。出现过敏、孕哺、儿童、慢病、用药或信息不足时，代码要求核对包装并咨询医生或药师，或不展示候选产品。
4. 模型请求异常时，服务切换到本地安全回复；短会话与图像上下文仅保留在进程内，不是账户级健康档案。

## 7 天记忆生产配置

该能力默认关闭。它只保存加密后的受限文字令牌，不保存舌照、图片结果或完整聊天记录；任何记忆故障都必须失败关闭，普通聊天和舌诊继续工作。

安装当前生产已验证的依赖：

```sh
python3 -m pip install -r requirements.txt
```

由受保护的 systemd `EnvironmentFile` 提供下列变量；仓库和日志只能出现变量名，不能出现密钥正文：

```ini
HEALTH_RECENT_MEMORY_ENABLED=0
HEALTH_MEMORY_KEY=<Fernet key>
HEALTH_MEMORY_REVOCATION_DB=/var/lib/hqbot/revoked-memory.sqlite3
HEALTH_MEMORY_COMPACTION_HOURLY_LIMIT=300
HEALTH_MEMORY_COMPACTION_TIMEOUT=12
```

`HEALTH_MEMORY_KEY` 必须在重启和发布后保持稳定。作废库目录应由真实 systemd 服务账号独占，例如：

```sh
install -d -m 700 -o <service-user> -g <service-group> /var/lib/hqbot
```

H5 的跨站请求按生产域名精确拦截；原生微信请求没有 `Origin`，因此当前仍允许无 `Origin` 的 HTTPS 客户端。加密令牌、用户与会话绑定只能保护令牌内容，不能代替账号登录鉴权；正式账号体系接入后应改为服务端会话校验。

Nginx 需在通用 `/hqapi/` 转发之前加入三个精确入口。以下片段中的上游地址应与当前生产服务保持一致；`limit_req_zone` 放在 `http` 级：

```nginx
limit_req_zone $binary_remote_addr zone=hq_recent_memory:10m rate=30r/m;

location = /hqapi/api/chat/memory {
    client_max_body_size 32k;
    limit_req zone=hq_recent_memory burst=10 nodelay;
    limit_req_status 429;
    proxy_pass http://127.0.0.1:8093/api/chat/memory;
    proxy_read_timeout 60s;
    add_header Cache-Control "no-store" always;
}

location = /hqapi/api/chat/memory/compact {
    client_max_body_size 16k;
    limit_req zone=hq_recent_memory burst=10 nodelay;
    limit_req_status 429;
    proxy_pass http://127.0.0.1:8093/api/chat/memory/compact;
    proxy_read_timeout 15s;
    add_header Cache-Control "no-store" always;
}

location = /hqapi/api/chat/memory/revoke {
    client_max_body_size 16k;
    limit_req zone=hq_recent_memory burst=10 nodelay;
    limit_req_status 429;
    proxy_pass http://127.0.0.1:8093/api/chat/memory/revoke;
    proxy_read_timeout 15s;
    add_header Cache-Control "no-store" always;
}
```

现有普通入口也必须在读取请求前限制大小：`/hqapi/api/chat` 为 `32k`，`/hqapi/api/tongue` 为 `16m`；舌诊响应同样加 `Cache-Control: no-store`。应用层已经保留同样的第二道限制。

`/ai/` 的生产响应同时需要以下 CSP；H5 已把 JavaScript 移到独立 `app.js`，不再依赖内联脚本：

```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' https://chat.huangquechuanmei.com; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'" always;
```

启用顺序：

1. 保持 `HEALTH_RECENT_MEMORY_ENABLED=0` 部署代码和 H5，确认旧 `/api/chat`、`/api/tongue` 与 `/health` 不变。
2. 核对请求体、响应体、令牌和摘要没有进入 Nginx、应用、代理或错误追踪日志；确认模型供应商的数据处理与留存边界及用户提示。
3. 核对 SQLite 可提交、重启后仍可查询；检查三个精确入口的 32/16/16 KiB、429、`no-store` 和 H5 CSP。
4. 再把开关改为 `1`，重启服务，并用脱敏测试用户完成开启、4 轮整理、续接、清除、服务重启和舌诊后继续文字的验收。

回滚时先把开关恢复为 `0` 并隐藏客户端开关。密钥和作废库至少保留 7 天，防止已经作废的旧副本因回滚重新可用；不要删除或重建作废库来“清缓存”。

## 最小运行

需要一个 OpenAI 兼容的文字/视觉接口。密钥只通过环境变量提供，不能提交到仓库：

```sh
export OPENAI_API_KEY="..."
export OPENAI_BASE="https://example.com/v1"
python3 hqbot_api.py
```

启动后可先运行上面的 `/health` 请求。图片接口的 `image` 字段是原始文件内容的 base64 字符串；单个输入由代码限制为 12 MB 以内，仅接受 JPEG、PNG 或 WebP。

## 安全与限制

- 仅用于日常健康与营养信息参考；不诊断疾病，不开处方，不承诺治疗效果，也不建议自行开始、停用或调整药物、保健品或中成药。
- 舌照只描述图中可见特征，不能确认疾病、症状、体质、性别、生理周期、年龄或其他图外信息；体测报告只转写清晰可见的原文指标。
- 产品成分和支持方向来自企业资料。实际配料、过敏原、食用要求及是否适合，以产品包装标签和专业人员意见为准。
- 仓库不包含生产密钥、密码、真实用户健康数据、价格、库存或订单信息。
- 尚未验证生产部署、持续运行、真实模型输出或线上数据处理流程；请勿把本仓库视为已经投入临床或生产使用的服务。

## 许可

当前**未授予开源许可**。代码公开用于项目协作与版本追踪；其他使用需取得项目所有者授权。
