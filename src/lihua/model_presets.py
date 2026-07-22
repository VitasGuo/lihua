"""LLM 预设模型清单（2026 年 7 月最新版）。

为用户提供一键切换主流国产大模型的便利。每个预设包含：
- provider：API 调用协议（均为 openai-compat）
- api_base：API 端点
- models：模型选项列表，每个选项标记 tier（basic/pro）+ is_free
- recommended_model：推荐默认模型 ID（**默认选最贵旗舰**，挑剔的懒人不在乎花钱）
- requires_api_key：是否需要 API Key
- description：简短描述（前端展示用）

第 6 项 "custom" 用于任何 OpenAI 兼容端点（包括 SenseNova、本地 Ollama 等）。

模型清单更新日期：2026-07-22（v0.8.25 全面更新）
来源：智谱 GLM-5.2 / DeepSeek V4 / Kimi K3 / MiMo V2.5 / MiniMax-M3 官方文档

设计原则（v0.7.3 调整）：
- **默认推荐 pro 旗舰**：用户不在乎花钱，要最好的体验
- **明确警告低能力模型**：能力低于 deepseek-v4-flash 的模型可能无法正确调用工具
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelOption:
    """单个模型选项。"""

    id: str  # 模型 ID（API 调用用）
    name: str  # 显示名
    tier: str  # "basic" 或 "pro"
    is_free: bool = False
    context_length: str = ""  # 例如 "128K" / "1M"
    description: str = ""


@dataclass(frozen=True)
class ModelPreset:
    """LLM 厂商预设。"""

    id: str
    name: str
    provider: str
    api_base: str
    models: list[ModelOption] = field(default_factory=list)
    recommended_model: str = ""  # 推荐默认模型 ID
    requires_api_key: bool = True
    description: str = ""
    homepage: str = ""  # 用户申请 API Key 的页面
    docs_note: str = ""  # 备注


# === 6 个预设：5 个国产厂商 + 1 个自定义 ===
# 排序原则：按能力默认推荐 pro 旗舰（用户要最好的体验，不在乎花钱）
PRESETS: list[ModelPreset] = [
    ModelPreset(
        id="zhipu",
        name="智谱 GLM",
        provider="openai-compat",
        api_base="https://open.bigmodel.cn/api/paas/v4",
        recommended_model="glm-5.2",  # 默认旗舰
        models=[
            ModelOption(
                id="glm-4.7-flash",
                name="GLM-4.7-Flash",
                tier="basic",
                is_free=True,
                context_length="200K",
                description="完全免费，200K 上下文，支持 function calling，入门首选",
            ),
            ModelOption(
                id="glm-4.7",
                name="GLM-4.7",
                tier="basic",
                context_length="200K",
                description="标准版，200K 上下文，能力均衡性价比高",
            ),
            ModelOption(
                id="glm-4-plus",
                name="GLM-4-Plus",
                tier="basic",
                context_length="128K",
                description="经典旗舰，工具调用稳定可靠",
            ),
            ModelOption(
                id="glm-5.2",
                name="GLM-5.2",
                tier="pro",
                context_length="200K",
                description="最新旗舰，思考模式 + 复杂推理",
            ),
        ],
        requires_api_key=True,
        description="国产之光，GLM-4.7-Flash 完全免费可用",
        homepage="https://open.bigmodel.cn/usercenter/apikeys",
        docs_note="GLM-4.7-Flash 完全免费（200K）；GLM-5.2 是最新旗舰",
    ),
    ModelPreset(
        id="deepseek",
        name="DeepSeek",
        provider="openai-compat",
        api_base="https://api.deepseek.com/v1",
        recommended_model="deepseek-v4-pro",  # 默认旗舰
        models=[
            ModelOption(
                id="deepseek-v4-flash",
                name="DeepSeek V4 Flash",
                tier="basic",
                context_length="1M",
                description="经济高效版，1M 超长上下文，原生 function calling（能力下限）",
            ),
            ModelOption(
                id="deepseek-v4-pro",
                name="DeepSeek V4 Pro",
                tier="pro",
                context_length="1M",
                description="旗舰版，性能比肩顶级闭源，Agent 能力最强",
            ),
        ],
        requires_api_key=True,
        description="性价比之王，V4 系列原生支持 function calling",
        homepage="https://platform.deepseek.com/api_keys",
        docs_note="V4 Flash 是能力下限；V4 Pro 是旗舰",
    ),
    ModelPreset(
        id="kimi",
        name="Kimi 月之暗面",
        provider="openai-compat",
        api_base="https://api.moonshot.cn/v1",
        recommended_model="kimi-k3",  # 默认旗舰
        models=[
            ModelOption(
                id="kimi-k2.6",
                name="Kimi K2.6",
                tier="basic",
                context_length="256K",
                description="开源高效版，1T MoE，Agent 编程能力强",
            ),
            ModelOption(
                id="kimi-k3",
                name="Kimi K3",
                tier="pro",
                context_length="1M",
                description="最新旗舰，2.8T 参数，1M 上下文，挑战闭源旗舰",
            ),
        ],
        requires_api_key=True,
        description="开源 Agent 编程之王，长上下文 + 强 function calling",
        homepage="https://platform.moonshot.cn/console/api-keys",
        docs_note="K2.6 开源免费商用；K3 为最新旗舰（2026-07 发布）",
    ),
    ModelPreset(
        id="mimo",
        name="MiMo 小米",
        provider="openai-compat",
        api_base="https://api.mimo.xiaomi.com/v1",
        recommended_model="mimo-v2.5-pro",  # 默认旗舰
        models=[
            ModelOption(
                id="mimo-v2.5",
                name="MiMo V2.5",
                tier="basic",
                context_length="1M",
                description="全模态基础版，310B MoE，1M 上下文",
            ),
            ModelOption(
                id="mimo-v2.5-pro",
                name="MiMo V2.5 Pro",
                tier="pro",
                context_length="1M",
                description="旗舰版，1T MoE，长程推理 + Agent 效率",
            ),
        ],
        requires_api_key=True,
        description="小米自研，API 永久降价 99%，function calling 友好",
        homepage="https://platform.xiaomimimo.com/console/api-keys",
        docs_note="MiMo V2.5 系列已上线；旧 V2 系列于 2026-06-30 下线",
    ),
    ModelPreset(
        id="minimax",
        name="MiniMax",
        provider="openai-compat",
        api_base="https://api.minimax.chat/v1",
        recommended_model="MiniMax-M3",  # 默认旗舰
        models=[
            ModelOption(
                id="MiniMax-M2.7",
                name="MiniMax M2.7",
                tier="basic",
                context_length="200K",
                description="上一代旗舰，SWE-Bench Pro 56.2，推理能力强",
            ),
            ModelOption(
                id="MiniMax-M3",
                name="MiniMax M3",
                tier="pro",
                context_length="1M",
                description="2026-06 最新旗舰，1M 上下文，多模态 coding",
            ),
        ],
        requires_api_key=True,
        description="多模态、中文优化、长上下文 coding",
        homepage="https://platform.minimaxi.com/user-center/basic-information/interface-search",
        docs_note="M2.7 为上一代旗舰；M3 是最新旗舰（2026-06 发布）",
    ),
    ModelPreset(
        id="custom",
        name="自定义 (OpenAI 兼容)",
        provider="openai-compat",
        api_base="",
        recommended_model="",
        models=[],
        requires_api_key=True,
        description="任何 OpenAI 兼容端点，包括 SenseNova、本地 Ollama、阿里云百炼等",
        homepage="",
        docs_note="需手动填 api_base + model；SenseNova 示例：api_base=https://token.sensenova.cn/v1",
    ),
]


# 能力下限警告：低于此模型的模型不推荐用于 Agent 模式
MIN_RECOMMENDED_MODEL = "deepseek-v4-flash"
MIN_RECOMMENDED_WARNING = (
    "不建议使用能力低于 DeepSeek V4 Flash 的模型，否则 Agent 可能无法正确调用工具，"
    "导致任务失败或执行错误命令。"
)


def list_presets() -> list[dict]:
    """返回前端可用的预设清单。"""
    return [
        {
            "id": p.id,
            "name": p.name,
            "provider": p.provider,
            "api_base": p.api_base,
            "recommended_model": p.recommended_model,
            "models": [
                {
                    "id": m.id,
                    "name": m.name,
                    "tier": m.tier,
                    "is_free": m.is_free,
                    "context_length": m.context_length,
                    "description": m.description,
                }
                for m in p.models
            ],
            "requires_api_key": p.requires_api_key,
            "description": p.description,
            "homepage": p.homepage,
            "docs_note": p.docs_note,
        }
        for p in PRESETS
    ]


def get_min_recommended() -> dict[str, str]:
    """返回能力下限警告信息（前端展示用）。"""
    return {
        "model": MIN_RECOMMENDED_MODEL,
        "warning": MIN_RECOMMENDED_WARNING,
    }


def get_preset(preset_id: str) -> ModelPreset | None:
    """按 id 查找预设。"""
    for p in PRESETS:
        if p.id == preset_id:
            return p
    return None
