"""LLM 路由：litellm 优先，标准库 urllib 兜底。

支持三种 provider：
1. deepseek / openai / anthropic：通过 litellm 或 OpenAI 兼容 API
2. openai-compat：用户自定义 OpenAI 兼容端点（用 urllib 直 POST）
3. ollama：本地服务（也走 OpenAI 兼容协议）

所有调用统一返回 LLMResponse，失败抛 LLMError。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from lihua.config import LLMConfig


class LLMError(RuntimeError):
    """LLM 调用失败。"""


@dataclass
class LLMResponse:
    """LLM 调用结果。"""

    text: str
    model: str
    usage: dict[str, int] | None = None
    raw: Any = None
    provider: str = ""
    tool_calls: list[dict[str, Any]] | None = None
    finish_reason: str | None = None
    reasoning_content: str = ""  # v0.8.20: DeepSeek/GLM 思考链字段（OpenAI 兼容协议）

    @property
    def ok(self) -> bool:
        return bool(self.text) or bool(self.tool_calls)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


def _try_litellm() -> Any | None:
    """尝试导入 litellm，失败返回 None。"""
    try:
        import litellm  # type: ignore
        return litellm
    except ImportError:
        return None


def _call_openai_compat(cfg: LLMConfig, messages: list[dict[str, str]],
                       stream: bool = False) -> LLMResponse:
    """用 urllib 直接 POST OpenAI 兼容端点。"""
    if not cfg.api_base:
        raise LLMError("openai-compat 模式需要配置 api_base")
    if not cfg.api_key:
        raise LLMError("openai-compat 模式需要配置 api_key")

    url = cfg.api_base.rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "stream": False,  # 简化：不支持流式（CLI 单次请求）
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.api_key}",
    }

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:  # noqa: BLE001
            pass
        raise LLMError(f"HTTP {e.code} {e.reason}: {body_text}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"网络错误: {e.reason}") from e

    if not isinstance(data, dict):
        raise LLMError(f"返回格式异常：{data!r}")

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"返回结构异常: {data}") from e

    usage = data.get("usage")
    return LLMResponse(
        text=text or "",
        model=data.get("model", cfg.model),
        usage=usage,
        raw=data,
        provider="openai-compat",
    )


def _call_litellm(cfg: LLMConfig, messages: list[dict[str, str]]) -> LLMResponse:
    """通过 litellm 调用（支持 deepseek / openai / anthropic / ollama 等）。"""
    litellm = _try_litellm()
    if litellm is None:
        raise LLMError("litellm 未安装，请执行 `pip install 'lihua[llm]'`")

    model = cfg.model
    # litellm 前缀约定
    if cfg.provider == "deepseek" and not model.startswith("deepseek/"):
        model = f"deepseek/{model}"
    elif cfg.provider == "openai" and not model.startswith("openai/"):
        # 用户配置的 model 可能是 "gpt-4o-mini" 这种，litellm 接受
        pass
    elif cfg.provider == "anthropic" and not model.startswith("claude"):
        # claude-* 系列 litellm 直接接受
        pass
    elif cfg.provider == "ollama" and not model.startswith("ollama/"):
        model = f"ollama/{model}"
    elif cfg.provider == "openai-compat":
        # litellm 用 "openai/<model>" + api_base 调用兼容端点
        model = f"openai/{model}" if not model.startswith("openai/") else model

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "timeout": cfg.timeout,
    }
    if cfg.api_key:
        kwargs["api_key"] = cfg.api_key
    if cfg.api_base:
        kwargs["api_base"] = cfg.api_base

    try:
        resp = litellm.completion(**kwargs)
    except Exception as e:  # noqa: BLE001
        raise LLMError(f"litellm 调用失败: {e}") from e

    try:
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        usage_dict = None
        if usage:
            usage_dict = {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "total_tokens": getattr(usage, "total_tokens", 0),
            }
        model_used = getattr(resp, "model", cfg.model)
        return LLMResponse(
            text=text,
            model=model_used,
            usage=usage_dict,
            raw=resp,
            provider=cfg.provider,
        )
    except (AttributeError, IndexError, KeyError, TypeError) as e:
        raise LLMError(f"litellm 返回结构异常: {e}") from e


def call_llm(cfg: LLMConfig, messages: list[dict[str, str]]) -> LLMResponse:
    """统一 LLM 调用入口。

    选择策略：
    - openai-compat → 优先 litellm（如果装了），否则 urllib 直 POST
    - 其他 provider → litellm 必装
    """
    if not cfg.enabled:
        raise LLMError("LLM 未启用（config.toml [llm].enabled = false）")
    if not cfg.model:
        raise LLMError("未配置 LLM model")

    # openai-compat 优先用 urllib（避免 litellm 依赖）
    if cfg.provider == "openai-compat":
        if _try_litellm() is not None:
            try:
                return _call_litellm(cfg, messages)
            except LLMError:
                # litellm 失败，回退 urllib
                return _call_openai_compat(cfg, messages)
        return _call_openai_compat(cfg, messages)

    # 其他 provider 必须有 litellm
    return _call_litellm(cfg, messages)


def _call_openai_compat_with_tools(
    cfg: LLMConfig,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str = "auto",
) -> LLMResponse:
    """用 urllib POST OpenAI 兼容端点（带 tools / function calling 支持）。"""
    if not cfg.api_base:
        raise LLMError("openai-compat 模式需要配置 api_base")
    if not cfg.api_key:
        raise LLMError("openai-compat 模式需要配置 api_key")

    url = cfg.api_base.rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.api_key}",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:  # noqa: BLE001
            pass
        raise LLMError(f"HTTP {e.code} {e.reason}: {body_text}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"网络错误: {e.reason}") from e

    if not isinstance(data, dict):
        raise LLMError(f"返回格式异常：{data!r}")

    try:
        msg = data["choices"][0]["message"]
        text = msg.get("content") or ""
        tool_calls = msg.get("tool_calls")
        reasoning_content = msg.get("reasoning_content") or ""  # v0.8.20: DeepSeek/GLM 思考链
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"返回结构异常: {data}") from e

    usage = data.get("usage")
    return LLMResponse(
        text=text or "",
        model=data.get("model", cfg.model),
        usage=usage,
        raw=data,
        provider="openai-compat",
        tool_calls=tool_calls,
        finish_reason=data["choices"][0].get("finish_reason") if data.get("choices") else None,
        reasoning_content=reasoning_content,
    )


def call_llm_with_tools(
    cfg: LLMConfig,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str = "auto",
) -> LLMResponse:
    """带工具调用的 LLM 调用（支持 function calling）。

    返回的 LLMResponse.tool_calls 是 LLM 决定调用的工具列表，格式：
        [{"id": "...", "type": "function",
          "function": {"name": "install_app", "arguments": '{"target":"QQ"}'}}]
    无工具调用时为 None。
    """
    if not cfg.enabled:
        raise LLMError("LLM 未启用")
    if not cfg.model:
        raise LLMError("未配置 LLM model")

    if cfg.provider == "openai-compat":
        return _call_openai_compat_with_tools(cfg, messages, tools, tool_choice)

    # 其他 provider 走 litellm（litellm 原生支持 tools 参数）
    litellm = _try_litellm()
    if litellm is None:
        raise LLMError("非 openai-compat provider 需要 litellm，请执行 `pip install 'lihua[llm]'`")

    model = cfg.model
    if cfg.provider == "deepseek" and not model.startswith("deepseek/"):
        model = f"deepseek/{model}"
    elif cfg.provider == "ollama" and not model.startswith("ollama/"):
        model = f"ollama/{model}"

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "timeout": cfg.timeout,
    }
    if cfg.api_key:
        kwargs["api_key"] = cfg.api_key
    if cfg.api_base:
        kwargs["api_base"] = cfg.api_base
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice

    try:
        resp = litellm.completion(**kwargs)
    except Exception as e:  # noqa: BLE001
        raise LLMError(f"litellm 调用失败: {e}") from e

    try:
        msg = resp.choices[0].message
        text = msg.content or ""
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls and hasattr(tool_calls, "model_dump"):
            tool_calls = tool_calls.model_dump()
        elif tool_calls and hasattr(tool_calls, "__iter__"):
            tool_calls = [
                tc.model_dump() if hasattr(tc, "model_dump") else tc
                for tc in tool_calls
            ]
        finish_reason = getattr(resp.choices[0], "finish_reason", None)
        reasoning_content = getattr(msg, "reasoning_content", "") or ""  # v0.8.20: 思考链
        usage = getattr(resp, "usage", None)
        usage_dict = None
        if usage:
            usage_dict = {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "total_tokens": getattr(usage, "total_tokens", 0),
            }
        return LLMResponse(
            text=text,
            model=getattr(resp, "model", cfg.model),
            usage=usage_dict,
            raw=resp,
            provider=cfg.provider,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            reasoning_content=reasoning_content,
        )
    except (AttributeError, IndexError, KeyError, TypeError) as e:
        raise LLMError(f"litellm 返回结构异常: {e}") from e


def chat(cfg: LLMConfig, system: str, user: str) -> str:
    """便捷调用：单轮对话，返回文本。失败返回空字符串并打印错误。"""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        resp = call_llm(cfg, messages)
        return resp.text
    except LLMError as e:
        import sys
        print(f"[lihua] LLM 调用失败: {e}", file=sys.stderr)
        return ""


def is_available(cfg: LLMConfig) -> bool:
    """快捷判断 LLM 是否可用（启用 + 有 model/key）。"""
    if not cfg.enabled or not cfg.model:
        return False
    if cfg.provider == "openai-compat" and not (cfg.api_key and cfg.api_base):
        return False
    if cfg.provider in ("deepseek", "openai", "anthropic") and not cfg.api_key:
        return False
    return True
