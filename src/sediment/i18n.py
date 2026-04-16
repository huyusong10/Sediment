from __future__ import annotations

import copy
from typing import Any

from sediment.settings import load_settings

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
            "definition": ("什么是", "是什么", "是什么意思", "指什么", "定义", "含义"),
            "scope": ("适用于什么场景", "适用场景", "范围", "边界", "前提"),
            "why": ("为什么", "原因", "为何"),
            "when": ("什么时候", "何时"),
            "risk": ("风险", "坑", "误区", "避免"),
            "comparison": ("区别", "差异", "对比", "关系", "关联", "联系", "异同"),
            "guidance": ("如何", "怎么", "怎样", "步骤", "准备", "协作", "配合", "需要"),
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

_KB_QUERY_HEURISTIC_RULES: dict[str, dict[str, Any]] = {
    "zh": {
        "low_signal_entry_names": (
            "技术",
            "系统",
            "指标",
            "调查",
            "报告",
            "事件",
            "流程",
            "步骤",
            "内容",
            "定义",
            "规则",
            "配置",
            "接口",
            "能力",
            "现状",
            "机制",
        ),
        "low_signal_summary_markers": (
            "一种模式或状态",
            "正式流程中的一个阶段",
            "用于表达当前处理阶段",
            "相关系统",
            "名称 定义 目标值 告警阈值",
        ),
        "low_signal_name_prefixes": (
            "当前",
            "核心",
            "默认",
            "通知",
            "负责",
            "注册",
            "核对",
            "本人",
            "制定",
            "系统设计的",
        ),
        "low_signal_name_suffixes": ("检测", "执行", "记录", "归档", "通知"),
        "low_signal_name_contains_markers": (
            "中的",
            "里的",
            "时",
            "后",
            "前",
            "通知",
            "负责",
            "使用",
            "全部在",
            "加强了",
        ),
        "low_signal_name_terminal_suffixes": ("内容", "现状", "情况", "方式", "机制"),
        "overloaded_complete_markers": ("完整生命周期",),
        "overloaded_wrapper_markers": ("故障类型", "管理"),
        "question_prefixes": (
            "什么是",
            "什么叫",
            "请问",
            "为什么",
            "从",
            "根据",
            "结合",
            "综合",
            "如果",
            "基于",
            "当前",
            "一个",
            "请",
        ),
        "question_suffix_markers": (
            "是什么",
            "是什么意思",
            "有哪些",
            "多少",
            "的范围",
            "的区间",
            "的安全运行区间",
            "的部署策略",
            "的路由策略",
            "的触发条件",
            "分别指什么",
            "负责什么",
            "作用是什么",
            "衡量什么",
            "如何判断",
            "需要经历哪些阶段",
            "需要哪些步骤",
            "需要完成哪些准备",
            "应该采取哪些应对策略",
            "可能是什么问题",
            "可能遇到哪些类型的故障",
            "是否",
            "吗",
        ),
        "queryable_term_suffixes": (
            "节点的",
            "节点",
            "数据",
            "技术",
            "团队",
            "指标",
            "质量",
            "级别",
        ),
        "surface_fillers": ("完整", "当前", "默认", "整体", "全系统", "全局"),
        "projection_prefixes": ("管理", "完整", "当前", "默认", "整体", "全系统", "全局"),
        "coordination_splitters": ("和", "与", "及", "以及", "、", "从", "且", "并且"),
        "action_split_markers": (
            "建议增加",
            "建议扩展",
            "建议新增",
            "建议加装",
            "可能遇到",
            "可能出现",
            "增加",
            "新增",
            "加装",
            "扩展",
            "部署",
            "启用",
            "停用",
            "避免",
            "确认",
            "执行",
            "完成",
            "恢复",
            "触发",
        ),
        "temporal_markers": ("目前", "现在"),
        "possessive_markers": ("的",),
        "possessive_split_markers": ("的",),
        "structured_surface_groups": {
            "message_type": {
                "surface_terms": ("消息类型", "报文类型"),
                "question_terms": ("消息类型", "报文类型"),
            },
            "routing_strategy": {
                "surface_terms": ("路由策略", "路由规则"),
                "question_terms": ("路由策略", "路由规则"),
            },
            "fault_type": {
                "surface_terms": ("故障类型", "异常类", "类型的故障"),
                "question_terms": ("故障类型", "异常类", "类型的故障"),
            },
            "design_philosophy": {
                "surface_terms": ("设计哲学",),
                "question_terms": ("设计哲学",),
            },
            "lifecycle": {
                "surface_terms": ("生命周期",),
                "question_terms": ("生命周期",),
            },
            "monitoring_point": {
                "surface_terms": ("监测点", "监控点"),
                "question_terms": ("监测点", "监控点"),
            },
        },
        "artifact_wrapper_suffixes": ("路由表", "报文定义", "监测点配置"),
    },
    "en": {
        "low_signal_entry_names": (
            "technology",
            "system",
            "metric",
            "metrics",
            "investigation",
            "report",
            "incident",
            "process",
            "step",
            "steps",
            "content",
            "definition",
            "rule",
            "rules",
            "configuration",
            "config",
            "interface",
            "capability",
            "status",
            "mechanism",
        ),
        "low_signal_summary_markers": (
            "a generic mode or state",
            "a stage in a formal process",
            "used to describe the current processing stage",
            "related system",
            "name definition target value alert threshold",
        ),
        "low_signal_name_prefixes": (
            "current",
            "core",
            "default",
            "notification",
            "responsible",
            "register",
            "verify",
            "self",
            "define",
            "system design",
        ),
        "low_signal_name_suffixes": (
            "detection",
            "execution",
            "record",
            "archive",
            "notification",
        ),
        "low_signal_name_contains_markers": (
            " during ",
            " after ",
            " before ",
            " responsible ",
            " used ",
            " all in ",
            " strengthened ",
        ),
        "low_signal_name_terminal_suffixes": (
            "content",
            "status",
            "situation",
            "method",
            "mechanism",
        ),
        "overloaded_complete_markers": ("complete lifecycle",),
        "overloaded_wrapper_markers": ("fault type", "management"),
        "question_prefixes": (
            "what is",
            "what does",
            "why",
            "from",
            "according to",
            "based on",
            "combined with",
            "if",
            "currently",
            "please",
        ),
        "question_suffix_markers": (
            "what is",
            "what does it mean",
            "what are",
            "how many",
            "range",
            "interval",
            "safe operating interval",
            "deployment strategy",
            "routing strategy",
            "trigger condition",
            "trigger conditions",
            "responsible for",
            "used for",
            "measures what",
            "how to judge",
            "what stages",
            "what steps",
            "what preparation",
            "what response strategies",
            "what problem",
            "what kinds of failures",
            "whether",
        ),
        "queryable_term_suffixes": (
            " node",
            " nodes",
            " data",
            " technology",
            " team",
            " metric",
            " metrics",
            " quality",
            " level",
        ),
        "surface_fillers": ("complete", "current", "default", "overall", "global", "system-wide"),
        "projection_prefixes": (
            "management",
            "complete",
            "current",
            "default",
            "overall",
            "global",
            "system-wide",
        ),
        "coordination_splitters": (" and ", " & ", " plus ", " with "),
        "action_split_markers": (
            " add ",
            " extend ",
            " deploy ",
            " enable ",
            " disable ",
            " avoid ",
            " confirm ",
            " execute ",
            " complete ",
            " restore ",
            " trigger ",
        ),
        "temporal_markers": ("currently", "now"),
        "possessive_markers": (),
        "possessive_split_markers": (),
        "structured_surface_groups": {
            "message_type": {
                "surface_terms": ("message type", "message types"),
                "question_terms": ("message type", "message types"),
            },
            "routing_strategy": {
                "surface_terms": ("routing strategy", "routing strategies", "route strategy", "route strategies"),
                "question_terms": ("routing strategy", "routing strategies", "route strategy", "route strategies"),
            },
            "fault_type": {
                "surface_terms": ("fault type", "fault types", "failure type", "failure types"),
                "question_terms": ("fault type", "fault types", "failure type", "failure types"),
            },
            "design_philosophy": {
                "surface_terms": ("design philosophy", "system philosophy"),
                "question_terms": ("design philosophy", "system philosophy"),
            },
            "lifecycle": {
                "surface_terms": ("lifecycle", "life cycle"),
                "question_terms": ("lifecycle", "life cycle"),
            },
            "monitoring_point": {
                "surface_terms": ("monitoring point", "monitoring points", "monitor point", "monitor points"),
                "question_terms": ("monitoring point", "monitoring points", "monitor point", "monitor points"),
            },
        },
        "artifact_wrapper_suffixes": ("route table", "message definition", "monitoring config"),
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


def kb_query_heuristic_rules() -> dict[str, Any]:
    tuple_keys = (
        "low_signal_entry_names",
        "low_signal_summary_markers",
        "low_signal_name_prefixes",
        "low_signal_name_suffixes",
        "low_signal_name_contains_markers",
        "low_signal_name_terminal_suffixes",
        "overloaded_complete_markers",
        "overloaded_wrapper_markers",
        "question_prefixes",
        "question_suffix_markers",
        "queryable_term_suffixes",
        "surface_fillers",
        "projection_prefixes",
        "coordination_splitters",
        "action_split_markers",
        "temporal_markers",
        "possessive_markers",
        "possessive_split_markers",
        "artifact_wrapper_suffixes",
    )
    merged: dict[str, list[str]] = {key: [] for key in tuple_keys}
    structured_groups: dict[str, dict[str, list[str]]] = {}

    for rule in _KB_QUERY_HEURISTIC_RULES.values():
        for key in tuple_keys:
            for item in rule.get(key, ()):
                if item not in merged[key]:
                    merged[key].append(item)
        for group_name, group in rule.get("structured_surface_groups", {}).items():
            bucket = structured_groups.setdefault(
                group_name,
                {"surface_terms": [], "question_terms": []},
            )
            for key in ("surface_terms", "question_terms"):
                for item in group.get(key, ()):
                    if item not in bucket[key]:
                        bucket[key].append(item)

    return {
        **{key: tuple(values) for key, values in merged.items()},
        "structured_surface_groups": {
            name: {
                "surface_terms": tuple(group["surface_terms"]),
                "question_terms": tuple(group["question_terms"]),
            }
            for name, group in structured_groups.items()
        },
    }
