# ruff: noqa: E501
from __future__ import annotations

import json
from functools import lru_cache
from urllib.parse import quote

from sediment.package_data import read_asset_text, render_asset_template


@lru_cache(maxsize=1)
def _logo_mark_svg() -> str:
    return read_asset_text("logo-mark.svg").strip()


@lru_cache(maxsize=1)
def _logo_mark_data_uri() -> str:
    return f"data:image/svg+xml;utf8,{quote(_logo_mark_svg())}"


def _logo_inline(class_name: str = "brand-mark") -> str:
    return _logo_mark_svg().replace("<svg ", f'<svg class="{class_name}" aria-hidden="true" ')


def _normalize_locale(locale: str | None) -> str:
    return "zh" if str(locale or "").strip().lower().startswith("zh") else "en"


def _html_lang(locale: str) -> str:
    return "zh-CN" if _normalize_locale(locale) == "zh" else "en"


def _localized_path(path: str, locale: str) -> str:
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}lang={_normalize_locale(locale)}"


def _nav_link(label: str, href: str, *, primary: bool = False) -> str:
    classes = "button primary" if primary else "button"
    return f'<a class="{classes}" href="{href}">{label}</a>'


def _render_html_template(name: str, **replacements: str) -> str:
    return render_asset_template(name, replacements)


def _asset_url(name: str) -> str:
    return f"/ui-assets/{name}"


def _json_script_payload(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")


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
            "门户首页" if is_zh else "Home",
            _localized_path("/", active_locale),
            primary=page == "home",
        ),
        "SEARCH_LINK": _nav_link(
            "搜索" if is_zh else "Search",
            _localized_path("/search", active_locale),
            primary=page == "search",
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
) -> str:
    active_locale = _normalize_locale(locale)
    is_zh = active_locale == "zh"
    page = page if page in {"home", "search", "entry", "submit"} else "home"
    nav = _public_nav(active_locale, page=page)
    subtitles = {
        "home": "搜索" if is_zh else "Search",
        "search": "全文搜索" if is_zh else "Full-text search",
        "entry": "正式条目" if is_zh else "Canonical entry",
        "submit": "提交缓冲区" if is_zh else "Buffered submission",
    }
    common = {
        "LOGO_INLINE": _logo_inline(),
        "KNOWLEDGE_NAME": knowledge_name,
        "INSTANCE_NAME": instance_name,
        "ACTIVE_LOCALE": active_locale,
        "PAGE_KICKER": subtitles[page],
        "SEARCH_PLACEHOLDER": (
            "搜索概念、规则、经验，比如：热备份 泄洪 暗流"
            if is_zh
            else "Search concepts, rules, or lessons. Example: hot backup failover stream"
        ),
        "SEARCH_BUTTON_LABEL": "搜索" if is_zh else "Search",
        "STATS_TITLE": "门户统计" if is_zh else "Portal stats",
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
        **nav,
    }
    templates = {
        "home": "portal-home-body.html",
        "search": "portal-search-body.html",
        "entry": "portal-entry-body.html",
        "submit": "portal-submit-body.html",
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
        "user": current_user,
        "routes": {
            "home": _localized_path("/", active_locale),
            "search": _localized_path("/search", active_locale),
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
        f"{knowledge_name} Portal",
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
    admin_kb_path: str,
) -> str:
    active_locale = _normalize_locale(locale)
    is_zh = active_locale == "zh"
    body = _render_html_template(
        "portal-quartz-fallback-body.html",
        LOGO_INLINE=_logo_inline(),
        KNOWLEDGE_NAME=knowledge_name,
        INSTANCE_NAME=instance_name,
        HOME_LINK=_nav_link("门户首页" if is_zh else "Home", _localized_path("/", active_locale)),
        SEARCH_LINK=_nav_link("搜索" if is_zh else "Search", _localized_path("/search", active_locale)),
        SUBMIT_LINK=_nav_link("提交" if is_zh else "Submit", _localized_path("/submit", active_locale)),
        QUARTZ_LINK=_nav_link("Quartz", _localized_path("/quartz/", active_locale), primary=True),
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
            "前往管理台系统页" if is_zh else "Open admin system page",
            _localized_path("/admin/system", active_locale),
            primary=True,
        ),
        OPEN_QUARTZ_LINK=_nav_link(
            "打开 Quartz" if is_zh else "Open Quartz",
            _localized_path("/quartz/", active_locale),
            primary=True,
        ),
    )
    return shared_shell(
        f"{knowledge_name} Quartz",
        body,
        locale=active_locale,
        shell_variant="portal",
    )


def admin_login_html(*, knowledge_name: str, instance_name: str, locale: str, next_path: str) -> str:
    active_locale = _normalize_locale(locale)
    is_zh = active_locale == "zh"
    body = _render_html_template(
        "admin-login-body.html",
        LOGO_INLINE=_logo_inline(),
        KNOWLEDGE_NAME=knowledge_name,
        INSTANCE_NAME=instance_name,
        HOME_LINK=_nav_link("门户首页" if is_zh else "Home", _localized_path("/", active_locale)),
        SEARCH_LINK=_nav_link("搜索" if is_zh else "Search", _localized_path("/search", active_locale)),
        SUBMIT_LINK=_nav_link("提交" if is_zh else "Submit", _localized_path("/submit", active_locale)),
        QUARTZ_LINK=_nav_link("Quartz", _localized_path("/quartz/", active_locale)),
        TOKEN_LABEL="登录 Token" if is_zh else "Sign-in token",
        TOKEN_PLACEHOLDER="输入 owner 或 committer token" if is_zh else "Enter an owner or committer token",
        OPEN_ADMIN_LABEL="进入管理台" if is_zh else "Open admin",
        LOGIN_STATUS="需要有效 token 才能进入后台。" if is_zh else "A valid token is required.",
    )
    return shared_shell(
        f"{knowledge_name} Admin Login",
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
    allowed_sections = {"overview", "kb", "reviews", "users", "system"}
    section = section if section in allowed_sections else "overview"
    is_owner = bool(current_user and current_user.get("role") == "owner")
    section_links = {
        "OVERVIEW_LINK": _nav_link(
            "总览" if is_zh else "Overview",
            _localized_path("/admin/overview", active_locale),
            primary=section == "overview",
        ),
        "KB_LINK": _nav_link(
            "知识库" if is_zh else "KB",
            _localized_path("/admin/kb", active_locale),
            primary=section == "kb",
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
                "系统" if is_zh else "System",
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
            EXPLORE_TITLE="知识探索" if is_zh else "KB explore",
            EXPLORE_NOTE="知识库问答" if is_zh else "KB Q&A",
            EXPLORE_INPUT_LABEL="问题 / 场景" if is_zh else "Question / scenario",
            EXPLORE_INPUT_PLACEHOLDER=(
                "例如：热备份在什么情况下不该当成主备切换方案？"
                if is_zh
                else "Example: when should hot backup not be treated as a failover strategy?"
            ),
            EXPLORE_BUTTON="运行探索" if is_zh else "Run explore",
            EXPLORE_RESULT_EMPTY="这里会显示回答、来源和缺口。" if is_zh else "Answers, sources, and gaps appear here.",
            SUBMISSION_TITLE="待处理提交" if is_zh else "Buffered submissions",
            SUBMISSION_NOTE="匿名提交默认开启" if is_zh else "Anonymous by default",
            TIDY_TITLE="KB 级维护" if is_zh else "KB-level tidy",
            TIDY_NOTE="按 scope 发起治理任务" if is_zh else "Queue maintenance by scope",
            TIDY_SCOPE_LABEL="维护范围" if is_zh else "Scope",
            TIDY_SCOPE_FULL="全库维护" if is_zh else "Full KB",
            TIDY_SCOPE_GRAPH="图谱修复" if is_zh else "Graph repair",
            TIDY_SCOPE_INDEXES="索引整理" if is_zh else "Index cleanup",
            TIDY_SCOPE_HEALTH_BLOCKING="阻断问题" if is_zh else "Blocking health issues",
            TIDY_REASON_LABEL="原因" if is_zh else "Reason",
            TIDY_REASON_PLACEHOLDER="例如：修复图谱断链与孤岛条目" if is_zh else "Example: repair dangling links and orphan entries",
            TIDY_BUTTON="发起 Tidy" if is_zh else "Run tidy",
            ISSUE_TITLE="健康问题队列" if is_zh else "Health issue queue",
            ISSUE_NOTE="逐条阅读问题，但只通过上面的 KB 级 tidy 发起治理" if is_zh else "Review issues here, but queue maintenance only through the KB-level tidy controls above",
            EDITOR_TITLE="在线编辑" if is_zh else "Inline editor",
            EDITOR_NAME_LABEL="条目名" if is_zh else "Entry name",
            EDITOR_NAME_PLACEHOLDER="例如：热备份" if is_zh else "Example: hot-backup",
            LOAD_ENTRY_BUTTON="加载条目" if is_zh else "Load entry",
            EDITOR_CONTENT_LABEL="内容" if is_zh else "Content",
            SAVE_ENTRY_BUTTON="保存条目" if is_zh else "Save entry",
            EDITOR_STATUS="这里会显示校验结果和保存反馈。" if is_zh else "Validation and save feedback appears here.",
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
            SYSTEM_TITLE="系统状态" if is_zh else "System status",
            SYSTEM_NOTE="仅所有者可操作" if is_zh else "Owner only",
            QUARTZ_TITLE="Quartz" if is_zh else "Quartz",
            QUARTZ_NOTE="运行时 / 构建状态 / 刷新" if is_zh else "runtime / build state / refresh",
            QUARTZ_BUTTON="构建 / 刷新 Quartz" if is_zh else "Build / refresh Quartz",
            OPEN_QUARTZ_LINK=_nav_link(
                "打开 Quartz" if is_zh else "Open Quartz",
                _localized_path("/quartz/", active_locale),
            ),
        ),
    }[section]
    body = _render_html_template(
        "admin-body.html",
        LOGO_INLINE=_logo_inline(),
        KNOWLEDGE_NAME=knowledge_name,
        INSTANCE_NAME=instance_name,
        READY_MESSAGE="管理台加载中..." if is_zh else "Loading admin...",
        PORTAL_LINK=_nav_link("返回门户" if is_zh else "Back to portal", _localized_path("/", active_locale)),
        LOGOUT_LABEL="退出登录" if is_zh else "Log out",
        SECTION_MARKUP=section_markup,
        **section_links,
    )
    return shared_shell(
        f"{knowledge_name} Admin",
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
                "submission_empty": "暂无待处理提交。" if is_zh else "No buffered submissions right now.",
                "review_empty": "暂无待审补丁。" if is_zh else "No pending reviews right now.",
                "job_empty": "暂无任务。" if is_zh else "No jobs right now.",
                "audit_empty": "暂无审计日志。" if is_zh else "No audit logs yet.",
                "diff_empty": "选择待审 patch 后在这里查看。" if is_zh else "Select a pending review to inspect its diff here.",
                "editor_loaded": "已加载" if is_zh else "Loaded",
                "editor_saved": "保存成功" if is_zh else "Saved",
                "explore_answer": "回答" if is_zh else "Answer",
                "explore_sources": "来源" if is_zh else "Sources",
                "explore_gaps": "缺口" if is_zh else "Gaps",
                "explore_confidence": "置信度" if is_zh else "Confidence",
                "manual_tidy_reason_required": "请填写 tidy 原因。" if is_zh else "Enter a tidy reason.",
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
            },
            "quartz": quartz,
        },
        shell_variant="admin",
    )
