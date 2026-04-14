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
) -> str:
    active_locale = _normalize_locale(locale)
    toggle_label = "EN" if active_locale == "zh" else "中文"
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
        SHELL_DATA=_json_script_payload({"toggleLabel": toggle_label}),
        PAGE_DATA_TAG=page_data_tag,
        PAGE_SCRIPT_TAG=page_script_tag,
    )


def portal_html(*, knowledge_name: str, instance_name: str, locale: str) -> str:
    active_locale = _normalize_locale(locale)
    is_zh = active_locale == "zh"
    copy = {
        "portal": "知识门户" if is_zh else "Portal",
        "graph": "Quartz 图谱" if is_zh else "Quartz Graph",
        "admin": "管理台" if is_zh else "Admin",
        "subtitle": (
            f"Sediment Knowledge Portal · 实例：{instance_name}"
            if is_zh
            else f"Sediment Knowledge Portal · instance: {instance_name}"
        ),
        "hero": (
            "把主要空间留给全文搜索，把图谱放到独立的 Quartz 页面；门户负责稳定搜索、查看正式知识，并把新概念和文档送入提交缓冲区。"
            if is_zh
            else "Keep the main surface focused on search. Quartz gets its own graph page, while the portal handles retrieval, reading, and buffered submissions."
        ),
        "message": (
            "门户已就绪，可以搜索正式知识，或把新材料提交到缓冲区。"
            if is_zh
            else "The portal is ready. Search the formal knowledge layer or submit new material into the buffer."
        ),
        "search_title": "全文搜索" if is_zh else "Full-text search",
        "search_hint": (
            "标题、别名、摘要、正文。点击结果可弹出全文。"
            if is_zh
            else "Title, aliases, summary, and body. Click any result to open the full entry."
        ),
        "search_placeholder": (
            "搜索概念、规则、教训，比如：热备份 泄洪 暗流"
            if is_zh
            else "Search concepts, rules, or lessons. Example: hot backup failover stream"
        ),
        "search_button": "搜索" if is_zh else "Search",
        "search_idle": "输入关键词后即可全文搜索。" if is_zh else "Enter keywords to start searching.",
        "updates": "最近更新" if is_zh else "Recent updates",
        "updates_empty": "暂无最近更新" if is_zh else "No recent updates yet.",
        "buffer": "提交到缓冲区" if is_zh else "Submit to the buffer",
        "buffer_note": (
            "所有提交都会进入缓冲区，由 committer 审核后才能进入正式知识层。系统会记录你的名字与来源 IP，并限制同一 IP 每分钟最多提交 1 次。"
            if is_zh
            else "Every submission enters a review buffer first. A committer promotes it into the formal knowledge layer after review. Sediment records submitter name and source IP, and rate-limits each IP to one submission per minute."
        ),
        "text_title": "纯文本概念 / 经验" if is_zh else "Plain-text concept / lesson",
        "name": "你的名字" if is_zh else "Your name",
        "name_ph": "例如：Alice" if is_zh else "Example: Alice",
        "title": "标题" if is_zh else "Title",
        "title_ph": "例如：泄洪前先确认热备份" if is_zh else "Example: Verify hot backup before flood release",
        "type": "类型" if is_zh else "Type",
        "concept": "概念" if is_zh else "Concept",
        "lesson": "经验" if is_zh else "Lesson",
        "feedback": "意见" if is_zh else "Feedback",
        "content": "内容" if is_zh else "Content",
        "content_ph": (
            "写下你的概念、经验、修订建议或问题背景。"
            if is_zh
            else "Describe the concept, lesson, correction, or background in your own words."
        ),
        "submit_text": "提交文本" if is_zh else "Submit text",
        "text_status": (
            "文本提交前会先经过 Agent 扫描知识库，并给出 committer 建议。"
            if is_zh
            else "Before the text is stored, an Agent scans the KB and produces committer-facing suggestions."
        ),
        "analysis_idle": (
            "这里会显示提交前后的建议摘要，帮助 committer 更快判断。"
            if is_zh
            else "The recommendation summary appears here to help the committer triage quickly."
        ),
        "modal_empty": "点击搜索结果后在这里查看。" if is_zh else "Click a search result to preview it here.",
        "upload_title": "文档上传" if is_zh else "Document upload",
        "upload_file": "上传文件 / 压缩包" if is_zh else "Upload file / archive",
        "upload_folder": "上传文件夹" if is_zh else "Upload folder",
        "submit_file": "上传文档" if is_zh else "Upload documents",
        "file_status": (
            "支持单文件、文件夹和 zip 压缩包。系统会自动解压并提取其中的文本。"
            if is_zh
            else "Supports single files, folders, and zip archives. Sediment extracts text automatically."
        ),
        "entry_title": "条目全文" if is_zh else "Entry",
        "close": "关闭" if is_zh else "Close",
    }
    body = _render_html_template(
        "portal-body.html",
        LOGO_INLINE=_logo_inline(),
        KNOWLEDGE_NAME=knowledge_name,
        NAV_PORTAL=_nav_link(copy["portal"], _localized_path("/portal", active_locale), primary=True),
        NAV_GRAPH=_nav_link(copy["graph"], _localized_path("/portal/graph-view", active_locale)),
        NAV_ADMIN=_nav_link(copy["admin"], _localized_path("/admin", active_locale)),
        SUBTITLE=copy["subtitle"],
        HERO_TEXT=copy["hero"],
        MESSAGE=copy["message"],
        SEARCH_TITLE=copy["search_title"],
        SEARCH_HINT=copy["search_hint"],
        SEARCH_PLACEHOLDER=copy["search_placeholder"],
        SEARCH_BUTTON=copy["search_button"],
        SEARCH_IDLE=copy["search_idle"],
        UPDATES_TITLE=copy["updates"],
        UPDATES_LINK=_nav_link(copy["graph"], _localized_path("/portal/graph-view", active_locale)),
        BUFFER_TITLE=copy["buffer"],
        BUFFER_NOTE=copy["buffer_note"],
        TEXT_TITLE=copy["text_title"],
        NAME_LABEL=copy["name"],
        NAME_PLACEHOLDER=copy["name_ph"],
        TITLE_LABEL=copy["title"],
        TITLE_PLACEHOLDER=copy["title_ph"],
        TYPE_LABEL=copy["type"],
        TYPE_CONCEPT=copy["concept"],
        TYPE_LESSON=copy["lesson"],
        TYPE_FEEDBACK=copy["feedback"],
        CONTENT_LABEL=copy["content"],
        CONTENT_PLACEHOLDER=copy["content_ph"],
        SUBMIT_TEXT_LABEL=copy["submit_text"],
        TEXT_STATUS=copy["text_status"],
        ANALYSIS_IDLE=copy["analysis_idle"],
        UPLOAD_TITLE=copy["upload_title"],
        UPLOAD_FILE_LABEL=copy["upload_file"],
        UPLOAD_FOLDER_LABEL=copy["upload_folder"],
        SUBMIT_FILE_LABEL=copy["submit_file"],
        FILE_STATUS=copy["file_status"],
        ENTRY_TITLE=copy["entry_title"],
        CLOSE_LABEL=copy["close"],
        MODAL_EMPTY=copy["modal_empty"],
    )

    page_data = {
        "formal_entries": "正式条目" if is_zh else "Formal entries",
        "placeholders": "缺口条目" if is_zh else "Placeholders",
        "indexes": "索引" if is_zh else "Indexes",
        "pending": "待审提交" if is_zh else "Pending submissions",
        "health": "Health 问题" if is_zh else "Health issues",
        "updates_empty": copy["updates_empty"],
        "search_empty": "没有搜索到结果" if is_zh else "No matching results.",
        "search_prompt": "请输入关键词后再搜索。" if is_zh else "Enter a query before searching.",
        "search_busy": "搜索中..." if is_zh else "Searching...",
        "found_prefix": "找到" if is_zh else "Found",
        "found_suffix": "条结果。" if is_zh else "results.",
        "opened": "已打开条目：" if is_zh else "Opened entry: ",
        "submit_text_busy": "分析中..." if is_zh else "Analyzing...",
        "submit_file_busy": "上传中..." if is_zh else "Uploading...",
        "file_required": "请先选择文件、压缩包或文件夹" if is_zh else "Select a file, folder, or archive first.",
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
        "no_content": "暂无内容" if is_zh else "No content",
        "unknown": "未知" if is_zh else "unknown",
    }
    return shared_shell(
        f"{knowledge_name} Portal",
        body,
        locale=active_locale,
        page_script_name="portal.js",
        page_data=page_data,
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
    remote_install = (
        "curl -fsSL https://raw.githubusercontent.com/huyusong10/Sediment/master/install.sh "
        "| bash -s -- --quartz-only"
    )
    local_install = "bash install.sh --quartz-only"
    manual_install = (
        f"git clone https://github.com/jackyzha0/quartz.git \"{quartz['runtime_path']}\"\n"
        f"cd \"{quartz['runtime_path']}\"\n"
        "npm i"
    )
    graph_title = "Quartz 4 图谱" if is_zh else "Quartz 4 Graph"
    content = (
        _render_html_template(
            "portal-graph-available.html",
            GRAPH_TITLE=graph_title,
            GRAPH_HINT="在新窗口打开完整 Quartz 站点" if is_zh else "Open the full Quartz site in a new window",
            GRAPH_MESSAGE=(
                "不再把 Quartz 压缩进门户页面里。直接在新窗口打开完整站点，可以保留原生布局、侧边栏和图谱交互。"
                if is_zh
                else "Quartz no longer gets squeezed into the portal surface. Open the full site in a new window to keep its native layout, sidebar, and graph interactions."
            ),
            OPEN_BUTTON_LABEL="打开完整 Quartz" if is_zh else "Open full Quartz",
        )
        if quartz.get("site_available")
        else _render_html_template(
            "portal-graph-unavailable.html",
            GRAPH_TITLE=graph_title,
            GRAPH_HINT="可选图谱页面" if is_zh else "Optional graph surface",
            EMPTY_MESSAGE=(
                "当前实例还没有可打开的 Quartz 站点，所以这里暂时不能直接进入完整图谱。"
                if is_zh
                else "This instance does not have a built Quartz site yet, so the full graph cannot be opened yet."
            ),
            INSTALL_MESSAGE=(
                (
                    f"Quartz runtime 还没有安装成功。请优先重跑安装脚本：<code>{remote_install}</code>；如果你就在 Sediment 仓库目录里，也可以直接运行 <code>{local_install}</code>。"
                    if is_zh
                    else f"Quartz runtime is not ready yet. Rerun the installer with <code>{remote_install}</code>; if you are already inside the Sediment repository, run <code>{local_install}</code>."
                )
                if not quartz.get("runtime_available")
                else (
                    f"Quartz runtime 已经安装到 <code>{quartz['runtime_path']}</code>，但这个实例还没有完成图谱构建。请前往管理台的知识库管理页执行一次构建。"
                    if is_zh
                    else f"The shared Quartz runtime is ready at <code>{quartz['runtime_path']}</code>, but this instance has not built its graph site yet. Open the knowledge-base management page in Admin and run one build."
                )
            ),
            MANUAL_INSTALL_LEAD=(
                "如果你想手工安装 Quartz runtime，可以按官方方式执行："
                if is_zh
                else "If you want to install the Quartz runtime manually, run:"
            ),
            MANUAL_INSTALL_COMMAND=manual_install,
            REQUIREMENT_MESSAGE=(
                "Quartz 4 目前要求至少 Node v22 和 npm v10.9.2。安装好 runtime 后，再由管理台为当前实例构建静态图谱站点即可。"
                if is_zh
                else "Quartz 4 currently requires at least Node v22 and npm v10.9.2. Once the runtime is installed, let the Admin knowledge-base page build the instance site."
            ),
            ADMIN_KB_LINK=_nav_link(
                "去管理台知识库管理页" if is_zh else "Open admin KB page",
                admin_kb_path,
                primary=True,
            ),
        )
    )
    body = _render_html_template(
        "portal-graph-body.html",
        LOGO_INLINE=_logo_inline(),
        KNOWLEDGE_NAME=knowledge_name,
        NAV_PORTAL=_nav_link("知识门户" if is_zh else "Portal", _localized_path("/portal", active_locale)),
        NAV_GRAPH=_nav_link(
            "Quartz 图谱" if is_zh else "Quartz Graph",
            _localized_path("/portal/graph-view", active_locale),
            primary=True,
        ),
        NAV_ADMIN=_nav_link("管理台" if is_zh else "Admin", _localized_path("/admin", active_locale)),
        SUBTITLE=(
            f"{'Quartz Graph View · 实例：' if is_zh else 'Quartz Graph View · instance: '}{instance_name}"
        ),
        HERO_TEXT=(
            "Quartz 会以独立窗口打开，避免嵌入式视图压缩布局，让门户继续专注搜索与提交。"
            if is_zh
            else "Quartz opens in its own window so the graph keeps its full layout while the portal stays focused on search and submission."
        ),
        GRAPH_CONTENT=content,
    )
    return shared_shell(f"{knowledge_name} Quartz Graph", body, locale=active_locale)


def admin_login_html(*, knowledge_name: str, instance_name: str, locale: str, next_path: str) -> str:
    active_locale = _normalize_locale(locale)
    is_zh = active_locale == "zh"
    body = _render_html_template(
        "admin-login-body.html",
        LOGO_INLINE=_logo_inline(),
        KNOWLEDGE_NAME=knowledge_name,
        NAV_PORTAL=_nav_link("知识门户" if is_zh else "Portal", _localized_path("/portal", active_locale)),
        NAV_GRAPH=_nav_link(
            "Quartz 图谱" if is_zh else "Quartz Graph",
            _localized_path("/portal/graph-view", active_locale),
        ),
        NAV_LOGIN=_nav_link("管理台登录" if is_zh else "Admin sign in", next_path, primary=True),
        SUBTITLE=(
            f"{'Sediment Admin Sign-in · 实例：' if is_zh else 'Sediment Admin Sign-in · instance: '}{instance_name}"
        ),
        HERO_TEXT=(
            "管理台只开放给 committer 和平台维护者。可以使用服务器启动时终端里显示的一次性 token，或 config 中配置的持久 token 登录。"
            if is_zh
            else "The admin surface is reserved for committers and platform maintainers. Use the one-time token shown when the server starts, or the persistent token configured in config.yaml."
        ),
        TOKEN_LABEL="Admin Token" if is_zh else "Admin token",
        TOKEN_PLACEHOLDER=(
            "输入启动时终端显示的 token，或 config.yaml 中配置的 token"
            if is_zh
            else "Enter the startup token or the persistent token from config.yaml"
        ),
        OPEN_ADMIN_LABEL="登录管理台" if is_zh else "Open admin",
        LOGIN_STATUS="需要有效 token 才能进入后台。" if is_zh else "A valid admin token is required.",
    )

    page_data = {
        "login_failed": "登录失败" if is_zh else "Sign-in failed",
        "redirect": next_path,
    }
    return shared_shell(
        f"{knowledge_name} Admin Login",
        body,
        locale=active_locale,
        page_script_name="admin-login.js",
        page_data=page_data,
    )


def admin_html(
    *,
    knowledge_name: str,
    instance_name: str,
    locale: str,
    section: str,
    quartz: dict[str, object],
) -> str:
    active_locale = _normalize_locale(locale)
    is_zh = active_locale == "zh"
    section = section if section in {"overview", "kb", "reviews"} else "overview"

    copy = {
        "portal": "知识门户" if is_zh else "Portal",
        "graph": "Quartz 图谱" if is_zh else "Quartz Graph",
        "admin": "管理台" if is_zh else "Admin",
        "overview": "总览" if is_zh else "Overview",
        "kb": "知识库管理" if is_zh else "KB Management",
        "reviews": "Commit 评审" if is_zh else "Commit Review",
        "subtitle": (
            f"Sediment Control Room · 实例：{instance_name}"
            if is_zh
            else f"Sediment Control Room · instance: {instance_name}"
        ),
        "hero": (
            "按 committer 的真实工作路径组织后台：先看系统状态，再进入知识库管理做 explore / ingest / tidy / 编辑，最后到评审页处理 patch 与任务。"
            if is_zh
            else "The admin surface follows the committer workflow: start with overall health, move into knowledge-base operations, then review generated patches and jobs."
        ),
        "ready": (
            "管理台已就绪，可以从这里持续管理健康状态、知识库操作与提交评审。"
            if is_zh
            else "The admin surface is ready. Use it to manage health, KB operations, and commit reviews."
        ),
        "refresh": "刷新当前页" if is_zh else "Refresh this page",
    }

    overview_markup = _render_html_template(
        "admin-overview-section.html",
        SYSTEM_OVERVIEW_TITLE="系统总览" if is_zh else "System overview",
        SYSTEM_OVERVIEW_NOTE="队列 / review / 健康度" if is_zh else "queue / reviews / health",
        HEALTH_SEVERITY_TITLE="Health 严重度" if is_zh else "Health severity",
        HEALTH_SEVERITY_NOTE="问题分布" if is_zh else "issue distribution",
        SYSTEM_STATUS_TITLE="系统状态" if is_zh else "System status",
        QUARTZ_NOTE="图谱运行时与实例站点" if is_zh else "runtime and instance site",
        PRIORITY_ISSUES_TITLE="优先处理的问题" if is_zh else "Priority issues",
        PRIORITY_ISSUES_NOTE="展示前 8 条" if is_zh else "top 8 only",
        AUDIT_LOG_TITLE="最近审计日志" if is_zh else "Recent audit logs",
        AUDIT_LOG_NOTE="最近 12 条" if is_zh else "latest 12 entries",
    )

    kb_markup = _render_html_template(
        "admin-kb-section.html",
        EXPLORE_TITLE="Explore" if is_zh else "Explore",
        EXPLORE_NOTE="输入一段问题或场景描述" if is_zh else "Ask with a full question or scenario",
        EXPLORE_INPUT_LABEL="问题 / 场景" if is_zh else "Question / scenario",
        EXPLORE_INPUT_PLACEHOLDER=(
            "例如：热备份在什么情况下不该当成主备切换方案？"
            if is_zh
            else "Example: when should hot backup not be treated as a failover strategy?"
        ),
        EXPLORE_BUTTON="运行 Explore" if is_zh else "Run explore",
        EXPLORE_RESULT_EMPTY="这里会显示回答、来源和缺口。" if is_zh else "Answers, sources, and gaps appear here.",
        QUARTZ_NOTE="构建或刷新实例图谱" if is_zh else "build or refresh the instance graph",
        QUARTZ_BUTTON="构建 / 刷新 Quartz 站点" if is_zh else "Build / refresh Quartz site",
        OPEN_GRAPH_LINK=_nav_link(
            "打开 Quartz 图谱页" if is_zh else "Open Quartz graph",
            _localized_path("/portal/graph-view", active_locale),
        ),
        SUBMISSION_TITLE="待处理提交" if is_zh else "Buffered submissions",
        SUBMISSION_NOTE="先归类，再发起 ingest" if is_zh else "triage first, then ingest",
        TIDY_TITLE="Tidy 入口" if is_zh else "Tidy entry points",
        TIDY_NOTE="问题队列 + 手工发起" if is_zh else "issue queue + manual trigger",
        MANUAL_TIDY_LABEL="手工 tidy 目标" if is_zh else "Manual tidy target",
        MANUAL_TIDY_PLACEHOLDER="例如：薄弱条目" if is_zh else "Example: fragile-entry",
        MANUAL_TIDY_BUTTON="对目标发起 Tidy" if is_zh else "Run tidy for target",
        EDITOR_TITLE="在线编辑" if is_zh else "Inline editor",
        EDITOR_NAME_LABEL="条目名" if is_zh else "Entry name",
        EDITOR_NAME_PLACEHOLDER="例如：热备份" if is_zh else "Example: hot-backup",
        LOAD_ENTRY_BUTTON="加载条目" if is_zh else "Load entry",
        EDITOR_CONTENT_LABEL="内容" if is_zh else "Content",
        SAVE_ENTRY_BUTTON="保存条目" if is_zh else "Save entry",
        EDITOR_STATUS=(
            "这里会显示校验结果和保存反馈。"
            if is_zh
            else "Validation and save feedback appears here."
        ),
        SYSTEM_STATUS_TITLE="系统状态" if is_zh else "System status",
    )

    review_markup = _render_html_template(
        "admin-reviews-section.html",
        PENDING_REVIEWS_TITLE="待审 Patch" if is_zh else "Pending reviews",
        PENDING_REVIEWS_NOTE="先看 diff，再决定是否合并" if is_zh else "review the diff before merging",
        DIFF_PREVIEW_TITLE="Diff 预览" if is_zh else "Diff preview",
        DIFF_PREVIEW_NOTE="当前选中的 review" if is_zh else "currently selected review",
        DIFF_EMPTY="选择待审 patch 后在这里查看。" if is_zh else "Select a pending review to inspect its diff here.",
        JOB_TITLE="任务队列" if is_zh else "Jobs",
        JOB_NOTE="排队 / 运行 / 失败 / 可重试" if is_zh else "queued / running / failed / retryable",
        AUDIT_LOG_TITLE="最近审计日志" if is_zh else "Recent audit logs",
        AUDIT_LOG_NOTE="review 与任务动作" if is_zh else "review and job actions",
    )

    section_markup = {
        "overview": overview_markup,
        "kb": kb_markup,
        "reviews": review_markup,
    }[section]

    body = _render_html_template(
        "admin-body.html",
        LOGO_INLINE=_logo_inline(),
        KNOWLEDGE_NAME=knowledge_name,
        NAV_PORTAL=_nav_link(copy["portal"], _localized_path("/portal", active_locale)),
        NAV_GRAPH=_nav_link(copy["graph"], _localized_path("/portal/graph-view", active_locale)),
        NAV_ADMIN=_nav_link(copy["admin"], _localized_path("/admin", active_locale), primary=True),
        SUBTITLE=copy["subtitle"],
        HERO_TEXT=copy["hero"],
        REFRESH_LABEL=copy["refresh"],
        SESSION_LABEL="Session 已建立" if is_zh else "Session active",
        OVERVIEW_LINK=_nav_link(
            copy["overview"], _localized_path("/admin", active_locale), primary=section == "overview"
        ),
        KB_LINK=_nav_link(copy["kb"], _localized_path("/admin/kb", active_locale), primary=section == "kb"),
        REVIEWS_LINK=_nav_link(
            copy["reviews"],
            _localized_path("/admin/reviews", active_locale),
            primary=section == "reviews",
        ),
        READY_MESSAGE=copy["ready"],
        SECTION_MARKUP=section_markup,
    )

    page_data = {
        "ui": {
            "section": section,
            "refresh_busy": "刷新中..." if is_zh else "Refreshing...",
            "busy_loading": "加载中..." if is_zh else "Loading...",
            "busy_queue": "排队中..." if is_zh else "Queueing...",
            "busy_saving": "保存中..." if is_zh else "Saving...",
            "busy_approve": "批准中..." if is_zh else "Approving...",
            "busy_reject": "拒绝中..." if is_zh else "Rejecting...",
            "stats_pending": "待审提交" if is_zh else "Pending submissions",
            "stats_draft": "草案待审" if is_zh else "Draft-ready submissions",
            "stats_queue": "排队任务" if is_zh else "Queued jobs",
            "stats_running": "运行中任务" if is_zh else "Running jobs",
            "stats_cancel": "取消中任务" if is_zh else "Cancelling jobs",
            "stats_stale": "陈旧任务" if is_zh else "Stale jobs",
            "stats_reviews": "待审 Review" if is_zh else "Pending reviews",
            "stats_blocking": "阻断问题" if is_zh else "Blocking issues",
            "system_runtime": "运行模式" if is_zh else "Runtime mode",
            "system_auth": "管理员鉴权" if is_zh else "Admin auth",
            "system_proxy": "可信代理头" if is_zh else "Trusted proxy headers",
            "system_rate": "速率限制" if is_zh else "Rate limit",
            "system_text_limit": "文本上限" if is_zh else "Text limit",
            "system_upload_limit": "文档上限" if is_zh else "Upload limit",
            "system_retry_limit": "任务重试上限" if is_zh else "Job retry limit",
            "system_stale_limit": "任务过期阈值" if is_zh else "Stale job threshold",
            "system_portal": "Portal" if is_zh else "Portal",
            "system_admin": "Admin" if is_zh else "Admin",
            "system_instance": "实例" if is_zh else "Instance",
            "system_enabled": "开启" if is_zh else "Enabled",
            "system_disabled": "关闭" if is_zh else "Disabled",
            "issue_empty": "当前没有需要立即处理的问题。" if is_zh else "No urgent issues right now.",
            "submission_empty": "暂无待处理提交。" if is_zh else "No buffered submissions right now.",
            "review_empty": "暂无待审 patch。" if is_zh else "No pending reviews right now.",
            "job_empty": "暂无任务。" if is_zh else "No jobs right now.",
            "audit_empty": "暂无审计日志。" if is_zh else "No audit logs yet.",
            "diff_empty": "选择待审 patch 后在这里查看。" if is_zh else "Select a pending review to inspect its diff here.",
            "editor_loaded": "已加载" if is_zh else "Loaded",
            "editor_saved": "保存成功" if is_zh else "Saved",
            "quartz_ready": "Quartz 站点已就绪" if is_zh else "Quartz site is ready",
            "quartz_missing_site": "尚未构建实例站点" if is_zh else "Instance site is not built yet",
            "quartz_missing_runtime": "Quartz runtime 不可用" if is_zh else "Quartz runtime is unavailable",
            "quartz_runtime_path": "runtime 路径" if is_zh else "runtime path",
            "quartz_site_path": "站点路径" if is_zh else "site path",
            "quartz_built_at": "最后构建时间" if is_zh else "last built",
            "quartz_build_success": "Quartz 站点已刷新。" if is_zh else "Quartz site refreshed.",
            "quartz_cta": "前往图谱页查看效果。" if is_zh else "Open the graph page to verify the result.",
            "explore_answer": "回答" if is_zh else "Answer",
            "explore_sources": "来源" if is_zh else "Sources",
            "explore_gaps": "缺口" if is_zh else "Gaps",
            "explore_confidence": "置信度" if is_zh else "Confidence",
            "explore_idle": "这里会显示回答、来源和缺口。" if is_zh else "Answers, sources, and gaps appear here.",
            "explore_error": "Explore 失败" if is_zh else "Explore failed",
            "manual_tidy_target_required": "请先填写 tidy 目标。" if is_zh else "Enter a tidy target first.",
            "submitted_related": "关联" if is_zh else "Related",
            "submitted_advice": "建议" if is_zh else "Advice",
            "triaged": "已归类" if is_zh else "Triaged",
            "reject": "拒绝提交" if is_zh else "Reject",
            "run_ingest": "运行 Ingest" if is_zh else "Run ingest",
            "run_tidy": "发起 Tidy" if is_zh else "Run tidy",
            "show_diff": "查看 Diff" if is_zh else "Show diff",
            "approve": "批准" if is_zh else "Approve",
            "reject_review": "拒绝" if is_zh else "Reject",
            "retry": "重试" if is_zh else "Retry",
            "cancel": "取消" if is_zh else "Cancel",
            "triage_done": "提交已标记为" if is_zh else "Submission marked as",
            "ingest_done": "已创建 ingest 任务：" if is_zh else "Created ingest job: ",
            "tidy_done": "已创建 tidy 任务：" if is_zh else "Created tidy job: ",
            "review_loaded": "已加载 review diff：" if is_zh else "Loaded review diff: ",
            "review_approved": "Review 已批准：" if is_zh else "Approved review: ",
            "review_rejected": "Review 已拒绝：" if is_zh else "Rejected review: ",
            "job_retried": "任务已重新入队：" if is_zh else "Requeued job: ",
            "job_cancelled": "任务已请求取消：" if is_zh else "Cancellation requested for job: ",
            "unknown": "未知" if is_zh else "unknown",
        },
        "quartz": quartz,
    }
    return shared_shell(
        f"{knowledge_name} Admin",
        body,
        locale=active_locale,
        page_script_name="admin.js",
        page_data=page_data,
    )
