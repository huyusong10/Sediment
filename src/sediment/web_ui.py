# ruff: noqa: E501
from __future__ import annotations

import json
from functools import lru_cache
from html import escape

from sediment.package_data import render_asset_template
from sediment.web_ui_shared import (
    html_lang,
    json_script_payload,
    localized_path,
    logo_mark_data_uri,
    logo_mark_svg,
    logo_svg,
    normalize_locale,
    render_shell_template,
)


def _logo_mark_svg() -> str:
    return logo_mark_svg()


def _logo_svg() -> str:
    return logo_svg()


def _logo_mark_data_uri() -> str:
    return logo_mark_data_uri()


def _logo_inline(class_name: str = "brand-lockup") -> str:
    return _logo_svg().replace("<svg ", f'<svg class="{class_name}" aria-hidden="true" ')


def _normalize_locale(locale: str | None) -> str:
    return normalize_locale(locale)


def _html_lang(locale: str) -> str:
    return html_lang(locale)


def _localized_path(path: str, locale: str) -> str:
    return localized_path(path, locale)


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
    extra_attrs_parts: list[str] = []
    if variant == "nav":
        extra_attrs_parts.append('data-shell-nav-link="true"')
    if primary and variant == "nav":
        extra_attrs_parts.append('aria-current="page"')
    extra_attrs = ' target="_blank" rel="noopener noreferrer"' if new_tab else ""
    if extra_attrs_parts:
        extra_attrs += " " + " ".join(extra_attrs_parts)
    return (
        f'<a class="{" ".join(classes)}" href="{escape(href, quote=True)}"{extra_attrs}>'
        f"{escape(label)}</a>"
    )


def _render_html_template(name: str, **replacements: str) -> str:
    return render_asset_template(name, replacements)


def _asset_url(name: str) -> str:
    return f"/ui-assets/{name}"


def _json_script_payload(payload: object) -> str:
    return json_script_payload(payload)


def _document_title(*parts: str) -> str:
    return " | ".join(part for part in parts if str(part).strip())


def _portal_page_title(page: str, *, is_zh: bool, entry_name: str = "") -> str:
    return {
        "home": "知识库概览" if is_zh else "Knowledge base overview",
        "search": "全文搜索" if is_zh else "Full-text search",
        "entry": entry_name or ("条目详情" if is_zh else "Entry detail"),
        "submit": "提交入口" if is_zh else "Submit",
        "tutorial": "接入教程" if is_zh else "Integration guide",
    }[page]


def _admin_page_title(section: str, *, is_zh: bool) -> str:
    return {
        "overview": "总览" if is_zh else "Overview",
        "kb": "知识库管理" if is_zh else "Knowledge base management",
        "files": "文件管理" if is_zh else "File management",
        "inbox": "提交收件箱" if is_zh else "Submission Inbox",
        "version_control": "版本管理" if is_zh else "Version control",
        "reviews": "提交收件箱" if is_zh else "Submission Inbox",
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
    extra_script_names: list[str] | None = None,
    page_style_names: list[str] | None = None,
    page_data: object | None = None,
    shell_variant: str = "portal",
) -> str:
    active_locale = _normalize_locale(locale)
    toggle_label = "EN" if active_locale == "zh" else "中"
    toggle_aria_label = "切换语言" if active_locale == "zh" else "Switch language"
    theme_dark_label = "切换到暗色" if active_locale == "zh" else "Switch to dark mode"
    theme_light_label = "切换到明亮" if active_locale == "zh" else "Switch to light mode"
    extra_tags = []
    for style_name in page_style_names or []:
        extra_tags.append(f'<link rel="stylesheet" href="{_asset_url(style_name)}" />')
    for script_name in extra_script_names or []:
        extra_tags.append(f'<script src="{_asset_url(script_name)}"></script>')
    if page_script_name:
        extra_tags.append(f'<script src="{_asset_url(page_script_name)}"></script>')
    page_script_tag = "".join(extra_tags)
    return render_shell_template(
        title,
        body,
        locale=active_locale,
        page_data=page_data,
        page_script_tag=page_script_tag,
        shell_variant=shell_variant,
        shell_data={
            "toggleLabel": toggle_label,
            "toggleAriaLabel": toggle_aria_label,
            "themeDarkLabel": theme_dark_label,
            "themeDarkIcon": "◐",
            "themeLightLabel": theme_light_label,
            "themeLightIcon": "☀",
        },
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
        "submit": "提交入口" if is_zh else "Submit",
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
        "TEXT_SUBMISSION_TITLE": "文本意见" if is_zh else "Text feedback",
        "TEXT_SUBMISSION_NOTE": (
            "提交后会进入提交收件箱，由 committer 人工查看并处理。"
            if is_zh
            else "After submission, this goes to the Submission Inbox for manual committer handling."
        ),
        "DOCUMENT_UPLOAD_TITLE": "文档上传" if is_zh else "Document upload",
        "SUBMITTER_NAME_LABEL": "提交者" if is_zh else "Your name",
        "SUBMITTER_NAME_PLACEHOLDER": "例如：Alice" if is_zh else "Example: Alice",
        "SUBMISSION_TITLE_LABEL": "标题" if is_zh else "Title",
        "SUBMISSION_TITLE_PLACEHOLDER": (
            "例如：泄洪前先确认热备份接管链路"
            if is_zh
            else "Example: verify hot backup takeover chain before flood release"
        ),
        "SUBMISSION_CONTENT_LABEL": "内容" if is_zh else "Content",
        "SUBMIT_TEXT_BUTTON": "提交文本" if is_zh else "Submit text",
        "UPLOAD_FILES_LABEL": "上传文件" if is_zh else "Upload files",
        "UPLOAD_FILE_BUTTON": "选择文件" if is_zh else "Choose files",
        "UPLOAD_FILE_EMPTY": "未选择文件" if is_zh else "No files selected",
        "UPLOAD_FOLDER_LABEL": "上传文件夹" if is_zh else "Upload folder",
        "UPLOAD_FOLDER_BUTTON": "选择文件夹" if is_zh else "Choose folder",
        "UPLOAD_FOLDER_EMPTY": "未选择文件夹" if is_zh else "No folder selected",
        "FILE_PICKER_SELECTED_PREFIX": "已选择" if is_zh else "Selected",
        "FILE_PICKER_SELECTED_SUFFIX": "个文件" if is_zh else "files",
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
        "MCP_EXAMPLES_TITLE": "如何让智能体用对工具" if is_zh else "How to steer the agent toward the right tools",
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
        "GRAPH_HERO_TITLE": "知识宇宙" if is_zh else "Knowledge universe",
        "GRAPH_HERO_NOTE": (
            "不是全量知识图，而是知识从碎片里持续迸发、汇聚、稳定下来的那一刻。"
            if is_zh
            else "Not the full knowledge map, but the moment when knowledge bursts from fragments, gathers, and settles."
        ),
        "GRAPH_FRAME_TITLE": "知识磁场" if is_zh else "Knowledge field",
        "GRAPH_FRAME_NOTE": (
            "ingest 会把新知识抛入场中，explore / tidy 会唤醒既有碎片，把它们压缩成新的通路与知识节点。"
            if is_zh
            else "Ingest throws new knowledge into the field, while explore and tidy awaken fragments and compress them into new routes and nodes."
        ),
        "GRAPH_CAPTION": (
            "你看到的不是库存，而是最近仍然有能量的知识形成过程。"
            if is_zh
            else "This surface shows knowledge while it is still alive with formation energy, not the full inventory."
        ),
        "GRAPH_STORY_TITLE": "最近形成的场" if is_zh else "Formation field",
        "GRAPH_STORY_BODY": (
            "灰线是尚弱的关联，脉冲通路表示近期提问或治理动作正在把知识压缩成更稳定的结构。"
            if is_zh
            else "Gray links are weak affinities; pulsing routes show recent questions or governance actions compressing knowledge into more stable structures."
        ),
        "LEGEND_WEAK": "弱连接" if is_zh else "Weak affinity",
        "LEGEND_ACTIVE": "强化通路" if is_zh else "Reinforced route",
        "LEGEND_FORMING": "正在形成" if is_zh else "Forming knowledge",
        "LEGEND_STABLE": "稳定节点" if is_zh else "Stable knowledge",
        "STATS_TITLE": "知识概览" if is_zh else "Knowledge snapshot",
        "GRAPH_STATS_TITLE": "宇宙脉冲" if is_zh else "Universe pulse",
        "STAT_NODES": "节点" if is_zh else "Nodes",
        "STAT_EDGES": "连线" if is_zh else "Edges",
        "STAT_COVERAGE": "聚类覆盖" if is_zh else "Cluster coverage",
        "STAT_INSIGHTS": "候选知识" if is_zh else "Insight proposals",
        "OPEN_GRAPH_LINK": _nav_link(
            "展开宇宙" if is_zh else "Open universe",
            _localized_path("/portal/graph-view", active_locale),
            variant="action",
        ),
        "GRAPH_EXPAND_LABEL": "展开宇宙" if is_zh else "Open universe",
        "GRAPH_MODAL_TITLE": "知识详情" if is_zh else "Knowledge detail",
        "GRAPH_MODAL_CLOSE": "关闭" if is_zh else "Close",
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
            "pending": "待处理收件" if is_zh else "Pending inbox items",
            "health": "治理问题" if is_zh else "Health issues",
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
            "submit_text_busy": "提交中..." if is_zh else "Submitting...",
            "submit_file_busy": "上传中..." if is_zh else "Uploading...",
            "file_required": "请先选择文件、压缩包或文件夹" if is_zh else "Select a file, folder, or archive first.",
            "file_read_error": "读取文件失败" if is_zh else "Failed to read file.",
            "submit_text_success": "文本意见已提交，item_id=" if is_zh else "Text feedback submitted, item_id=",
            "submit_file_success": "文档已暂存，item_id=" if is_zh else "Document staged, item_id=",
            "submitted_text_prefix": "已提交文本意见：" if is_zh else "Submitted text feedback: ",
            "submitted_file_prefix": "已暂存文档：" if is_zh else "Staged document: ",
            "unknown_error": "未知错误" if is_zh else "Unknown error",
            "graph_modal_title": "知识详情" if is_zh else "Knowledge detail",
            "graph_modal_close": "关闭" if is_zh else "Close",
            "graph_event": "最近事件" if is_zh else "Recent event",
            "graph_focus_reason": "为什么出现在这里" if is_zh else "Why it appears here",
            "graph_focus_summary": "当前摘要" if is_zh else "Current summary",
            "graph_focus_hypothesis": "形成假设" if is_zh else "Formation hypothesis",
            "graph_supporting_entries": "支撑知识" if is_zh else "Supporting knowledge",
            "graph_trigger_queries": "触发问题" if is_zh else "Trigger queries",
            "graph_neighbor_nodes": "共同形成的邻近节点" if is_zh else "Nearby co-forming nodes",
            "graph_focus_empty": "当前还没有更多上下文。" if is_zh else "There is no additional context yet.",
            "graph_story_empty": "当前还没有足够强的形成事件。" if is_zh else "There are not enough strong formation events yet.",
        },
    }
    shell_kwargs = {
        "locale": active_locale,
        "page_script_name": "portal.js",
        "page_data": page_data,
        "shell_variant": "portal",
    }
    if page == "home":
        page_data.update(
            {
                "graphApi": _localized_path("/api/portal/graph", active_locale) + "&scene=home"
                if "?" in _localized_path("/api/portal/graph", active_locale)
                else _localized_path("/api/portal/graph", active_locale) + "?scene=home",
                "graphKind": "portal",
                "graphLocale": active_locale,
                "graphScene": "home",
            }
        )
        shell_kwargs["page_style_names"] = ["graph.bundle.css"]
        shell_kwargs["extra_script_names"] = ["graph.bundle.js"]
    return shared_shell(
        _document_title(page_title, knowledge_name),
        body,
        **shell_kwargs,
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
    page_title = "知识宇宙" if is_zh else "Knowledge universe"
    body = _render_html_template(
        "portal-graph-body.html",
        LOGO_INLINE=_logo_inline(),
        KNOWLEDGE_NAME=knowledge_name,
        INSTANCE_NAME=instance_name,
        PAGE_TITLE=page_title,
        GRAPH_HINT=(
            "点击节点进入聚焦，再点背景回到漫游。"
            if is_zh
            else "Click a node to focus, then click the void to drift again."
        ),
        GRAPH_CAPTION=(
            "这不是条目列表，而是最近仍在发光的知识形成瞬间。"
            if is_zh
            else "This is not a list of entries, but the moments of knowledge formation that still glow."
        ),
        MODAL_TITLE="知识详情" if is_zh else "Knowledge detail",
        MODAL_CLOSE="关闭" if is_zh else "Close",
        HOME_FLOAT_LINK=_nav_link(
            "返回知识库" if is_zh else "Back to knowledge base",
            _localized_path("/", active_locale),
            variant="action",
        ),
        OPEN_QUARTZ_LINK=_nav_link(
            "打开 Quartz" if is_zh else "Open Quartz",
            _localized_path("/quartz/", active_locale),
            variant="action",
            new_tab=True,
        ),
    )
    return shared_shell(
        _document_title(page_title, knowledge_name),
        body,
        locale=active_locale,
        page_script_name="graph.bundle.js",
        page_style_names=["graph.bundle.css"],
        page_data={
            "graphApi": _localized_path("/api/portal/graph", active_locale) + "&scene=full"
            if "?" in _localized_path("/api/portal/graph", active_locale)
            else _localized_path("/api/portal/graph", active_locale) + "?scene=full",
            "graphKind": "portal",
            "graphLocale": active_locale,
            "graphScene": "full",
            "entryPrefix": "/entries/",
            "ui": {
                "graph_modal_title": "知识详情" if is_zh else "Knowledge detail",
                "graph_modal_close": "关闭" if is_zh else "Close",
                "graph_event": "最近事件" if is_zh else "Recent event",
                "graph_focus_reason": "为什么出现在这里" if is_zh else "Why it appears here",
                "graph_focus_summary": "当前摘要" if is_zh else "Current summary",
                "graph_focus_hypothesis": "形成假设" if is_zh else "Formation hypothesis",
                "graph_supporting_entries": "支撑知识" if is_zh else "Supporting knowledge",
                "graph_trigger_queries": "触发问题" if is_zh else "Trigger queries",
                "graph_neighbor_nodes": "共同形成的邻近节点" if is_zh else "Nearby co-forming nodes",
                "graph_focus_empty": "当前还没有更多上下文。"
                if is_zh
                else "There is no additional context yet.",
                "graph_story_empty": "当前还没有足够强的形成事件。"
                if is_zh
                else "There are not enough strong formation events yet.",
            },
        },
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
        TOKEN_LABEL="登录令牌" if is_zh else "Sign-in token",
        TOKEN_PLACEHOLDER="输入所有者或提交者令牌" if is_zh else "Enter an owner or committer token",
        OPEN_ADMIN_LABEL="进入管理台" if is_zh else "Open admin",
        LOGIN_STATUS="需要有效令牌才能进入后台。" if is_zh else "A valid token is required.",
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
    allowed_sections = {"overview", "kb", "files", "inbox", "version_control", "reviews", "users", "system"}
    if section == "reviews":
        section = "inbox"
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
        "INBOX_LINK": _nav_link(
            "提交收件箱" if is_zh else "Submission Inbox",
            _localized_path("/admin/inbox", active_locale),
            primary=section == "inbox",
        ),
        "VERSION_CONTROL_LINK": _nav_link(
            "版本管理" if is_zh else "Version control",
            _localized_path("/admin/version-control", active_locale),
            primary=section == "version_control",
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
            QUEUE_NOTE="提交 / 评审 / 任务" if is_zh else "submissions / reviews / jobs",
            HEALTH_TITLE="治理健康度" if is_zh else "Health",
            HEALTH_NOTE="问题分布与阻断项" if is_zh else "severity distribution and blockers",
            ISSUE_TITLE="治理焦点" if is_zh else "Priority issues",
            ISSUE_NOTE="只读概览，不在这里直接执行操作" if is_zh else "Read-only overview for current blockers",
            ACTIVITY_TITLE="最近活动" if is_zh else "Recent activity",
            ACTIVITY_NOTE="审计与操作痕迹" if is_zh else "audit trail",
            EMERGING_TITLE="形成中的知识" if is_zh else "Emerging knowledge",
            EMERGING_NOTE="高频 latent clusters" if is_zh else "high-signal latent clusters",
            STRESS_TITLE="Canonical 压力点" if is_zh else "Canonical stress points",
            STRESS_NOTE="哪些正式知识正在被长尾问题围攻" if is_zh else "where long-tail questions keep converging",
        ),
        "kb": _render_html_template(
            "admin-kb-section.html",
            KB_WORKSPACE_TITLE="知识运营工作台" if is_zh else "Knowledge operations workspace",
            KB_WORKSPACE_NOTE=(
                "把导入、隐性知识形成、治理图和实时轨迹收进同一个知识运营表面。"
                if is_zh
                else "Bring ingest, latent knowledge formation, governance graph, and live runtime traces into one operational surface."
            ),
            PANE_OPERATIONS="操作" if is_zh else "Operations",
            PANE_INSIGHTS="Insights",
            PANE_GRAPH="图谱" if is_zh else "Graph",
            PANE_LIVE="Live",
            INGEST_TITLE="导入" if is_zh else "Ingest",
            INGEST_TIP=_tutorial_tip(
                "拖入文档后直接入队。" if is_zh else "Drop documents and enqueue immediately.",
                (
                    "支持 Markdown、文本、DOCX、PPTX 和 zip；也可以直接选择文件或文件夹。这里负责执行 ingest，不再展示独立 review 队列。"
                    if is_zh
                    else "Supports Markdown, text, DOCX, PPTX, and zip. You can also choose files or folders directly. This page executes ingest runs directly instead of sending them to a separate review queue."
                ),
                locale=active_locale,
                testid="admin-kb-ingest-tip",
            ),
            INGEST_DROPZONE_TITLE="拖入文档或压缩包" if is_zh else "Drop documents or an archive",
            INGEST_DROPZONE_BODY=(
                "支持 Markdown、文本、DOCX、PPTX 和 zip；也可以直接选择文件或文件夹。"
                if is_zh
                else "Supports Markdown, text, DOCX, PPTX, and zip. You can also choose files or folders directly."
            ),
            INGEST_FILE_LABEL="选择文件" if is_zh else "Choose files",
            INGEST_FILE_BUTTON="选择文件" if is_zh else "Choose files",
            INGEST_FILE_EMPTY="未选择文件" if is_zh else "No files selected",
            INGEST_FOLDER_LABEL="选择文件夹" if is_zh else "Choose folder",
            INGEST_FOLDER_BUTTON="选择文件夹" if is_zh else "Choose folder",
            INGEST_FOLDER_EMPTY="未选择文件夹" if is_zh else "No folder selected",
            FILE_PICKER_SELECTED_PREFIX="已选择" if is_zh else "Selected",
            FILE_PICKER_SELECTED_SUFFIX="个文件" if is_zh else "files",
            INGEST_SELECTION_LABEL="当前导入选择" if is_zh else "Current import selection",
            INGEST_SELECTION_EMPTY="还没有选择任何文档。" if is_zh else "No documents selected yet.",
            INGEST_BUTTON="上传并执行导入" if is_zh else "Upload and run ingest",
            INGEST_STATUS="下方运行台会同步显示请求与任务反馈。" if is_zh else "The runtime workspace below mirrors request and job feedback.",
            TIDY_TITLE="整理" if is_zh else "Tidy",
            TIDY_TIP=_tutorial_tip(
                "输入原因后直接发起治理。" if is_zh else "Enter a reason and queue maintenance.",
                (
                    "后台会按阻断性健康问题创建 tidy 任务。需要更大范围或更细粒度的整理时，建议改走 CLI 或专门任务。"
                    if is_zh
                    else "The admin UI creates a tidy job against blocking health issues. Use the CLI or a dedicated task when you need a broader or more granular cleanup."
                ),
                locale=active_locale,
                testid="admin-kb-tidy-tip",
            ),
            TIDY_REASON_LABEL="本次整理原因" if is_zh else "Tidy reason",
            TIDY_REASON_PLACEHOLDER="例如：整理悬空链接与未覆盖正式条目" if is_zh else "Example: clean up dangling links and uncovered formal entries",
            TIDY_BUTTON="执行整理" if is_zh else "Run tidy",
            TIDY_STATUS="创建任务后，请求与返回会同步写进下方运行台。" if is_zh else "Once the job is created, the request and response appear in the shared runtime workspace below.",
            EXPLORE_TITLE="探索" if is_zh else "Knowledge explore",
            EXPLORE_TIP=_tutorial_tip(
                "输入问题后直接运行；最终结果显示在下方结果区，过程持续写进 Live。" if is_zh else "Run the question directly; the final result appears in the shared result area below while the full trace stays in Live.",
                (
                    "探索不再把固定错误包装成“回答”。如果 Agent 输出无效、CLI 卡住或重试失败，公共结果区会直接显示失败，完整命令调用与终端输出会写到下方 Live。"
                    if is_zh
                    else "Explore no longer wraps fixed fallback text as an answer. When agent output is invalid, the CLI stalls, or retries fail, the shared result area shows an explicit failure and the full command / terminal trace is written into the Live panel below."
                ),
                locale=active_locale,
                testid="admin-kb-explore-tip",
            ),
            EXPLORE_INPUT_LABEL="问题 / 场景" if is_zh else "Question / scenario",
            EXPLORE_INPUT_PLACEHOLDER=(
                "例如：热备份在什么情况下不该当成主备切换方案？"
                if is_zh
                else "Example: when should hot backup not be treated as a failover strategy?"
            ),
            EXPLORE_BUTTON="运行探索" if is_zh else "Run explore",
            EXPLORE_STATUS="最终结果会显示在下方结果区。" if is_zh else "The final result appears in the shared result area below.",
            RUNTIME_TITLE="结果与 Live" if is_zh else "Result and Live",
            RUNTIME_TIP=_tutorial_tip(
                "上方显示最终结果，下方持续记录命令与终端轨迹。" if is_zh else "Final results stay on top while command and terminal traces keep streaming below.",
                (
                    "结果区固定在运行台顶部，不再塞回各自面板里触发重排；Live 维持更大的默认高度，并保留人工竖向缩放能力。"
                    if is_zh
                    else "The result area stays pinned to the top of the runtime workspace instead of reflowing inside individual panels; Live keeps a larger default height and can still be resized vertically."
                ),
                locale=active_locale,
                testid="admin-kb-runtime-tip",
            ),
            RESULT_TITLE="最终结果" if is_zh else "Final result",
            RESULT_STATUS="等待下一次运行结果。" if is_zh else "Waiting for the next runtime result.",
            RESULT_EMPTY=(
                "最终结果会显示在这里；完整命令与终端输出在下方 Live。"
                if is_zh
                else "Final results appear here; full commands and terminal output stay in Live below."
            ),
            LIVE_TITLE="Live",
            LIVE_CLEAR_BUTTON="清空记录" if is_zh else "Clear log",
            LIVE_STATUS="等待下一次导入 / 整理 / 探索。" if is_zh else "Waiting for the next ingest / tidy / explore run.",
            LIVE_EMPTY="LIVE READY\n" if is_zh else "LIVE READY\n",
            INSIGHTS_TITLE="形成中的知识" if is_zh else "Emerging insights",
            INSIGHTS_NOTE=(
                "这些候选还没有进入 canonical 共识层，但已经具备被审阅和提升的价值。"
                if is_zh
                else "These candidates are not canonical yet, but they already contain enough evidence to be reviewed and promoted."
            ),
            INSIGHTS_SUMMARY_EMPTY="等待 insight proposal..." if is_zh else "Waiting for insight proposals...",
            INSIGHT_DETAIL_TITLE="Proposal 详情" if is_zh else "Proposal detail",
            INSIGHT_DETAIL_TIP=_tutorial_tip(
                "查看假设、支撑条目和触发问题，然后决定下一步。" if is_zh else "Inspect the hypothesis, evidence, and trigger queries before deciding the next move.",
                (
                    "Promote 会创建新的 canonical entry；Merge 会把结论回灌到现有条目；Observe 和 Reject 只更新 insight 层。"
                    if is_zh
                    else "Promote creates a new canonical entry; Merge folds the conclusion back into an existing entry; Observe and Reject only mutate the insights layer."
                ),
                locale=active_locale,
                testid="admin-kb-insight-tip",
            ),
            INSIGHT_DETAIL_EMPTY="选择一条 proposal 以查看细节。" if is_zh else "Select a proposal to inspect its details.",
            INSIGHT_TARGET_PLACEHOLDER="merge 目标条目，例如：热备份" if is_zh else "Merge target, for example: hot backup",
            INSIGHT_TITLE_PLACEHOLDER="promote 后的新条目标题" if is_zh else "New canonical title for promote",
            INSIGHT_NOTE_PLACEHOLDER="可选备注" if is_zh else "Optional note",
            INSIGHT_ACTION_OBSERVE="继续观察" if is_zh else "Keep observing",
            INSIGHT_ACTION_MERGE="并入现有条目" if is_zh else "Merge",
            INSIGHT_ACTION_PROMOTE="提升为正式知识" if is_zh else "Promote",
            INSIGHT_ACTION_REJECT="拒绝" if is_zh else "Reject",
            INSIGHT_STATUS="选择动作后会创建受管 job，并写入版本历史。" if is_zh else "Each review action becomes a managed job and is recorded in version history.",
            GRAPH_TITLE="治理图" if is_zh else "Governance graph",
            GRAPH_NOTE=(
                "这张图表达 query cluster、insight proposal 与 canonical entry 之间的治理关系。"
                if is_zh
                else "This view shows the governance relationships between query clusters, insight proposals, and canonical entries."
            ),
            GRAPH_STATS_EMPTY="等待图谱载入..." if is_zh else "Waiting for graph data...",
            GRAPH_DETAIL_TITLE="图谱细节" if is_zh else "Graph detail",
            GRAPH_DETAIL_TIP=_tutorial_tip(
                "点击节点后，查看它和哪些知识或信号相连。" if is_zh else "Select a node to inspect the knowledge and signals connected to it.",
                (
                    "后台图优先强调证据、去向和动作，不追求门户图里的氛围动效。"
                    if is_zh
                    else "The admin graph prioritizes evidence, destinations, and actions rather than the atmospheric effects used in the portal graph."
                ),
                locale=active_locale,
                testid="admin-kb-graph-tip",
            ),
            GRAPH_DETAIL_EMPTY="点击图中的节点，查看证据和建议动作。" if is_zh else "Select a graph node to inspect evidence and suggested actions.",
        ),
        "files": _render_html_template(
            "admin-files-section.html",
            FILE_BROWSER_TITLE="文件入口" if is_zh else "File entry points",
            FILE_BROWSER_TIP=_tutorial_tip(
                (
                    "索引导航和健康队列并列作为入口，右侧编辑器保持常驻。"
                    if is_zh
                    else "Keep index navigation and the health queue as parallel entry points while the editor stays persistent on the right."
                ),
                (
                    "Tidy 会维护 index.root 与分段 index 的可导航性；文件管理页复用这套结构，并把治理健康队列作为同级入口，方便先定位、再编辑。"
                    if is_zh
                    else "Tidy maintains the navigability of index.root and segment indexes. This page reuses that structure and promotes the governance queue to a peer entry point so people can locate first and edit second."
                ),
                locale=active_locale,
                testid="admin-files-entry-tip",
            ),
            FILE_COUNTS_INDEXED="已纳入索引" if is_zh else "Indexed",
            FILE_COUNTS_UNINDEXED="未纳入索引" if is_zh else "Unindexed",
            FILE_SEARCH_LABEL="搜索并直接打开文档" if is_zh else "Search and open a document",
            FILE_SEARCH_PLACEHOLDER="输入标题、别名、路径或索引名称" if is_zh else "Search by title, alias, path, or index name",
            FILE_SEARCH_STATUS=(
                "输入后显示自动建议；用上下键选择，再按回车打开。"
                if is_zh
                else "Suggestions appear as you type. Use arrow keys to choose one, then press Enter to open it."
            ),
            FILE_ENTRY_TABS_LABEL="文件入口视图" if is_zh else "File entry views",
            FILE_ENTRY_TAB_INDEX="索引导航" if is_zh else "Index navigation",
            FILE_ENTRY_TAB_HEALTH="健康队列" if is_zh else "Health queue",
            DOC_STRUCTURE_TITLE="索引导航" if is_zh else "Index navigation",
            DOC_STRUCTURE_NOTE="按根索引与分段索引展开" if is_zh else "root and segment indexes",
            DOC_HEALTH_TITLE="健康队列" if is_zh else "Health queue",
            DOC_HEALTH_NOTE="按文档聚合并直达编辑器" if is_zh else "grouped by document and linked straight to the editor",
            EDITOR_TITLE="编辑控制台" if is_zh else "Editor console",
            EDITOR_NOTE="核心信息、预览、恢复和保存都集中在同一处" if is_zh else "Keep key context, preview, reset, and save controls together",
            EDITOR_CURRENT_LABEL="当前文档" if is_zh else "Current document",
            EDITOR_CURRENT_EMPTY="还没有选中文档。" if is_zh else "No document selected yet.",
            EDITOR_CURRENT_PATH_EMPTY="选择文档后在这里显示路径。" if is_zh else "The document path appears here after you open one.",
            EDITOR_CONTENT_LABEL="Markdown 内容" if is_zh else "Markdown content",
            EDITOR_PREVIEW_BUTTON="预览" if is_zh else "Preview",
            EDITOR_PREVIEW_CLOSE="关闭预览" if is_zh else "Close preview",
            EDITOR_CONSOLE_TABS_LABEL="文档信息视图" if is_zh else "Document info views",
            EDITOR_CONSOLE_TAB_META="元数据" if is_zh else "Metadata",
            EDITOR_CONSOLE_TAB_ISSUES="关联问题" if is_zh else "Linked issues",
            RESET_ENTRY_BUTTON="恢复" if is_zh else "Reset",
            RELOAD_ENTRY_BUTTON="重新载入" if is_zh else "Reload",
            EDITOR_RELOAD_TARGET="重新载入当前文档" if is_zh else "Reload current document",
            SAVE_ENTRY_BUTTON="保存 Markdown" if is_zh else "Save markdown",
            EDITOR_CLEAN_LABEL="已保存" if is_zh else "Saved",
            EDITOR_PREVIEW_TITLE="预览" if is_zh else "Preview",
            EDITOR_PREVIEW_EMPTY="选中文档后，可在弹窗里查看实时 Markdown 预览。" if is_zh else "After you select a document, open the modal to inspect the live Markdown preview.",
            EDITOR_LINKED_ISSUES_TITLE="关联问题" if is_zh else "Linked issues",
            EDITOR_META_TITLE="元数据" if is_zh else "Metadata",
            EDITOR_STATUS="这里会显示校验结果、保存反馈和冲突提示。" if is_zh else "Validation, save feedback, and conflict hints appear here.",
            EDITOR_SWITCH_TITLE="未保存的修改" if is_zh else "Unsaved changes",
            EDITOR_SWITCH_BODY=(
                "当前文件还有未保存的修改。继续操作会丢失这些内容。"
                if is_zh
                else "The current file has unsaved changes. Continuing will discard them."
            ),
            EDITOR_SWITCH_CANCEL="继续编辑" if is_zh else "Keep editing",
            EDITOR_SWITCH_CONFIRM="放弃并继续" if is_zh else "Discard and continue",
        ),
        "inbox": _render_html_template(
            "admin-inbox-section.html",
            OPEN_FEEDBACK_TITLE="文本意见" if is_zh else "Text feedback",
            OPEN_FEEDBACK_NOTE="人工查看后标记已解决，必要时可再恢复。" if is_zh else "Review manually, resolve when handled, and reopen when needed.",
            STAGED_TITLE="文档暂存区" if is_zh else "Document staging",
            STAGED_NOTE="上传原件先停在这里，可下载、移除或放入待导入区。" if is_zh else "Uploaded originals land here first. Download, remove, or move them to ready-to-ingest.",
            READY_TITLE="Ready To Ingest" if is_zh else "Ready To Ingest",
            READY_NOTE="勾选待导入文档后，跳转到知识库管理页并自动触发 ingest。" if is_zh else "Select ready documents, then jump to KB management and auto-start ingest.",
            INGESTING_TITLE="处理中" if is_zh else "In progress",
            INGESTING_NOTE="展示已经绑定到 ingest 批次、正在运行的文档。" if is_zh else "Documents already bound to an ingest batch and currently running.",
            HISTORY_TITLE="历史" if is_zh else "History",
            HISTORY_NOTE="已解决意见、已导入文档和移除记录都会沉到这里。" if is_zh else "Resolved feedback, ingested documents, and removed uploads land here.",
            READY_BUTTON="创建导入批次" if is_zh else "Create ingest batch",
            READY_STATUS="收件箱操作结果会显示在这里。" if is_zh else "Inbox action results appear here.",
        ),
        "version_control": _render_html_template(
            "admin-version-control-section.html",
            STATUS_TITLE="仓库状态" if is_zh else "Repository status",
            STATUS_NOTE="查看当前分支、工作区变更和仓库锁。" if is_zh else "Inspect the current branch, working tree changes, and repo lock.",
            COMMIT_TITLE="手工提交" if is_zh else "Manual commit",
            COMMIT_NOTE="文件管理页的修改会留在工作区，必须在这里填写理由后提交。" if is_zh else "Edits from file management stay in the working tree until you commit them here with a reason.",
            COMMIT_REASON_LABEL="提交理由" if is_zh else "Commit reason",
            COMMIT_REASON_PLACEHOLDER=(
                "第一行写摘要，后续补充原因或上下文。"
                if is_zh
                else "Use the first line as the summary, then add any context below."
            ),
            COMMIT_BUTTON="提交 tracked changes" if is_zh else "Commit tracked changes",
            PUSH_BUTTON="推送当前分支" if is_zh else "Push current branch",
            STATUS_LINE="版本管理操作反馈会显示在这里。" if is_zh else "Version-control action feedback appears here.",
            CHANGES_TITLE="待提交改动" if is_zh else "Pending tracked changes",
            COMMITS_TITLE="最近提交" if is_zh else "Recent commits",
        ),
        "users": _render_html_template(
            "admin-users-section.html",
            USERS_NOTE="仅所有者可操作" if is_zh else "Owner only",
            CREATE_TITLE="新增提交者" if is_zh else "Create committer",
            NAME_LABEL="姓名" if is_zh else "Name",
            NAME_PLACEHOLDER="例如：运维提交者" if is_zh else "Example: Ops Committer",
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
            SETTINGS_NOTE="仅所有者可查看与修改" if is_zh else "owner-only view and edit",
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
        extra_script_names=["graph.bundle.js"],
        page_style_names=["graph.bundle.css"],
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
                "stats_reviews": "待处理反馈" if is_zh else "Open feedback",
                "stats_blocking": "阻断问题" if is_zh else "Blocking issues",
                "stats_stale": "陈旧任务" if is_zh else "Stale jobs",
                "issue_empty": "当前没有需要立即处理的问题。" if is_zh else "No urgent issues right now.",
                "issue_scope_label": "建议范围" if is_zh else "Suggested scope",
                "issue_action_label": "建议动作" if is_zh else "Suggested action",
                "issue_target_label": "目标" if is_zh else "Target",
                "issue_open_document": "打开文档" if is_zh else "Open document",
                "submission_empty": "暂无待处理提交。" if is_zh else "No buffered submissions right now.",
                "inbox_empty": "收件箱当前为空。" if is_zh else "The inbox is empty right now.",
                "inbox_feedback_empty": "当前没有待处理文本意见。" if is_zh else "No open text feedback right now.",
                "inbox_documents_empty": "当前没有暂存文档。" if is_zh else "No staged documents right now.",
                "inbox_ready_empty": "当前没有 ready to ingest 文档。" if is_zh else "No ready-to-ingest documents right now.",
                "inbox_ingesting_empty": "当前没有正在 ingest 的文档。" if is_zh else "No documents are ingesting right now.",
                "inbox_history_empty": "当前还没有历史记录。" if is_zh else "No inbox history yet.",
                "inbox_resolve": "已解决" if is_zh else "Resolve",
                "inbox_reopen": "恢复为未解决" if is_zh else "Reopen",
                "inbox_mark_ready": "放入待导入区" if is_zh else "Move to ready",
                "inbox_move_to_staged": "移回暂存区" if is_zh else "Move back to staged",
                "inbox_remove": "移除" if is_zh else "Remove",
                "inbox_download": "下载原件" if is_zh else "Download",
                "inbox_resolved": "文本意见已标记为已解决。" if is_zh else "Feedback marked as resolved.",
                "inbox_reopened": "文本意见已恢复为未解决。" if is_zh else "Feedback reopened.",
                "inbox_marked_ready": "文档已放入待导入区。" if is_zh else "Document moved to ready.",
                "inbox_moved_to_staged": "文档已移回暂存区。" if is_zh else "Document moved back to staged.",
                "inbox_removed": "文档已移除。" if is_zh else "Document removed.",
                "inbox_select_ready_required": "请至少选择一个 ready 文档。" if is_zh else "Select at least one ready document.",
                "inbox_batch_created": "已创建导入批次，正在跳转到知识库管理。" if is_zh else "Ingest batch created. Redirecting to KB management.",
                "inbox_batch_redirected": "已为批次自动触发 ingest：" if is_zh else "Auto-started ingest for batch: ",
                "review_empty": "暂无待审补丁。" if is_zh else "No pending reviews right now.",
                "job_empty": "暂无任务。" if is_zh else "No jobs right now.",
                "audit_empty": "暂无审计日志。" if is_zh else "No audit logs yet.",
                "diff_empty": "选择待审补丁后在这里查看差异。" if is_zh else "Select a pending review to inspect its diff here.",
                "editor_loaded": "已加载" if is_zh else "Loaded",
                "editor_saved": "保存成功" if is_zh else "Saved",
                "editor_reset": "已恢复到最近一次载入的内容" if is_zh else "Reset to the last loaded content",
                "editor_reloaded": "已重新载入服务器版本" if is_zh else "Reloaded the latest server version",
                "editor_preview_empty": "预览将在这里显示。" if is_zh else "Preview appears here.",
                "editor_linked_issues_empty": "当前文档没有关联治理问题。" if is_zh else "No linked governance issues for this document.",
                "file_dirty": "未保存修改" if is_zh else "Unsaved changes",
                "file_clean": "已保存" if is_zh else "Saved",
                "file_current_path_empty": (
                    "选择文档后在这里显示路径。"
                    if is_zh
                    else "The document path appears here after you open one."
                ),
                "file_exit_warning": (
                    "当前文件还有未保存的修改。"
                    if is_zh
                    else "The current file has unsaved changes."
                ),
                "explore_answer": "回答" if is_zh else "Answer",
                "explore_sources": "来源" if is_zh else "Sources",
                "explore_gaps": "缺口" if is_zh else "Gaps",
                "explore_confidence": "置信度" if is_zh else "Confidence",
                "result_ready": "等待下一次运行结果。" if is_zh else "Waiting for the next runtime result.",
                "result_running": "等待 Agent 最终结果；完整过程见下方 Live。" if is_zh else "Waiting for the final agent result; see Live below for the full trace.",
                "explore_running": "正在运行探索，详情见 Live。" if is_zh else "Explore is running; see Live for details.",
                "explore_completed": "探索已完成。" if is_zh else "Explore completed.",
                "explore_failed": "探索失败" if is_zh else "Explore failed",
                "explore_invalid_output": (
                    "Agent 返回了内部运行内容，结果区已改为失败提示；原始轨迹请查看下方 Live。"
                    if is_zh
                    else "The agent returned internal runtime content, so the result area was downgraded to a failure message. Check Live below for the raw trace."
                ),
                "explore_failed_hint": "请查看下方 Live 区的命令调用与终端输出。" if is_zh else "Check the Live panel below for the command trace and terminal output.",
                "explore_no_result": "探索结束了，但没有收到最终 Agent 输出。" if is_zh else "The explore run finished without a final agent result.",
                "live_ready": "等待下一次导入 / 整理 / 探索。" if is_zh else "Waiting for the next ingest / tidy / explore run.",
                "live_running": "Live 正在接收运行事件..." if is_zh else "Live is receiving runtime events...",
                "live_cleared": "Live 记录已清空。" if is_zh else "Live log cleared.",
                "live_request_label": "请求" if is_zh else "Request",
                "live_response_label": "响应" if is_zh else "Response",
                "live_command_label": "命令" if is_zh else "Command",
                "live_command_redacted": (
                    "Agent CLI 已启动；内部 prompt / schema 细节已隐藏。"
                    if is_zh
                    else "Agent CLI launched; internal prompt/schema details are hidden."
                ),
                "live_stdout_label": "标准输出" if is_zh else "Stdout",
                "live_stderr_label": "标准错误" if is_zh else "Stderr",
                "live_status_label": "状态" if is_zh else "Status",
                "live_retry_label": "重试" if is_zh else "Retry",
                "live_excerpt_redacted": (
                    "内部运行摘录已隐藏；如需诊断，请查看安全失败提示。"
                    if is_zh
                    else "Internal runtime excerpt hidden; use the failure summary for diagnostics."
                ),
                "live_error_label": "错误" if is_zh else "Error",
                "live_result_label": "结果" if is_zh else "Result",
                "live_done_label": "结束" if is_zh else "Done",
                "manual_tidy_reason_required": "请填写整理原因。" if is_zh else "Enter a tidy reason.",
                "ingest_file_required": "请先拖入或选择至少一个文档。" if is_zh else "Drop or choose at least one document first.",
                "ingest_selection_empty": "还没有选择任何文档。" if is_zh else "No documents selected yet.",
                "ingest_selected_prefix": "当前已选择" if is_zh else "Selected",
                "ingest_selected_suffix": "个文件" if is_zh else "files",
                "ingest_uploaded": "已创建导入任务：" if is_zh else "Created ingest: ",
                "ingest_item_prefix": "条目" if is_zh else "item",
                "ingest_submission_prefix": "提交" if is_zh else "submission",
                "doc_group_formal": "正式条目" if is_zh else "Formal entries",
                "doc_group_placeholder": "Placeholders" if not is_zh else "待补全条目",
                "doc_group_index": "索引" if is_zh else "Indexes",
                "doc_counts_formal": "正式条目" if is_zh else "Formal",
                "doc_counts_placeholder": "待补全" if is_zh else "Placeholders",
                "doc_counts_index": "索引" if is_zh else "Indexes",
                "doc_browser_empty": "没有匹配的文档。" if is_zh else "No matching documents.",
                "doc_health_empty": "当前没有可联动的治理问题。" if is_zh else "No governance issues to link right now.",
                "doc_selected": "已选中文档：" if is_zh else "Selected document: ",
                "doc_select_prompt": "请先从左侧入口选择一个文档。" if is_zh else "Select a document from the left entry pane first.",
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
                "run_ingest": "执行导入" if is_zh else "Run ingest",
                "show_diff": "查看详情" if is_zh else "Open detail",
                "approve": "批准" if is_zh else "Approve",
                "reject_review": "拒绝" if is_zh else "Reject",
                "retry": "重试" if is_zh else "Retry",
                "cancel": "取消" if is_zh else "Cancel",
                "logout_done": "已退出登录。" if is_zh else "Signed out.",
                "tidy_done": "已创建整理任务：" if is_zh else "Created tidy job: ",
                "ingest_done": "已创建导入任务：" if is_zh else "Created ingest job: ",
                "review_loaded": "已加载评审差异：" if is_zh else "Loaded review diff: ",
                "review_approved": "已批准评审：" if is_zh else "Approved review: ",
                "review_rejected": "已退回评审：" if is_zh else "Rejected review: ",
                "job_retried": "任务已重新入队：" if is_zh else "Requeued job: ",
                "job_cancelled": "任务已请求取消：" if is_zh else "Cancellation requested for job: ",
                "job_running_prefix": "任务状态：" if is_zh else "Job status: ",
                "job_completed_prefix": "已生成提交：" if is_zh else "Committed as: ",
                "job_monitor_timeout": "等待任务结果超时，请稍后刷新页面。" if is_zh else "Timed out while waiting for the job result. Refresh the page in a moment.",
                "job_monitor_missing": "缺少任务编号。" if is_zh else "Missing job id.",
                "job_result_empty": "任务已完成，但没有返回摘要。" if is_zh else "The job finished without a summary.",
                "job_type_label": "任务类型" if is_zh else "Job type",
                "job_change_count_label": "变更文件数" if is_zh else "Changed files",
                "job_commit_label": "提交" if is_zh else "Commit",
                "job_changed_items_label": "变更条目" if is_zh else "Changed items",
                "version_repo_root": "仓库根目录" if is_zh else "Repo root",
                "version_branch": "当前分支" if is_zh else "Current branch",
                "version_upstream": "上游状态" if is_zh else "Upstream",
                "version_upstream_ready": "已配置 upstream" if is_zh else "Upstream configured",
                "version_upstream_missing": "未配置 upstream" if is_zh else "No upstream configured",
                "version_repo_lock": "仓库锁" if is_zh else "Repo lock",
                "version_repo_lock_free": "空闲" if is_zh else "Idle",
                "version_no_changes": "tracked 路径当前没有未提交改动。" if is_zh else "No uncommitted changes under tracked paths.",
                "version_commits_empty": "还没有可显示的提交记录。" if is_zh else "No recent commits to show.",
                "version_revert": "回退" if is_zh else "Revert",
                "version_commit_done": "已创建提交：" if is_zh else "Created commit: ",
                "version_push_done": "已推送分支：" if is_zh else "Pushed branch: ",
                "version_revert_done": "已创建回退提交：" if is_zh else "Created revert commit: ",
                "quartz_ready": "Quartz 站点已就绪" if is_zh else "Quartz site is ready",
                "quartz_missing_site": "尚未构建实例站点" if is_zh else "Instance site is not built yet",
                "quartz_missing_runtime": "Quartz 运行时不可用" if is_zh else "Quartz runtime is unavailable",
                "quartz_runtime_path": "运行时路径" if is_zh else "runtime path",
                "quartz_site_path": "站点路径" if is_zh else "site path",
                "quartz_built_at": "最后构建时间" if is_zh else "last built",
                "quartz_build_success": "Quartz 站点已刷新。" if is_zh else "Quartz site refreshed.",
                "token_revealed": "访问令牌已就地展开。" if is_zh else "Token expanded inline.",
                "token_show": "显示令牌" if is_zh else "Show token",
                "token_hide": "收起令牌" if is_zh else "Hide token",
                "token_label": "Token" if not is_zh else "访问令牌",
                "disable_user": "停用" if is_zh else "Disable",
                "user_created": "用户已创建：" if is_zh else "Created user: ",
                "user_disabled": "用户已停用：" if is_zh else "Disabled user: ",
                "current_session": "当前会话" if is_zh else "Current session",
                "user_disabled_label": "已停用" if is_zh else "Disabled",
                "role_owner": "所有者" if is_zh else "owner",
                "role_committer": "提交者" if is_zh else "committer",
                "review_selected": "已载入评审：" if is_zh else "Loaded review: ",
                "review_select_prompt": "先从左侧选择一个待审补丁。" if is_zh else "Select a pending review from the left first.",
                "review_summary": "改动摘要" if is_zh else "Patch summary",
                "review_source_submission": "来源提交" if is_zh else "Source submission",
                "review_job_type": "任务类型" if is_zh else "Job type",
                "review_decision": "当前状态" if is_zh else "Current state",
                "review_patch_count": "变更数" if is_zh else "Operations",
                "review_created_at": "创建时间" if is_zh else "Created",
                "review_submission_status": "提交状态" if is_zh else "Submission status",
                "review_submission_author": "提交者" if is_zh else "Submitter",
                "review_queue_empty_detail": "当前没有待审补丁。" if is_zh else "There is no pending review right now.",
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
                "file_search_hint": (
                    "输入后显示自动建议；用上下键选择，再按回车打开。"
                    if is_zh
                    else "Suggestions appear as you type. Use arrow keys to choose one, then press Enter to open it."
                ),
                "file_search_matches": "条匹配" if is_zh else "matches",
                "file_unindexed_group": "未纳入任何索引的文档" if is_zh else "Documents outside all indexes",
                "file_index_direct_docs": "直接文档" if is_zh else "Direct documents",
                "file_index_child_indexes": "子索引" if is_zh else "Child indexes",
                "file_tokens_label": "令牌估算" if is_zh else "tokens",
            },
            "quartz": quartz,
        },
        shell_variant="admin",
    )
