# ruff: noqa: E501
from __future__ import annotations

import json

from sediment.web_ui_shell import (
    localized_path as _localized_path,
)
from sediment.web_ui_shell import (
    logo_inline as _logo_inline,
)
from sediment.web_ui_shell import (
    nav_link as _nav_link,
)
from sediment.web_ui_shell import (
    normalize_locale as _normalize_locale,
)
from sediment.web_ui_shell import (
    shared_shell,
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
        "search_clear": "清空" if is_zh else "Clear",
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
        "file_selection_idle": (
            "当前还没有选择文件。"
            if is_zh
            else "No files are selected yet."
        ),
        "entry_title": "条目全文" if is_zh else "Entry",
        "close": "关闭" if is_zh else "Close",
    }
    body = f"""
    <div class="page">
      <section class="hero">
        <div class="hero-top">
          <div class="brand">
            {_logo_inline()}
            <div class="brand-copy">
              <span>Sediment</span>
              <strong>{knowledge_name}</strong>
            </div>
          </div>
          <div class="nav" data-shell-nav>
            {_nav_link(copy["portal"], _localized_path("/portal", active_locale), primary=True)}
            {_nav_link(copy["graph"], _localized_path("/portal/graph-view", active_locale))}
            {_nav_link(copy["admin"], _localized_path("/admin", active_locale))}
          </div>
        </div>
        <h1>{knowledge_name}</h1>
        <p class="subtle">{copy["subtitle"]}</p>
        <p>{copy["hero"]}</p>
      </section>

      <section class="panel" style="margin-top:20px;">
        <div class="stats" id="portal-stats"></div>
        <div class="notice" id="portal-message" data-testid="portal-message" role="status" aria-live="polite">{copy["message"]}</div>
      </section>

      <section class="panel" style="margin-top:20px;">
        <div class="row spread">
          <h2>{copy["search_title"]}</h2>
          <span class="subtle">{copy["search_hint"]}</span>
        </div>
        <div class="row">
          <input id="search-input" data-testid="portal-search-input" placeholder="{copy["search_placeholder"]}" />
          <button class="primary" id="search-button" data-testid="portal-search-button">{copy["search_button"]}</button>
          <button id="search-clear-button" type="button">{copy["search_clear"]}</button>
        </div>
        <div id="search-status" class="subtle" style="margin-top:12px;" role="status" aria-live="polite">{copy["search_idle"]}</div>
        <div class="list" id="search-results" data-testid="portal-search-results" style="margin-top:14px;"></div>
      </section>

      <section class="panel" style="margin-top:20px;">
        <div class="row spread">
          <h2>{copy["updates"]}</h2>
          {_nav_link(copy["graph"], _localized_path("/portal/graph-view", active_locale))}
        </div>
        <div class="list" id="recent-updates"></div>
      </section>

      <section class="panel" style="margin-top:20px;">
        <h2>{copy["buffer"]}</h2>
        <p class="subtle">{copy["buffer_note"]}</p>
        <div class="grid cols-2">
          <div class="card">
            <h3>{copy["text_title"]}</h3>
            <div class="grid">
              <label>{copy["name"]}<input id="submit-name" placeholder="{copy["name_ph"]}" /></label>
              <label>{copy["title"]}<input id="submit-title" placeholder="{copy["title_ph"]}" /></label>
              <label>{copy["type"]}
                <select id="submit-type">
                  <option value="concept">{copy["concept"]}</option>
                  <option value="lesson">{copy["lesson"]}</option>
                  <option value="feedback">{copy["feedback"]}</option>
                </select>
              </label>
              <label>{copy["content"]}<textarea id="submit-content" placeholder="{copy["content_ph"]}"></textarea></label>
              <button class="primary" id="submit-text-button" data-testid="portal-submit-text-button">{copy["submit_text"]}</button>
              <div id="submit-text-status" class="subtle" role="status" aria-live="polite">{copy["text_status"]}</div>
              <div id="submit-text-analysis" class="empty">{copy["analysis_idle"]}</div>
            </div>
          </div>
          <div class="card">
            <h3>{copy["upload_title"]}</h3>
            <div class="grid">
              <label>{copy["name"]}<input id="upload-name" placeholder="{copy["name_ph"]}" /></label>
              <div class="upload-grid">
                <label>{copy["upload_file"]}
                  <input id="upload-file" data-testid="portal-upload-file" type="file" multiple accept=".txt,.md,.docx,.pptx,.zip" />
                </label>
                <label>{copy["upload_folder"]}
                  <input id="upload-folder" data-testid="portal-upload-folder" type="file" webkitdirectory directory multiple />
                </label>
              </div>
              <button class="primary" id="submit-file-button" data-testid="portal-submit-file-button">{copy["submit_file"]}</button>
              <div id="submit-file-status" class="subtle" role="status" aria-live="polite">{copy["file_status"]}</div>
              <div id="upload-selection" class="subtle">{copy["file_selection_idle"]}</div>
            </div>
          </div>
        </div>
      </section>

      <div id="entry-modal" class="modal-backdrop" hidden>
        <div class="modal-card">
          <div class="row spread">
            <h2 id="entry-modal-title">{copy["entry_title"]}</h2>
            <button id="entry-close-button" data-testid="portal-entry-close">{copy["close"]}</button>
          </div>
          <div id="entry-view" data-testid="portal-entry-view" class="markdown empty">{copy["modal_empty"]}</div>
        </div>
      </div>
    </div>
    """

    ui_json = json.dumps(
        {
            "formal_entries": "正式条目" if is_zh else "Formal entries",
            "placeholders": "缺口条目" if is_zh else "Placeholders",
            "indexes": "索引" if is_zh else "Indexes",
            "pending": "待审提交" if is_zh else "Pending submissions",
            "health": "Health 问题" if is_zh else "Health issues",
            "updates_empty": copy["updates_empty"],
            "search_empty": "没有搜索到结果" if is_zh else "No matching results.",
            "search_prompt": "请输入关键词后再搜索。" if is_zh else "Enter a query before searching.",
            "search_busy": "搜索中..." if is_zh else "Searching...",
            "search_cleared": "搜索条件已清空。" if is_zh else "Search cleared.",
            "search_query_label": "查询" if is_zh else "Query",
            "found_prefix": "找到" if is_zh else "Found",
            "found_suffix": "条结果。" if is_zh else "results.",
            "opened": "已打开条目：" if is_zh else "Opened entry: ",
            "submit_text_busy": "分析中..." if is_zh else "Analyzing...",
            "submit_file_busy": "上传中..." if is_zh else "Uploading...",
            "file_required": "请先选择文件、压缩包或文件夹" if is_zh else "Select a file, folder, or archive first.",
            "name_required": "请先填写名字。" if is_zh else "Enter your name first.",
            "title_required": "请先填写标题。" if is_zh else "Enter a title first.",
            "content_required": "请先填写正文内容。" if is_zh else "Enter submission content first.",
            "upload_selection_none": "当前还没有选择文件。" if is_zh else "No files are selected yet.",
            "upload_selection_files": "已选择文件" if is_zh else "Selected files",
            "upload_selection_root": "根目录" if is_zh else "Root",
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
        },
        ensure_ascii=False,
    )
    script = """
    const UI = __UI__;

    function setPortalMessage(message) {
      document.getElementById('portal-message').textContent = message;
    }

    function summarizeUploadSelection() {
      const fileInput = document.getElementById('upload-file');
      const folderInput = document.getElementById('upload-folder');
      const files = Array.from(fileInput.files || []);
      const folderFiles = Array.from(folderInput.files || []);
      const selected = folderFiles.length ? folderFiles : files;
      const node = document.getElementById('upload-selection');
      if (!selected.length) {
        node.textContent = UI.upload_selection_none;
        return;
      }
      const roots = Array.from(new Set(selected
        .map(file => String(file.webkitRelativePath || '').split('/')[0])
        .filter(Boolean)));
      const rootLabel = roots.length ? roots.join(', ') : UI.upload_selection_root;
      node.textContent = `${UI.upload_selection_files}: ${selected.length} · ${rootLabel}`;
    }

    async function withBusy(buttonId, busyLabel, task) {
      const button = document.getElementById(buttonId);
      const originalLabel = button.textContent;
      button.disabled = true;
      button.textContent = busyLabel;
      try {
        return await task();
      } finally {
        button.disabled = false;
        button.textContent = originalLabel;
      }
    }

    async function loadHome() {
      const payload = await fetchJson('/api/portal/home');
      const stats = [
        [UI.formal_entries, payload.counts.formal_entries],
        [UI.placeholders, payload.counts.placeholders],
        [UI.indexes, payload.counts.indexes],
        [UI.pending, payload.counts.pending_submissions],
        [UI.health, payload.counts.health_issues]
      ];
      document.getElementById('portal-stats').innerHTML = stats.map(([label, value]) => `
        <div class="stat">
          <strong>${value}</strong>
          <span>${label}</span>
        </div>
      `).join('');

      document.getElementById('recent-updates').innerHTML = payload.recent_updates.length
        ? payload.recent_updates.map(item => `
            <div class="card interactive" data-entry-name="${encodeURIComponent(item.name)}">
              <div class="row spread">
                <strong>${escapeHtml(item.name)}</strong>
                <span class="tag">${escapeHtml(item.entry_type)}</span>
              </div>
            </div>`).join('')
        : `<div class="empty">${escapeHtml(UI.updates_empty)}</div>`;
    }

    async function openEntry(encodedName) {
      const payload = await fetchJson(`/api/portal/entries/${encodedName}`);
      document.getElementById('entry-modal-title').textContent = payload.name;
      document.getElementById('entry-view').innerHTML = `
        <div class="row spread">
          <h3>${escapeHtml(payload.name)}</h3>
          <span class="tag ${payload.metadata.status === 'fact' ? 'ok' : 'warn'}">${escapeHtml(payload.metadata.status || payload.metadata.kind)}</span>
        </div>
        ${renderMarkdown(payload.content)}
      `;
      document.getElementById('entry-modal').hidden = false;
      setPortalMessage(`${UI.opened}${payload.name}`);
    }

    async function runSearch() {
      const query = document.getElementById('search-input').value.trim();
      if (!query) {
        document.getElementById('search-status').textContent = UI.search_prompt;
        document.getElementById('search-results').innerHTML = `<div class="empty">${escapeHtml(UI.search_empty)}</div>`;
        return;
      }
      const results = await fetchJson(`/api/portal/search?q=${encodeURIComponent(query)}`);
      document.getElementById('search-status').textContent = `${UI.search_query_label}: ${query} · ${UI.found_prefix} ${results.length} ${UI.found_suffix}`;
      document.getElementById('search-results').innerHTML = results.length
        ? results.map(item => `
            <div class="card interactive" data-entry-name="${encodeURIComponent(item.name)}">
              <div class="row spread">
                <strong>${escapeHtml(item.name)}</strong>
                <span class="tag">${escapeHtml(item.entry_type)}</span>
              </div>
              <div class="subtle">${escapeHtml(item.snippet || item.summary || '')}</div>
            </div>`).join('')
        : `<div class="empty">${escapeHtml(UI.search_empty)}</div>`;
    }

    function clearSearch() {
      document.getElementById('search-input').value = '';
      document.getElementById('search-status').textContent = UI.search_cleared;
      document.getElementById('search-results').innerHTML = '';
      setPortalMessage(UI.search_cleared);
    }

    async function submitText() {
      const submitterName = document.getElementById('submit-name').value.trim();
      const title = document.getElementById('submit-title').value.trim();
      const content = document.getElementById('submit-content').value.trim();
      if (!submitterName) throw new Error(UI.name_required);
      if (!title) throw new Error(UI.title_required);
      if (!content) throw new Error(UI.content_required);
      const payload = {
        title,
        content,
        submitter_name: submitterName,
        submission_type: document.getElementById('submit-type').value
      };
      const result = await fetchJson('/api/portal/submissions/text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      document.getElementById('submit-text-status').textContent = `${UI.submit_text_success}${result.id}`;
      document.getElementById('submit-text-analysis').innerHTML = renderSubmissionAnalysis(result.analysis);
      document.getElementById('submit-title').value = '';
      document.getElementById('submit-content').value = '';
      setPortalMessage(`${UI.submitted_text_prefix}${result.title}`);
      await loadHome();
    }

    async function submitFile() {
      const fileInput = document.getElementById('upload-file');
      const folderInput = document.getElementById('upload-folder');
      const files = Array.from(fileInput.files || []);
      const folderFiles = Array.from(folderInput.files || []);
      if (!files.length && !folderFiles.length) throw new Error(UI.file_required);
      const submitterName = document.getElementById('upload-name').value.trim();
      if (!submitterName) throw new Error(UI.name_required);
      const payload = {
        submitter_name: submitterName
      };
      if (folderFiles.length || files.length > 1) {
        const bundle = await Promise.all((folderFiles.length ? folderFiles : files).map(async (file) => ({
          filename: file.name,
          relative_path: file.webkitRelativePath || file.name,
          mime_type: file.type || inferMimeType(file.name),
          content_base64: await encodeFileAsBase64(file)
        })));
        payload.filename = folderFiles.length ? inferBundleName(bundle) : 'document-bundle';
        payload.mime_type = 'application/zip';
        payload.files = bundle;
      } else {
        const file = files[0];
        payload.filename = file.name;
        payload.mime_type = file.type || inferMimeType(file.name);
        payload.content_base64 = await encodeFileAsBase64(file);
      }
      const response = await fetch('/api/portal/submissions/document', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '上传失败');
      document.getElementById('submit-file-status').textContent = `${UI.submit_file_success}${data.id}`;
      fileInput.value = '';
      folderInput.value = '';
      summarizeUploadSelection();
      setPortalMessage(`${UI.submitted_file_prefix}${data.title}`);
      await loadHome();
    }

    async function encodeFileAsBase64(file) {
      const buffer = await file.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      let binary = '';
      for (const byte of bytes) binary += String.fromCharCode(byte);
      return btoa(binary);
    }

    function inferBundleName(files) {
      const roots = new Set(files
        .map(file => String(file.relative_path || '').split('/')[0])
        .filter(Boolean));
      if (roots.size === 1) return Array.from(roots)[0];
      return 'document-bundle';
    }

    function inferMimeType(filename) {
      const lower = filename.toLowerCase();
      if (lower.endsWith('.md')) return 'text/markdown';
      if (lower.endsWith('.txt')) return 'text/plain';
      if (lower.endsWith('.docx')) return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
      if (lower.endsWith('.pptx')) return 'application/vnd.openxmlformats-officedocument.presentationml.presentation';
      if (lower.endsWith('.zip')) return 'application/zip';
      return 'application/octet-stream';
    }

    function renderSubmissionAnalysis(analysis) {
      if (!analysis) return `<div class="empty">${escapeHtml(UI.analysis_related_empty)}</div>`;
      const related = Array.isArray(analysis.related_entries) && analysis.related_entries.length
        ? analysis.related_entries.map(item => `
            <li><strong>${escapeHtml(item.name)}</strong> · ${escapeHtml(item.reason || '')}</li>
          `).join('')
        : `<li>${escapeHtml(UI.analysis_related_empty)}</li>`;
      const warnings = Array.isArray(analysis.warnings) && analysis.warnings.length
        ? `<div class="subtle">${analysis.warnings.map(item => escapeHtml(item)).join('；')}</div>`
        : '';
      return `
        <div class="card">
          <div class="row spread">
            <strong>${escapeHtml(UI.analysis_title)}</strong>
            <span class="tag ${analysis.status === 'ok' ? 'ok' : 'warn'}">${escapeHtml(analysis.status || UI.unknown)}</span>
          </div>
          <div class="subtle">${escapeHtml(analysis.summary || '')}</div>
          <div class="subtle">${escapeHtml(UI.analysis_title_label)}: ${escapeHtml(analysis.recommended_title || '-')}</div>
          <div class="subtle">${escapeHtml(UI.analysis_type_label)}: ${escapeHtml(analysis.recommended_type || '-')} · ${escapeHtml(UI.analysis_risk_label)}: ${escapeHtml(analysis.duplicate_risk || '-')} · ${escapeHtml(UI.analysis_action_label)}: ${escapeHtml(analysis.committer_action || '-')}</div>
          <div class="subtle">${escapeHtml(UI.analysis_note_label)}: ${escapeHtml(analysis.committer_note || '')}</div>
          <ul>${related}</ul>
          ${warnings}
        </div>
      `;
    }

    function handleEntryClick(event) {
      const card = event.target.closest('[data-entry-name]');
      if (!card) return;
      openEntry(card.dataset.entryName).catch(showError);
    }

    document.getElementById('search-results').addEventListener('click', handleEntryClick);
    document.getElementById('recent-updates').addEventListener('click', handleEntryClick);

    document.getElementById('search-button').addEventListener('click', () => withBusy('search-button', UI.search_busy, () => runSearch()).catch(showError));
    document.getElementById('search-clear-button').addEventListener('click', clearSearch);
    document.getElementById('submit-text-button').addEventListener('click', () => withBusy('submit-text-button', UI.submit_text_busy, () => submitText()).catch(showError));
    document.getElementById('submit-file-button').addEventListener('click', () => withBusy('submit-file-button', UI.submit_file_busy, () => submitFile()).catch(showError));
    document.getElementById('upload-file').addEventListener('change', summarizeUploadSelection);
    document.getElementById('upload-folder').addEventListener('change', summarizeUploadSelection);
    document.getElementById('entry-close-button').addEventListener('click', () => {
      document.getElementById('entry-modal').hidden = true;
    });
    document.getElementById('entry-modal').addEventListener('click', (event) => {
      if (event.target.id === 'entry-modal') {
        document.getElementById('entry-modal').hidden = true;
      }
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        document.getElementById('entry-modal').hidden = true;
      }
    });
    document.getElementById('search-input').addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        withBusy('search-button', UI.search_busy, () => runSearch()).catch(showError);
      }
    });

    function showError(error) {
      document.getElementById('submit-text-status').textContent = error.message;
      document.getElementById('submit-file-status').textContent = error.message;
      document.getElementById('search-status').textContent = error.message;
      setPortalMessage(error.message);
    }

    loadHome().catch(showError);
    summarizeUploadSelection();
    """.replace("__UI__", ui_json)
    return shared_shell(f"{knowledge_name} Portal", body, script, locale=active_locale)


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
    content = (
        """
        <div class="panel" style="margin-top:20px;">
          <div class="row spread">
            <h2>"""
        + ("Quartz 4 图谱" if is_zh else "Quartz 4 Graph")
        + """</h2>
            <span class="subtle">"""
        + ("嵌入的只读 Quartz 页面" if is_zh else "Embedded read-only Quartz view")
        + """</span>
          </div>
          <iframe class="quartz-frame" data-testid="portal-quartz-frame" src="/quartz/"></iframe>
        </div>
        """
        if quartz.get("site_available")
        else (
            """
        <div class="panel" style="margin-top:20px;">
          <div class="row spread">
            <h2>"""
            + ("Quartz 4 图谱" if is_zh else "Quartz 4 Graph")
            + """</h2>
            <span class="subtle">"""
            + ("可选图谱页面" if is_zh else "Optional graph surface")
            + """</span>
          </div>
          <div class="markdown">
            <p>"""
            + (
                "当前实例还没有可嵌入的 Quartz 站点，所以这里暂时不显示图谱。"
                if is_zh
                else "This instance does not have a built Quartz site yet, so the graph page is empty for now."
            )
            + """</p>
            <p>"""
            + (
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
            )
            + f"""</p>
            <p>{'如果你想手工安装 Quartz runtime，可以按官方方式执行：' if is_zh else 'If you want to install the Quartz runtime manually, run:'}</p>
            <pre class="mono">{manual_install}</pre>
            <p>{'Quartz 4 目前要求至少 Node v22 和 npm v10.9.2。安装好 runtime 后，再由管理台为当前实例构建静态图谱站点即可。' if is_zh else 'Quartz 4 currently requires at least Node v22 and npm v10.9.2. Once the runtime is installed, let the Admin knowledge-base page build the instance site.'}</p>
            <div class="row" style="margin-top:12px;">
              {_nav_link('去管理台知识库管理页' if is_zh else 'Open admin KB page', admin_kb_path, primary=True)}
            </div>
          </div>
        </div>
        """
        )
    )
    body = f"""
    <div class="page">
      <section class="hero">
        <div class="hero-top">
          <div class="brand">
            {_logo_inline()}
            <div class="brand-copy">
              <span>Sediment</span>
              <strong>{knowledge_name}</strong>
            </div>
          </div>
          <div class="nav" data-shell-nav>
            {_nav_link('知识门户' if is_zh else 'Portal', _localized_path('/portal', active_locale))}
            {_nav_link('Quartz 图谱' if is_zh else 'Quartz Graph', _localized_path('/portal/graph-view', active_locale), primary=True)}
            {_nav_link('管理台' if is_zh else 'Admin', _localized_path('/admin', active_locale))}
          </div>
        </div>
        <h1>{knowledge_name}</h1>
        <p class="subtle">{'Quartz Graph View · 实例：' if is_zh else 'Quartz Graph View · instance: '}{instance_name}</p>
        <p>{'这里承载更完整的只读知识图谱体验，让 Portal 首页保持轻量，把主空间留给搜索与提交。' if is_zh else 'This page hosts the full read-only graph so the portal can stay focused on search and submission.'}</p>
      </section>
      {content}
    </div>
    """
    return shared_shell(f"{knowledge_name} Quartz Graph", body, "", locale=active_locale)


def admin_login_html(*, knowledge_name: str, instance_name: str, locale: str, next_path: str) -> str:
    active_locale = _normalize_locale(locale)
    is_zh = active_locale == "zh"
    body = f"""
    <div class="page">
      <section class="hero">
        <div class="hero-top">
          <div class="brand">
            {_logo_inline()}
            <div class="brand-copy">
              <span>Sediment</span>
              <strong>{knowledge_name}</strong>
            </div>
          </div>
          <div class="nav" data-shell-nav>
            {_nav_link('知识门户' if is_zh else 'Portal', _localized_path('/portal', active_locale))}
            {_nav_link('Quartz 图谱' if is_zh else 'Quartz Graph', _localized_path('/portal/graph-view', active_locale))}
            {_nav_link('管理台登录' if is_zh else 'Admin sign in', next_path, primary=True)}
          </div>
        </div>
        <h1>{knowledge_name}</h1>
        <p class="subtle">{'Sediment Admin Sign-in · 实例：' if is_zh else 'Sediment Admin Sign-in · instance: '}{instance_name}</p>
        <p>{'管理台只开放给 committer 和平台维护者。可以使用服务器启动时终端里显示的一次性 token，或 config 中配置的持久 token 登录。' if is_zh else 'The admin surface is reserved for committers and platform maintainers. Use the one-time token shown when the server starts, or the persistent token configured in config.yaml.'}</p>
      </section>

      <section class="panel" style="margin-top:20px; max-width:560px;">
        <div class="grid">
          <label>{'Admin Token' if is_zh else 'Admin token'}<input id="admin-session-token" data-testid="admin-login-token" type="password" placeholder="{'输入启动时终端显示的 token，或 config.yaml 中配置的 token' if is_zh else 'Enter the startup token or the persistent token from config.yaml'}" /></label>
          <button class="primary" id="login-button" data-testid="admin-login-button">{'登录管理台' if is_zh else 'Open admin'}</button>
          <div id="login-status" data-testid="admin-login-status" class="subtle" role="status" aria-live="polite">{'需要有效 token 才能进入后台。' if is_zh else 'A valid admin token is required.'}</div>
        </div>
      </section>
    </div>
    """

    ui_json = json.dumps(
        {
            "login_failed": "登录失败" if is_zh else "Sign-in failed",
            "redirect": next_path,
        },
        ensure_ascii=False,
    )
    script = """
    const UI = __UI__;

    async function signIn() {
      const token = document.getElementById('admin-session-token').value.trim();
      const response = await fetch('/api/admin/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || UI.login_failed);
      window.location.href = UI.redirect;
    }

    async function checkSession() {
      const response = await fetch('/api/admin/session');
      const data = await response.json();
      if (data.authenticated) {
        window.location.href = UI.redirect;
      }
    }

    function showError(error) {
      document.getElementById('login-status').textContent = error.message;
    }

    document.getElementById('login-button').addEventListener('click', () => signIn().catch(showError));
    document.getElementById('admin-session-token').addEventListener('keydown', (event) => {
      if (event.key === 'Enter') signIn().catch(showError);
    });

    checkSession().catch(showError);
    """.replace("__UI__", ui_json)
    return shared_shell(f"{knowledge_name} Admin Login", body, script, locale=active_locale)


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

    overview_markup = f"""
      <section class="grid cols-2">
        <div class="panel">
          <div class="row spread">
            <h2>{'系统总览' if is_zh else 'System overview'}</h2>
            <span class="tabs-note">{'队列 / review / 健康度' if is_zh else 'queue / reviews / health'}</span>
          </div>
          <div class="stats" id="admin-stats" data-testid="admin-stats"></div>
        </div>
        <div class="panel">
          <div class="row spread">
            <h2>{'Health 严重度' if is_zh else 'Health severity'}</h2>
            <span class="tabs-note">{'问题分布' if is_zh else 'issue distribution'}</span>
          </div>
          <div class="severity-bar" id="severity-bars" data-testid="admin-severity"></div>
        </div>
      </section>

      <section class="grid cols-2">
        <div class="panel">
          <div class="row spread">
            <h2>{'系统状态' if is_zh else 'System status'}</h2>
            <span class="tabs-note">auth / queue / limits</span>
          </div>
          <div class="list" id="system-status" data-testid="admin-system-status"></div>
        </div>
        <div class="panel">
          <div class="row spread">
            <h2>Quartz</h2>
            <span class="tabs-note">{'图谱运行时与实例站点' if is_zh else 'runtime and instance site'}</span>
          </div>
          <div class="list" id="quartz-status"></div>
        </div>
      </section>

      <section class="grid cols-2">
        <div class="panel">
          <div class="row spread">
            <h2>{'优先处理的问题' if is_zh else 'Priority issues'}</h2>
            <span class="tabs-note">{'展示前 8 条' if is_zh else 'top 8 only'}</span>
          </div>
          <div class="list" id="issue-list" data-testid="admin-issue-list"></div>
        </div>
        <div class="panel">
          <div class="row spread">
            <h2>{'最近审计日志' if is_zh else 'Recent audit logs'}</h2>
            <span class="tabs-note">{'最近 12 条' if is_zh else 'latest 12 entries'}</span>
          </div>
          <div class="list" id="audit-log-list" data-testid="admin-audit-log-list"></div>
        </div>
      </section>
    """

    kb_markup = f"""
      <section class="grid cols-2">
        <div class="panel">
          <div class="row spread">
            <h2>{'Explore' if is_zh else 'Explore'}</h2>
            <span class="tabs-note">{'输入一段问题或场景描述' if is_zh else 'Ask with a full question or scenario'}</span>
          </div>
          <div class="grid">
            <label>{'问题 / 场景' if is_zh else 'Question / scenario'}<textarea id="admin-explore-input" data-testid="admin-explore-input" placeholder="{'例如：热备份在什么情况下不该当成主备切换方案？' if is_zh else 'Example: when should hot backup not be treated as a failover strategy?'}"></textarea></label>
            <button class="primary" id="admin-explore-button" data-testid="admin-explore-button">{'运行 Explore' if is_zh else 'Run explore'}</button>
            <div id="admin-explore-result" data-testid="admin-explore-result" class="markdown empty">{'这里会显示回答、来源和缺口。' if is_zh else 'Answers, sources, and gaps appear here.'}</div>
          </div>
        </div>
        <div class="panel">
          <div class="row spread">
            <h2>Quartz</h2>
            <span class="tabs-note">{'构建或刷新实例图谱' if is_zh else 'build or refresh the instance graph'}</span>
          </div>
          <div class="stack">
            <div id="quartz-status" class="list"></div>
            <div class="row">
              <button class="primary" id="admin-quartz-build-button" data-testid="admin-quartz-build-button">{'构建 / 刷新 Quartz 站点' if is_zh else 'Build / refresh Quartz site'}</button>
              {_nav_link('打开 Quartz 图谱页' if is_zh else 'Open Quartz graph', _localized_path('/portal/graph-view', active_locale))}
            </div>
          </div>
        </div>
      </section>

      <section class="grid cols-2">
        <div class="panel">
          <div class="row spread">
            <h2>{'待处理提交' if is_zh else 'Buffered submissions'}</h2>
            <span class="tabs-note">{'先归类，再发起 ingest' if is_zh else 'triage first, then ingest'}</span>
          </div>
          <div class="list" id="submission-list" data-testid="admin-submission-list"></div>
        </div>
        <div class="panel">
          <div class="row spread">
            <h2>{'Tidy 入口' if is_zh else 'Tidy entry points'}</h2>
            <span class="tabs-note">{'问题队列 + 手工发起' if is_zh else 'issue queue + manual trigger'}</span>
          </div>
          <div class="grid">
            <label>{'手工 tidy 目标' if is_zh else 'Manual tidy target'}<input id="manual-tidy-target" placeholder="{'例如：薄弱条目' if is_zh else 'Example: fragile-entry'}" /></label>
            <div class="row">
              <button id="manual-tidy-button" data-testid="admin-manual-tidy-button">{'对目标发起 Tidy' if is_zh else 'Run tidy for target'}</button>
            </div>
          </div>
          <div class="list" id="issue-list" data-testid="admin-issue-list" style="margin-top:12px;"></div>
        </div>
      </section>

      <section class="grid cols-2">
        <div class="panel">
          <h2>{'在线编辑' if is_zh else 'Inline editor'}</h2>
          <div class="grid">
            <label>{'条目名' if is_zh else 'Entry name'}<input id="editor-name" data-testid="admin-editor-name" placeholder="{'例如：热备份' if is_zh else 'Example: hot-backup'}" /></label>
            <button id="load-entry-button" data-testid="admin-load-entry-button">{'加载条目' if is_zh else 'Load entry'}</button>
            <label>{'内容' if is_zh else 'Content'}<textarea id="editor-content" data-testid="admin-editor-content"></textarea></label>
            <button class="primary" id="save-entry-button" data-testid="admin-save-entry-button">{'保存条目' if is_zh else 'Save entry'}</button>
            <div id="editor-status" data-testid="admin-editor-status" class="subtle" role="status" aria-live="polite">{'这里会显示校验结果和保存反馈。' if is_zh else 'Validation and save feedback appears here.'}</div>
          </div>
        </div>
        <div class="panel">
          <h2>{'系统状态' if is_zh else 'System status'}</h2>
          <div class="list" id="system-status" data-testid="admin-system-status"></div>
        </div>
      </section>
    """

    review_markup = f"""
      <section class="grid cols-2">
        <div class="panel">
          <div class="row spread">
            <h2>{'待审 Patch' if is_zh else 'Pending reviews'}</h2>
            <span class="tabs-note">{'先看 diff，再决定是否合并' if is_zh else 'review the diff before merging'}</span>
          </div>
          <div class="list" id="review-list" data-testid="admin-review-list"></div>
        </div>
        <div class="panel">
          <div class="row spread">
            <h2>{'Diff 预览' if is_zh else 'Diff preview'}</h2>
            <span class="tabs-note">{'当前选中的 review' if is_zh else 'currently selected review'}</span>
          </div>
          <div id="diff-view" data-testid="admin-diff-view" class="mono empty">{'选择待审 patch 后在这里查看。' if is_zh else 'Select a pending review to inspect its diff here.'}</div>
        </div>
      </section>

      <section class="grid cols-2">
        <div class="panel">
          <div class="row spread">
            <h2>{'任务队列' if is_zh else 'Jobs'}</h2>
            <span class="tabs-note">{'排队 / 运行 / 失败 / 可重试' if is_zh else 'queued / running / failed / retryable'}</span>
          </div>
          <div class="list" id="job-list" data-testid="admin-job-list"></div>
        </div>
        <div class="panel">
          <div class="row spread">
            <h2>{'最近审计日志' if is_zh else 'Recent audit logs'}</h2>
            <span class="tabs-note">{'review 与任务动作' if is_zh else 'review and job actions'}</span>
          </div>
          <div class="list" id="audit-log-list" data-testid="admin-audit-log-list"></div>
        </div>
      </section>
    """

    section_markup = {
        "overview": overview_markup,
        "kb": kb_markup,
        "reviews": review_markup,
    }[section]

    body = f"""
    <div class="page">
      <section class="hero">
        <div class="hero-top">
          <div class="brand">
            {_logo_inline()}
            <div class="brand-copy">
              <span>Sediment</span>
              <strong>{knowledge_name}</strong>
            </div>
          </div>
          <div class="nav" data-shell-nav>
            {_nav_link(copy["portal"], _localized_path("/portal", active_locale))}
            {_nav_link(copy["graph"], _localized_path("/portal/graph-view", active_locale))}
            {_nav_link(copy["admin"], _localized_path("/admin", active_locale), primary=True)}
          </div>
        </div>
        <h1>{knowledge_name}</h1>
        <p class="subtle">{copy["subtitle"]}</p>
        <p>{copy["hero"]}</p>
        <div class="row">
          <button class="primary" id="refresh-admin" data-testid="admin-refresh-button">{copy["refresh"]}</button>
          <span class="tag ok">{'Session 已建立' if is_zh else 'Session active'}</span>
          <span class="subtle" id="admin-refresh-status">{'尚未刷新' if is_zh else 'Not refreshed yet'}</span>
        </div>
        <div class="section-nav">
          {_nav_link(copy["overview"], _localized_path("/admin", active_locale), primary=section == "overview")}
          {_nav_link(copy["kb"], _localized_path("/admin/kb", active_locale), primary=section == "kb")}
          {_nav_link(copy["reviews"], _localized_path("/admin/reviews", active_locale), primary=section == "reviews")}
        </div>
        <div class="notice" id="admin-message" data-testid="admin-message" role="status" aria-live="polite">{copy["ready"]}</div>
      </section>
      {section_markup}
    </div>
    """

    ui_json = json.dumps(
        {
            "section": section,
            "refresh_busy": "刷新中..." if is_zh else "Refreshing...",
            "refresh_done_prefix": "最近刷新：" if is_zh else "Last refreshed: ",
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
        ensure_ascii=False,
    )
    quartz_json = json.dumps(quartz, ensure_ascii=False)
    script = """
    const UI = __UI__;
    const INITIAL_QUARTZ = __QUARTZ__;

    function setAdminMessage(message) {{
      document.getElementById('admin-message').textContent = message;
    }}

    function setRefreshStatus() {{
      const node = document.getElementById('admin-refresh-status');
      if (!node) return;
      node.textContent = `${{UI.refresh_done_prefix}}${{new Date().toLocaleTimeString()}}`;
    }}

    async function withBusyButton(button, busyLabel, task) {{
      const originalLabel = button.textContent;
      button.disabled = true;
      button.textContent = busyLabel;
      try {{
        return await task();
      }} finally {{
        button.disabled = false;
        button.textContent = originalLabel;
      }}
    }}

    async function fetchAdmin(url, options = {{}}) {{
      return fetchJson(url, options);
    }}

    function renderStats(overview) {{
      const stats = [
        [UI.stats_pending, overview.submission_counts.pending || 0],
        [UI.stats_draft, overview.submission_counts.draft_ready || 0],
        [UI.stats_queue, overview.queued_jobs || 0],
        [UI.stats_running, overview.running_jobs || 0],
        [UI.stats_cancel, overview.cancel_requested_jobs || 0],
        [UI.stats_stale, overview.stale_jobs || 0],
        [UI.stats_reviews, overview.pending_reviews || 0],
        [UI.stats_blocking, overview.severity_counts.blocking || 0]
      ];
      const node = document.getElementById('admin-stats');
      if (!node) return;
      node.innerHTML = stats.map(([label, value]) => `<div class="stat"><strong>${{value}}</strong><span>${{label}}</span></div>`).join('');

      const severityNode = document.getElementById('severity-bars');
      if (!severityNode) return;
      const total = Object.values(overview.severity_counts || {{}}).reduce((sum, value) => sum + value, 0) || 1;
      const severityOrder = ['blocking', 'high', 'medium', 'low'];
      severityNode.innerHTML = severityOrder.map(level => {{
        const count = overview.severity_counts[level] || 0;
        const width = Math.round((count / total) * 100);
        return `
          <div class="severity-item">
            <div class="row spread"><strong>${{escapeHtml(level)}}</strong><span>${{count}}</span></div>
            <div class="bar"><span style="width:${{width}}%;"></span></div>
          </div>
        `;
      }}).join('');
    }}

    function renderSubmissionAnalysis(analysis) {{
      if (!analysis) return '';
      const related = Array.isArray(analysis.related_entries) && analysis.related_entries.length
        ? analysis.related_entries.slice(0, 3).map(item => escapeHtml(item.name)).join(' · ')
        : '-';
      return `
        <div class="subtle" style="margin-top:8px;">${{escapeHtml(UI.submitted_advice)}}: ${{escapeHtml(analysis.recommended_type || '-')}} · ${{escapeHtml(analysis.duplicate_risk || '-')}} · ${{escapeHtml(analysis.committer_action || '-')}}</div>
        <div class="subtle">${{escapeHtml(analysis.summary || '')}}</div>
        <div class="subtle">${{escapeHtml(UI.submitted_related)}}: ${{related}}</div>
      `;
    }}

    function renderQuartzStatus(payload) {{
      const node = document.getElementById('quartz-status');
      if (!node) return;
      const statusLabel = payload.site_available
        ? UI.quartz_ready
        : payload.runtime_available
          ? UI.quartz_missing_site
          : UI.quartz_missing_runtime;
      node.innerHTML = `
        <div class="card">
          <div class="row spread">
            <strong>Quartz</strong>
            <span class="tag ${{payload.site_available ? 'ok' : payload.runtime_available ? 'warn' : 'danger'}}">${{escapeHtml(statusLabel)}}</span>
          </div>
          <div class="subtle">${{escapeHtml(UI.quartz_runtime_path)}}: ${{escapeHtml(payload.runtime_path)}}</div>
          <div class="subtle">${{escapeHtml(UI.quartz_site_path)}}: ${{escapeHtml(payload.site_path)}}</div>
          <div class="subtle">${{escapeHtml(UI.quartz_built_at)}}: ${{payload.site_last_built_at ? new Date(payload.site_last_built_at * 1000).toLocaleString() : '-'}}</div>
        </div>
      `;
    }}

    async function loadOverview() {{
      const overview = await fetchAdmin('/api/admin/overview');
      renderStats(overview);
    }}

    async function loadSystemStatus() {{
      const payload = await fetchAdmin('/api/admin/system/status');
      const node = document.getElementById('system-status');
      if (!node) return;
      const bytesMb = (payload.limits.max_upload_bytes / (1024 * 1024)).toFixed(1);
      node.innerHTML = `
        <div class="card">
          <div class="row spread"><strong>${{escapeHtml(UI.system_runtime)}}</strong><span class="tag">${{escapeHtml(payload.worker_mode)}}</span></div>
          <div class="subtle">${{escapeHtml(UI.system_auth)}}: ${{payload.auth_required ? UI.system_enabled : UI.system_disabled}}</div>
          <div class="subtle">${{escapeHtml(UI.system_proxy)}}: ${{payload.proxy.trust_proxy_headers ? UI.system_enabled : UI.system_disabled}}</div>
          <div class="subtle">${{escapeHtml(UI.system_rate)}}: ${{payload.limits.submission_rate_limit_count}} / ${{payload.limits.submission_rate_limit_window_seconds}}s</div>
          <div class="subtle">${{escapeHtml(UI.system_text_limit)}}: ${{payload.limits.max_text_submission_chars}}</div>
          <div class="subtle">${{escapeHtml(UI.system_upload_limit)}}: ${{bytesMb}} MiB</div>
          <div class="subtle">${{escapeHtml(UI.system_retry_limit)}}: ${{payload.limits.job_max_attempts}}</div>
          <div class="subtle">${{escapeHtml(UI.system_stale_limit)}}: ${{payload.limits.job_stale_after_seconds}}s</div>
          <div class="subtle">${{escapeHtml(UI.system_portal)}}: <a href="${{payload.urls.portal}}" target="_blank" rel="noreferrer">${{escapeHtml(payload.urls.portal)}}</a></div>
          <div class="subtle">${{escapeHtml(UI.system_admin)}}: <a href="${{payload.urls.admin}}" target="_blank" rel="noreferrer">${{escapeHtml(payload.urls.admin)}}</a></div>
          <div class="subtle">${{escapeHtml(UI.system_instance)}}: ${{escapeHtml(payload.instance.name)}}</div>
        </div>
      `;
    }}

    async function loadIssues() {{
      const payload = await fetchAdmin('/api/admin/health/issues');
      const node = document.getElementById('issue-list');
      if (!node) return;
      node.innerHTML = payload.issues.length
        ? payload.issues.slice(0, UI.section === 'overview' ? 8 : 20).map(item => `
            <div class="card">
              <div class="row spread">
                <strong>${{escapeHtml(item.target)}}</strong>
                <span class="tag ${{item.severity === 'blocking' || item.severity === 'high' ? 'danger' : item.severity === 'medium' ? 'warn' : 'ok'}}">${{escapeHtml(item.severity)}}</span>
              </div>
              <div class="subtle">${{escapeHtml(item.summary)}}</div>
              <div class="row" style="margin-top:10px;">
                <button data-action="run-tidy" data-target="${{encodeURIComponent(item.target)}}" data-issue-type="${{encodeURIComponent(item.type || '')}}">${{escapeHtml(UI.run_tidy)}}</button>
              </div>
            </div>
          `).join('')
        : `<div class="empty">${{escapeHtml(UI.issue_empty)}}</div>`;
    }}

    async function loadSubmissions() {{
      const payload = await fetchAdmin('/api/admin/submissions');
      const node = document.getElementById('submission-list');
      if (!node) return;
      node.innerHTML = payload.submissions.length
        ? payload.submissions.map(item => `
            <div class="card">
              <div class="row spread">
                <strong>${{escapeHtml(item.title)}}</strong>
                <span class="tag">${{escapeHtml(item.status)}}</span>
              </div>
              <div class="subtle">${{escapeHtml(item.submitter_name)}} · ${{escapeHtml(item.submission_type)}} · ${{escapeHtml(item.created_at || '')}}</div>
              ${{renderSubmissionAnalysis(item.analysis)}}
              <div class="row" style="margin-top:10px;">
                <button data-action="triage-submission" data-submission-id="${{item.id}}" data-status="triaged">${{escapeHtml(UI.triaged)}}</button>
                <button data-action="triage-submission" data-submission-id="${{item.id}}" data-status="rejected">${{escapeHtml(UI.reject)}}</button>
                <button class="primary" data-action="run-ingest" data-submission-id="${{item.id}}">${{escapeHtml(UI.run_ingest)}}</button>
              </div>
            </div>
          `).join('')
        : `<div class="empty">${{escapeHtml(UI.submission_empty)}}</div>`;
    }}

    async function loadReviews() {{
      const payload = await fetchAdmin('/api/admin/reviews?decision=pending');
      const node = document.getElementById('review-list');
      if (!node) return;
      node.innerHTML = payload.reviews.length
        ? payload.reviews.map(item => `
            <div class="card">
              <div class="row spread">
                <strong>${{escapeHtml(item.job.job_type)}} · ${{escapeHtml(item.job.id.slice(0, 8))}}</strong>
                <span class="tag">${{escapeHtml(item.decision)}}</span>
              </div>
              <div class="subtle">${{escapeHtml(item.job.result_payload?.summary || '')}}</div>
              <div class="row" style="margin-top:10px;">
                <button data-action="show-diff" data-review-id="${{item.id}}">${{escapeHtml(UI.show_diff)}}</button>
                <button class="primary" data-action="approve-review" data-review-id="${{item.id}}">${{escapeHtml(UI.approve)}}</button>
                <button data-action="reject-review" data-review-id="${{item.id}}">${{escapeHtml(UI.reject_review)}}</button>
              </div>
            </div>
          `).join('')
        : `<div class="empty">${{escapeHtml(UI.review_empty)}}</div>`;
    }}

    async function loadJobs() {{
      const payload = await fetchAdmin('/api/admin/jobs');
      const node = document.getElementById('job-list');
      if (!node) return;
      node.innerHTML = payload.jobs.length
        ? payload.jobs.map(item => `
            <div class="card">
              <div class="row spread">
                <strong>${{escapeHtml(item.job_type)}} · ${{escapeHtml(item.id.slice(0, 8))}}</strong>
                <span class="tag">${{escapeHtml(item.status)}}</span>
              </div>
              <div class="subtle">${{escapeHtml(item.error_message || item.result_payload?.summary || '')}}</div>
              <div class="subtle">${{item.attempt_count || 0}} / ${{item.max_attempts || 0}}</div>
              <div class="row" style="margin-top:10px;">
                ${{['failed', 'cancelled'].includes(item.status) ? `<button data-action="retry-job" data-job-id="${{item.id}}">${{escapeHtml(UI.retry)}}</button>` : ''}}
                ${{['queued', 'running', 'awaiting_review'].includes(item.status) ? `<button data-action="cancel-job" data-job-id="${{item.id}}">${{escapeHtml(UI.cancel)}}</button>` : ''}}
              </div>
            </div>
          `).join('')
        : `<div class="empty">${{escapeHtml(UI.job_empty)}}</div>`;
    }}

    async function loadAuditLogs() {{
      const payload = await fetchAdmin('/api/admin/audit?limit=12');
      const node = document.getElementById('audit-log-list');
      if (!node) return;
      node.innerHTML = payload.logs.length
        ? payload.logs.map(item => `
            <div class="card">
              <div class="row spread">
                <strong>${{escapeHtml(item.action)}}</strong>
                <span class="tag">${{escapeHtml(item.actor_role)}}</span>
              </div>
              <div class="subtle">${{escapeHtml(item.actor_name)}} · ${{escapeHtml(item.target_type)}} · ${{escapeHtml(item.created_at)}}</div>
              <div class="subtle">${{escapeHtml(JSON.stringify(item.details || {{}}))}}</div>
            </div>
          `).join('')
        : `<div class="empty">${{escapeHtml(UI.audit_empty)}}</div>`;
    }}

    async function loadQuartzStatus() {{
      const payload = await fetchAdmin('/api/admin/quartz/status');
      renderQuartzStatus(payload);
    }}

    async function runQuartzBuild() {{
      const payload = await fetchAdmin('/api/admin/quartz/build', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ actor_name: 'admin-web' }})
      }});
      renderQuartzStatus(payload);
      setAdminMessage(`${{UI.quartz_build_success}} ${{UI.quartz_cta}}`);
    }}

    async function runExplore() {{
      const question = document.getElementById('admin-explore-input').value.trim();
      const payload = await fetchAdmin('/api/admin/explore', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ question }})
      }});
      const node = document.getElementById('admin-explore-result');
      node.innerHTML = `
        <div class="card">
          <div class="row spread">
            <strong>${{escapeHtml(UI.explore_answer)}}</strong>
            <span class="tag">${{escapeHtml(payload.confidence || UI.unknown)}}</span>
          </div>
          <div class="subtle">${{escapeHtml(UI.explore_confidence)}}: ${{escapeHtml(payload.confidence || UI.unknown)}}</div>
          <div class="markdown">${{renderMarkdown(payload.answer || '')}}</div>
          <div class="subtle">${{escapeHtml(UI.explore_sources)}}: ${{escapeHtml((payload.sources || []).join(', ') || '-')}}</div>
          <div class="subtle">${{escapeHtml(UI.explore_gaps)}}: ${{escapeHtml((payload.gaps || []).join(' | ') || '-')}}</div>
        </div>
      `;
      setAdminMessage((payload.answer || '').slice(0, 140));
    }}

    async function triageSubmission(id, status) {{
      await fetchAdmin(`/api/admin/submissions/${{id}}/triage`, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ status, actor_name: 'admin-web' }})
      }});
      setAdminMessage(`${{UI.triage_done}} ${{status}} · ${{id.slice(0, 8)}}`);
      await refreshCurrentPage();
    }}

    async function runIngest(id) {{
      const job = await fetchAdmin(`/api/admin/submissions/${{id}}/run-ingest`, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ actor_name: 'admin-web' }})
      }});
      setAdminMessage(`${{UI.ingest_done}}${{job.id.slice(0, 8)}}`);
      await refreshCurrentPage();
    }}

    async function runTidy(issue) {{
      const job = await fetchAdmin('/api/admin/tidy', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ issue, actor_name: 'admin-web' }})
      }});
      setAdminMessage(`${{UI.tidy_done}}${{job.id.slice(0, 8)}}`);
      await refreshCurrentPage();
    }}

    async function showDiff(reviewId) {{
      const payload = await fetchAdmin(`/api/admin/reviews/${{reviewId}}`);
      const operations = payload.job.result_payload?.operations || [];
      const diffNode = document.getElementById('diff-view');
      if (diffNode) {{
        diffNode.textContent = operations.length ? operations.map(item => item.diff).join('\\n\\n') : UI.diff_empty;
      }}
      setAdminMessage(`${{UI.review_loaded}}${{reviewId.slice(0, 8)}}`);
    }}

    async function approveReview(reviewId) {{
      await fetchAdmin(`/api/admin/reviews/${{reviewId}}/approve`, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ reviewer_name: 'admin-web', comment: 'Approved from admin UI' }})
      }});
      setAdminMessage(`${{UI.review_approved}}${{reviewId.slice(0, 8)}}`);
      await refreshCurrentPage();
    }}

    async function rejectReview(reviewId) {{
      await fetchAdmin(`/api/admin/reviews/${{reviewId}}/reject`, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ reviewer_name: 'admin-web', comment: 'Rejected from admin UI' }})
      }});
      setAdminMessage(`${{UI.review_rejected}}${{reviewId.slice(0, 8)}}`);
      await refreshCurrentPage();
    }}

    async function retryJob(jobId) {{
      await fetchAdmin(`/api/admin/jobs/${{jobId}}/retry`, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ actor_name: 'admin-web' }})
      }});
      setAdminMessage(`${{UI.job_retried}}${{jobId.slice(0, 8)}}`);
      await refreshCurrentPage();
    }}

    async function cancelJob(jobId) {{
      await fetchAdmin(`/api/admin/jobs/${{jobId}}/cancel`, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ actor_name: 'admin-web', reason: 'Cancelled from admin UI' }})
      }});
      setAdminMessage(`${{UI.job_cancelled}}${{jobId.slice(0, 8)}}`);
      await refreshCurrentPage();
    }}

    async function loadEntryForEdit() {{
      const name = document.getElementById('editor-name').value.trim();
      const payload = await fetchAdmin(`/api/admin/entries/${{encodeURIComponent(name)}}`);
      document.getElementById('editor-content').value = payload.content;
      document.getElementById('editor-content').dataset.hash = payload.content_hash;
      document.getElementById('editor-status').textContent = `${{UI.editor_loaded}} ${{payload.name}} · hash=${{payload.content_hash.slice(0, 12)}}`;
      setAdminMessage(`${{UI.editor_loaded}} ${{payload.name}}`);
    }}

    async function saveEntry() {{
      const name = document.getElementById('editor-name').value.trim();
      const content = document.getElementById('editor-content').value;
      const expected_hash = document.getElementById('editor-content').dataset.hash || null;
      const payload = await fetchAdmin(`/api/admin/entries/${{encodeURIComponent(name)}}`, {{
        method: 'PUT',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ content, expected_hash, actor_name: 'admin-web' }})
      }});
      document.getElementById('editor-status').textContent = `${{UI.editor_saved}}：${{payload.name}}`;
      document.getElementById('editor-content').dataset.hash = payload.content_hash;
      setAdminMessage(`${{UI.editor_saved}} ${payload.name}`);
    }}

    async function runManualTidy() {{
      const target = document.getElementById('manual-tidy-target').value.trim();
      if (!target) throw new Error(UI.manual_tidy_target_required);
      await runTidy({{ target, type: 'manual_tidy_request' }});
    }}

    async function refreshCurrentPage() {{
      const tasks = [loadQuartzStatus(), loadSystemStatus()];
      if (UI.section === 'overview') {{
        tasks.push(loadOverview(), loadIssues(), loadAuditLogs());
      }}
      if (UI.section === 'kb') {{
        tasks.push(loadSubmissions(), loadIssues());
      }}
      if (UI.section === 'reviews') {{
        tasks.push(loadReviews(), loadJobs(), loadAuditLogs());
      }}
      await Promise.all(tasks);
      setRefreshStatus();
    }}

    function showAdminError(error) {{
      const diffNode = document.getElementById('diff-view');
      if (diffNode) diffNode.textContent = error.message;
      const exploreNode = document.getElementById('admin-explore-result');
      if (exploreNode && UI.section === 'kb') exploreNode.textContent = error.message;
      setAdminMessage(error.message);
    }}

    function bindClick(containerId, handler) {{
      const node = document.getElementById(containerId);
      if (!node) return;
      node.addEventListener('click', (event) => handler(event).catch(showAdminError));
    }}

    bindClick('issue-list', async (event) => {{
      const button = event.target.closest('button[data-action="run-tidy"]');
      if (!button) return;
      const issue = {{
        target: decodeURIComponent(button.dataset.target),
        type: button.dataset.issueType ? decodeURIComponent(button.dataset.issueType) : null,
      }};
      await withBusyButton(button, UI.busy_queue, () => runTidy(issue));
    }});

    bindClick('submission-list', async (event) => {{
      const button = event.target.closest('button[data-action]');
      if (!button) return;
      if (button.dataset.action === 'triage-submission') {{
        await withBusyButton(button, UI.busy_loading, () => triageSubmission(button.dataset.submissionId, button.dataset.status));
      }}
      if (button.dataset.action === 'run-ingest') {{
        await withBusyButton(button, UI.busy_queue, () => runIngest(button.dataset.submissionId));
      }}
    }});

    bindClick('review-list', async (event) => {{
      const button = event.target.closest('button[data-action]');
      if (!button) return;
      if (button.dataset.action === 'show-diff') {{
        await withBusyButton(button, UI.busy_loading, () => showDiff(button.dataset.reviewId));
      }}
      if (button.dataset.action === 'approve-review') {{
        await withBusyButton(button, UI.busy_approve, () => approveReview(button.dataset.reviewId));
      }}
      if (button.dataset.action === 'reject-review') {{
        await withBusyButton(button, UI.busy_reject, () => rejectReview(button.dataset.reviewId));
      }}
    }});

    bindClick('job-list', async (event) => {{
      const button = event.target.closest('button[data-action]');
      if (!button) return;
      if (button.dataset.action === 'retry-job') {{
        await withBusyButton(button, UI.busy_loading, () => retryJob(button.dataset.jobId));
      }}
      if (button.dataset.action === 'cancel-job') {{
        await withBusyButton(button, UI.busy_loading, () => cancelJob(button.dataset.jobId));
      }}
    }});

    document.getElementById('refresh-admin').addEventListener('click', (event) => withBusyButton(event.currentTarget, UI.refresh_busy, () => refreshCurrentPage()).catch(showAdminError));

    const loadEntryButton = document.getElementById('load-entry-button');
    if (loadEntryButton) {{
      loadEntryButton.addEventListener('click', (event) => withBusyButton(event.currentTarget, UI.busy_loading, () => loadEntryForEdit()).catch(showAdminError));
    }}
    const saveEntryButton = document.getElementById('save-entry-button');
    if (saveEntryButton) {{
      saveEntryButton.addEventListener('click', (event) => withBusyButton(event.currentTarget, UI.busy_saving, () => saveEntry()).catch(showAdminError));
    }}
    const exploreButton = document.getElementById('admin-explore-button');
    if (exploreButton) {{
      exploreButton.addEventListener('click', (event) => withBusyButton(event.currentTarget, UI.busy_loading, () => runExplore()).catch(showAdminError));
    }}
    const quartzButton = document.getElementById('admin-quartz-build-button');
    if (quartzButton) {{
      quartzButton.addEventListener('click', (event) => withBusyButton(event.currentTarget, UI.busy_loading, () => runQuartzBuild()).catch(showAdminError));
    }}
    const manualTidyButton = document.getElementById('manual-tidy-button');
    if (manualTidyButton) {{
      manualTidyButton.addEventListener('click', (event) => withBusyButton(event.currentTarget, UI.busy_queue, () => runManualTidy()).catch(showAdminError));
    }}

    renderQuartzStatus(INITIAL_QUARTZ);
    refreshCurrentPage().catch(showAdminError);
    setInterval(() => refreshCurrentPage().catch(showAdminError), 20000);
    """.replace("__UI__", ui_json).replace("__QUARTZ__", quartz_json).replace("{{", "{").replace("}}", "}")
    return shared_shell(f"{knowledge_name} Admin", body, script, locale=active_locale)
