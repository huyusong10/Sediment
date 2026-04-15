# ruff: noqa: E501
from __future__ import annotations

import json
from functools import lru_cache
from html import escape
from urllib.parse import quote

from sediment.package_data import read_asset_text, render_asset_template


@lru_cache(maxsize=1)
def _logo_mark_svg() -> str:
    return read_asset_text("logo-mark.svg").strip()


@lru_cache(maxsize=1)
def _logo_svg() -> str:
    return read_asset_text("logo.svg").strip()


@lru_cache(maxsize=1)
def _logo_mark_data_uri() -> str:
    return f"data:image/svg+xml;utf8,{quote(_logo_mark_svg())}"


def _logo_inline(class_name: str = "brand-lockup") -> str:
    return _logo_svg().replace("<svg ", f'<svg class="{class_name}" aria-hidden="true" ')


def _normalize_locale(locale: str | None) -> str:
    return "zh" if str(locale or "").strip().lower().startswith("zh") else "en"


def _html_lang(locale: str) -> str:
    return "zh-CN" if _normalize_locale(locale) == "zh" else "en"


def _localized_path(path: str, locale: str) -> str:
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}lang={_normalize_locale(locale)}"


def _nav_link(
    label: str,
    href: str,
    *,
    primary: bool = False,
    variant: str = "nav",
    new_tab: bool = False,
) -> str:
    variant_class = {
        "nav": "nav-link",
        "action": "action-link",
        "utility": "utility-action",
        "download": "download-action",
    }.get(variant, "nav-link")
    classes = ["button", variant_class]
    if primary:
        classes.append("primary")
    extra_attrs = ' target="_blank" rel="noopener noreferrer"' if new_tab else ""
    return (
        f'<a class="{" ".join(classes)}" href="{escape(href, quote=True)}"{extra_attrs}>'
        f"{escape(label)}</a>"
    )


def _render_html_template(name: str, **replacements: str) -> str:
    return render_asset_template(name, replacements)


def _asset_url(name: str) -> str:
    return f"/ui-assets/{name}"


def _json_script_payload(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")


def _document_title(*parts: str) -> str:
    return " | ".join(part for part in parts if str(part).strip())


def _portal_page_title(page: str, *, is_zh: bool, entry_name: str = "") -> str:
    return {
        "home": "知识库概览" if is_zh else "Knowledge base overview",
        "search": "全文搜索" if is_zh else "Full-text search",
        "entry": entry_name or ("条目详情" if is_zh else "Entry detail"),
        "submit": "提交缓冲区" if is_zh else "Buffered submission",
        "tutorial": "接入教程" if is_zh else "Integration guide",
    }[page]


def _admin_page_title(section: str, *, is_zh: bool) -> str:
    return {
        "overview": "总览" if is_zh else "Overview",
        "kb": "KB Management 知识库管理" if is_zh else "Knowledge base management",
        "files": "Files 文件管理" if is_zh else "File management",
        "reviews": "评审" if is_zh else "Reviews",
        "users": "用户" if is_zh else "Users",
        "system": "设置" if is_zh else "Settings",
    }[section]


def _tutorial_skill_slug() -> str:
    return "mcp-explore"


def _tutorial_skill_filename() -> str:
    return "sediment-mcp-explore-SKILL.md"


def _mono(text: str) -> str:
    return f'<span class="inline-mono">{escape(text)}</span>'


def _tutorial_tip(summary_html: str, detail_html: str, *, locale: str, testid: str = "") -> str:
    label = "更多说明" if _normalize_locale(locale) == "zh" else "More details"
    data_attr = f' data-testid="{escape(testid, quote=True)}"' if testid else ""
    return "\n".join(
        [
            f'<div class="compact-note"{data_attr}>',
            f'  <span class="compact-note-text">{summary_html}</span>',
            '  <span class="tip-anchor">',
            f'    <button class="tip-trigger" type="button" aria-label="{escape(label, quote=True)}">i</button>',
            f'    <span class="tip-panel" role="note">{detail_html}</span>',
            "  </span>",
            "</div>",
        ]
    )


@lru_cache(maxsize=2)
def _tutorial_mcp_tool_cards(locale: str) -> str:
    active_locale = _normalize_locale(locale)
    is_zh = active_locale == "zh"
    cards = [
        {
            "title": "knowledge_list",
            "badge": "候选集合" if is_zh else "Candidate set",
            "summary_html": (
                f"先用 {_mono('knowledge_list')} 缩小候选集合。"
                if is_zh
                else f"Use {_mono('knowledge_list')} to narrow the candidate set first."
            ),
            "detail_html": (
                "它最适合做别名比对、范围收敛和第一次分流。不要一上来就穷举读取全文，否则上下文会很快膨胀。"
                if is_zh
                else "Use it for alias matching, scope narrowing, and the first split of likely entries. Avoid reading the entire KB up front or you will waste context."
            ),
            "call": "knowledge_list()",
        },
        {
            "title": "knowledge_read",
            "badge": "原文读取" if is_zh else "Entry read",
            "summary_html": (
                f"用 {_mono('knowledge_read')} 读取关键条目原文。"
                if is_zh
                else f"Use {_mono('knowledge_read')} to inspect the key entries in full text."
            ),
            "detail_html": (
                "通常连续读取 1 到 5 个最相关条目即可。如果 Related、别名或 Scope 指向新的关键概念，再补 1 到 2 跳，不要无限扩散。"
                if is_zh
                else "Usually 1-5 closely related entries are enough. Add only 1-2 more hops when Related, aliases, or Scope point to another key concept."
            ),
            "call": (
                'knowledge_read(filename="热备份")'
                if is_zh
                else 'knowledge_read(filename="hot-backup")'
            ),
        },
        {
            "title": "knowledge_ask",
            "badge": "快速问答" if is_zh else "Fast answer",
            "summary_html": (
                f"{_mono('knowledge_ask')} 直接返回服务端综合结果。"
                if is_zh
                else f"{_mono('knowledge_ask')} returns a server-side synthesized answer directly."
            ),
            "detail_html": (
                "适合想快速接入、统一服务端行为，或只需要一个高层答案的场景。若你想自己控制证据链或降低远端往返依赖，就只暴露 knowledge_list / knowledge_read。"
                if is_zh
                else "Use it when you want the fastest integration path, a service-owned reasoning loop, or a quick top-level answer. If you want local white-box control, expose only knowledge_list and knowledge_read instead."
            ),
            "call": (
                'knowledge_ask(question="热备份的前置条件是什么？")'
                if is_zh
                else 'knowledge_ask(question="What are the preconditions for hot backup?")'
            ),
        },
    ]
    return "\n".join(
        "\n".join(
            [
                '<article class="card tutorial-tool-card">',
                '  <div class="row spread tutorial-card-heading">',
                f"    <strong>{escape(card['title'])}</strong>",
                f'    <span class="tag">{escape(card["badge"])}</span>',
                "  </div>",
                "  "
                + _tutorial_tip(
                    card["summary_html"],
                    card["detail_html"],
                    locale=active_locale,
                    testid=f"tutorial-tool-{card['title']}",
                ),
                f'  <div class="subtle mono">{escape(card["call"])}</div>',
                "</article>",
            ]
        )
        for card in cards
    )


@lru_cache(maxsize=2)
def _tutorial_decision_cards(locale: str) -> str:
    active_locale = _normalize_locale(locale)
    is_zh = active_locale == "zh"
    cards = [
        {
            "title": "选 MCP" if is_zh else "Choose MCP",
            "summary_html": (
                f"服务端直接用 {_mono('knowledge_ask')} 给答案。"
                if is_zh
                else f"Let the service answer directly with {_mono('knowledge_ask')}."
            ),
            "detail_html": (
                "优点是接入简单、结果直达，而且不会把整段探索过程塞进你本地 Agent 的上下文。代价是会占用服务端 Agent 算力，自由度也更低。"
                if is_zh
                else "This path is simple to integrate, returns an answer directly, and avoids pushing the whole exploration loop into your local agent context. The tradeoff is that it consumes server-side agent capacity and offers less control."
            ),
        },
        {
            "title": "选 SKILL" if is_zh else "Choose SKILL",
            "summary_html": (
                f"本地 Agent 结合 Skill，自主调用 {_mono('knowledge_list')} / {_mono('knowledge_read')}。"
                if is_zh
                else f"Let the local agent use the Skill with {_mono('knowledge_list')} / {_mono('knowledge_read')}."
            ),
            "detail_html": (
                "优点是自由度高、证据链白盒可控，也更适合想复刻 ask 逻辑或继续深挖的场景。代价是需要本地 Agent 自己探索，通常更依赖本地上下文与执行质量。"
                if is_zh
                else "This path gives you higher freedom, a white-box evidence chain, and more room to reproduce or extend the ask logic locally. The tradeoff is that your local agent must do the exploration itself, so it depends more on local context budget and execution quality."
            ),
        },
    ]
    return "\n".join(
        "\n".join(
            [
                '<article class="card tutorial-decision-card">',
                f"  <strong>{escape(card['title'])}</strong>",
                f'  {_tutorial_tip(card["summary_html"], card["detail_html"], locale=active_locale)}',
                "</article>",
            ]
        )
        for card in cards
    )


@lru_cache(maxsize=2)
def _tutorial_skill_cards(locale: str) -> str:
    active_locale = _normalize_locale(locale)
    is_zh = active_locale == "zh"
    title = "Sediment MCP Explore SKILL"
    summary_html = (
        f"把 Sediment Explore 的推导习惯搬到本地 Agent。"
        if is_zh
        else "Bring the Sediment Explore reasoning style into the local agent."
    )
    detail_html = (
        "适合在本地白盒复刻 ask 逻辑。它是刻意的 list/read 路线，不要求 knowledge_ask。"
        if is_zh
        else "Use it when you want to reproduce the ask workflow locally in a white-box way. It intentionally follows the list/read path and does not require knowledge_ask."
    )
    download_label = "下载 SKILL" if is_zh else "Download SKILL"
    return "\n".join(
        [
            '<article class="card tutorial-skill-card">',
            '  <div class="row spread">',
            f"    <strong>{escape(title)}</strong>",
            f'    {_nav_link(download_label, _localized_path(f"/downloads/skills/{_tutorial_skill_slug()}", active_locale), variant="download")}',
            "  </div>",
            f'  {_tutorial_tip(summary_html, detail_html, locale=active_locale, testid="tutorial-skill-card-tip")}',
            f'  <div class="subtle mono">{escape(_tutorial_skill_filename())}</div>',
            "</article>",
        ]
    )


@lru_cache(maxsize=2)
def _tutorial_agent_guides(locale: str) -> str:
    active_locale = _normalize_locale(locale)
    is_zh = active_locale == "zh"
    cards = [
        {
            "title": "快速问答路径" if is_zh else "Fast-answer path",
            "summary_html": (
                f'直接告诉 Agent：使用 Sediment MCP，并优先调用 {_mono("knowledge_ask")}。'
                if is_zh
                else f'Tell the agent: use Sediment MCP and prefer {_mono("knowledge_ask")} for this task.'
            ),
            "detail_html": (
                "适合 Codex / OpenCode / Claude Code 这类命令式 Agent 运行时里的快速接法。你只需要在任务里点名 server 或 tool，通常就足够让它走对路径。"
                if is_zh
                else "This is the quickest path in command-style agent runtimes such as Codex, OpenCode, or Claude Code. In many cases, naming the MCP server or tool directly in the task is enough to steer the run."
            ),
        },
        {
            "title": "本地白盒路径" if is_zh else "Local white-box path",
            "summary_html": (
                f'直接告诉 Agent：不要调用 {_mono("knowledge_ask")}，只用 {_mono("knowledge_list")} / {_mono("knowledge_read")}。'
                if is_zh
                else f'Tell the agent: do not call {_mono("knowledge_ask")}; use only {_mono("knowledge_list")} / {_mono("knowledge_read")} instead.'
            ),
            "detail_html": (
                "这条提示最适合需要可审计证据链、想把综合推理留在本地，或感觉远端 ask 往返太慢的时候。下载区里的本地 Skill 就是围绕这条路径设计的。"
                if is_zh
                else "Use this when you need an auditable evidence chain, want synthesis to stay local, or find the remote ask round-trip too slow. The downloadable local Skill is built around this path."
            ),
        },
        {
            "title": "如果运行时支持限缩工具" if is_zh else "When the runtime can narrow tools",
            "summary_html": (
                "如果框架支持 tool allowlist 或 tool filter，就直接收窄可见工具。"
                if is_zh
                else "If your framework supports a tool allowlist or tool filter, narrow the visible tools directly."
            ),
            "detail_html": (
                "例如：快速问答 Agent 只看 knowledge_ask，研究型 Agent 只看 knowledge_list / knowledge_read。这样比纯靠 prompt 更稳定，也能减少无关工具干扰。"
                if is_zh
                else "For example, let a fast-answer agent see only knowledge_ask, while a research agent sees only knowledge_list and knowledge_read. This is usually more stable than prompt-only steering and reduces distraction from irrelevant tools."
            ),
        },
    ]
    return "\n".join(
        "\n".join(
            [
                '<article class="card tutorial-guide-card">',
                f"  <strong>{escape(card['title'])}</strong>",
                f'  {_tutorial_tip(card["summary_html"], card["detail_html"], locale=active_locale)}',
                "</article>",
            ]
        )
        for card in cards
    )


def shared_shell(
    title: str,
    body: str,
    *,
    locale: str,
    page_script_name: str | None = None,
    page_data: object | None = None,
    shell_variant: str = "portal",
) -> str:
    active_locale = _normalize_locale(locale)
    toggle_label = "EN" if active_locale == "zh" else "中"
    toggle_aria_label = "切换语言" if active_locale == "zh" else "Switch language"
    theme_dark_label = "切换到暗色" if active_locale == "zh" else "Switch to dark mode"
    theme_light_label = "切换到明亮" if active_locale == "zh" else "Switch to light mode"
    page_data_tag = ""
    if page_data is not None:
        page_data_tag = (
            '<script id="sediment-page-data" type="application/json">'
            f"{_json_script_payload(page_data)}"
            "</script>"
        )
    page_script_tag = (
        f'<script src="{_asset_url(page_script_name)}"></script>' if page_script_name else ""
    )
    return _render_html_template(
        "web-shell.html",
        HTML_LANG=_html_lang(active_locale),
        ACTIVE_LOCALE=active_locale,
        TITLE=title,
        LOGO_MARK_DATA_URI=_logo_mark_data_uri(),
        BODY=body,
        SHELL_DATA=_json_script_payload(
            {
                "toggleLabel": toggle_label,
                "toggleAriaLabel": toggle_aria_label,
                "themeDarkLabel": theme_dark_label,
                "themeDarkIcon": "◐",
                "themeLightLabel": theme_light_label,
                "themeLightIcon": "☀",
            }
        ),
        PAGE_DATA_TAG=page_data_tag,
        PAGE_SCRIPT_TAG=page_script_tag,
        SHELL_VARIANT=shell_variant,
    )


def _public_nav(active_locale: str, *, page: str) -> dict[str, str]:
    is_zh = active_locale == "zh"
    return {
        "HOME_LINK": _nav_link(
            "知识库概览" if is_zh else "KB Overview",
            _localized_path("/", active_locale),
            primary=page == "home",
        ),
        "SEARCH_LINK": _nav_link(
            "搜索" if is_zh else "Search",
            _localized_path("/search", active_locale),
            primary=page == "search",
        ),
        "TUTORIAL_LINK": _nav_link(
            "接入教程" if is_zh else "Integration Guide",
            _localized_path("/tutorial", active_locale),
            primary=page == "tutorial",
        ),
        "SUBMIT_LINK": _nav_link(
            "提交" if is_zh else "Submit",
            _localized_path("/submit", active_locale),
            primary=page == "submit",
        ),
        "QUARTZ_LINK": _nav_link(
            "Quartz" if is_zh else "Quartz",
            _localized_path("/quartz/", active_locale),
            primary=page == "quartz",
            new_tab=True,
        ),
    }


def portal_html(
    *,
    knowledge_name: str,
    instance_name: str,
    locale: str,
    page: str = "home",
    initial_query: str = "",
    entry_name: str = "",
    current_user: dict[str, object] | None = None,
    mcp_endpoint: str = "",
) -> str:
    active_locale = _normalize_locale(locale)
    is_zh = active_locale == "zh"
    page = page if page in {"home", "search", "entry", "submit", "tutorial"} else "home"
    nav = _public_nav(active_locale, page=page)
    page_title = _portal_page_title(page, is_zh=is_zh, entry_name=entry_name)
    subtitles = {
        "home": "搜索" if is_zh else "Search",
        "search": "全文搜索" if is_zh else "Full-text search",
        "entry": "正式条目" if is_zh else "Canonical entry",
        "submit": "提交缓冲区" if is_zh else "Buffered submission",
        "tutorial": "接入" if is_zh else "Access",
    }
    common = {
        "LOGO_INLINE": _logo_inline(),
        "KNOWLEDGE_NAME": knowledge_name,
        "INSTANCE_NAME": instance_name,
        "ACTIVE_LOCALE": active_locale,
        "PAGE_TITLE": page_title,
        "PAGE_TITLE_CLASS": "page-title sr-only" if page == "home" else "page-title",
        "PAGE_KICKER": subtitles[page],
        "SEARCH_PLACEHOLDER": (
            "搜索概念、规则、经验，比如：热备份 泄洪 暗流"
            if is_zh
            else "Search concepts, rules, or lessons. Example: hot backup failover stream"
        ),
        "SEARCH_BUTTON_LABEL": "搜索" if is_zh else "Search",
        "STATS_TITLE": "知识库统计" if is_zh else "Knowledge base stats",
        "UPDATES_TITLE": "最近更新" if is_zh else "Recent updates",
        "ENTRY_SIGNALS_TITLE": "条目信号" if is_zh else "Entry signals",
        "ENTRY_SECTIONS_TITLE": "结构化分区" if is_zh else "Structured sections",
        "ENTRY_BODY_TITLE": "Markdown 正文" if is_zh else "Markdown body",
        "TEXT_SUBMISSION_TITLE": "文本提交" if is_zh else "Text submission",
        "DOCUMENT_UPLOAD_TITLE": "文档上传" if is_zh else "Document upload",
        "SUBMITTER_NAME_LABEL": "提交者" if is_zh else "Your name",
        "SUBMITTER_NAME_PLACEHOLDER": "例如：Alice" if is_zh else "Example: Alice",
        "SUBMISSION_TITLE_LABEL": "标题" if is_zh else "Title",
        "SUBMISSION_TITLE_PLACEHOLDER": (
            "例如：泄洪前先确认热备份接管链路"
            if is_zh
            else "Example: verify hot backup takeover chain before flood release"
        ),
        "SUBMISSION_TYPE_LABEL": "类型" if is_zh else "Type",
        "TYPE_CONCEPT": "概念" if is_zh else "Concept",
        "TYPE_LESSON": "经验" if is_zh else "Lesson",
        "TYPE_FEEDBACK": "反馈" if is_zh else "Feedback",
        "SUBMISSION_CONTENT_LABEL": "内容" if is_zh else "Content",
        "SUBMIT_TEXT_BUTTON": "提交文本" if is_zh else "Submit text",
        "UPLOAD_FILES_LABEL": "上传文件" if is_zh else "Upload files",
        "UPLOAD_FOLDER_LABEL": "上传文件夹" if is_zh else "Upload folder",
        "SUBMIT_FILE_BUTTON": "上传文档" if is_zh else "Upload documents",
        "MCP_TITLE": "通过 MCP 接入" if is_zh else "Connect via MCP",
        "MCP_INTRO": _tutorial_tip(
            (
                f"让 Sediment 在服务端直接给结果。"
                if is_zh
                else "Let Sediment return the answer from the service side."
            ),
            (
                f"最直接的方式是让 Agent 走 {_mono('knowledge_ask')}。如果运行时支持 tool allowlist / tool filter，就把可见工具收窄到当前路径需要的那几个；如果不支持，在提示词里点名具体 tool 也通常有效。"
                if is_zh
                else f"The simplest path is to steer the agent toward {_mono('knowledge_ask')}. If your runtime supports a tool allowlist or tool filter, narrow the visible tools to the current path. If it does not, explicitly naming the target tool in the prompt is still an effective fallback."
            ),
            locale=active_locale,
            testid="tutorial-mcp-intro",
        ),
        "MCP_ENDPOINT_LABEL": "SSE 端点" if is_zh else "SSE endpoint",
        "MCP_ENDPOINT": mcp_endpoint,
        "DECISION_TITLE": "怎么选" if is_zh else "Which path to choose",
        "DECISION_INTRO": _tutorial_tip(
            (
                "真正需要先做的决策只有一个：这次是走 MCP，还是走本地 Skill。"
                if is_zh
                else "There is really only one decision to make first: use MCP this time, or use the local Skill."
            ),
            (
                "如果你更看重接入速度和直接拿结果，就偏向 MCP；如果你更看重自由度、证据链控制和本地自主探索，就偏向 Skill。"
                if is_zh
                else "Lean toward MCP when you want the fastest path and a direct answer. Lean toward the Skill when you want more control, a clearer evidence trail, and local autonomous exploration."
            ),
            locale=active_locale,
            testid="tutorial-decision-intro",
        ),
        "DECISION_CARDS": _tutorial_decision_cards(active_locale),
        "TOOLS_TITLE": "工具分工" if is_zh else "Tool roles",
        "MCP_TOOL_CARDS": _tutorial_mcp_tool_cards(active_locale),
        "MCP_EXAMPLES_TITLE": "如何让 Agent 用对工具" if is_zh else "How to steer the agent toward the right tools",
        "MCP_EXAMPLES_INTRO": _tutorial_tip(
            (
                "大多数 Agent 运行时都支持“在任务里点名 server 或 tool”。"
                if is_zh
                else "Most agent runtimes support naming the server or tool directly in the task."
            ),
            (
                "下面这些例子故意不用代码，而是用你可以直接贴给 Agent 的指令句式。"
                if is_zh
                else "The examples below are intentionally written as instructions you can paste directly into an agent, instead of code."
            ),
            locale=active_locale,
            testid="tutorial-agent-guides-intro",
        ),
        "MCP_AGENT_GUIDES": _tutorial_agent_guides(active_locale),
        "SKILL_TITLE": "通过 SKILL 接入" if is_zh else "Connect via SKILL",
        "SKILL_INTRO": _tutorial_tip(
            (
                "让本地 Agent 自己探索和综合。"
                if is_zh
                else "Let the local agent explore and synthesize on its own."
            ),
            (
                f"这个 Skill 默认只依赖 {_mono('knowledge_list')} / {_mono('knowledge_read')}。如果你不想把远端 MCP 往返放进推理链里，或者想保留更高的本地自由度，就优先考虑这条路径。"
                if is_zh
                else f"It assumes only {_mono('knowledge_list')} / {_mono('knowledge_read')}. Prefer this path when you do not want remote MCP round-trips inside the reasoning loop, or when you want more local freedom."
            ),
            locale=active_locale,
            testid="tutorial-skill-intro",
        ),
        "SKILL_INSTALL_PATH_LABEL": "建议安装位置" if is_zh else "Suggested install location",
        "SKILL_INSTALL_PATH": (
            "$CODEX_HOME/skills/ 或你的 Agent 运行时 skills 目录"
            if is_zh
            else "$CODEX_HOME/skills/ or your agent runtime's skills directory"
        ),
        "SKILL_DOWNLOADS": _tutorial_skill_cards(active_locale),
        **nav,
    }
    templates = {
        "home": "portal-home-body.html",
        "search": "portal-search-body.html",
        "entry": "portal-entry-body.html",
        "submit": "portal-submit-body.html",
        "tutorial": "portal-tutorial-body.html",
    }
    body = _render_html_template(
        templates[page],
        **common,
        ENTRY_NAME=entry_name,
        ATTRIBUTION=(
            (
                f"已识别登录身份：{current_user['name']} ({current_user['role']})"
                if is_zh
                else f"Authenticated as {current_user['name']} ({current_user['role']})"
            )
            if current_user
            else ("当前将以匿名方式提交。" if is_zh else "This submission will be anonymous by default.")
        ),
    )
    page_data = {
        "pageKind": page,
        "initialQuery": initial_query,
        "entryName": entry_name,
        "knowledgeName": knowledge_name,
        "routes": {
            "home": _localized_path("/", active_locale),
            "search": _localized_path("/search", active_locale),
            "tutorial": _localized_path("/tutorial", active_locale),
            "submit": _localized_path("/submit", active_locale),
            "entryPrefix": "/entries/",
            "quartz": _localized_path("/quartz/", active_locale),
        },
        "ui": {
            "formal_entries": "正式条目" if is_zh else "Formal entries",
            "placeholders": "待补全概念" if is_zh else "Placeholders",
            "indexes": "索引" if is_zh else "Indexes",
            "pending": "待审提交" if is_zh else "Pending submissions",
            "health": "治理问题" if is_zh else "Health issues",
            "updates_empty": "暂无最近更新" if is_zh else "No recent updates yet.",
            "home_ready": "知识库已就绪。" if is_zh else "Knowledge base ready.",
            "search_placeholder": (
                "搜索概念、规则、经验，比如：热备份 泄洪 暗流"
                if is_zh
                else "Search concepts, rules, or lessons. Example: hot backup failover stream"
            ),
            "search_button": "搜索" if is_zh else "Search",
            "search_busy": "搜索中..." if is_zh else "Searching...",
            "search_prompt": "请输入关键词后再搜索。" if is_zh else "Enter a query before searching.",
            "search_empty": "没有搜索到结果。" if is_zh else "No matching results.",
            "search_hint": (
                "使用上下键选中建议，回车直达条目，或查看完整结果。"
                if is_zh
                else "Use arrow keys to navigate suggestions, Enter to open an entry, or view all results."
            ),
            "suggestions_empty": "暂无建议" if is_zh else "No suggestions yet.",
            "view_all_results": "查看全部结果" if is_zh else "View all results",
            "found_prefix": "找到" if is_zh else "Found",
            "found_suffix": "条结果。" if is_zh else "results.",
            "entry_open": "打开条目：" if is_zh else "Opened entry: ",
            "detail_type": "类型" if is_zh else "Type",
            "detail_status": "状态" if is_zh else "Status",
            "detail_related": "Related" if not is_zh else "关联",
            "detail_aliases": "Aliases" if not is_zh else "别名",
            "detail_sources": "Sources" if not is_zh else "来源",
            "detail_validation": "Validation" if not is_zh else "校验",
            "detail_valid": "有效" if is_zh else "Valid",
            "detail_warn": "警告" if is_zh else "Warnings",
            "detail_fail": "失败" if is_zh else "Failures",
            "detail_empty": "条目加载中..." if is_zh else "Loading entry...",
            "no_content": "暂无内容" if is_zh else "No content",
            "unknown": "未知" if is_zh else "unknown",
            "submit_text_busy": "分析中..." if is_zh else "Analyzing...",
            "submit_file_busy": "上传中..." if is_zh else "Uploading...",
            "file_required": "请先选择文件、压缩包或文件夹" if is_zh else "Select a file, folder, or archive first.",
            "file_read_error": "读取文件失败" if is_zh else "Failed to read file.",
            "analysis_title": "Agent 建议" if is_zh else "Agent recommendation",
            "analysis_related_empty": "暂无明显关联条目" if is_zh else "No obvious related entries.",
            "analysis_title_label": "建议标题" if is_zh else "Suggested title",
            "analysis_type_label": "建议类型" if is_zh else "Suggested type",
            "analysis_risk_label": "风险" if is_zh else "Risk",
            "analysis_action_label": "下一步" if is_zh else "Next step",
            "analysis_note_label": "Committer 提示" if is_zh else "Committer note",
            "submit_text_success": "文本提交成功，submission_id=" if is_zh else "Text submission created, submission_id=",
            "submit_file_success": "文档提交成功，submission_id=" if is_zh else "Document submission created, submission_id=",
            "submitted_text_prefix": "已提交文本草案：" if is_zh else "Submitted text draft: ",
            "submitted_file_prefix": "已提交文档：" if is_zh else "Submitted document bundle: ",
            "unknown_error": "未知错误" if is_zh else "Unknown error",
        },
    }
    return shared_shell(
        _document_title(page_title, knowledge_name),
        body,
        locale=active_locale,
        page_script_name="portal.js",
        page_data=page_data,
        shell_variant="portal",
    )


def portal_graph_html(
    *,
    knowledge_name: str,
    instance_name: str,
    locale: str,
    quartz: dict[str, object],
) -> str:
    active_locale = _normalize_locale(locale)
    is_zh = active_locale == "zh"
    page_title = "Quartz"
    nav = _public_nav(active_locale, page="quartz")
    body = _render_html_template(
        "portal-quartz-fallback-body.html",
        LOGO_INLINE=_logo_inline(),
        KNOWLEDGE_NAME=knowledge_name,
        INSTANCE_NAME=instance_name,
        PAGE_TITLE=page_title,
        STATUS_LABEL=(
            "站点已构建，可直接打开 Quartz。" if quartz.get("site_available") else "当前实例还没有可用的 Quartz 站点。"
            if is_zh
            else "Quartz site is built and ready." if quartz.get("site_available") else "This instance does not have a built Quartz site yet."
        ),
        DETAIL_TEXT=(
            f"runtime: {quartz.get('runtime_path', '-')}\nsite: {quartz.get('site_path', '-')}"
        ),
        ACTIONS_TITLE="操作" if is_zh else "Actions",
        ADMIN_KB_LINK=_nav_link(
            "前往管理台设置页" if is_zh else "Open admin settings page",
            _localized_path("/admin/system", active_locale),
            variant="action",
        ),
        OPEN_QUARTZ_LINK=_nav_link(
            "打开 Quartz" if is_zh else "Open Quartz",
            _localized_path("/quartz/", active_locale),
            primary=True,
            variant="action",
            new_tab=True,
        ),
        **nav,
    )
    return shared_shell(
        _document_title(page_title, knowledge_name),
        body,
        locale=active_locale,
        shell_variant="portal",
    )


def admin_login_html(*, knowledge_name: str, instance_name: str, locale: str, next_path: str) -> str:
    active_locale = _normalize_locale(locale)
    is_zh = active_locale == "zh"
    page_title = "管理台登录" if is_zh else "Admin sign in"
    nav = _public_nav(active_locale, page="")
    body = _render_html_template(
        "admin-login-body.html",
        LOGO_INLINE=_logo_inline(),
        KNOWLEDGE_NAME=knowledge_name,
        INSTANCE_NAME=instance_name,
        PAGE_TITLE=page_title,
        TOKEN_LABEL="登录 Token" if is_zh else "Sign-in token",
        TOKEN_PLACEHOLDER="输入 owner 或 committer token" if is_zh else "Enter an owner or committer token",
        OPEN_ADMIN_LABEL="进入管理台" if is_zh else "Open admin",
        LOGIN_STATUS="需要有效 token 才能进入后台。" if is_zh else "A valid token is required.",
        **nav,
    )
    return shared_shell(
        _document_title(page_title, knowledge_name),
        body,
        locale=active_locale,
        page_script_name="admin-login.js",
        page_data={
            "login_failed": "登录失败" if is_zh else "Sign-in failed",
            "redirect": next_path,
        },
        shell_variant="admin",
    )


def admin_html(
    *,
    knowledge_name: str,
    instance_name: str,
    locale: str,
    section: str,
    quartz: dict[str, object],
    current_user: dict[str, object] | None = None,
) -> str:
    active_locale = _normalize_locale(locale)
    is_zh = active_locale == "zh"
    allowed_sections = {"overview", "kb", "files", "reviews", "users", "system"}
    section = section if section in allowed_sections else "overview"
    page_title = _admin_page_title(section, is_zh=is_zh)
    is_owner = bool(current_user and current_user.get("role") == "owner")
    section_links = {
        "OVERVIEW_LINK": _nav_link(
            "总览" if is_zh else "Overview",
            _localized_path("/admin/overview", active_locale),
            primary=section == "overview",
        ),
        "KB_LINK": _nav_link(
            "知识库管理" if is_zh else "KB Management",
            _localized_path("/admin/kb", active_locale),
            primary=section == "kb",
        ),
        "FILES_LINK": _nav_link(
            "文件管理" if is_zh else "Files",
            _localized_path("/admin/files", active_locale),
            primary=section == "files",
        ),
        "REVIEWS_LINK": _nav_link(
            "评审" if is_zh else "Reviews",
            _localized_path("/admin/reviews", active_locale),
            primary=section == "reviews",
        ),
        "USERS_LINK": (
            _nav_link(
                "用户" if is_zh else "Users",
                _localized_path("/admin/users", active_locale),
                primary=section == "users",
            )
            if is_owner
            else ""
        ),
        "SYSTEM_LINK": (
            _nav_link(
                "设置" if is_zh else "Settings",
                _localized_path("/admin/system", active_locale),
                primary=section == "system",
            )
            if is_owner
            else ""
        ),
    }
    section_markup = {
        "overview": _render_html_template(
            "admin-overview-section.html",
            QUEUE_TITLE="工作队列" if is_zh else "Queue",
            QUEUE_NOTE="提交 / review / 任务" if is_zh else "submissions / reviews / jobs",
            HEALTH_TITLE="治理健康度" if is_zh else "Health",
            HEALTH_NOTE="问题分布与阻断项" if is_zh else "severity distribution and blockers",
            ISSUE_TITLE="治理焦点" if is_zh else "Priority issues",
            ISSUE_NOTE="只读概览，不在这里直接执行操作" if is_zh else "Read-only overview for current blockers",
            ACTIVITY_TITLE="最近活动" if is_zh else "Recent activity",
            ACTIVITY_NOTE="审计与操作痕迹" if is_zh else "audit trail",
        ),
        "kb": _render_html_template(
            "admin-kb-section.html",
            INGEST_TITLE="Ingest 导入" if is_zh else "Ingest",
            INGEST_NOTE="拖入文档后直接入队" if is_zh else "drop documents and enqueue immediately",
            INGEST_DROPZONE_TITLE="拖入文档或压缩包" if is_zh else "Drop documents or an archive",
            INGEST_DROPZONE_BODY=(
                "支持 Markdown、文本、DOCX、PPTX 和 zip；也可以直接选择文件或文件夹。"
                if is_zh
                else "Supports Markdown, text, DOCX, PPTX, and zip. You can also choose files or folders directly."
            ),
            INGEST_FILE_LABEL="选择文件" if is_zh else "Choose files",
            INGEST_FOLDER_LABEL="选择文件夹" if is_zh else "Choose folder",
            INGEST_SELECTION_LABEL="当前导入选择" if is_zh else "Current import selection",
            INGEST_SELECTION_EMPTY="还没有选择任何文档。" if is_zh else "No documents selected yet.",
            INGEST_BUTTON="上传并运行 Ingest" if is_zh else "Upload and run ingest",
            INGEST_STATUS="上传完成后会在这里显示 submission 与 job 信息。" if is_zh else "Submission and job feedback appears here after upload.",
            TIDY_TITLE="Tidy 整理" if is_zh else "Tidy",
            TIDY_NOTE="输入原因后直接发起治理" if is_zh else "enter a reason and queue maintenance",
            TIDY_REASON_LABEL="本次 tidy 原因" if is_zh else "Tidy reason",
            TIDY_REASON_PLACEHOLDER="例如：整理 dangling links 与未覆盖正式条目" if is_zh else "Example: clean up dangling links and uncovered formal entries",
            TIDY_BUTTON="执行 Tidy" if is_zh else "Run tidy",
            TIDY_HINT_TITLE="默认范围" if is_zh else "Default scope",
            TIDY_HINT_BODY=(
                "这里默认按阻断性健康问题执行；如果你需要更大范围的整理，建议走 CLI 或专门任务。"
                if is_zh
                else "This button targets blocking health issues by default. Use the CLI or a dedicated task when you need a broader cleanup."
            ),
            EXPLORE_TITLE="Explore 探索" if is_zh else "Knowledge explore",
            EXPLORE_NOTE="保留当前问答能力" if is_zh else "keep the current Q&A path",
            EXPLORE_INPUT_LABEL="问题 / 场景" if is_zh else "Question / scenario",
            EXPLORE_INPUT_PLACEHOLDER=(
                "例如：热备份在什么情况下不该当成主备切换方案？"
                if is_zh
                else "Example: when should hot backup not be treated as a failover strategy?"
            ),
            EXPLORE_BUTTON="运行探索" if is_zh else "Run explore",
            EXPLORE_RESULT_EMPTY="这里会显示回答、来源和缺口。" if is_zh else "Answers, sources, and gaps appear here.",
        ),
        "files": _render_html_template(
            "admin-files-section.html",
            FILE_BROWSER_TITLE="Files 文件结构" if is_zh else "File browser",
            FILE_BROWSER_NOTE=(
                "按 index 导航组织文档，而不是把所有 Markdown 平铺出来。"
                if is_zh
                else "Browse documents through the index network instead of a flat markdown dump."
            ),
            FILE_COUNTS_INDEXED="已纳入索引" if is_zh else "Indexed",
            FILE_COUNTS_UNINDEXED="未纳入索引" if is_zh else "Unindexed",
            FILE_SEARCH_LABEL="搜索并直接打开文档" if is_zh else "Search and open a document",
            FILE_SEARCH_PLACEHOLDER="输入标题、别名、路径或 index 名称" if is_zh else "Search by title, alias, path, or index name",
            FILE_SEARCH_STATUS="输入后会显示自动建议；选中后直接载入编辑区。" if is_zh else "Suggestions appear as you type and open directly in the editor.",
            FILE_BROWSE_HINT_TITLE="Index 治理约定" if is_zh else "Index governance",
            FILE_BROWSE_HINT_BODY=(
                "Tidy 会负责维护 index.root 与分段 index 的可导航性；文件管理页沿用这套结构来浏览与修订文档。"
                if is_zh
                else "Tidy maintains index.root and segment indexes; this page reuses that structure for browsing and editing."
            ),
            DOC_STRUCTURE_TITLE="Index 结构浏览" if is_zh else "Index structure",
            DOC_STRUCTURE_NOTE="按根索引与分段索引展开" if is_zh else "expand root and segment indexes",
            DOC_HEALTH_TITLE="健康队列联动" if is_zh else "Health-driven selection",
            DOC_HEALTH_NOTE="可从治理问题直接跳到对应文档" if is_zh else "jump from a governance issue straight into the related document",
            EDITOR_TITLE="Markdown 编辑器" if is_zh else "Markdown editor",
            EDITOR_NOTE="复用门户渲染，保存前先看预览与关联问题" if is_zh else "reuse the portal renderer and inspect linked issues before saving",
            EDITOR_CURRENT_LABEL="当前文档" if is_zh else "Current document",
            EDITOR_CURRENT_EMPTY="还没有选中文档。" if is_zh else "No document selected yet.",
            EDITOR_CONTENT_LABEL="Markdown 内容" if is_zh else "Markdown content",
            SAVE_ENTRY_BUTTON="保存 Markdown" if is_zh else "Save markdown",
            EDITOR_PREVIEW_TITLE="预览" if is_zh else "Preview",
            EDITOR_PREVIEW_EMPTY="选中文档后，这里会复用门户的 Markdown 渲染方式预览。" if is_zh else "After you select a document, the portal-style Markdown preview appears here.",
            EDITOR_LINKED_ISSUES_TITLE="关联治理问题" if is_zh else "Linked governance issues",
            EDITOR_STATUS="这里会显示校验结果、保存反馈和冲突提示。" if is_zh else "Validation, save feedback, and conflict hints appear here.",
        ),
        "reviews": _render_html_template(
            "admin-reviews-section.html",
            PENDING_REVIEWS_TITLE="待审补丁" if is_zh else "Pending reviews",
            PENDING_REVIEWS_NOTE="先选中补丁，再进入详情和决策" if is_zh else "Select a patch first, then review details and decide",
            DETAIL_TITLE="评审详情" if is_zh else "Review detail",
            DETAIL_NOTE="按条查看来源、摘要与 diff，再给出结论" if is_zh else "Inspect source context, summary, and diff before deciding",
            DETAIL_EMPTY="选择左侧待审补丁后，在这里展开完整上下文。" if is_zh else "Select a pending review on the left to open its full context here.",
            REVIEW_COMMENT_LABEL="评审备注" if is_zh else "Review comment",
            REVIEW_COMMENT_PLACEHOLDER="为批准、退回或拒绝留下简短原因。" if is_zh else "Leave a short rationale for approval, changes, or rejection.",
            APPROVE_BUTTON="批准合并" if is_zh else "Approve merge",
            REJECT_BUTTON="退回 / 拒绝" if is_zh else "Request changes / reject",
            DIFF_EMPTY="选择待审 patch 后在这里查看。" if is_zh else "Select a pending review to inspect its diff here.",
            JOB_TITLE="任务" if is_zh else "Jobs",
            JOB_NOTE="用来观察 ingest / tidy / review 的后续状态" if is_zh else "Track follow-up state for ingest, tidy, and review jobs",
        ),
        "users": _render_html_template(
            "admin-users-section.html",
            USERS_NOTE="仅所有者可操作" if is_zh else "Owner only",
            CREATE_TITLE="新增提交者" if is_zh else "Create committer",
            NAME_LABEL="姓名" if is_zh else "Name",
            NAME_PLACEHOLDER="例如：Ops Committer" if is_zh else "Example: Ops Committer",
            CREATE_HELP=(
                "新建用户固定为提交者。所有者只有初始化时生成的唯一账户。"
                if is_zh
                else "New users are always committers. The owner account is the unique account created during init."
            ),
            CREATE_BUTTON="创建用户" if is_zh else "Create user",
            OWNER_TITLE="所有者账户" if is_zh else "Owner account",
            OWNER_NOTE="唯一且不可新增" if is_zh else "Unique and not user-creatable",
            OWNER_BODY=(
                "所有者负责用户与系统级操作；管理台和 CLI 都不再提供新增所有者的入口。"
                if is_zh
                else "The owner handles user and system operations. Neither the admin UI nor the CLI offers owner creation."
            ),
            LIST_TITLE="当前用户" if is_zh else "Current users",
        ),
        "system": _render_html_template(
            "admin-system-section.html",
            SETTINGS_TITLE="配置文件" if is_zh else "Config file",
            SETTINGS_NOTE="仅 owner 可查看与修改" if is_zh else "owner-only view and edit",
            SETTINGS_PATH_LABEL="当前配置路径" if is_zh else "Current config path",
            SETTINGS_PATH_EMPTY="配置路径加载中..." if is_zh else "Loading config path...",
            SETTINGS_EDITOR_LABEL="原始 YAML 配置" if is_zh else "Raw YAML config",
            SETTINGS_RELOAD_BUTTON="从磁盘重新载入" if is_zh else "Reload from disk",
            SETTINGS_SAVE_BUTTON="保存配置" if is_zh else "Save config",
            SETTINGS_RESTART_BUTTON="一键重启服务" if is_zh else "Restart service",
            SETTINGS_STATUS="这里会显示保存结果与校验反馈。" if is_zh else "Validation and save feedback appears here.",
            SETTINGS_RUNTIME_NOTE_TITLE="生效说明" if is_zh else "Runtime note",
            SETTINGS_RUNTIME_NOTE=(
                "大多数配置会在保存后立即重载；监听地址、端口和 SSE 路径需要重启服务才能完全生效。保存后可直接点一键重启。"
                if is_zh
                else "Most settings reload immediately after save. Bind address, port, and SSE path still need a service restart. Use the restart button after saving when needed."
            ),
            EFFECTIVE_SETTINGS_TITLE="展开后的有效配置" if is_zh else "Resolved effective config",
            EFFECTIVE_SETTINGS_NOTE="包含默认值、路径展开和运行态结果" if is_zh else "includes defaults, resolved paths, and runtime values",
            EFFECTIVE_SETTINGS_EMPTY="有效配置加载中..." if is_zh else "Loading effective config...",
            QUARTZ_TITLE="Quartz" if is_zh else "Quartz",
            QUARTZ_NOTE="运行时 / 构建状态 / 刷新" if is_zh else "runtime / build state / refresh",
            QUARTZ_BUTTON="构建 / 刷新 Quartz" if is_zh else "Build / refresh Quartz",
            OPEN_QUARTZ_LINK=_nav_link(
                "打开 Quartz" if is_zh else "Open Quartz",
                _localized_path("/quartz/", active_locale),
                variant="action",
                new_tab=True,
            ),
        ),
    }[section]
    body = _render_html_template(
        "admin-body.html",
        LOGO_INLINE=_logo_inline(),
        KNOWLEDGE_NAME=knowledge_name,
        INSTANCE_NAME=instance_name,
        PAGE_TITLE=page_title,
        READY_MESSAGE="管理台加载中..." if is_zh else "Loading admin...",
        PORTAL_LINK=_nav_link(
            "返回知识库" if is_zh else "Back to knowledge base",
            _localized_path("/", active_locale),
            variant="utility",
        ),
        LOGOUT_LABEL="退出登录" if is_zh else "Log out",
        SECTION_MARKUP=section_markup,
        **section_links,
    )
    return shared_shell(
        _document_title(page_title, knowledge_name),
        body,
        locale=active_locale,
        page_script_name="admin.js",
        page_data={
            "ui": {
                "section": section,
                "user": current_user,
                "is_owner": is_owner,
                "busy_loading": "加载中..." if is_zh else "Loading...",
                "busy_queue": "排队中..." if is_zh else "Queueing...",
                "busy_saving": "保存中..." if is_zh else "Saving...",
                "busy_approve": "批准中..." if is_zh else "Approving...",
                "busy_reject": "拒绝中..." if is_zh else "Rejecting...",
                "stats_pending": "待审提交" if is_zh else "Pending submissions",
                "stats_queue": "排队任务" if is_zh else "Queued jobs",
                "stats_running": "运行中任务" if is_zh else "Running jobs",
                "stats_reviews": "待审评审" if is_zh else "Pending reviews",
                "stats_blocking": "阻断问题" if is_zh else "Blocking issues",
                "stats_stale": "陈旧任务" if is_zh else "Stale jobs",
                "issue_empty": "当前没有需要立即处理的问题。" if is_zh else "No urgent issues right now.",
                "issue_scope_label": "建议范围" if is_zh else "Suggested scope",
                "issue_action_label": "建议动作" if is_zh else "Suggested action",
                "issue_target_label": "目标" if is_zh else "Target",
                "issue_open_document": "打开文档" if is_zh else "Open document",
                "submission_empty": "暂无待处理提交。" if is_zh else "No buffered submissions right now.",
                "review_empty": "暂无待审补丁。" if is_zh else "No pending reviews right now.",
                "job_empty": "暂无任务。" if is_zh else "No jobs right now.",
                "audit_empty": "暂无审计日志。" if is_zh else "No audit logs yet.",
                "diff_empty": "选择待审 patch 后在这里查看。" if is_zh else "Select a pending review to inspect its diff here.",
                "editor_loaded": "已加载" if is_zh else "Loaded",
                "editor_saved": "保存成功" if is_zh else "Saved",
                "editor_preview_empty": "预览将在这里显示。" if is_zh else "Preview appears here.",
                "editor_linked_issues_empty": "当前文档没有关联治理问题。" if is_zh else "No linked governance issues for this document.",
                "explore_answer": "回答" if is_zh else "Answer",
                "explore_sources": "来源" if is_zh else "Sources",
                "explore_gaps": "缺口" if is_zh else "Gaps",
                "explore_confidence": "置信度" if is_zh else "Confidence",
                "manual_tidy_reason_required": "请填写 tidy 原因。" if is_zh else "Enter a tidy reason.",
                "ingest_file_required": "请先拖入或选择至少一个文档。" if is_zh else "Drop or choose at least one document first.",
                "ingest_selected_prefix": "当前已选择" if is_zh else "Selected",
                "ingest_selected_suffix": "个文件" if is_zh else "files",
                "ingest_uploaded": "已创建 Ingest：" if is_zh else "Created ingest: ",
                "ingest_submission_prefix": "submission" if is_zh else "submission",
                "doc_group_formal": "正式条目" if is_zh else "Formal entries",
                "doc_group_placeholder": "Placeholders" if not is_zh else "待补全条目",
                "doc_group_index": "索引" if is_zh else "Indexes",
                "doc_counts_formal": "正式条目" if is_zh else "Formal",
                "doc_counts_placeholder": "待补全" if is_zh else "Placeholders",
                "doc_counts_index": "索引" if is_zh else "Indexes",
                "doc_browser_empty": "没有匹配的文档。" if is_zh else "No matching documents.",
                "doc_health_empty": "当前没有可联动的治理问题。" if is_zh else "No governance issues to link right now.",
                "doc_selected": "已选中文档：" if is_zh else "Selected document: ",
                "doc_select_prompt": "请先从左侧选择一个文档。" if is_zh else "Select a document from the left first.",
                "doc_path_label": "路径" if is_zh else "Path",
                "doc_kind_label": "类别" if is_zh else "Kind",
                "doc_status_label": "状态" if is_zh else "Status",
                "doc_issues_label": "治理问题" if is_zh else "Issues",
                "doc_indexes_label": "所在索引" if is_zh else "Indexes",
                "doc_aliases_label": "别名" if is_zh else "Aliases",
                "doc_links_label": "链接" if is_zh else "Links",
                "doc_updated_label": "最后修改" if is_zh else "Updated",
                "doc_issue_count_suffix": "个" if is_zh else "",
                "settings_loaded": "已从磁盘载入配置。" if is_zh else "Config reloaded from disk.",
                "settings_saved": "配置已保存。" if is_zh else "Config saved.",
                "settings_restart_scheduled": "服务重启已安排，页面会自动重新连接。" if is_zh else "Service restart scheduled. The page will reconnect automatically.",
                "triaged": "标记已归类" if is_zh else "Mark triaged",
                "reject": "拒绝提交" if is_zh else "Reject",
                "run_ingest": "运行 Ingest" if is_zh else "Run ingest",
                "show_diff": "查看详情" if is_zh else "Open detail",
                "approve": "批准" if is_zh else "Approve",
                "reject_review": "拒绝" if is_zh else "Reject",
                "retry": "重试" if is_zh else "Retry",
                "cancel": "取消" if is_zh else "Cancel",
                "logout_done": "已退出登录。" if is_zh else "Signed out.",
                "tidy_done": "已创建 tidy 任务：" if is_zh else "Created tidy job: ",
                "ingest_done": "已创建 ingest 任务：" if is_zh else "Created ingest job: ",
                "review_loaded": "已加载 review diff：" if is_zh else "Loaded review diff: ",
                "review_approved": "Review 已批准：" if is_zh else "Approved review: ",
                "review_rejected": "Review 已拒绝：" if is_zh else "Rejected review: ",
                "job_retried": "任务已重新入队：" if is_zh else "Requeued job: ",
                "job_cancelled": "任务已请求取消：" if is_zh else "Cancellation requested for job: ",
                "quartz_ready": "Quartz 站点已就绪" if is_zh else "Quartz site is ready",
                "quartz_missing_site": "尚未构建实例站点" if is_zh else "Instance site is not built yet",
                "quartz_missing_runtime": "Quartz runtime 不可用" if is_zh else "Quartz runtime is unavailable",
                "quartz_runtime_path": "runtime 路径" if is_zh else "runtime path",
                "quartz_site_path": "站点路径" if is_zh else "site path",
                "quartz_built_at": "最后构建时间" if is_zh else "last built",
                "quartz_build_success": "Quartz 站点已刷新。" if is_zh else "Quartz site refreshed.",
                "token_revealed": "Token 已就地展开。" if is_zh else "Token expanded inline.",
                "token_show": "显示 Token" if is_zh else "Show token",
                "token_hide": "收起 Token" if is_zh else "Hide token",
                "token_label": "Token" if not is_zh else "访问令牌",
                "disable_user": "停用" if is_zh else "Disable",
                "user_created": "用户已创建：" if is_zh else "Created user: ",
                "user_disabled": "用户已停用：" if is_zh else "Disabled user: ",
                "current_session": "当前会话" if is_zh else "Current session",
                "user_disabled_label": "已停用" if is_zh else "Disabled",
                "role_owner": "所有者" if is_zh else "owner",
                "role_committer": "提交者" if is_zh else "committer",
                "review_selected": "已载入评审：" if is_zh else "Loaded review: ",
                "review_select_prompt": "先从左侧选择一个待审 patch。" if is_zh else "Select a pending review from the left first.",
                "review_summary": "改动摘要" if is_zh else "Patch summary",
                "review_source_submission": "来源提交" if is_zh else "Source submission",
                "review_job_type": "任务类型" if is_zh else "Job type",
                "review_decision": "当前状态" if is_zh else "Current state",
                "review_patch_count": "变更数" if is_zh else "Operations",
                "review_created_at": "创建时间" if is_zh else "Created",
                "review_submission_status": "提交状态" if is_zh else "Submission status",
                "review_submission_author": "提交者" if is_zh else "Submitter",
                "review_queue_empty_detail": "当前没有待审 patch。" if is_zh else "There is no pending review right now.",
                "review_comment_approve": "由管理台批准" if is_zh else "Approved from admin UI",
                "review_comment_reject": "由管理台退回" if is_zh else "Rejected from admin UI",
                "scope_full": "全库维护" if is_zh else "Full KB",
                "scope_graph": "图谱修复" if is_zh else "Graph",
                "scope_indexes": "索引整理" if is_zh else "Indexes",
                "scope_health_blocking": "阻断问题" if is_zh else "Blocking issues",
                "file_counts_formal": "正式条目" if is_zh else "Formal",
                "file_counts_placeholder": "待补全" if is_zh else "Placeholders",
                "file_counts_index": "索引" if is_zh else "Indexes",
                "file_counts_indexed": "已纳入索引" if is_zh else "Indexed",
                "file_counts_unindexed": "未纳入索引" if is_zh else "Unindexed",
                "file_search_empty": "没有匹配的文档。" if is_zh else "No matching documents.",
                "file_search_hint": "输入后会显示自动建议；选中后直接载入编辑区。" if is_zh else "Suggestions appear as you type and open directly in the editor.",
                "file_search_matches": "条匹配" if is_zh else "matches",
                "file_search_auto_loading": "检测到精确匹配，正在载入：" if is_zh else "Exact match detected, loading: ",
                "file_unindexed_group": "未纳入任何索引的文档" if is_zh else "Documents outside all indexes",
                "file_index_direct_docs": "直接文档" if is_zh else "Direct documents",
                "file_index_child_indexes": "子索引" if is_zh else "Child indexes",
                "file_tokens_label": "token 估算" if is_zh else "tokens",
            },
            "quartz": quartz,
        },
        shell_variant="admin",
    )
