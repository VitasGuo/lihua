"""v0.8.11 记忆系统——让 agent 拥有跨会话的长期记忆。

二次进化第一支柱。没有记忆的 agent 每次都从零开始，无法学习、无法改进。

三种记忆：

1. **情景记忆（episodes.jsonl）**：记录每次交互的完整过程
   - 用户输入、工具调用链、成功/失败、agent 回复、用户反馈
   - 追加写入（高效），保留最近 1000 条
   - 用于检索相似历史经验

2. **知识库（knowledge.json）**：从情景记忆中提炼的问题→解决方案映射
   - 关键词 → 工具链 → 成功率
   - 自动更新：每次交互后从 episode 提取/更新 pattern
   - 用于快速检索"这类问题之前用什么解决的"

3. **用户偏好（preferences.json）**：从交互中学习的用户习惯
   - 常用工具排行、常见任务类型、偏好的确认方式
   - 用于个性化 agent 行为

设计原则：
- 无外部依赖（不用 sqlite/embeddings/vector DB），纯 JSON 文件
- 线程安全（文件锁 + append-only episodes）
- 可配置（memory.enabled / max_episodes / max_knowledge_patterns）
- 可遗忘（老数据自动清理，用户可手动清空）

文件位置：
- ~/.local/share/lihua/memory/episodes.jsonl
- ~/.local/share/lihua/memory/knowledge.json
- ~/.local/share/lihua/memory/preferences.json
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from lihua.config import data_dir
from lihua.logging_config import get_logger

log = get_logger(__name__)

# 记忆存储目录
_MEM_DIR = data_dir() / "memory"
_EPISODES_FILE = _MEM_DIR / "episodes.jsonl"
_KNOWLEDGE_FILE = _MEM_DIR / "knowledge.json"
_PREFS_FILE = _MEM_DIR / "preferences.json"
_TRAPS_FILE = _MEM_DIR / "traps.jsonl"  # v0.8.18: 踩坑记录（失败案例结构化根因分析）

# 容量限制（防无限增长）
_MAX_EPISODES = 1000
_MAX_KNOWLEDGE_PATTERNS = 500
_MAX_TRAPS = 200  # v0.8.18: 最多保留 200 条踩坑记录
_MAX_QUERY_RESULTS = 10

# v0.8.16: 记忆分层加载默认值（参考 OpenClaw L0-L4 设计）
# L0 核心：system prompt（在 prompt_builder.py）
# L1 长期：knowledge.json + preferences.json（每次必加载）
# L2 热：最近 hot_days 天 episodes（每次注入 context）
# L3 温：warm_days 天内 episodes（memory_recall 检索范围）
# L4 冷：archive_days 天前 episodes（归档到 archive/，不加载）
_HOT_DAYS = 3
_WARM_DAYS = 7
_ARCHIVE_DAYS = 30


@dataclass
class ToolCallRecord:
    """记忆系统里的工具调用记录（与 agent.ToolCallRecord 同构但独立，避免循环依赖）。"""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    duration: float = 0.0
    error: str = ""


@dataclass
class Episode:
    """一次完整的交互情景。"""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: float = field(default_factory=time.time)
    user_input: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    success: bool = True
    agent_response: str = ""
    user_feedback: str | None = None  # None=无反馈 / "positive" / "negative"
    session_id: str = ""
    duration: float = 0.0  # 整次交互耗时（秒）
    reasoning: str = ""  # v0.8.20: LLM 思考链（reasoning_content），可能为空

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Episode":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


@dataclass
class KnowledgePattern:
    """知识库中的一条模式：某类问题用什么工具链解决。"""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    keywords: list[str] = field(default_factory=list)  # 问题关键词
    tool_chain: list[str] = field(default_factory=list)  # 工具名序列
    success_count: int = 0
    fail_count: int = 0
    last_used: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)
    example_episode_id: str = ""

    @property
    def total_count(self) -> int:
        return self.success_count + self.fail_count

    @property
    def success_rate(self) -> float:
        return self.success_count / max(1, self.total_count)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "KnowledgePattern":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


@dataclass
class UserPreferences:
    """从交互中学习的用户偏好。"""

    tool_usage: dict[str, int] = field(default_factory=dict)  # 工具名 → 使用次数
    common_keywords: dict[str, int] = field(default_factory=dict)  # 关键词 → 出现次数
    total_episodes: int = 0
    success_rate: float = 1.0
    last_session: float = 0.0
    first_session: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "UserPreferences":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


@dataclass
class Trap:
    """v0.8.18: 踩坑记录——失败案例的结构化根因分析。

    参考 trae 工作流里的 traps.md 三段式：现象 → 根因 → 解决方案。
    与 usage_log（每次使用记录）/ rules（提炼规则）互补：
    - usage_log 记每次使用（成功/失败 + 参数快照）
    - rules 记从 usage_log 提炼的"已验证稳定规则"
    - traps 记失败案例的结构化根因分析（为什么失败 + 怎么修复）

    生命周期：
    1. skill 执行失败 → 自动创建 trap（status=open，root_cause/solution 留空）
    2. LLM 诊断出根因 + 解决方案 → 调 trap_update 填充 root_cause/solution
    3. 下次同类问题成功解决 → 调 trap_update 标记 status=fixed
    """

    id: int = 0  # 编号递增（T001, T002...）
    timestamp: float = field(default_factory=time.time)  # 发现时间
    symptom: str = ""  # 现象（错误原文 / 用户描述 / 失败的 skill + 参数）
    root_cause: str = ""  # 根因（源码行号 / 配置项 / 环境问题）
    solution: str = ""  # 解决方案（改哪个文件哪个值 / 用什么参数）
    status: str = "open"  # open（未修复）/ fixed（已修复）/ workaround（绕过）
    related_skills: list[str] = field(default_factory=list)  # 相关 skill 名
    related_keywords: list[str] = field(default_factory=list)  # 相关关键词（便于检索）
    fixed_at: float | None = None  # 修复时间
    fix_verified: bool = False  # 修复是否验证（下次同类问题成功后标记）
    occurrence_count: int = 1  # 重复出现次数（同类失败累加）

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Trap":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


# ─── 文本工具 ──────────────────────────────────────────────


def _extract_keywords(text: str, max_keywords: int = 8) -> list[str]:
    """从文本提取关键词（简单分词 + 停用词过滤）。

    中文按字符切分有意义片段，英文按单词。过滤常见停用词和短词。
    """
    if not text:
        return []

    # 停用词（中文 + 英文常见）
    stop_words = {
        "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一",
        "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没",
        "看", "好", "自己", "这", "那", "它", "他", "她",
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "shall", "can", "need", "to", "of",
        "in", "on", "at", "by", "for", "with", "about", "as", "into", "through",
    }

    keywords: list[str] = []

    # 提取英文单词（3+ 字符）
    en_words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text)
    for w in en_words:
        lw = w.lower()
        if lw not in stop_words and len(lw) >= 3:
            keywords.append(lw)

    # 提取 2+ 字符大写缩写（QQ / AI / GPU / CPU / USB 等，避免 3+ 字符规则漏掉）
    # 用 lookbehind/lookahead 让缩写前后允许中文（\b 在中英边界不生效）
    acronyms = re.findall(r"(?<![a-zA-Z])[A-Z]{2,6}(?![a-zA-Z])", text)
    for ac in acronyms:
        if ac.lower() not in stop_words:
            keywords.append(ac)

    # 提取中文片段（2-6 字符的有意义词组）
    # 简单策略：按非中文字符分割，保留 2-6 字的片段
    cn_segments = re.findall(r"[\u4e00-\u9fff]{2,6}", text)
    for seg in cn_segments:
        if seg not in stop_words:
            keywords.append(seg)

    # 去重 + 截断
    seen: set[str] = set()
    unique: list[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)

    return unique[:max_keywords]


def _keyword_overlap(kw1: list[str], kw2: list[str]) -> int:
    """计算两组关键词的重叠数。"""
    return len(set(kw1) & set(kw2))


# ─── MemoryStore ──────────────────────────────────────────


class MemoryStore:
    """记忆系统主类——管理情景记忆、知识库、用户偏好。

    线程安全：episodes 用追加写入（无竞争），knowledge/preferences 用文件锁。
    所有方法都是幂等的——文件不存在时返回空数据，不抛异常。
    """

    def __init__(
        self,
        mem_dir: Path | None = None,
        max_episodes: int | None = None,
        max_knowledge_patterns: int | None = None,
        hot_days: int | None = None,
        warm_days: int | None = None,
        archive_days: int | None = None,
    ) -> None:
        self._dir = mem_dir or _MEM_DIR
        self._episodes_file = self._dir / "episodes.jsonl"
        self._knowledge_file = self._dir / "knowledge.json"
        self._prefs_file = self._dir / "preferences.json"
        self._traps_file = self._dir / "traps.jsonl"  # v0.8.18: 踩坑记录
        self._archive_dir = self._dir / "archive"  # v0.8.16: L4 冷数据归档目录
        self._lock = threading.Lock()
        # v0.8.11: 容量可配置（None 则用模块常量默认值）
        self._max_episodes = max_episodes or _MAX_EPISODES
        self._max_knowledge_patterns = max_knowledge_patterns or _MAX_KNOWLEDGE_PATTERNS
        # v0.8.16: 分层加载参数（参考 OpenClaw L0-L4 设计）
        self._hot_days = hot_days if hot_days is not None else _HOT_DAYS
        self._warm_days = warm_days if warm_days is not None else _WARM_DAYS
        self._archive_days = archive_days if archive_days is not None else _ARCHIVE_DAYS
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """确保记忆目录存在。"""
        self._dir.mkdir(parents=True, exist_ok=True)

    # ─── 情景记忆 ──────────────────────────────────────

    def record_episode(self, episode: Episode) -> None:
        """记录一次交互情景到 episodes.jsonl。

        追加写入（高效），超过 _MAX_EPISODES 时自动裁剪旧数据。
        同时更新知识库和用户偏好。
        """
        with self._lock:
            try:
                with open(self._episodes_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(episode.to_dict(), ensure_ascii=False) + "\n")
            except OSError as e:
                log.warning(f"记录 episode 失败: {e}")
                return

        # 更新知识库和偏好
        self._update_knowledge(episode)
        self._update_preferences(episode)

        # 定期裁剪（每 100 条检查一次）
        if episode.timestamp % 100 == 0:
            self._prune_episodes()

    def query_episodes(
        self, keywords: list[str], limit: int = _MAX_QUERY_RESULTS, days: int | None = None
    ) -> list[Episode]:
        """按关键词检索相关情景记忆。

        v0.8.16: 加 days 参数，只扫描最近 N 天的 episodes（默认 L3 温数据范围）。
        简单策略：遍历 days 天内的 episode，按关键词重叠数排序，返回 top N。
        对于 1000 条以内的数据，线性扫描足够快（<10ms）。

        days=None: 用 self._warm_days（L3 温数据，默认 7 天）
        days=0: 不过滤（扫描全部，向后兼容）
        """
        if not keywords or not self._episodes_file.exists():
            return []

        # v0.8.16: 确定扫描范围（L3 温数据）
        scan_days = self._warm_days if days is None else days
        cutoff = time.time() - scan_days * 86400 if scan_days > 0 else 0

        results: list[tuple[int, float, Episode]] = []
        try:
            with open(self._episodes_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ep = Episode.from_dict(json.loads(line))
                    except (json.JSONDecodeError, TypeError):
                        continue

                    # v0.8.16: L3 时间过滤（days=0 时跳过过滤）
                    if cutoff > 0 and ep.timestamp < cutoff:
                        continue

                    ep_keywords = _extract_keywords(ep.user_input)
                    overlap = _keyword_overlap(keywords, ep_keywords)
                    if overlap > 0:
                        # 优先返回成功的 + 最近的
                        score = overlap * 10 + (1.0 if ep.success else 0.0) + ep.timestamp / 1e10
                        results.append((overlap, score, ep))
        except OSError:
            return []

        # 按分数排序，取 top N
        results.sort(key=lambda x: x[1], reverse=True)
        return [r[2] for r in results[:limit]]

    def get_recent_episodes(self, limit: int = 20) -> list[Episode]:
        """获取最近的 N 条情景记忆。"""
        if not self._episodes_file.exists():
            return []

        episodes: list[Episode] = []
        try:
            with open(self._episodes_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return []

        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                episodes.append(Episode.from_dict(json.loads(line)))
            except (json.JSONDecodeError, TypeError):
                continue

        return episodes

    # ─── v0.8.20: 按 session_id 聚合（历史对话调取）──────────

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        """v0.8.20: 按 session_id 聚合所有 episode，返回会话列表（最近优先）。

        返回 [{"session_id", "episode_count", "first_ts", "last_ts", "first_user_input"}, ...]
        session_id 为空的 episode 不纳入（v0.8.20 之前的旧数据）。
        """
        if not self._episodes_file.exists():
            return []
        sessions: dict[str, list[Episode]] = {}
        try:
            with open(self._episodes_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ep = Episode.from_dict(json.loads(line))
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if not ep.session_id:
                        continue
                    sessions.setdefault(ep.session_id, []).append(ep)
        except OSError:
            return []
        result = []
        for sid, eps in sessions.items():
            eps.sort(key=lambda e: e.timestamp)
            result.append({
                "session_id": sid,
                "episode_count": len(eps),
                "first_ts": eps[0].timestamp,
                "last_ts": eps[-1].timestamp,
                "first_user_input": eps[0].user_input[:80],
            })
        result.sort(key=lambda x: x["last_ts"], reverse=True)
        return result[:limit]

    def get_session_episodes(self, session_id: str, limit: int = 100) -> list[Episode]:
        """v0.8.20: 获取某个 session 的所有 episode（按时间正序）。"""
        if not self._episodes_file.exists() or not session_id:
            return []
        matched: list[Episode] = []
        try:
            with open(self._episodes_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ep = Episode.from_dict(json.loads(line))
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if ep.session_id == session_id:
                        matched.append(ep)
        except OSError:
            return []
        matched.sort(key=lambda e: e.timestamp)
        return matched[:limit]

    # ─── v0.8.16: 分层加载（L2 热 / L3 温 / L4 冷）──────────

    def _load_episodes_in_days(self, days: int) -> list[Episode]:
        """加载最近 N 天内的 episodes（L2/L3 通用方法）。

        按 timestamp 过滤，返回按时间正序排列的列表。
        days=0 表示不过滤（返回全部，等价于加载所有 episodes）。
        """
        if not self._episodes_file.exists():
            return []
        if days <= 0:
            # 不过滤：返回全部
            return self.get_recent_episodes(limit=self._max_episodes)

        cutoff = time.time() - days * 86400
        episodes: list[Episode] = []
        try:
            with open(self._episodes_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ep = Episode.from_dict(json.loads(line))
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if ep.timestamp >= cutoff:
                        episodes.append(ep)
        except OSError:
            return []
        return episodes

    def get_hot_episodes(self, days: int | None = None) -> list[Episode]:
        """L2 热数据：最近 hot_days 天的 episodes。

        每次注入 context 时用，确保注入的是"最近的"经验而非陈年旧事。
        实现"记忆衰减"——旧经验自动淡出，新经验优先。
        """
        return self._load_episodes_in_days(days if days is not None else self._hot_days)

    def get_warm_episodes(self, days: int | None = None) -> list[Episode]:
        """L3 温数据：最近 warm_days 天的 episodes。

        memory_recall 工具检索范围，比 L2 范围更大但仍有边界。
        """
        return self._load_episodes_in_days(days if days is not None else self._warm_days)

    def archive_old_episodes(self, days: int | None = None) -> dict[str, Any]:
        """L4 冷数据归档：把 N 天前的 episodes 按月分组移到 archive/ 目录。

        v0.8.17 P1-2 实现：参考 OpenClaw "每月末压缩上月日志到 memory/archive/YYYY-MM.md" 设计。
        - 按 episode 的 timestamp 月份分组归档（如 2026-06 的所有旧 episodes → archive/episodes_2026-06.jsonl）
        - 主 episodes.jsonl 只保留 N 天内的 episodes
        - 归档目录：self._archive_dir（默认 ~/.local/share/lihua/memory/archive/）
        - 已存在的月度归档文件会追加（不覆盖），便于多次归档累积

        返回：{
            "archived_count": 实际归档条数,
            "archivable_count": 可归档条数（=archived_count，全部归档）,
            "archive_dir": 归档目录路径,
            "archive_files": [归档文件名列表],
            "cutoff_timestamp": 截止时间戳,
            "remaining_count": 主文件剩余条数,
            "implemented": True
        }
        """
        import datetime as _dt

        days = days if days is not None else self._archive_days
        cutoff = time.time() - days * 86400
        archivable: list[tuple[Episode, str]] = []  # (episode, 原始 json 行)
        keep_lines: list[str] = []  # 保留的原始行

        if self._episodes_file.exists():
            try:
                with open(self._episodes_file, "r", encoding="utf-8") as f:
                    for line in f:
                        stripped = line.strip()
                        if not stripped:
                            continue
                        try:
                            ep = Episode.from_dict(json.loads(stripped))
                            if ep.timestamp < cutoff:
                                archivable.append((ep, stripped))
                            else:
                                keep_lines.append(stripped)
                        except (json.JSONDecodeError, TypeError):
                            # 无法解析的行保留在主文件（不丢数据）
                            keep_lines.append(stripped)
            except OSError as e:
                log.warning(f"读取 episodes 文件失败（归档中止）：{e}")
                return {
                    "archived_count": 0,
                    "archivable_count": 0,
                    "archive_dir": str(self._archive_dir),
                    "archive_files": [],
                    "cutoff_timestamp": cutoff,
                    "remaining_count": 0,
                    "implemented": True,
                    "error": str(e),
                }

        if not archivable:
            # 没有可归档的
            return {
                "archived_count": 0,
                "archivable_count": 0,
                "archive_dir": str(self._archive_dir),
                "archive_files": [],
                "cutoff_timestamp": cutoff,
                "remaining_count": len(keep_lines),
                "implemented": True,
            }

        # 按月份分组（基于 episode.timestamp）
        by_month: dict[str, list[str]] = {}  # "YYYY-MM" -> [json 行列表]
        for ep, line in archivable:
            try:
                dt = _dt.datetime.fromtimestamp(ep.timestamp)
                month_key = dt.strftime("%Y-%m")
            except (OSError, ValueError):
                month_key = "unknown"
            by_month.setdefault(month_key, []).append(line)

        # 确保归档目录存在
        try:
            self._archive_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log.warning(f"创建归档目录失败（归档中止）：{e}")
            return {
                "archived_count": 0,
                "archivable_count": len(archivable),
                "archive_dir": str(self._archive_dir),
                "archive_files": [],
                "cutoff_timestamp": cutoff,
                "remaining_count": len(keep_lines),
                "implemented": True,
                "error": f"创建归档目录失败：{e}",
            }

        # 写入月度归档文件（追加模式，便于多次归档累积）
        archive_files: list[str] = []
        for month_key, lines in by_month.items():
            archive_path = self._archive_dir / f"episodes_{month_key}.jsonl"
            try:
                with open(archive_path, "a", encoding="utf-8") as f:
                    for line in lines:
                        f.write(line + "\n")
                archive_files.append(archive_path.name)
                log.info(f"归档 {len(lines)} 条 episodes 到 {archive_path.name}")
            except OSError as e:
                log.warning(f"写入归档文件 {archive_path} 失败（这些数据保留在主文件）：{e}")
                # 失败的月份的 lines 放回 keep_lines（不丢数据）
                keep_lines.extend(lines)

        # 重写主 episodes.jsonl（只保留 keep_lines）
        try:
            tmp_path = self._episodes_file.with_suffix(".jsonl.tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                for line in keep_lines:
                    f.write(line + "\n")
            # 原子替换
            tmp_path.replace(self._episodes_file)
        except OSError as e:
            log.warning(f"重写主 episodes 文件失败（归档文件已写入，但主文件未清理）：{e}")
            return {
                "archived_count": len(archivable),
                "archivable_count": len(archivable),
                "archive_dir": str(self._archive_dir),
                "archive_files": archive_files,
                "cutoff_timestamp": cutoff,
                "remaining_count": -1,  # -1 表示主文件未清理
                "implemented": True,
                "warning": f"主文件重写失败：{e}",
            }

        return {
            "archived_count": len(archivable),
            "archivable_count": len(archivable),
            "archive_dir": str(self._archive_dir),
            "archive_files": archive_files,
            "cutoff_timestamp": cutoff,
            "remaining_count": len(keep_lines),
            "implemented": True,
        }

    # ─── 踩坑记录（v0.8.18）──────────────────────────────

    def add_trap(
        self,
        symptom: str,
        related_skills: list[str] | None = None,
        related_keywords: list[str] | None = None,
        root_cause: str = "",
        solution: str = "",
        status: str = "open",
    ) -> Trap:
        """v0.8.18: 追加一条踩坑记录。

        自动分配递增 id（T001, T002...）。
        超过 _MAX_TRAPS 时裁剪最旧的 open trap（fixed 的优先保留作历史教训）。
        """
        with self._lock:
            traps = self._load_traps_locked()
            # 分配新 id
            new_id = (max((t.id for t in traps), default=0) + 1) if traps else 1
            trap = Trap(
                id=new_id,
                timestamp=time.time(),
                symptom=symptom[:500],  # 截断防 JSON 爆炸
                root_cause=root_cause[:500],
                solution=solution[:500],
                status=status,
                related_skills=list(related_skills or []),
                related_keywords=list(related_keywords or [])[:10],
            )
            traps.append(trap)
            # 裁剪：超过上限时删最旧的 open trap（fixed 优先保留）
            if len(traps) > _MAX_TRAPS:
                open_traps = [t for t in traps if t.status == "open"]
                if open_traps:
                    oldest_open = min(open_traps, key=lambda t: t.timestamp)
                    traps.remove(oldest_open)
                else:
                    traps = traps[-_MAX_TRAPS:]  # 全是 fixed 时按时间保留最新
            self._save_traps_locked(traps)
        log.info(f"追加 trap T{trap.id:03d}: {symptom[:80]}")
        return trap

    def get_traps(self, status: str | None = None) -> list[Trap]:
        """获取所有 traps（可按 status 过滤）。"""
        traps = self._load_traps_locked()
        if status:
            traps = [t for t in traps if t.status == status]
        return traps

    def get_trap(self, trap_id: int) -> Trap | None:
        """按 id 获取单条 trap。"""
        for t in self._load_traps_locked():
            if t.id == trap_id:
                return t
        return None

    def update_trap(self, trap_id: int, updates: dict[str, Any]) -> tuple[bool, str, Trap | None]:
        """v0.8.18: 更新一条 trap（填根因 / 标记修复 / 累加出现次数）。

        返回 (是否成功, 消息, 更新后的 trap)。
        """
        with self._lock:
            traps = self._load_traps_locked()
            for t in traps:
                if t.id == trap_id:
                    if "symptom" in updates:
                        t.symptom = str(updates["symptom"])[:500]
                    if "root_cause" in updates:
                        t.root_cause = str(updates["root_cause"])[:500]
                    if "solution" in updates:
                        t.solution = str(updates["solution"])[:500]
                    if "status" in updates:
                        new_status = str(updates["status"])
                        if new_status in ("open", "fixed", "workaround"):
                            t.status = new_status
                            if new_status == "fixed" and t.fixed_at is None:
                                t.fixed_at = time.time()
                    if "fix_verified" in updates:
                        t.fix_verified = bool(updates["fix_verified"])
                    if "occurrence_count" in updates:
                        try:
                            t.occurrence_count = int(updates["occurrence_count"])
                        except (TypeError, ValueError):
                            pass
                    if "related_skills" in updates and isinstance(updates["related_skills"], list):
                        t.related_skills = [str(s) for s in updates["related_skills"]]
                    self._save_traps_locked(traps)
                    log.info(f"更新 trap T{trap_id:03d}: {updates}")
                    return True, f"trap T{trap_id:03d} 已更新", t
            return False, f"trap T{trap_id:03d} 不存在", None

    def search_traps(
        self, keywords: list[str], status: str | None = None, limit: int = 10
    ) -> list[Trap]:
        """v0.8.18: 按关键词搜索 traps（按相关度排序）。

        匹配 symptom / root_cause / solution / related_keywords 字段。
        status=None: 所有状态；status="open": 只搜未修复的坑。
        """
        if not keywords:
            traps = self.get_traps(status=status)
            return traps[:limit]
        traps = self._load_traps_locked()
        if status:
            traps = [t for t in traps if t.status == status]
        scored: list[tuple[int, float, Trap]] = []
        for t in traps:
            # 计算关键词命中数
            text = " ".join([
                t.symptom, t.root_cause, t.solution,
                " ".join(t.related_keywords), " ".join(t.related_skills),
            ]).lower()
            hits = sum(1 for kw in keywords if kw.lower() in text)
            if hits > 0:
                # 评分：命中数 × 10 + open 优先（open=2, workaround=1, fixed=0）
                status_bonus = {"open": 2.0, "workaround": 1.0, "fixed": 0.0}.get(t.status, 0.0)
                score = hits * 10 + status_bonus
                scored.append((hits, score, t))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [r[2] for r in scored[:limit]]

    def _load_traps_locked(self) -> list[Trap]:
        """加载所有 traps（需在锁内调用）。"""
        if not self._traps_file.exists():
            return []
        traps: list[Trap] = []
        try:
            with open(self._traps_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        traps.append(Trap.from_dict(json.loads(line)))
                    except (json.JSONDecodeError, TypeError) as e:
                        log.warning(f"解析 trap 行失败: {e}")
        except OSError as e:
            log.warning(f"读取 traps 文件失败: {e}")
        return traps

    def _save_traps_locked(self, traps: list[Trap]) -> None:
        """保存所有 traps（需在锁内调用）。"""
        try:
            tmp_path = self._traps_file.with_suffix(".jsonl.tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                for t in traps:
                    f.write(json.dumps(t.to_dict(), ensure_ascii=False) + "\n")
            tmp_path.replace(self._traps_file)
        except OSError as e:
            log.warning(f"保存 traps 文件失败: {e}")

    def _prune_episodes(self) -> None:
        """裁剪旧 episode，保留最近 _MAX_EPISODES 条。"""
        if not self._episodes_file.exists():
            return

        try:
            with open(self._episodes_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return

        if len(lines) <= self._max_episodes:
            return

        # 保留最后 _max_episodes 条
        kept = lines[-self._max_episodes:]
        try:
            with open(self._episodes_file, "w", encoding="utf-8") as f:
                f.writelines(kept)
            log.info(f"裁剪 episodes：{len(lines)} → {len(kept)}")
        except OSError as e:
            log.warning(f"裁剪 episodes 失败: {e}")

    # ─── 知识库 ────────────────────────────────────────

    def _load_knowledge(self) -> list[KnowledgePattern]:
        """加载知识库。"""
        if not self._knowledge_file.exists():
            return []
        try:
            with open(self._knowledge_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [KnowledgePattern.from_dict(p) for p in data.get("patterns", [])]
        except (OSError, json.JSONDecodeError, TypeError) as e:
            log.warning(f"加载知识库失败: {e}")
            return []

    def _save_knowledge(self, patterns: list[KnowledgePattern]) -> None:
        """保存知识库。"""
        try:
            with open(self._knowledge_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"patterns": [p.to_dict() for p in patterns], "version": 1},
                    f, ensure_ascii=False, indent=2,
                )
        except OSError as e:
            log.warning(f"保存知识库失败: {e}")

    def _update_knowledge(self, episode: Episode) -> None:
        """从一次交互中更新知识库。

        策略：
        1. 提取用户输入关键词
        2. 提取工具链
        3. 查找是否有匹配的 pattern（关键词重叠 >= 1 且工具链相同）
        4. 有则更新计数，无则创建新 pattern
        """
        keywords = _extract_keywords(episode.user_input)
        tool_chain = [tc.get("name", "") for tc in episode.tool_calls if tc.get("name")]

        if not keywords or not tool_chain:
            return

        with self._lock:
            patterns = self._load_knowledge()

            # 查找匹配的 pattern
            matched = None
            for p in patterns:
                if p.tool_chain == tool_chain and _keyword_overlap(p.keywords, keywords) > 0:
                    matched = p
                    break

            if matched:
                # 更新现有 pattern
                if episode.success:
                    matched.success_count += 1
                else:
                    matched.fail_count += 1
                matched.last_used = episode.timestamp
                # 合并关键词（去重）
                for kw in keywords:
                    if kw not in matched.keywords:
                        matched.keywords.append(kw)
            else:
                # 创建新 pattern
                matched = KnowledgePattern(
                    keywords=keywords,
                    tool_chain=tool_chain,
                    success_count=1 if episode.success else 0,
                    fail_count=0 if episode.success else 1,
                    last_used=episode.timestamp,
                    created_at=episode.timestamp,
                    example_episode_id=episode.id,
                )
                patterns.append(matched)

            # 裁剪：按使用次数排序，保留 top N
            if len(patterns) > self._max_knowledge_patterns:
                patterns.sort(key=lambda p: p.total_count, reverse=True)
                patterns = patterns[:self._max_knowledge_patterns]

            self._save_knowledge(patterns)

    def get_relevant_knowledge(self, problem: str, limit: int = 5) -> list[KnowledgePattern]:
        """检索与当前问题相关的知识。

        策略：按关键词重叠数 + 成功率排序。
        """
        if not problem:
            return []

        keywords = _extract_keywords(problem)
        if not keywords:
            return []

        patterns = self._load_knowledge()
        if not patterns:
            return []

        scored: list[tuple[float, KnowledgePattern]] = []
        for p in patterns:
            overlap = _keyword_overlap(keywords, p.keywords)
            if overlap > 0:
                # 分数 = 关键词重叠 * 10 + 成功率 * 5 + 使用次数 * 0.1
                score = overlap * 10 + p.success_rate * 5 + p.total_count * 0.1
                scored.append((score, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:limit]]

    # ─── 用户偏好 ──────────────────────────────────────

    def _load_preferences(self) -> UserPreferences:
        """加载用户偏好。"""
        if not self._prefs_file.exists():
            return UserPreferences()
        try:
            with open(self._prefs_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return UserPreferences.from_dict(data)
        except (OSError, json.JSONDecodeError, TypeError):
            return UserPreferences()

    def _save_preferences(self, prefs: UserPreferences) -> None:
        """保存用户偏好。"""
        try:
            with open(self._prefs_file, "w", encoding="utf-8") as f:
                json.dump(prefs.to_dict(), f, ensure_ascii=False, indent=2)
        except OSError as e:
            log.warning(f"保存用户偏好失败: {e}")

    def _update_preferences(self, episode: Episode) -> None:
        """从一次交互中更新用户偏好。"""
        with self._lock:
            prefs = self._load_preferences()

            # 更新工具使用统计
            for tc in episode.tool_calls:
                name = tc.get("name", "")
                if name:
                    prefs.tool_usage[name] = prefs.tool_usage.get(name, 0) + 1

            # 更新关键词统计
            keywords = _extract_keywords(episode.user_input, max_keywords=5)
            for kw in keywords:
                prefs.common_keywords[kw] = prefs.common_keywords.get(kw, 0) + 1

            # 更新会话统计
            if prefs.first_session == 0:
                prefs.first_session = episode.timestamp
            prefs.last_session = episode.timestamp
            prefs.total_episodes += 1

            # 更新成功率（滑动平均）
            alpha = 0.1  # 学习率
            current = 1.0 if episode.success else 0.0
            prefs.success_rate = prefs.success_rate * (1 - alpha) + current * alpha

            self._save_preferences(prefs)

    def get_preferences(self) -> UserPreferences:
        """获取用户偏好。"""
        return self._load_preferences()

    # ─── 上下文注入 ────────────────────────────────────

    def get_context_for_prompt(self, user_input: str) -> str:
        """为 system prompt 生成记忆上下文。

        v0.8.16: 分层加载优化
        - L1 长期：knowledge.json + preferences.json（每次必加载）
        - L2 热：最近 hot_days 天 episodes（注入最近案例）
        - L3 温：仅 memory_recall 工具调用时扫描（这里不用）

        注入内容：
        1. 相关知识（之前怎么解决类似问题的）—— L1
        2. 用户偏好（常用工具、成功率）—— L1
        3. 最近的成功案例 —— L2（不是全部 episodes）

        返回空字符串表示无可用记忆。
        """
        parts: list[str] = []

        # L1: 相关知识
        knowledge = self.get_relevant_knowledge(user_input, limit=3)
        if knowledge:
            parts.append("## 历史经验（从过去交互中学到的）")
            for p in knowledge:
                tools_str = " → ".join(p.tool_chain)
                parts.append(
                    f"- 类似问题（成功率 {p.success_rate:.0%}，用过 {p.total_count} 次）"
                    f"：{tools_str}"
                )
            parts.append("")

        # L2: 最近成功案例（v0.8.16: 只扫最近 hot_days 天，不扫全部）
        keywords = _extract_keywords(user_input)
        if keywords:
            # v0.8.16: 用 get_hot_episodes 限制范围，再按关键词过滤
            hot_episodes = self.get_hot_episodes()
            if hot_episodes:
                # 按 keywords 过滤 + 排序，取 top 2
                scored: list[tuple[int, float, Episode]] = []
                for ep in hot_episodes:
                    ep_kw = _extract_keywords(ep.user_input)
                    overlap = _keyword_overlap(keywords, ep_kw)
                    if overlap > 0:
                        score = overlap * 10 + (1.0 if ep.success else 0.0)
                        scored.append((overlap, score, ep))
                scored.sort(key=lambda x: x[1], reverse=True)
                recent_cases = [r[2] for r in scored[:2]]
                if recent_cases:
                    parts.append("## 最近的相关案例")
                    for ep in recent_cases:
                        status = "✓" if ep.success else "✗"
                        tools = ", ".join(tc.get("name", "?") for tc in ep.tool_calls)
                        parts.append(f"- {status} \"{ep.user_input[:60]}\" → {tools}")
                    parts.append("")

        # L1: 用户偏好（只在有足够数据时显示）
        prefs = self.get_preferences()
        if prefs.total_episodes >= 5:
            top_tools = sorted(prefs.tool_usage.items(), key=lambda x: x[1], reverse=True)[:5]
            if top_tools:
                tools_str = ", ".join(f"{name}({count})" for name, count in top_tools)
                parts.append(f"## 用户画像（{prefs.total_episodes} 次交互，成功率 {prefs.success_rate:.0%}）")
                parts.append(f"常用工具: {tools_str}")
                parts.append("")

        # v0.8.18: 注入 open traps（未修复的坑，让 LLM 知道"这些坑还没填"）
        # 按关键词匹配相关 open traps，最多 3 条（防 prompt 过长）
        open_traps = self.get_traps(status="open")
        if open_traps and keywords:
            matched: list[tuple[int, Trap]] = []
            for t in open_traps:
                text = " ".join([t.symptom, " ".join(t.related_keywords), " ".join(t.related_skills)]).lower()
                hits = sum(1 for kw in keywords if kw.lower() in text)
                if hits > 0:
                    matched.append((hits, t))
            matched.sort(key=lambda x: x[0], reverse=True)
            if matched:
                parts.append("## ⚠️ 已知踩坑（open traps，遇到要小心）")
                for _, t in matched[:3]:
                    skills_str = f" [{', '.join(t.related_skills)}]" if t.related_skills else ""
                    parts.append(
                        f"- T{t.id:03d}{skills_str}: {t.symptom[:100]}"
                        + (f"（出现 {t.occurrence_count} 次）" if t.occurrence_count > 1 else "")
                    )
                parts.append("")

        return "\n".join(parts) if parts else ""

    # ─── 管理 ──────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """获取记忆系统统计信息。

        v0.8.16: 加分层统计（L2 热 / L3 温 / L4 冷）。
        """
        episodes = self.get_recent_episodes(limit=_MAX_EPISODES)
        patterns = self._load_knowledge()
        prefs = self._load_preferences()

        # v0.8.16: 分层统计
        hot_eps = self.get_hot_episodes()
        warm_eps = self.get_warm_episodes()
        archive_info = self.archive_old_episodes()

        # v0.8.18: 踩坑记录统计
        all_traps = self.get_traps()
        open_traps = [t for t in all_traps if t.status == "open"]
        fixed_traps = [t for t in all_traps if t.status == "fixed"]

        return {
            "episodes_count": len(episodes),
            "knowledge_patterns": len(patterns),
            "total_interactions": prefs.total_episodes,
            "success_rate": round(prefs.success_rate, 3),
            "first_session": prefs.first_session,
            "last_session": prefs.last_session,
            "top_tools": dict(
                sorted(prefs.tool_usage.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
            "top_keywords": dict(
                sorted(prefs.common_keywords.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
            # v0.8.16: 分层加载统计
            "layers": {
                "L2_hot": {
                    "days": self._hot_days,
                    "episodes_count": len(hot_eps),
                },
                "L3_warm": {
                    "days": self._warm_days,
                    "episodes_count": len(warm_eps),
                },
                "L4_cold": {
                    "days": self._archive_days,
                    "archivable_count": archive_info["archivable_count"],
                    "archive_dir": archive_info["archive_dir"],
                    "archive_implemented": archive_info["implemented"],
                },
            },
            # v0.8.18: 踩坑记录统计
            "traps": {
                "total": len(all_traps),
                "open": len(open_traps),
                "fixed": len(fixed_traps),
                "workaround": len(all_traps) - len(open_traps) - len(fixed_traps),
            },
        }

    def clear_all(self) -> None:
        """清空所有记忆（用户请求时用）。"""
        with self._lock:
            for f in [self._episodes_file, self._knowledge_file, self._prefs_file, self._traps_file]:
                try:
                    if f.exists():
                        f.unlink()
                except OSError as e:
                    log.warning(f"删除 {f} 失败: {e}")
        log.info("所有记忆已清空")


# ─── 全局实例 ─────────────────────────────────────────────

_global_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    """获取全局 MemoryStore 单例。

    v0.8.16: 第一次创建时从 Config 读取分层参数（hot_days/warm_days/archive_days）。
    """
    global _global_store
    if _global_store is None:
        # v0.8.16: 从 config.toml 读取分层配置
        try:
            from lihua.config import Config
            cfg = Config.load()
            _global_store = MemoryStore(
                hot_days=cfg.memory.hot_days,
                warm_days=cfg.memory.warm_days,
                archive_days=cfg.memory.archive_days,
                max_episodes=cfg.memory.max_episodes,
                max_knowledge_patterns=cfg.memory.max_knowledge_patterns,
            )
        except Exception:
            # config 加载失败时用默认值（保持向后兼容）
            _global_store = MemoryStore()
    return _global_store
