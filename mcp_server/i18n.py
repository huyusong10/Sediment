from __future__ import annotations

import copy
from typing import Any

from mcp_server.settings import load_settings

DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = {"en", "zh"}

_MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "tool.knowledge_list.description": (
            "Return all knowledge document names (without .md suffix). "
            "Includes entries, placeholders, and index files. "
            "Useful as the first step for agentic exploration."
        ),
        "tool.knowledge_read.description": (
            "Read full Markdown for a knowledge document by filename (without .md suffix). "
            "Searches entries/, placeholders/, root index, then indexes/. "
            "Returns an error string instead of raising exceptions when not found."
        ),
        "tool.knowledge_read.filename": "Entry or index name without .md suffix",
        "tool.knowledge_ask.description": (
            "Ask a natural-language question against the KB via explore runtime. "
            "Response includes answer and sources, with confidence, exploration_summary, "
            "gaps, and contradictions."
        ),
        "tool.knowledge_ask.question": "Natural-language question",
        "tool.knowledge_submit_text.description": (
            "Submit a text concept, lesson, or feedback item into the review buffer. "
            "This does not write directly into the canonical knowledge base."
        ),
        "tool.knowledge_submit_document.description": (
            "Submit an uploaded document into the review buffer using base64 content. "
            "The service extracts text and stores the submission for committer review."
        ),
        "tool.knowledge_health_report.description": (
            "Return the current health summary and structured issue queue for the knowledge base."
        ),
        "tool.knowledge_platform_status.description": (
            "Return the platform status payload shared by the CLI status command "
            "and admin dashboard."
        ),
        "tool.knowledge_submission_queue.description": (
            "List recent buffered submissions and their workflow status."
        ),
        "tool.knowledge_job_status.description": (
            "Inspect the status and result payload for an ingest or tidy job."
        ),
        "tool.knowledge_tidy_request.description": (
            "Queue a manual tidy job for a KB target and return the created job record."
        ),
        "tool.knowledge_review_decide.description": (
            "Approve or reject a pending review for an ingest/tidy job."
        ),
    },
    "zh": {
        "tool.knowledge_list.description": (
            "返回知识库中所有知识文档的名称列表（不含 .md 后缀）。"
            "包含 entries/、placeholders/ 以及 index 文件。"
            "供调用方 Agent 推理相关文件名，是自主探索路径的入口。"
        ),
        "tool.knowledge_read.description": (
            "读取指定知识文档的完整 Markdown 内容。"
            "filename 不含 .md 后缀。"
            "自动在 entries/、placeholders/、root index 和 indexes/ 中查找。"
            "如果文件不存在，返回错误信息而非抛出异常。"
        ),
        "tool.knowledge_read.filename": "条目或索引名称，不含 .md 后缀",
        "tool.knowledge_ask.description": (
            "针对知识库提出自然语言问题，由内部 explore runtime 返回综合答案。"
            "返回格式至少包含 answer 和 sources，并附带 confidence、"
            "exploration_summary、gaps、contradictions。"
            "适合模糊语义问题，无法提前确定关键词时使用。"
        ),
        "tool.knowledge_ask.question": "自然语言问题",
        "tool.knowledge_submit_text.description": (
            "把纯文字概念、经验或意见提交到审核缓冲区。"
            "该操作不会直接写入正式知识库。"
        ),
        "tool.knowledge_submit_document.description": (
            "通过 base64 文档内容把上传文件提交到审核缓冲区。"
            "服务端会抽取文本并等待 committer 审核。"
        ),
        "tool.knowledge_health_report.description": (
            "返回当前知识库的 health 摘要和结构化问题队列。"
        ),
        "tool.knowledge_platform_status.description": (
            "返回与 CLI `sediment status` 和 Admin 面板共用的平台状态载荷。"
        ),
        "tool.knowledge_submission_queue.description": (
            "列出最近的缓冲区提交及其工作流状态。"
        ),
        "tool.knowledge_job_status.description": (
            "查看 ingest 或 tidy 任务的状态和结果载荷。"
        ),
        "tool.knowledge_tidy_request.description": (
            "为指定知识目标创建一个手工 tidy 任务，并返回新建 job。"
        ),
        "tool.knowledge_review_decide.description": (
            "批准或拒绝某个 ingest/tidy 待审结果。"
        ),
    },
}

_QUERY_LANGUAGE_RULES: dict[str, dict[str, Any]] = {
    "zh": {
        "stop_words": {
            "什么",
            "哪些",
            "多少",
            "几种",
            "为什么",
            "如何",
            "怎么",
            "怎样",
            "可以",
            "应该",
            "需要",
            "里面",
            "中",
            "里",
            "从",
            "看",
            "和",
            "与",
            "及",
            "是",
            "的",
            "了",
            "在",
            "由",
            "把",
            "将",
            "对",
            "有",
            "一个",
            "这个",
            "那个",
            "这些",
            "那些",
            "定义",
            "作用",
            "流程",
            "步骤",
            "逻辑",
            "问题",
            "系统",
            "知识",
            "文档",
        },
        "token_splitter": r"[和与及、/]",
        "focus_markers": {
            "definition": ("什么是", "定义", "含义"),
            "scope": ("适用于什么场景", "适用场景", "范围", "边界", "前提"),
            "why": ("为什么", "原因", "为何"),
            "when": ("什么时候", "何时"),
            "risk": ("风险", "坑", "误区", "避免"),
            "comparison": ("区别", "差异", "对比"),
            "guidance": ("如何", "怎么", "怎样"),
        },
        "section_aliases": {
            "来源": "Source",
            "相关": "Related",
            "上下文": "Scope",
            "触发": "Trigger",
            "风险": "Risks",
        },
        "sentence_markers": (
            "必须",
            "应该",
            "需要",
            "优先",
            "避免",
            "防止",
            "不要",
            "不能",
            "导致",
            "如果",
            "当",
            "先",
            "再",
            "前",
            "后",
            "时",
            "须",
        ),
    },
    "en": {
        "stop_words": {
            "what",
            "which",
            "how",
            "why",
            "when",
            "where",
            "who",
            "is",
            "are",
            "the",
            "a",
            "an",
            "of",
            "to",
            "for",
            "in",
            "on",
            "and",
            "or",
            "with",
            "about",
            "from",
            "by",
            "does",
            "do",
            "can",
            "should",
            "need",
            "definition",
            "system",
            "knowledge",
            "document",
        },
        "token_splitter": r"[,\s/]+",
        "focus_markers": {
            "definition": ("what is", "definition", "meaning"),
            "scope": ("scope", "boundary", "applies to"),
            "why": ("why", "reason"),
            "when": ("when",),
            "risk": ("risk", "pitfall", "avoid"),
            "comparison": ("compare", "difference", "versus", "vs"),
            "guidance": ("how", "steps"),
        },
        "section_aliases": {},
        "sentence_markers": (),
    },
}


def get_locale() -> str:
    preferred = str(load_settings().get("locale", DEFAULT_LOCALE)).strip().lower()
    if preferred in SUPPORTED_LOCALES:
        return preferred
    return DEFAULT_LOCALE


def tr(key: str, default: str = "") -> str:
    locale = get_locale()
    table = _MESSAGES.get(locale, {})
    if key in table:
        return table[key]
    return _MESSAGES[DEFAULT_LOCALE].get(key, default)


def query_language_rules() -> dict[str, dict[str, Any]]:
    return copy.deepcopy(_QUERY_LANGUAGE_RULES)


def kb_localized_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for rule in _QUERY_LANGUAGE_RULES.values():
        aliases.update(rule.get("section_aliases", {}))
    return aliases


def kb_sentence_markers() -> tuple[str, ...]:
    merged = []
    for rule in _QUERY_LANGUAGE_RULES.values():
        for marker in rule.get("sentence_markers", ()):
            if marker not in merged:
                merged.append(marker)
    return tuple(merged)
