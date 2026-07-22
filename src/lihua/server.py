"""FastAPI HTTP 服务（可选）。

需要安装 server extras: `pip install 'lihua[server]'`

API：
    GET  /api/health            健康检查
    GET  /api/skills            列出所有 Skill
    GET  /api/skills/{name}     查看 Skill 详情
    POST /api/parse             只解析意图不执行（规则模式）
    POST /api/chat              LLM Agent 模式：智能对话 + 工具调用
    POST /api/chat/stream       SSE 流式 Agent：实时推送工具调用和结果
    POST /api/chat/rule         规则模式：解析 + 执行（离线兜底）
    GET  /api/history           历史记录
    GET  /api/audit             审计日志（结构化 + 过滤搜索）
    GET  /api/audit/export      导出完整审计日志文件
    DELETE /api/audit           清空审计日志（备份后清空）
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, Field

from lihua import __version__
from lihua.agent import AgentResponse, run_agent, run_agent_streaming
from lihua.config import Config, audit_log_path, history_path
from lihua.executor import command_exists
from lihua.intent import understand
from lihua.router import is_available
from lihua.skill_runner import run_skill
from lihua.skills import get_registry
from lihua.model_presets import list_presets, get_preset


class ChatRequest(BaseModel):
    message: str = Field(..., description="自然语言指令")
    auto_confirm: bool = Field(False, description="自动确认灰名单任务（已废弃：v0.7.13 改用交互式 confirm）")
    dry_run: bool = Field(False, description="只解析不执行")
    no_llm: bool = Field(False, description="本次不调用 LLM（强制走规则匹配）")
    history: list[dict[str, str]] = Field(default_factory=list, description="多轮对话历史")
    session_id: str = Field("", description="v0.8.20: 会话 ID（前端生成，用于 episode 聚合 + 历史对话调取）")


class ConfirmRequest(BaseModel):
    """v0.7.13 交互式 confirm 端点请求。"""
    confirm_id: str = Field(..., description="needs_confirm 事件里的 id")
    decision: bool = Field(..., description="true=确认执行 / false=取消")


@dataclass
class _ConfirmSession:
    """单次灰名单确认会话。

    confirm_cb 被调用时：
    1. 生成 confirm_id，存入 _pending_confirms
    2. 把 needs_confirm 事件推到 event_queue（让 SSE 流能收到）
    3. 阻塞等待 response_event（前端 POST /api/chat/confirm 时 set）
    4. 返回 response_result[0] 给 confirm_cb
    """
    confirm_id: str
    response_event: threading.Event = field(default_factory=threading.Event)
    response_result: list[bool] = field(default_factory=lambda: [False])


# v0.7.13 交互式 confirm 全局状态
# confirm_id → _ConfirmSession（用于 /api/chat/confirm 查找）
_pending_confirms: dict[str, _ConfirmSession] = {}
_pending_lock = threading.Lock()

# confirm 超时（秒）：用户思考需要时间，10 分钟内不响应才超时
# v0.8.6：从 60s 延长到 600s。60s 太短，用户读 confirm 内容 + 思考就超时了，
# 然后用户点击确认时 session 已被 pop，导致"点确认却提示取消"的 UX bug
_CONFIRM_TIMEOUT = 600.0


class ParseRequest(BaseModel):
    message: str
    no_llm: bool = False


class LLMConfigUpdate(BaseModel):
    """LLM 配置更新请求。所有字段可选，None 表示不变。"""
    enabled: bool | None = None
    provider: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class ChatResponse(BaseModel):
    success: bool
    text: str = ""  # Agent 最终给用户的回复
    tool_calls: list[dict[str, Any]] = []  # Agent 调用的工具列表
    intent: dict[str, Any] | None = None  # 规则模式的意图（兼容旧前端）
    result: dict[str, Any] | None = None  # 规则模式的执行结果（兼容旧前端）
    error: str | None = None


def _load_config() -> Config:
    cfg = Config.load()
    cfg.ensure_dirs()
    return cfg


def _make_interactive_confirm_cb(
    event_queue: "queue.Queue[dict[str, Any]]",
) -> "Callable[[str, str], str]":
    """构造交互式 confirm 回调（v0.7.13）。

    confirm_cb 被 skill_runner 调用时：
    1. 生成 confirm_id，存入 _pending_confirms
    2. 推 needs_confirm 事件到 event_queue（SSE 流转发给前端）
    3. 阻塞等待 response_event（前端 POST /api/chat/confirm 时 set）
    4. 超时（600s）或前端取消 → 返回 "timeout" / "denied"

    返回值（v0.8.6）：
    - "confirmed"：用户点击确认
    - "denied"：用户点击取消
    - "timeout"：超时未响应

    event_queue 是 chat_stream 主循环用来取事件 yield 到 SSE 的队列。

    v0.8.4 改造：解析 msg 内容，加结构化字段（tool_name / intent / code / command_text），
    让前端 ConfirmSheet 能分别展示"意图说明"和"代码/命令"，而不是把 ```python
    标记和"命令："前缀当纯文本展示。

    v0.8.7 修复：log 变量未定义 bug。
    - 旧代码 L160 `log.warning(...)` 抛 NameError（log 只在 create_app 内定义，模块级函数访问不到）
    - confirm 超时时 NameError 传播到 run_agent_streaming，子线程异常退出
    - 导致 needs_confirm 事件后不再有 tool_call_end 事件，前端弹窗显示但后续流程中断
    - 修复：函数内部获取 logger
    """
    import queue as _queue
    from lihua.logging_config import get_logger
    _log = get_logger(__name__)

    def cb(msg: str, cmd: str) -> str:
        confirm_id = str(uuid.uuid4())
        session = _ConfirmSession(confirm_id=confirm_id)
        with _pending_lock:
            _pending_confirms[confirm_id] = session

        # v0.8.4: 解析 msg 提取结构化信息，让前端能针对性展示
        event: dict[str, Any] = {
            "type": "needs_confirm",
            "id": confirm_id,
            "message": msg,
            "command": cmd,
        }
        _enrich_confirm_event(event, msg, cmd)

        # 推 needs_confirm 事件到 SSE 流
        event_queue.put(event)

        # 阻塞等待前端响应
        if session.response_event.wait(timeout=_CONFIRM_TIMEOUT):
            with _pending_lock:
                _pending_confirms.pop(confirm_id, None)
            return "confirmed" if session.response_result[0] else "denied"
        # 超时——推 confirm_timeout 事件让前端关闭 ConfirmSheet
        with _pending_lock:
            _pending_confirms.pop(confirm_id, None)
        event_queue.put({"type": "confirm_timeout", "id": confirm_id})
        _log.warning(f"confirm 超时（{_CONFIRM_TIMEOUT}s）：confirm_id={confirm_id[:8]}...")
        return "timeout"

    return cb


def _enrich_confirm_event(event: dict[str, Any], msg: str, cmd: str) -> None:
    """v0.8.4 新增：从 confirm msg 解析结构化字段，加到 event 里。

    解析规则（按优先级）：
    1. run_python：msg 含 ```python\\n...``` 代码块标记
       - intent = 代码块前的部分
       - code = 代码块内容
    2. run_shell：msg 含 "\\n命令：" 前缀
       - intent = 命令前的部分
       - command_text = 命令内容
    3. 文件操作：msg 含 "写入文件" / "编辑文件" / "路径：" 等关键词
       - intent = msg 全文（文件操作的 msg 已经够清晰）
    4. 默认：不加额外字段，前端按纯文本展示

    这样前端 ConfirmSheet 能根据 tool_name 选择展示样式：
    - run_python：意图 + 代码块（带 Python 语法高亮样式）
    - run_shell：意图 + 命令块（带终端样式）
    - 文件操作：路径 + 内容预览/diff
    - 默认：纯文本
    """
    # run_python：检测 ```python 代码块标记
    if "```python\n" in msg:
        event["tool_name"] = "run_python"
        parts = msg.split("```python\n", 1)
        intent = parts[0].strip()
        if intent:
            event["intent"] = intent
        if len(parts) > 1 and "```" in parts[1]:
            # 提取代码块内容（去掉结尾的 ```）
            code = parts[1].rsplit("```", 1)[0]
            event["code"] = code
        return

    # run_shell：检测 "\n命令：" 前缀
    if "\n命令：" in msg:
        event["tool_name"] = "run_shell"
        parts = msg.split("\n命令：", 1)
        intent = parts[0].strip()
        if intent:
            event["intent"] = intent
        if len(parts) > 1:
            event["command_text"] = parts[1].strip()
        return

    # 文件操作：检测关键词
    file_op_keywords = ["写入文件", "编辑文件", "路径：", "覆盖文件", "新建文件"]
    if any(kw in msg for kw in file_op_keywords):
        event["tool_name"] = "file_op"
        # 文件操作的 msg 已经足够清晰，直接用纯文本展示
        return

    # 默认：不加 tool_name，前端按纯文本展示


def _intent_to_dict(intent) -> dict[str, Any]:  # noqa: ANN001
    return {
        "skill_name": intent.skill_name,
        "params": intent.params,
        "source": intent.source,
        "confidence": intent.confidence,
        "explanation": intent.explanation,
        "matched": intent.matched,
    }


def _result_to_dict(result) -> dict[str, Any]:  # noqa: ANN001
    return {
        "success": result.success,
        "final_message": result.final_message,
        "steps": [
            {
                "name": sr.step.name,
                "type": sr.step.type,
                "skipped": sr.skipped,
                "success": sr.success,
                "output": sr.output,
                "error": sr.error,
                "duration": sr.duration,
                "needs_confirm": sr.needs_confirm,
                "confirm_message": sr.confirm_message,
                "confirm_decision": sr.confirm_decision,
            }
            for sr in result.steps
        ],
        "ctx": dict(result.ctx),
    }


def _agent_response_to_dict(resp: AgentResponse) -> dict[str, Any]:
    """把 AgentResponse 转成 API 返回的 dict。"""
    return {
        "success": resp.success,
        "text": resp.text,
        "tool_calls": [
            {
                "tool_name": tc.tool_name,
                "arguments": tc.arguments,
                "success": tc.success,
                "result_message": tc.result_message,
                "error": tc.error,
                "details": tc.result_details,
            }
            for tc in resp.tool_calls
        ],
        "error": resp.error or None,
    }


def create_app() -> Any:
    """创建 FastAPI app。延迟 import，避免无 server 依赖时整个包导入失败。"""
    from fastapi import Body, FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware

    # v0.7.7: 初始化日志系统（无论是 cli.serve 还是 uvicorn 直接启动都生效）
    from lihua.logging_config import setup_logging, get_logger
    cfg = _load_config()
    setup_logging(level=cfg.log_level, enable_stderr=True)
    log = get_logger(__name__)
    log.info(f"FastAPI app 创建，版本 {__version__}")

    # v0.8.14: 启动时自动加载插件（错误隔离，不影响主流程）
    try:
        from lihua.plugin_loader import get_loader
        plugin_result = get_loader().load_all(cfg)
        loaded = sum(1 for i in plugin_result.values() if i.status == "loaded")
        errored = sum(1 for i in plugin_result.values() if i.status == "error")
        log.info(f"插件加载完成：{loaded} 成功，{errored} 失败，共 {len(plugin_result)} 个")
    except Exception as e:
        log.warning(f"插件加载失败（不影响主流程）：{e}")

    app = FastAPI(
        title="Lihua 狸花猫 API",
        description="AI 系统管家 HTTP 接口",
        version=__version__,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "name": "Lihua",
            "version": __version__,
            "docs": "/docs",
            "endpoints": [
                "/api/health", "/api/skills", "/api/parse",
                "/api/chat", "/api/history", "/api/audit",
            ],
        }

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        cfg = _load_config()
        registry = get_registry()
        registry.reload()
        return {
            "ok": True,
            "version": __version__,
            "llm_available": is_available(cfg.llm),
            "llm_provider": cfg.llm.provider if cfg.llm.enabled else None,
            "llm_model": cfg.llm.model if cfg.llm.enabled else None,
            "skills_count": len(registry.all()),
            "tools": {
                t: command_exists(t)
                for t in ("apt", "flatpak", "snap", "gsettings", "fcitx5", "notify-send")
            },
        }

    @app.get("/api/skills")
    def list_skills() -> list[dict[str, Any]]:
        registry = get_registry()
        registry.reload()
        return [
            {
                "name": s.name,
                "description": s.description,
                "version": s.version,
                "triggers": s.triggers,
                "examples": s.examples,
                "source": s.source,
                "parameters": [
                    {"name": p.name, "required": p.required, "description": p.description}
                    for p in s.parameters
                ],
            }
            for s in registry.all()
        ]

    @app.get("/api/skills/{name}")
    def get_skill(name: str) -> dict[str, Any]:
        registry = get_registry()
        registry.reload()
        s = registry.get(name)
        if not s:
            raise HTTPException(404, f"Skill not found: {name}")
        return {
            "name": s.name,
            "description": s.description,
            "version": s.version,
            "triggers": s.triggers,
            "examples": s.examples,
            "aliases": s.aliases,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "required": p.required,
                    "description": p.description,
                    "default": p.default,
                }
                for p in s.parameters
            ],
            "steps": [
                {
                    "name": st.name,
                    "type": st.type,
                    "description": st.description,
                    "command": st.command,
                    "safety": st.safety,
                    "confirm": st.confirm,
                    "condition": st.condition,
                    "on_failure": st.on_failure,
                    "timeout": st.timeout,
                }
                for st in s.steps
            ],
        }

    @app.post("/api/parse")
    def parse(req: ParseRequest) -> dict[str, Any]:
        cfg = _load_config()
        if req.no_llm:
            cfg.llm.enabled = False
        registry = get_registry()
        registry.reload()
        intent = understand(req.message, cfg, registry)
        return {"intent": _intent_to_dict(intent)}

    @app.post("/api/chat")
    def chat(req: ChatRequest) -> ChatResponse:
        """LLM Agent 模式：智能对话 + 工具调用。

        默认走 Agent（LLM 主导 + function calling）。
        no_llm=True 时回退到规则模式。
        """
        from lihua.logging_config import get_logger
        log = get_logger(__name__)
        log.info(f"用户输入：{req.message}", extra={
            "auto_confirm": req.auto_confirm,
            "dry_run": req.dry_run,
            "no_llm": req.no_llm,
        })

        cfg = _load_config()
        if req.no_llm:
            cfg.llm.enabled = False
        registry = get_registry()
        registry.reload()

        # 无 LLM → 走规则模式
        if not cfg.llm.enabled:
            log.debug("LLM 未启用，走规则模式")
            return _chat_via_rule(req, cfg, registry)

        # Agent 模式
        # v0.8.7: 修复非流式端点 confirm_cb bug
        # - 旧代码 `(lambda msg, cmd: req.auto_confirm) if req.auto_confirm else None` 有两个问题：
        #   1. auto_confirm=True 时返回 bool True，但 ConfirmCallback 类型是 Callable[..., str]，
        #      调用方用 `if decision != "confirmed"` 判断，True != "confirmed" 会被误判为取消
        #   2. auto_confirm=False 时 confirm_cb=None，灰名单操作返回"需要确认但未提供确认回调"
        # - 非流式接口没有 SSE 流，无法推送 needs_confirm 事件给前端，所以不支持交互式 confirm
        # - 修复后：auto_confirm=True → "confirmed"；auto_confirm=False → "denied"（明确拒绝）
        # - 需要 confirm 的操作请用 /api/chat/stream
        if req.auto_confirm:
            confirm_cb = lambda msg, cmd: "confirmed"  # noqa: E731
        else:
            def confirm_cb(msg: str, cmd: str) -> str:  # noqa: E306
                log.warning(f"非流式 /api/chat 不支持交互式 confirm，拒绝灰名单操作：{cmd[:80]}")
                return "denied"
        try:
            agent_resp = run_agent(
                user_text=req.message,
                cfg=cfg,
                registry=registry,
                confirm=confirm_cb,
                on_progress=None,
                dry_run=req.dry_run,
                history=req.history,
                session_id=req.session_id,
            )
            data = _agent_response_to_dict(agent_resp)
            log.info(
                f"Agent 完成：success={data['success']}, tool_calls={len(data['tool_calls'])}",
                extra={"tool_names": [tc.get("name", "") for tc in data["tool_calls"]]},
            )
            return ChatResponse(
                success=data["success"],
                text=data["text"],
                tool_calls=data["tool_calls"],
                error=data["error"],
            )
        except Exception as e:
            log.exception(f"Agent 执行失败：{e}")
            raise

    @app.post("/api/chat/stream")
    def chat_stream(req: ChatRequest):
        """SSE 流式 Agent：实时推送工具调用和结果。

        v0.7.13 改造：交互式 confirm 机制
        - 遇到灰名单操作时 yield `needs_confirm` 事件
        - 前端弹 ConfirmSheet，用户点击后 POST /api/chat/confirm
        - 后端 confirm_cb 阻塞等待，收到响应后继续执行

        事件格式（每行 data: {...}\\n\\n）：
            {"type": "start", "tools_count": N}
            {"type": "iteration", "n": 1, "max": 8}
            {"type": "text", "content": "..."}
            {"type": "tool_call_start", "name": "install_app", "arguments": {...}}
            {"type": "tool_call_end", "name": "install_app", "success": true, ...}
            {"type": "needs_confirm", "id": "uuid", "message": "...", "command": "..."}
            {"type": "done", "text": "...", "success": true, "tool_calls": [...]}
            {"type": "error", "message": "..."}
        """
        import json as _json
        import queue as _queue
        from fastapi.responses import StreamingResponse

        log.info(f"流式用户输入：{req.message}", extra={
            "auto_confirm": req.auto_confirm,
            "dry_run": req.dry_run,
            "history_len": len(req.history),
        })

        cfg = _load_config()
        if req.no_llm:
            cfg.llm.enabled = False
        registry = get_registry()
        registry.reload()

        # 无 LLM → 返回错误（流式模式需要 LLM）
        if not cfg.llm.enabled:
            def _no_llm_stream():
                yield f"data: {_json.dumps({'type': 'error', 'message': 'LLM 未启用，无法使用流式模式'}, ensure_ascii=False)}\n\n"
            return StreamingResponse(_no_llm_stream(), media_type="text/event-stream")

        # v0.7.13 交互式 confirm：
        # auto_confirm=True 时走旧的自动通过（向后兼容）
        # 否则用交互式 confirm_cb（推 needs_confirm 事件 + 阻塞等待前端响应）
        # v0.8.9 修复：返回 "confirmed"（str）而非 True（bool）
        #   v0.8.6 把 ConfirmCallback 返回类型从 bool 改成 str
        #   agent.py 用 `if confirm_decision != "confirmed"` 判断
        #   True != "confirmed" 会被误判为取消，导致 auto_confirm=True 时 edit_file/write_file 被取消
        if req.auto_confirm:
            confirm_cb = lambda msg, cmd: "confirmed"  # noqa: E731
        else:
            event_queue: _queue.Queue[dict[str, Any]] = _queue.Queue()
            confirm_cb = _make_interactive_confirm_cb(event_queue)

        def event_generator():
            try:
                # v0.7.13：交互式 confirm 需要子线程跑 run_agent_streaming
                # confirm_cb 阻塞时，主线程从 event_queue 取 needs_confirm 事件 yield
                if not req.auto_confirm:
                    done_event = threading.Event()
                    error_holder: list[str | None] = [None]

                    def run_in_thread():
                        try:
                            for event in run_agent_streaming(
                                user_text=req.message,
                                cfg=cfg,
                                registry=registry,
                                confirm=confirm_cb,
                                dry_run=req.dry_run,
                                history=req.history,
                                session_id=req.session_id,
                            ):
                                event_queue.put(event)
                        except Exception as e:  # noqa: BLE001
                            error_holder[0] = str(e)
                        finally:
                            done_event.set()

                    thread = threading.Thread(target=run_in_thread, daemon=True)
                    thread.start()

                    # 主线程：从 event_queue 取事件 yield 到 SSE
                    while not done_event.is_set():
                        try:
                            event = event_queue.get(timeout=0.5)
                            yield f"data: {_json.dumps(event, ensure_ascii=False)}\n\n"
                        except _queue.Empty:
                            continue
                    # 取剩余事件
                    while not event_queue.empty():
                        try:
                            event = event_queue.get_nowait()
                            yield f"data: {_json.dumps(event, ensure_ascii=False)}\n\n"
                        except _queue.Empty:
                            break
                    if error_holder[0]:
                        log.exception(f"流式 Agent 异常：{error_holder[0]}")
                        yield f"data: {_json.dumps({'type': 'error', 'message': f'Agent 异常: {error_holder[0]}'}, ensure_ascii=False)}\n\n"
                else:
                    # auto_confirm=True：旧路径，直接同步跑
                    for event in run_agent_streaming(
                        user_text=req.message,
                        cfg=cfg,
                        registry=registry,
                        confirm=confirm_cb,
                        dry_run=req.dry_run,
                        history=req.history,
                        session_id=req.session_id,
                    ):
                        yield f"data: {_json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as e:  # noqa: BLE001
                log.exception(f"流式 Agent 异常：{e}")
                yield f"data: {_json.dumps({'type': 'error', 'message': f'Agent 异常: {e}'}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # nginx 禁用缓冲
            },
        )

    @app.post("/api/chat/confirm")
    def chat_confirm(req: ConfirmRequest) -> dict[str, Any]:
        """v0.7.13 交互式 confirm 端点。

        前端收到 SSE needs_confirm 事件后弹窗，用户点击后 POST 此端点。
        后端设置 response_event，让阻塞中的 confirm_cb 解除阻塞。
        """
        # v0.8.5 诊断日志：记录所有 confirm 调用（最开头，确保一定记录）
        log.info(f"收到 confirm 请求：confirm_id={req.confirm_id[:8]}... decision={req.decision}")
        with _pending_lock:
            session = _pending_confirms.get(req.confirm_id)
            if not session:
                log.warning(
                    f"confirm_id 不匹配：收到 {req.confirm_id[:8]}... decision={req.decision}，"
                    f"但 _pending_confirms 里有 {len(_pending_confirms)} 个："
                    f"{[cid[:8] for cid in _pending_confirms.keys()]}"
                )
                # v0.8.6：错误信息更明确——通常是用户思考时间超过 _CONFIRM_TIMEOUT，
                # session 已被超时 pop，用户后点击的确认到了也无效
                return {"ok": False, "error": f"确认已超时（{_CONFIRM_TIMEOUT:.0f}s 内未响应），请重新发送指令"}
            session.response_result[0] = req.decision
            session.response_event.set()
        log.info(f"confirm 响应：{req.confirm_id[:8]}... = {req.decision}")
        return {"ok": True}

    @app.post("/api/chat/rule")
    def chat_rule(req: ChatRequest) -> ChatResponse:
        """规则模式：规则匹配 + skill 执行（离线兜底）。"""
        cfg = _load_config()
        if req.no_llm:
            cfg.llm.enabled = False
        registry = get_registry()
        registry.reload()
        return _chat_via_rule(req, cfg, registry)

    def _chat_via_rule(req: ChatRequest, cfg: Config, registry) -> ChatResponse:  # noqa: ANN001
        """规则模式内部实现。"""
        intent = understand(req.message, cfg, registry)
        if not intent.matched:
            return ChatResponse(
                success=False,
                intent=_intent_to_dict(intent),
                error=intent.explanation or "未匹配任何 Skill",
            )

        if req.dry_run:
            return ChatResponse(
                success=True,
                intent=_intent_to_dict(intent),
                result={"dry_run": True, "final_message": "仅解析未执行"},
            )

        # v0.8.9 修复：返回 "confirmed"（str）而非 True（bool），与 v0.8.6 ConfirmCallback 类型一致
        confirm_cb = (lambda msg, cmd: "confirmed") if req.auto_confirm else None
        result = run_skill(intent, cfg, confirm=confirm_cb, on_progress=None)
        return ChatResponse(
            success=result.success,
            intent=_intent_to_dict(intent),
            result=_result_to_dict(result),
        )

    @app.get("/api/history")
    def history(n: int = 20) -> dict[str, Any]:
        import json
        path = history_path()
        if not path.exists():
            return {"entries": []}
        try:
            lines = path.read_text(encoding="utf-8").strip().splitlines()
        except OSError:
            return {"entries": []}
        entries = []
        for line in lines[-n:]:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return {"entries": entries}

    @app.get("/api/audit")
    def audit(
        n: int = 100,
        success: bool | None = None,
        safety: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        """获取审计日志（结构化，支持过滤搜索）。

        Args:
            n: 返回最近 N 条（默认 100，最新在前）
            success: 过滤成功/失败（True=只看成成功的，False=只看失败的）
            safety: 过滤安全级别（white/grey/black/unknown）
            q: 搜索关键词（匹配 command 或 user_input，大小写不敏感）
        """
        from lihua.executor import parse_audit_line
        from lihua.logging_config import get_logger
        log = get_logger(__name__)

        path = audit_log_path()
        if not path.exists():
            return {"entries": [], "count": 0, "log_file": str(path)}

        try:
            lines = path.read_text(encoding="utf-8").strip().splitlines()
        except OSError:
            return {"entries": [], "count": 0, "log_file": str(path)}

        # 解析所有行（从新到旧）
        entries: list[dict[str, Any]] = []
        for line in reversed(lines):
            entry = parse_audit_line(line)
            if entry is None:
                continue
            # 过滤
            if success is not None and entry.get("success") != success:
                continue
            if safety and entry.get("safety_level") != safety:
                continue
            if q:
                ql = q.lower()
                cmd = (entry.get("command") or "").lower()
                ui = (entry.get("user_input") or "").lower()
                if ql not in cmd and ql not in ui:
                    continue
            entries.append(entry)
            if len(entries) >= n:
                break

        log.debug(f"审计日志查询：n={n}, success={success}, safety={safety}, q={q!r}, 返回 {len(entries)} 条")
        return {"entries": entries, "count": len(entries), "log_file": str(path)}

    @app.get("/api/audit/export")
    def audit_export():
        """导出完整审计日志文件（下载）。"""
        from fastapi.responses import PlainTextResponse
        from lihua.logging_config import get_logger
        log = get_logger(__name__)

        path = audit_log_path()
        if not path.exists():
            return PlainTextResponse("", status_code=404)

        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            log.error(f"读取审计日志失败：{e}")
            return PlainTextResponse(f"读取失败: {e}", status_code=500)

        log.info(f"导出审计日志：{len(content)} 字节")
        return PlainTextResponse(
            content,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="lihua-audit-{__version__}.log"',
            },
        )

    @app.delete("/api/audit")
    def audit_clear():
        """清空审计日志（危险操作，需前端二次确认）。"""
        from lihua.logging_config import get_logger
        log = get_logger(__name__)

        path = audit_log_path()
        if not path.exists():
            return {"ok": True, "message": "审计日志文件不存在"}

        try:
            # 备份再清空（避免误操作）
            backup = path.with_suffix(".log.bak")
            if backup.exists():
                backup.unlink()
            path.rename(backup)
            path.touch()
            log.warning(f"审计日志已清空（备份至 {backup.name}）")
            return {"ok": True, "message": f"已清空，备份至 {backup.name}"}
        except OSError as e:
            log.error(f"清空审计日志失败：{e}")
            return {"ok": False, "error": str(e)}

    # === 日志系统（v0.7.7+）===

    @app.get("/api/logs")
    def get_logs(n: int = 100, level: str | None = None) -> dict[str, Any]:
        """获取最近 N 条日志（从内存环形缓冲区读）。

        Args:
            n: 返回条数（最新在前）
            level: 过滤级别（DEBUG/INFO/WARNING/ERROR/CRITICAL），None 表示全部
        """
        from lihua.logging_config import get_recent_logs, log_file_path

        entries = get_recent_logs(n=n, level=level)
        return {
            "entries": entries,
            "count": len(entries),
            "log_file": str(log_file_path()),
        }

    @app.get("/api/logs/stream")
    def logs_stream():
        """SSE 流式推送实时日志。前端用 EventSource 监听。"""
        import asyncio
        import json as _json
        from fastapi.responses import StreamingResponse
        from lihua.logging_config import subscribe_sse, unsubscribe_sse

        q = subscribe_sse()

        async def event_generator():
            try:
                while True:
                    try:
                        # 非阻塞获取，配合 asyncio.sleep 避免卡死
                        entry = q.get_nowait()
                        yield f"data: {_json.dumps(entry, ensure_ascii=False)}\n\n"
                    except Exception:
                        # 队列为空，等 200ms 再试
                        await asyncio.sleep(0.2)
            finally:
                unsubscribe_sse(q)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/logs/level")
    def set_log_level(payload: dict[str, str]) -> dict[str, Any]:
        """运行时调整日志级别。body: {"level": "DEBUG"}"""
        from lihua.logging_config import set_level, DEFAULT_LEVEL

        level = (payload.get("level") or DEFAULT_LEVEL).upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"无效级别：{level}")
        set_level(level)
        # 持久化到 config.toml
        try:
            cfg = _load_config()
            cfg.log_level = level
            cfg.save()
        except Exception:
            pass
        return {"ok": True, "level": level}

    @app.get("/api/logs/file")
    def get_log_file(n: int = 200) -> dict[str, Any]:
        """直接读取日志文件的最后 N 行（比 /api/logs 更完整，但只返回文本）。

        用于 AuditSheet 或调试时查看完整日志（包括轮转前的日志）。
        """
        from lihua.logging_config import log_file_path

        path = log_file_path()
        if not path.exists():
            return {"lines": [], "path": str(path)}
        try:
            lines = path.read_text(encoding="utf-8").strip().splitlines()
        except OSError as e:
            return {"lines": [], "path": str(path), "error": str(e)}
        return {"lines": lines[-n:], "path": str(path)}

    # === LLM 配置管理 ===

    @app.get("/api/models/presets")
    def models_presets() -> dict[str, Any]:
        """返回所有预设模型清单。"""
        return {"presets": list_presets()}

    @app.get("/api/config/llm")
    def get_llm_config() -> dict[str, Any]:
        """返回当前 LLM 配置（API Key 脱敏）。"""
        cfg = _load_config()
        api_key = cfg.llm.api_key
        # 脱敏：只返回前 4 + 后 4，中间用 * 代替
        if api_key and len(api_key) > 12:
            masked = f"{api_key[:4]}{'*' * (len(api_key) - 8)}{api_key[-4:]}"
        else:
            masked = "***" if api_key else ""
        return {
            "enabled": cfg.llm.enabled,
            "provider": cfg.llm.provider,
            "api_key_masked": masked,
            "api_key_set": bool(api_key),
            "api_base": cfg.llm.api_base,
            "model": cfg.llm.model,
            "temperature": cfg.llm.temperature,
            "max_tokens": cfg.llm.max_tokens,
        }

    @app.post("/api/config/llm")
    def update_llm_config(req: LLMConfigUpdate) -> dict[str, Any]:
        """增量更新 LLM 配置，立即生效并持久化到 config.toml。"""
        cfg = _load_config()
        # api_key 为空字符串表示用户没改，不更新
        update_kwargs: dict[str, Any] = {}
        if req.enabled is not None:
            update_kwargs["enabled"] = req.enabled
        if req.provider is not None:
            update_kwargs["provider"] = req.provider
        if req.api_key:  # 非空字符串才更新
            update_kwargs["api_key"] = req.api_key
        if req.api_base is not None:
            update_kwargs["api_base"] = req.api_base or None
        if req.model is not None:
            update_kwargs["model"] = req.model
        if req.temperature is not None:
            update_kwargs["temperature"] = float(req.temperature)
        if req.max_tokens is not None:
            update_kwargs["max_tokens"] = int(req.max_tokens)

        if not update_kwargs:
            return {"ok": False, "error": "没有要更新的字段"}

        try:
            cfg.update_llm(**update_kwargs)
        except OSError as e:
            return {"ok": False, "error": f"保存配置失败：{e}"}

        return {
            "ok": True,
            "llm": {
                "enabled": cfg.llm.enabled,
                "provider": cfg.llm.provider,
                "api_base": cfg.llm.api_base,
                "model": cfg.llm.model,
                "api_key_set": bool(cfg.llm.api_key),
            },
        }

    @app.post("/api/config/llm/preset/{preset_id}")
    def apply_preset(preset_id: str, body: dict | None = None) -> dict[str, Any]:
        """一键应用预设：设置 provider + api_base + model。

        可在 body 里指定 model_id 选择具体模型，否则用 recommended_model。
        不修改 api_key（用户需单独填）。
        """
        preset = get_preset(preset_id)
        if not preset:
            return {"ok": False, "error": f"未知预设：{preset_id}"}

        # 选择具体模型：body.model_id 优先，否则 recommended_model
        model_id = preset.recommended_model
        if body and isinstance(body, dict):
            req_model = body.get("model_id")
            if req_model:
                # 验证模型在预设里（custom 预设允许任意）
                if preset.id == "custom":
                    model_id = req_model
                else:
                    valid = [m.id for m in preset.models]
                    if req_model in valid:
                        model_id = req_model
                    else:
                        return {"ok": False, "error": f"模型 {req_model} 不在预设 {preset.name} 中"}

        # custom 预设没有 recommended_model，需要 body 里带 api_base + model_id
        if preset.id == "custom" and not model_id:
            return {"ok": False, "error": "自定义预设需要指定 model_id 和 api_base"}

        cfg = _load_config()
        try:
            updates: dict[str, Any] = {
                "provider": preset.provider,
                "api_base": preset.api_base,
                "model": model_id,
            }
            # custom 模式可能传 api_base 覆盖
            if body and preset.id == "custom":
                custom_base = body.get("api_base")
                if custom_base:
                    updates["api_base"] = custom_base
            cfg.update_llm(**updates)
        except OSError as e:
            return {"ok": False, "error": f"保存配置失败：{e}"}

        return {
            "ok": True,
            "preset": {
                "id": preset.id,
                "name": preset.name,
                "api_base": cfg.llm.api_base,
                "recommended_model": preset.recommended_model,
                "models": [
                    {
                        "id": m.id, "name": m.name, "tier": m.tier,
                        "is_free": m.is_free, "context_length": m.context_length,
                        "description": m.description,
                    }
                    for m in preset.models
                ],
                "requires_api_key": preset.requires_api_key,
            },
            "llm": {
                "enabled": cfg.llm.enabled,
                "provider": cfg.llm.provider,
                "api_base": cfg.llm.api_base,
                "model": cfg.llm.model,
                "api_key_set": bool(cfg.llm.api_key),
            },
        }

    # =====================================================================
    # v0.8.9: 自进化接口——让 LLM 能重启后端、编译桌面端、查状态
    # v0.8.22: 逻辑抽到 lihua.self_evolve 模块，CLI 与 server 共用
    # =====================================================================
    from lihua.self_evolve import (
        bump_version as _self_bump_version,
        read_self_status as _self_read_status,
        trigger_build as _self_trigger_build,
        trigger_restart as _self_trigger_restart,
    )

    @app.post("/api/self/restart")
    def self_restart() -> dict[str, Any]:
        """v0.8.9: 重启后端服务（异步：spawn detached 脚本，约 8 秒新后端就绪）。"""
        return _self_trigger_restart()

    @app.post("/api/self/build")
    def self_build() -> dict[str, Any]:
        """v0.8.9: 后台编译桌面端 Tauri 二进制（异步，30-60s，状态写到 build-status.json）。"""
        return _self_trigger_build()

    @app.get("/api/self/status")
    def self_status() -> dict[str, Any]:
        """v0.8.9: 查询编译/重启状态（build/restart + current_pid + current_version）。"""
        return _self_read_status()

    @app.post("/api/self/version_bump")
    def self_version_bump(body: dict = None) -> dict[str, Any]:
        """v0.8.9: 一键升级 6 个版本号文件（Python a0 / Rust / Rust -alpha 三格式）。"""
        body = body or {}
        return _self_bump_version(str(body.get("version", "")).strip())

    # ─── v0.8.11: 记忆系统接口 ──────────────────────────────────

    @app.get("/api/memory/stats")
    def memory_stats() -> dict[str, Any]:
        """获取记忆系统统计信息。

        返回：episodes_count / knowledge_patterns / total_interactions /
              success_rate / top_tools / top_keywords 等。
        """
        try:
            from lihua.memory import get_memory_store
            return {"ok": True, "stats": get_memory_store().get_stats()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/memory/query")
    def memory_query(body: dict | None = None) -> dict[str, Any]:
        """检索记忆（知识库 + 历史情景）。

        Body: {"query": "问题或关键词", "limit": 5}
        """
        body = body or {}
        query = str(body.get("query", "")).strip()
        limit = int(body.get("limit", 5))
        limit = max(1, min(limit, 20))
        if not query:
            return {"ok": False, "error": "query 不能为空"}
        try:
            from lihua.memory import get_memory_store, _extract_keywords
            store = get_memory_store()
            knowledge = store.get_relevant_knowledge(query, limit=5)
            keywords = _extract_keywords(query)
            episodes = store.query_episodes(keywords, limit=limit) if keywords else []
            return {
                "ok": True,
                "query": query,
                "knowledge": [p.to_dict() for p in knowledge],
                "episodes": [ep.to_dict() for ep in episodes],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.delete("/api/memory/clear")
    def memory_clear() -> dict[str, Any]:
        """清空所有记忆（episodes + knowledge + preferences）。"""
        try:
            from lihua.memory import get_memory_store
            get_memory_store().clear_all()
            return {"ok": True, "message": "所有记忆已清空"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/memory/preferences")
    def memory_preferences() -> dict[str, Any]:
        """获取用户偏好（工具使用统计 + 关键词统计 + 成功率）。"""
        try:
            from lihua.memory import get_memory_store
            return {"ok": True, "preferences": get_memory_store().get_preferences().to_dict()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/memory/sessions")
    def memory_sessions(limit: int = 50) -> dict[str, Any]:
        """v0.8.20: 列出所有会话（按 session_id 聚合）。"""
        try:
            from lihua.memory import get_memory_store
            return {"ok": True, "sessions": get_memory_store().list_sessions(limit=limit)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/memory/sessions/{session_id}")
    def memory_session_detail(session_id: str) -> dict[str, Any]:
        """v0.8.20: 获取某个会话的所有 episode（含 reasoning + tool_calls）。"""
        try:
            from lihua.memory import get_memory_store
            eps = get_memory_store().get_session_episodes(session_id)
            return {
                "ok": True,
                "session_id": session_id,
                "episode_count": len(eps),
                "episodes": [ep.to_dict() for ep in eps],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/memory/knowledge")
    def memory_knowledge() -> dict[str, Any]:
        """v0.8.20: 获取所有知识库模式（用于 MemorySheet 知识库 tab 展示）。"""
        try:
            from lihua.memory import get_memory_store
            store = get_memory_store()
            patterns = store._load_knowledge()
            return {
                "ok": True,
                "patterns": [p.to_dict() for p in patterns],
                "count": len(patterns),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/memory/export")
    def memory_export() -> dict[str, Any]:
        """v0.8.20: 导出所有记忆数据（stats + preferences + traps，用于 MemorySheet 导出）。"""
        try:
            from lihua.memory import get_memory_store
            store = get_memory_store()
            return {
                "ok": True,
                "stats": store.get_stats(),
                "preferences": store.get_preferences().to_dict(),
                "traps": [t.to_dict() for t in store.get_traps()],
                "exported_at": time.time(),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/memory/archive")
    def memory_archive(body: dict | None = Body(None)) -> dict[str, Any]:
        """v0.8.17 P1-2: 触发记忆归档（把 N 天前的 episodes 移到 archive/）。

        Body: {"days": 30}  # 可选，默认用 config.memory.archive_days
        """
        body = body or {}
        days = body.get("days")
        if days is not None:
            try:
                days = int(days)
                if days < 1:
                    return {"ok": False, "error": "days 必须 >= 1"}
            except (TypeError, ValueError):
                return {"ok": False, "error": "days 必须是整数"}
        try:
            from lihua.memory import get_memory_store
            result = get_memory_store().archive_old_episodes(days)
            return {"ok": True, "result": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/memory/traps")
    def memory_traps_list(status: str | None = None) -> dict[str, Any]:
        """v0.8.18: 获取所有踩坑记录（traps）。

        Query: ?status=open 只返回未修复的坑
        """
        try:
            from lihua.memory import get_memory_store
            traps = get_memory_store().get_traps(status=status)
            return {
                "ok": True,
                "traps": [t.to_dict() for t in traps],
                "count": len(traps),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/memory/traps/search")
    def memory_traps_search(q: str = "", status: str | None = None, limit: int = 10) -> dict[str, Any]:
        """v0.8.18: 搜索踩坑记录。

        Query: ?q=install_app&status=open&limit=10
        """
        try:
            from lihua.memory import get_memory_store, _extract_keywords
            store = get_memory_store()
            if q:
                keywords = _extract_keywords(q)
                traps = store.search_traps(keywords, status=status, limit=limit)
            else:
                traps = store.get_traps(status=status)[:limit]
            return {
                "ok": True,
                "traps": [t.to_dict() for t in traps],
                "count": len(traps),
                "query": q,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/memory/traps")
    def memory_traps_add(body: dict | None = Body(None)) -> dict[str, Any]:
        """v0.8.18: 手动添加踩坑记录。

        Body: {"symptom": "...", "root_cause": "...", "solution": "...", "related_skills": [...]}
        """
        body = body or {}
        symptom = str(body.get("symptom", "")).strip()
        if not symptom:
            return {"ok": False, "error": "symptom 不能为空"}
        try:
            from lihua.memory import get_memory_store
            trap = get_memory_store().add_trap(
                symptom=symptom,
                related_skills=body.get("related_skills"),
                related_keywords=body.get("related_keywords"),
                root_cause=str(body.get("root_cause", "")),
                solution=str(body.get("solution", "")),
                status=str(body.get("status", "open")),
            )
            return {"ok": True, "trap": trap.to_dict()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.patch("/api/memory/traps/{trap_id}")
    def memory_traps_update(trap_id: int, body: dict | None = Body(None)) -> dict[str, Any]:
        """v0.8.18: 更新踩坑记录（填根因/标记修复）。

        Path: /api/memory/traps/3
        Body: {"root_cause": "...", "solution": "...", "status": "fixed", "fix_verified": true}
        """
        body = body or {}
        try:
            from lihua.memory import get_memory_store
            # 只允许更新的字段
            allowed = {"symptom", "root_cause", "solution", "status", "fix_verified", "occurrence_count", "related_skills"}
            updates = {k: v for k, v in body.items() if k in allowed}
            if not updates:
                return {"ok": False, "error": "没有可更新的字段"}
            ok, msg, trap = get_memory_store().update_trap(trap_id, updates)
            if not ok:
                return {"ok": False, "error": msg}
            return {"ok": True, "trap": trap.to_dict() if trap else None, "msg": msg}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ─── v0.8.12: 技能自生成接口 ────────────────────────────────

    @app.get("/api/skill/auto/stats")
    def auto_skill_stats() -> dict[str, Any]:
        """获取技能自生成系统统计信息。

        返回：auto_skills_count / auto_skills 列表 / repeated_patterns /
              threshold / auto_skills_dir 路径。
        """
        try:
            from lihua.skill_generator import get_skill_stats
            return {"ok": True, "stats": get_skill_stats()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/skill/auto/list")
    def auto_skill_list() -> dict[str, Any]:
        """列出所有自动生成的技能（~/.config/lihua/skills/auto_generated/）。"""
        try:
            from lihua.skill_generator import list_auto_skills
            skills = list_auto_skills()
            return {"ok": True, "count": len(skills), "skills": skills}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.delete("/api/skill/auto/{name}")
    def auto_skill_delete(name: str) -> dict[str, Any]:
        """删除一个自动生成的技能。

        删除后自动 reload SkillRegistry，让删除立即生效。
        """
        try:
            from lihua.skill_generator import delete_auto_skill, reload_registry
            ok, msg = delete_auto_skill(name)
            if not ok:
                return {"ok": False, "error": msg}
            _, reload_msg, skill_count = reload_registry()
            return {"ok": True, "message": msg, "skill_count": skill_count}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/skill/auto/reload")
    def auto_skill_reload() -> dict[str, Any]:
        """重新加载 SkillRegistry（手动让新加的 YAML 文件生效）。"""
        try:
            from lihua.skill_generator import reload_registry
            ok, msg, count = reload_registry()
            return {"ok": ok, "message": msg, "skill_count": count}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/skill/auto/patterns")
    def auto_skill_patterns() -> dict[str, Any]:
        """从记忆系统检测重复工具链（出现 3+ 次），提示 LLM 考虑生成技能。"""
        try:
            from lihua.skill_generator import detect_repeated_patterns
            patterns = detect_repeated_patterns()
            return {"ok": True, "count": len(patterns), "patterns": patterns}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ─── v0.8.13: 模块化 Prompt 系统接口 ──────────────────────────

    @app.get("/api/prompt/stats")
    def prompt_stats() -> dict[str, Any]:
        """获取 PromptBuilder 的 section 统计信息。

        返回 total / enabled / disabled / sections 列表（name/priority/enabled/tags/description）。
        """
        try:
            from lihua.prompt_builder import get_builder
            return {"ok": True, "stats": get_builder().stats()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/prompt/sections")
    def prompt_sections() -> dict[str, Any]:
        """列出所有 section（按 priority 排序）。"""
        try:
            from lihua.prompt_builder import get_builder
            sections = get_builder().list_sections()
            return {
                "ok": True,
                "count": len(sections),
                "sections": [
                    {
                        "name": s.name,
                        "priority": s.priority,
                        "enabled": s.enabled,
                        "tags": s.tags,
                        "description": s.description,
                        "content_length": len(s.content),
                    }
                    for s in sections
                ],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/prompt/section/{name}/enable")
    def prompt_section_enable(name: str) -> dict[str, Any]:
        """启用一个 section。"""
        try:
            from lihua.prompt_builder import get_builder
            builder = get_builder()
            if not builder.get_section(name):
                return {"ok": False, "error": f"section '{name}' 不存在"}
            builder.enable(name)
            return {"ok": True, "message": f"section '{name}' 已启用"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/prompt/section/{name}/disable")
    def prompt_section_disable(name: str) -> dict[str, Any]:
        """禁用一个 section。"""
        try:
            from lihua.prompt_builder import get_builder
            builder = get_builder()
            if not builder.get_section(name):
                return {"ok": False, "error": f"section '{name}' 不存在"}
            builder.disable(name)
            return {"ok": True, "message": f"section '{name}' 已禁用"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/prompt/tag/{tag}/enable")
    def prompt_tag_enable(tag: str) -> dict[str, Any]:
        """按标签批量启用 section。"""
        try:
            from lihua.prompt_builder import get_builder
            get_builder().enable_by_tag(tag)
            return {"ok": True, "message": f"标签 '{tag}' 的所有 section 已启用"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/prompt/tag/{tag}/disable")
    def prompt_tag_disable(tag: str) -> dict[str, Any]:
        """按标签批量禁用 section。"""
        try:
            from lihua.prompt_builder import get_builder
            get_builder().disable_by_tag(tag)
            return {"ok": True, "message": f"标签 '{tag}' 的所有 section 已禁用"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/prompt/reset")
    def prompt_reset() -> dict[str, Any]:
        """重置 PromptBuilder（重新注册所有内置 section，清除插件注册的 section）。"""
        try:
            from lihua.prompt_builder import reset_builder
            reset_builder()
            return {"ok": True, "message": "PromptBuilder 已重置"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ─── v0.8.14: 插件架构接口 ────────────────────────────────────

    @app.get("/api/plugin/stats")
    def plugin_stats() -> dict[str, Any]:
        """获取插件加载器统计信息。

        返回 total / loaded / disabled / error / skipped / plugins 列表。
        """
        try:
            from lihua.plugin_loader import get_loader
            return {"ok": True, "stats": get_loader().stats()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/plugin/list")
    def plugin_list() -> dict[str, Any]:
        """列出所有已发现的插件（按名字排序）。"""
        try:
            from lihua.plugin_loader import get_loader
            plugins = get_loader().list_plugins()
            return {
                "ok": True,
                "count": len(plugins),
                "plugins": [
                    {
                        "name": p.name,
                        "status": p.status,
                        "error": p.error,
                        "path": p.path,
                        "meta": p.meta.to_dict(),
                        "registered_sections": list(p.registered_sections),
                    }
                    for p in plugins
                ],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/plugin/{name}/info")
    def plugin_info(name: str) -> dict[str, Any]:
        """获取单个插件详情。"""
        try:
            from lihua.plugin_loader import get_loader
            info = get_loader().get_plugin(name)
            if info is None:
                return {"ok": False, "error": f"插件 '{name}' 不存在"}
            return {
                "ok": True,
                "plugin": {
                    "name": info.name,
                    "status": info.status,
                    "error": info.error,
                    "path": info.path,
                    "meta": info.meta.to_dict(),
                    "registered_sections": list(info.registered_sections),
                },
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/plugin/reload")
    def plugin_reload() -> dict[str, Any]:
        """重新加载所有插件（unload + load）。"""
        try:
            from lihua.plugin_loader import get_loader
            result = get_loader().reload()
            loaded = sum(1 for i in result.values() if i.status == "loaded")
            error = sum(1 for i in result.values() if i.status == "error")
            return {
                "ok": True,
                "message": f"插件重载完成：{loaded} 成功，{error} 失败",
                "loaded": loaded,
                "error": error,
                "total": len(result),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/plugin/{name}/enable")
    def plugin_enable(name: str) -> dict[str, Any]:
        """启用单个插件（从 disabled 移除 + 加载）。"""
        try:
            from lihua.plugin_loader import get_loader
            ok, msg = get_loader().enable_plugin(name)
            return {"ok": ok, "message": msg}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/plugin/{name}/disable")
    def plugin_disable(name: str) -> dict[str, Any]:
        """禁用单个插件（加入 disabled + 卸载）。"""
        try:
            from lihua.plugin_loader import get_loader
            ok, msg = get_loader().disable_plugin(name)
            return {"ok": ok, "message": msg}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ─── v0.8.15: 自监控分析接口 ──────────────────────────────────

    @app.get("/api/analytics/overview")
    def analytics_overview() -> dict[str, Any]:
        """总览统计：总交互数、成功率、平均耗时、活跃天数等。"""
        try:
            from lihua.analytics import get_overview
            return {"ok": True, "overview": get_overview()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/analytics/tools")
    def analytics_tools() -> dict[str, Any]:
        """工具使用统计：每个工具的调用次数、成功率、平均耗时。"""
        try:
            from lihua.analytics import get_tool_stats
            return {"ok": True, "stats": get_tool_stats()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/analytics/errors")
    def analytics_errors() -> dict[str, Any]:
        """错误分析：失败工具排行、错误分类、错误样本。"""
        try:
            from lihua.analytics import get_error_analysis
            return {"ok": True, "analysis": get_error_analysis()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/analytics/questions")
    def analytics_questions() -> dict[str, Any]:
        """用户问题分类统计：诊断类/修复类/查询类/配置类占比。"""
        try:
            from lihua.analytics import get_question_categories
            return {"ok": True, "categories": get_question_categories()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/analytics/skills")
    def analytics_skills() -> dict[str, Any]:
        """技能（预定义 skill）使用频率统计。"""
        try:
            from lihua.analytics import get_skill_usage
            return {"ok": True, "usage": get_skill_usage()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/analytics/commands")
    def analytics_commands() -> dict[str, Any]:
        """从 audit_log 统计命令使用情况（按命令分类）。"""
        try:
            from lihua.analytics import get_command_stats
            return {"ok": True, "stats": get_command_stats()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/analytics/suggestions")
    def analytics_suggestions() -> dict[str, Any]:
        """基于数据的改进建议列表。"""
        try:
            from lihua.analytics import get_suggestions
            return {"ok": True, "suggestions": get_suggestions()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/analytics/report")
    def analytics_report() -> dict[str, Any]:
        """完整分析报告（含所有统计 + 建议）。"""
        try:
            from lihua.analytics import generate_report, generate_text_report
            return {
                "ok": True,
                "report": generate_report(),
                "text_report": generate_text_report(),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return app
