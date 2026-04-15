(function () {
  const shell = window.SedimentShell;
  const pageData = shell.readJsonScript("sediment-page-data") || {};
  const UI = pageData.ui || {};
  const INITIAL_QUARTZ = pageData.quartz || {};
  const { collectUploads, escapeHtml, fetchJson, renderMarkdown } = shell;
  const isZh = document.documentElement.dataset.locale === "zh";
  const state = {
    reviews: [],
    reviewDetails: {},
    selectedReviewId: null,
    users: [],
    revealedTokens: {},
    documents: { counts: {}, documents_by_name: {}, top_indexes: [], unindexed_documents: [], health_issues: [] },
    fileSuggestions: [],
    selectedDocumentName: null,
    selectedDocumentDetail: null,
    ingestFiles: [],
  };
  let fileSuggestionRequestId = 0;
  let fileSearchAutoLoadTimer = 0;

  function setAdminMessage(message) {
    const node = document.getElementById("admin-message");
    if (node) node.textContent = String(message || "");
  }

  function setSectionStatus(id, message) {
    const node = document.getElementById(id);
    if (node) node.textContent = String(message || "");
  }

  function formatDateTime(value) {
    if (!value) return "-";
    const numeric = Number(value);
    if (Number.isFinite(numeric) && String(value).length <= 12) {
      return new Date(numeric * 1000).toLocaleString();
    }
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
  }

  async function withBusyButton(button, busyLabel, task) {
    if (!button) return task();
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

  async function fetchAdmin(url, options = {}) {
    return fetchJson(url, options);
  }

  function showAdminError(error) {
    const message = error && error.message ? error.message : "Unknown error";
    const diffNode = document.getElementById("diff-view");
    if (diffNode) diffNode.textContent = message;
    const exploreNode = document.getElementById("admin-explore-result");
    if (exploreNode && UI.section === "kb") exploreNode.textContent = message;
    setSectionStatus("editor-status", message);
    setSectionStatus("admin-ingest-status", message);
    setSectionStatus("settings-status", message);
    setAdminMessage(message);
  }

  function roleLabel(role) {
    if (role === "owner") return UI.role_owner || "owner";
    if (role === "committer") return UI.role_committer || "committer";
    return role || "-";
  }

  function scopeLabel(scope) {
    if (scope === "full") return UI.scope_full || "Full KB";
    if (scope === "graph") return UI.scope_graph || "Graph";
    if (scope === "indexes") return UI.scope_indexes || "Indexes";
    if (scope === "health_blocking") return UI.scope_health_blocking || "Blocking issues";
    return scope || "-";
  }

  function scopeForIssue(issue) {
    const issueType = String((issue || {}).type || "").trim().toLowerCase();
    if (["dangling_link", "orphan_entry", "canonical_gap", "promotable_placeholder"].includes(issueType)) {
      return "graph";
    }
    if (["invalid_index", "overloaded_index", "unknown_index_link"].includes(issueType)) {
      return "indexes";
    }
    return "health_blocking";
  }

  function actionLabel(action) {
    if (action === "run_tidy") return isZh ? "KB 级 tidy" : "KB-level tidy";
    if (action === "edit_entry") return isZh ? "在线编辑" : "Inline edit";
    if (action === "promote_placeholder") return isZh ? "补全并提升 placeholder" : "Promote placeholder";
    if (action === "review_entry") return isZh ? "人工复核" : "Manual review";
    return action || "-";
  }

  function docGroupLabel(group) {
    if (group === "formal") return UI.doc_group_formal || "Formal entries";
    if (group === "placeholder") return UI.doc_group_placeholder || "Placeholders";
    if (group === "index") return UI.doc_group_index || "Indexes";
    return group || "-";
  }

  function selectedDocumentRecord() {
    return state.documents?.documents_by_name?.[state.selectedDocumentName] || null;
  }

  function updateEditorPreview(content) {
    const node = document.getElementById("editor-preview");
    if (!node) return;
    const text = String(content || "");
    if (!text.trim()) {
      node.className = "markdown empty";
      node.textContent = UI.editor_preview_empty || "";
      return;
    }
    node.className = "markdown";
    node.innerHTML = renderMarkdown(text);
  }

  function renderFileCounts() {
    const node = document.getElementById("admin-file-counts");
    if (!node) return;
    const counts = state.documents?.counts || {};
    const stats = [
      [UI.file_counts_formal || "Formal", counts.formal || 0],
      [UI.file_counts_placeholder || "Placeholders", counts.placeholder || 0],
      [UI.file_counts_index || "Indexes", counts.index || 0],
      [UI.file_counts_indexed || "Indexed", counts.indexed || 0],
      [UI.file_counts_unindexed || "Unindexed", counts.unindexed || 0],
    ];
    node.innerHTML = stats
      .map(
        ([label, value]) =>
          `<div class="stat"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`
      )
      .join("");
  }

  function setCurrentDocumentLabel() {
    const node = document.getElementById("admin-file-current-name");
    if (!node) return;
    const detail = state.selectedDocumentDetail;
    const record = selectedDocumentRecord();
    node.textContent =
      detail?.structured?.title ||
      record?.title ||
      state.selectedDocumentName ||
      UI.doc_select_prompt ||
      (isZh ? "请先选择文档。" : "Select a document first.");
  }

  function syncFileEditorState() {
    const editor = document.getElementById("editor-content");
    const saveButton = document.getElementById("save-entry-button");
    const hasSelection = Boolean(state.selectedDocumentName);
    if (editor) {
      editor.disabled = !hasSelection;
      if (!hasSelection) {
        editor.value = "";
        editor.dataset.hash = "";
      }
    }
    if (saveButton) saveButton.disabled = !hasSelection;
    if (!hasSelection) {
      updateEditorPreview("");
      setSectionStatus("editor-status", UI.doc_select_prompt || (isZh ? "请先选择文档。" : "Select a document first."));
    }
    setCurrentDocumentLabel();
  }

  function renderStats(overview) {
    const node = document.getElementById("admin-stats");
    if (!node) return;
    const stats = [
      [UI.stats_pending, overview.submission_counts?.pending || 0],
      [UI.stats_queue, overview.queued_jobs || 0],
      [UI.stats_running, overview.running_jobs || 0],
      [UI.stats_reviews, overview.pending_reviews || 0],
      [UI.stats_blocking, overview.severity_counts?.blocking || 0],
      [UI.stats_stale, overview.stale_jobs || 0],
    ];
    node.innerHTML = stats
      .map(
        ([label, value]) =>
          `<div class="stat"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`
      )
      .join("");

    const severityNode = document.getElementById("severity-bars");
    if (!severityNode) return;
    const total =
      Object.values(overview.severity_counts || {}).reduce((sum, value) => sum + value, 0) || 1;
    const severityOrder = ["blocking", "high", "medium", "low"];
    severityNode.innerHTML = severityOrder
      .map((level) => {
        const count = overview.severity_counts?.[level] || 0;
        const width = Math.round((count / total) * 100);
        return `
          <div class="severity-item">
            <div class="row spread"><strong>${escapeHtml(level)}</strong><span>${escapeHtml(count)}</span></div>
            <div class="bar"><span style="width:${width}%;"></span></div>
          </div>
        `;
      })
      .join("");
  }

  function renderIssueList(issues) {
    const node = document.getElementById("issue-list");
    if (!node) return;
    node.innerHTML = Array.isArray(issues) && issues.length
      ? issues.map((item) => {
          const severityClass =
            item.severity === "blocking" || item.severity === "high"
              ? "danger"
              : item.severity === "medium"
                ? "warn"
                : "ok";
          return `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(item.target)}</strong>
                <span class="tag ${severityClass}">${escapeHtml(item.severity)}</span>
              </div>
              <div class="subtle">${escapeHtml(item.summary || "")}</div>
              <div class="issue-card-meta">
                <span class="tag">${escapeHtml(UI.issue_target_label || "Target")}: ${escapeHtml(item.target || "-")}</span>
                <span class="tag">${escapeHtml(UI.issue_action_label || "Suggested action")}: ${escapeHtml(actionLabel(item.suggested_action || ""))}</span>
                ${
                  item.suggested_action === "run_tidy"
                    ? `<span class="tag">${escapeHtml(UI.issue_scope_label || "Suggested scope")}: ${escapeHtml(scopeLabel(scopeForIssue(item)))}</span>`
                    : ""
                }
              </div>
            </div>
          `;
        }).join("")
      : `<div class="empty">${escapeHtml(UI.issue_empty)}</div>`;
  }

  function renderAuditLogs(logs) {
    const node = document.getElementById("audit-log-list");
    if (!node) return;
    node.innerHTML = Array.isArray(logs) && logs.length
      ? logs.map((item) => `
          <div class="card">
            <div class="row spread">
              <strong>${escapeHtml(item.action || "")}</strong>
              <span class="tag">${escapeHtml(roleLabel(item.actor_role || ""))}</span>
            </div>
            <div class="subtle">${escapeHtml(item.actor_name || "")} · ${escapeHtml(item.target_type || "")} · ${escapeHtml(formatDateTime(item.created_at))}</div>
            <div class="subtle">${escapeHtml(JSON.stringify(item.details || {}))}</div>
          </div>
        `).join("")
      : `<div class="empty">${escapeHtml(UI.audit_empty)}</div>`;
  }

  function renderSubmissionAnalysis(analysis) {
    if (!analysis) return "";
    const related = Array.isArray(analysis.related_entries) && analysis.related_entries.length
      ? analysis.related_entries.slice(0, 4).map((item) => escapeHtml(item.name || "")).join(" · ")
      : "-";
    return `
      <div class="subtle">${escapeHtml(analysis.summary || "")}</div>
      <div class="subtle">${escapeHtml(analysis.recommended_type || "-")} · ${escapeHtml(analysis.duplicate_risk || "-")} · ${escapeHtml(analysis.committer_action || "-")}</div>
      <div class="subtle">${related}</div>
    `;
  }

  function renderSubmissions(submissions) {
    const node = document.getElementById("submission-list");
    if (!node) return;
    node.innerHTML = Array.isArray(submissions) && submissions.length
      ? submissions.map((item) => `
          <div class="card">
            <div class="row spread">
              <strong>${escapeHtml(item.title || "")}</strong>
              <span class="tag">${escapeHtml(item.status || "")}</span>
            </div>
            <div class="subtle">${escapeHtml(item.submitter_name || "")} · ${escapeHtml(item.submission_type || "")} · ${escapeHtml(formatDateTime(item.created_at))}</div>
            ${renderSubmissionAnalysis(item.analysis)}
            <div class="row" style="margin-top:10px;">
              <button data-action="triage-submission" data-submission-id="${escapeHtml(item.id || "")}" data-status="triaged">${escapeHtml(UI.triaged)}</button>
              <button data-action="triage-submission" data-submission-id="${escapeHtml(item.id || "")}" data-status="rejected">${escapeHtml(UI.reject)}</button>
              <button class="primary" data-action="run-ingest" data-submission-id="${escapeHtml(item.id || "")}">${escapeHtml(UI.run_ingest)}</button>
            </div>
          </div>
        `).join("")
      : `<div class="empty">${escapeHtml(UI.submission_empty)}</div>`;
  }

  function renderReviews(reviews) {
    const node = document.getElementById("review-list");
    if (!node) return;
    state.reviews = Array.isArray(reviews) ? reviews : [];
    node.innerHTML = state.reviews.length
      ? state.reviews.map((item) => {
          const reviewId = String(item.id || "");
          const selected = reviewId === state.selectedReviewId;
          const headline =
            item.submission?.title ||
            item.job?.result_payload?.summary ||
            `${item.job?.job_type || ""} · ${reviewId.slice(0, 8)}`;
          return `
            <button
              type="button"
              class="card interactive ${selected ? "selected" : ""}"
              data-action="select-review"
              data-review-id="${escapeHtml(reviewId)}"
            >
              <div class="row spread">
                <strong>${escapeHtml(headline)}</strong>
                <span class="tag">${escapeHtml(item.decision || "")}</span>
              </div>
              <div class="subtle">${escapeHtml(item.job?.job_type || "")} · ${escapeHtml((item.job?.id || "").slice(0, 8))}</div>
              <div class="subtle">${escapeHtml(item.job?.result_payload?.summary || "")}</div>
              <div class="issue-card-meta">
                ${item.submission?.status ? `<span class="tag">${escapeHtml(UI.review_submission_status || "Submission status")}: ${escapeHtml(item.submission.status)}</span>` : ""}
                <span class="tag">${escapeHtml(UI.review_patch_count || "Operations")}: ${escapeHtml((item.job?.result_payload?.operations || []).length || 0)}</span>
                <span class="tag">${escapeHtml(UI.review_created_at || "Created")}: ${escapeHtml(formatDateTime(item.created_at || item.job?.created_at || ""))}</span>
              </div>
            </button>
          `;
        }).join("")
      : `<div class="empty">${escapeHtml(UI.review_empty)}</div>`;
    syncReviewActionState();
  }

  function renderReviewDetail(payload) {
    const metaNode = document.getElementById("review-detail-meta");
    const diffNode = document.getElementById("diff-view");
    const commentNode = document.getElementById("review-comment");
    if (!metaNode || !diffNode) return;
    if (!payload || !payload.review || !payload.job) {
      metaNode.innerHTML = `<div class="empty">${escapeHtml(UI.review_queue_empty_detail || UI.review_select_prompt || UI.diff_empty)}</div>`;
      diffNode.textContent = UI.diff_empty;
      if (commentNode) commentNode.value = "";
      syncReviewActionState();
      return;
    }
    const operations = payload.job?.result_payload?.operations || [];
    const submission = payload.submission || null;
    metaNode.innerHTML = `
      <div class="detail-meta-grid">
        <div class="detail-block">
          <strong>${escapeHtml(UI.review_summary || "Patch summary")}</strong>
          <p>${escapeHtml(payload.job?.result_payload?.summary || "-")}</p>
        </div>
        <div class="detail-block">
          <strong>${escapeHtml(UI.review_job_type || "Job type")}</strong>
          <p>${escapeHtml(payload.job?.job_type || "-")} · ${escapeHtml((payload.job?.id || "").slice(0, 8))}</p>
        </div>
        <div class="detail-block">
          <strong>${escapeHtml(UI.review_decision || "Current state")}</strong>
          <p>${escapeHtml(payload.review?.decision || "-")}</p>
        </div>
        <div class="detail-block">
          <strong>${escapeHtml(UI.review_patch_count || "Operations")}</strong>
          <p>${escapeHtml(operations.length || 0)}</p>
        </div>
        <div class="detail-block">
          <strong>${escapeHtml(UI.review_created_at || "Created")}</strong>
          <p>${escapeHtml(formatDateTime(payload.review?.created_at || payload.job?.created_at || ""))}</p>
        </div>
        ${
          submission
            ? `
              <div class="detail-block">
                <strong>${escapeHtml(UI.review_source_submission || "Source submission")}</strong>
                <p>${escapeHtml(submission.title || submission.id || "-")}</p>
              </div>
              <div class="detail-block">
                <strong>${escapeHtml(UI.review_submission_author || "Submitter")}</strong>
                <p>${escapeHtml(submission.submitter_name || "-")}</p>
              </div>
              <div class="detail-block">
                <strong>${escapeHtml(UI.review_submission_status || "Submission status")}</strong>
                <p>${escapeHtml(submission.status || "-")}</p>
              </div>
            `
            : ""
        }
      </div>
    `;
    diffNode.textContent = operations.length
      ? operations.map((item) => item.diff || "").join("\n\n")
      : UI.diff_empty;
    if (commentNode) commentNode.value = payload.review?.comment || "";
    syncReviewActionState();
  }

  function renderJobs(jobs) {
    const node = document.getElementById("job-list");
    if (!node) return;
    node.innerHTML = Array.isArray(jobs) && jobs.length
      ? jobs.map((item) => `
          <div class="card">
            <div class="row spread">
              <strong>${escapeHtml(item.job_type || "")} · ${escapeHtml((item.id || "").slice(0, 8))}</strong>
              <span class="tag">${escapeHtml(item.status || "")}</span>
            </div>
            <div class="subtle">${escapeHtml(item.error_message || item.result_payload?.summary || "")}</div>
            <div class="subtle">${escapeHtml(item.attempt_count || 0)} / ${escapeHtml(item.max_attempts || 0)}</div>
            <div class="row" style="margin-top:10px;">
              ${
                ["failed", "cancelled"].includes(item.status)
                  ? `<button data-action="retry-job" data-job-id="${escapeHtml(item.id || "")}">${escapeHtml(UI.retry)}</button>`
                  : ""
              }
              ${
                ["queued", "running", "awaiting_review"].includes(item.status)
                  ? `<button data-action="cancel-job" data-job-id="${escapeHtml(item.id || "")}">${escapeHtml(UI.cancel)}</button>`
                  : ""
              }
            </div>
          </div>
        `).join("")
      : `<div class="empty">${escapeHtml(UI.job_empty)}</div>`;
  }

  function renderQuartzStatus(payload) {
    const node = document.getElementById("quartz-status");
    if (!node) return;
    const statusLabel = payload.site_available
      ? UI.quartz_ready
      : payload.runtime_available
        ? UI.quartz_missing_site
        : UI.quartz_missing_runtime;
    const statusClass = payload.site_available ? "ok" : payload.runtime_available ? "warn" : "danger";
    node.innerHTML = `
      <div class="card">
        <div class="row spread">
          <strong>Quartz</strong>
          <span class="tag ${statusClass}">${escapeHtml(statusLabel)}</span>
        </div>
        <div class="subtle">${escapeHtml(UI.quartz_runtime_path)}: ${escapeHtml(payload.runtime_path || "-")}</div>
        <div class="subtle">${escapeHtml(UI.quartz_site_path)}: ${escapeHtml(payload.site_path || "-")}</div>
        <div class="subtle">${escapeHtml(UI.quartz_built_at)}: ${escapeHtml(formatDateTime(payload.site_last_built_at))}</div>
      </div>
    `;
  }

  function renderSystemStatus(payload) {
    const node = document.getElementById("system-status");
    if (!node) return;
    const bytesMb = Number(payload.limits?.max_upload_bytes || 0) / (1024 * 1024);
    node.innerHTML = `
      <div class="card">
        <div class="row spread"><strong>${escapeHtml(payload.instance?.name || "")}</strong><span class="tag">${escapeHtml(payload.worker_mode || "")}</span></div>
        <div class="subtle">${escapeHtml(isZh ? "鉴权" : "Auth")}: ${escapeHtml(payload.auth_required ? (isZh ? "启用" : "enabled") : (isZh ? "关闭" : "disabled"))}</div>
        <div class="subtle">${escapeHtml(isZh ? "代理" : "Proxy")}: ${escapeHtml(payload.proxy?.trust_proxy_headers ? (isZh ? "启用" : "enabled") : (isZh ? "关闭" : "disabled"))}</div>
        <div class="subtle">${escapeHtml(isZh ? "速率" : "Rate")}: ${escapeHtml(payload.limits?.submission_rate_limit_count || 0)} / ${escapeHtml(payload.limits?.submission_rate_limit_window_seconds || 0)}s</div>
        <div class="subtle">${escapeHtml(isZh ? "文本" : "Text")}: ${escapeHtml(payload.limits?.max_text_submission_chars || 0)}</div>
        <div class="subtle">${escapeHtml(isZh ? "上传" : "Upload")}: ${escapeHtml(bytesMb.toFixed(1))} MiB</div>
        <div class="subtle">${escapeHtml(isZh ? "重试" : "Retry")}: ${escapeHtml(payload.limits?.job_max_attempts || 0)}</div>
        <div class="subtle">${escapeHtml(isZh ? "陈旧阈值" : "Stale")}: ${escapeHtml(payload.limits?.job_stale_after_seconds || 0)}s</div>
        <div class="subtle"><a href="${escapeHtml(payload.urls?.portal || "/")}" target="_blank" rel="noreferrer">${escapeHtml(payload.urls?.portal || "/")}</a></div>
        <div class="subtle"><a href="${escapeHtml(payload.urls?.mcp_sse || "/")}" target="_blank" rel="noreferrer">${escapeHtml(payload.urls?.mcp_sse || "/")}</a></div>
      </div>
    `;
  }

  function renderUserList(users) {
    const node = document.getElementById("user-list");
    if (!node) return;
    state.users = Array.isArray(users) ? users : [];
    node.innerHTML = state.users.length
      ? state.users.map((user) => {
          const userId = String(user.id || "");
          const token = state.revealedTokens[userId];
          const isCurrent = String(UI.user?.id || "") === userId;
          const tokenActionLabel = token ? UI.token_hide || "Hide token" : UI.token_show || "Show token";
          return `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(user.name || user.id || "")}</strong>
                <span class="tag ${user.disabled ? "warn" : "ok"}">${escapeHtml(roleLabel(user.role || ""))}${user.disabled ? ` · ${escapeHtml(UI.user_disabled_label || (isZh ? "已停用" : "disabled"))}` : ""}</span>
              </div>
              <div class="subtle">${escapeHtml(user.id || "")} · ${escapeHtml(user.token_fingerprint || "")}</div>
              <div class="subtle">${escapeHtml(formatDateTime(user.created_at))}</div>
              <div class="user-card-meta">
                ${isCurrent ? `<span class="tag">${escapeHtml(UI.current_session || "Current session")}</span>` : ""}
              </div>
              <div class="row" style="margin-top:10px;">
                <button data-action="show-token" data-user-id="${escapeHtml(userId)}">${escapeHtml(tokenActionLabel)}</button>
                ${user.disabled ? "" : `<button data-action="disable-user" data-user-id="${escapeHtml(userId)}">${escapeHtml(UI.disable_user || (isZh ? "停用" : "Disable"))}</button>`}
              </div>
              ${
                token
                  ? `
                    <div class="inline-token">
                      <strong>${escapeHtml(UI.token_label || "Token")}</strong>
                      <div class="mono">${escapeHtml(token)}</div>
                    </div>
                  `
                  : ""
              }
            </div>
          `;
        }).join("")
      : `<div class="empty">${escapeHtml(isZh ? "暂无用户。" : "No users.")}</div>`;
  }

  function renderDocumentButton(doc) {
    return `
      <button
        type="button"
        class="button doc-button ${doc.name === state.selectedDocumentName ? "active" : ""}"
        data-action="open-document"
        data-name="${escapeHtml(doc.name)}"
      >
        <span class="doc-button-label">
          <span class="doc-button-title">${escapeHtml(doc.title || doc.name)}</span>
          <span class="doc-button-meta">
            ${escapeHtml(doc.relative_path || "-")}
            ${doc.issue_count ? ` · ${escapeHtml(doc.issue_count)} ${escapeHtml(UI.doc_issues_label || "Issues")}` : ""}
          </span>
        </span>
      </button>
    `;
  }

  function renderIndexNode(node, level = 0) {
    const directDocuments = Array.isArray(node.direct_documents) ? node.direct_documents : [];
    const childIndexes = Array.isArray(node.child_indexes) ? node.child_indexes : [];
    const childMarkup = childIndexes.map((child) => renderIndexNode(child, level + 1)).join("");
    const directDocMarkup = directDocuments.map((doc) => renderDocumentButton(doc)).join("");
    const itemCount = Number(node.reachable_document_count || 0);
    const tokenCount = Number(node.estimated_tokens || 0);
    return `
      <details class="doc-tree-group index-tree-group" ${level < 1 ? "open" : ""}>
        <summary>
          <span class="doc-tree-summary">
            <strong>${escapeHtml(node.title || node.name)}</strong>
            <span class="doc-button-meta">
              ${escapeHtml(node.name || "")}
              · ${escapeHtml(itemCount)} ${escapeHtml(UI.file_counts_indexed || "Indexed")}
              · ${escapeHtml(tokenCount)} ${escapeHtml(UI.file_tokens_label || "tokens")}
            </span>
          </span>
        </summary>
        <div class="doc-tree-list">
          ${
            childMarkup
              ? `
                <div class="stack">
                  <div class="tabs-note">${escapeHtml(UI.file_index_child_indexes || "Child indexes")}</div>
                  ${childMarkup}
                </div>
              `
              : ""
          }
          ${
            directDocMarkup
              ? `
                <div class="stack">
                  <div class="tabs-note">${escapeHtml(UI.file_index_direct_docs || "Direct documents")}</div>
                  <div class="doc-tree-list">${directDocMarkup}</div>
                </div>
              `
              : ""
          }
        </div>
      </details>
    `;
  }

  function renderFileIndexTree() {
    const node = document.getElementById("admin-file-index-tree");
    if (!node) return;
    const topIndexes = Array.isArray(state.documents?.top_indexes) ? state.documents.top_indexes : [];
    const unindexed = Array.isArray(state.documents?.unindexed_documents) ? state.documents.unindexed_documents : [];
    const sections = topIndexes.map((item) => renderIndexNode(item));
    if (unindexed.length) {
      sections.push(`
        <details class="doc-tree-group" open>
          <summary>${escapeHtml(UI.file_unindexed_group || "Documents outside all indexes")} (${escapeHtml(unindexed.length)})</summary>
          <div class="doc-tree-list">
            ${unindexed.map((doc) => renderDocumentButton(doc)).join("")}
          </div>
        </details>
      `);
    }
    node.innerHTML = sections.join("") || `<div class="empty">${escapeHtml(UI.doc_browser_empty || UI.file_search_empty)}</div>`;
  }

  function renderDocumentMeta() {
    const node = document.getElementById("admin-doc-meta");
    if (!node) return;
    const detail = state.selectedDocumentDetail;
    const doc = selectedDocumentRecord();
    if (!detail && !doc) {
      node.innerHTML = `<div class="empty">${escapeHtml(UI.doc_select_prompt || UI.doc_browser_empty)}</div>`;
      setCurrentDocumentLabel();
      return;
    }
    const aliases = detail?.structured?.aliases || doc?.aliases || [];
    const links =
      detail?.structured?.related_links ||
      detail?.metadata?.links ||
      doc?.links ||
      [];
    const indexes = doc?.indexes || [];
    const linkedIssues = (state.documents?.health_issues || []).filter(
      (item) => item.document_name === (detail?.name || doc?.name)
    );
    const blocks = [
      [UI.doc_path_label || "Path", doc?.relative_path || detail?.path || "-"],
      [UI.doc_kind_label || "Kind", detail?.structured?.kind || doc?.kind || "-"],
      [UI.doc_status_label || "Status", detail?.structured?.status || doc?.status || "-"],
      [UI.doc_issues_label || "Issues", linkedIssues.length || 0],
      [UI.doc_indexes_label || "Indexes", indexes.length ? indexes.join(" · ") : "-"],
      [UI.doc_aliases_label || "Aliases", aliases.length ? aliases.join(" · ") : "-"],
      [UI.doc_links_label || "Links", links.length ? links.join(" · ") : "-"],
      [UI.doc_updated_label || "Updated", doc?.updated_at ? formatDateTime(doc.updated_at) : "-"],
    ];
    node.innerHTML = blocks
      .map(
        ([label, value]) => `
          <div class="detail-block">
            <strong>${escapeHtml(label)}</strong>
            <p>${escapeHtml(value)}</p>
          </div>
        `
      )
      .join("");
    setCurrentDocumentLabel();
  }

  function renderDocHealthList() {
    const node = document.getElementById("admin-doc-health-list");
    if (!node) return;
    const issues = state.documents?.health_issues || [];
    node.innerHTML = issues.length
      ? issues.map((item) => {
          const severityClass =
            item.severity === "blocking" || item.severity === "high"
              ? "danger"
              : item.severity === "medium"
                ? "warn"
                : "ok";
          return `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(item.document_name || item.target || "-")}</strong>
                <span class="tag ${severityClass}">${escapeHtml(item.severity || "")}</span>
              </div>
              <div class="subtle">${escapeHtml(item.summary || "")}</div>
              <div class="issue-card-meta">
                <span class="tag">${escapeHtml(item.type || "")}</span>
                ${item.document_name ? `<span class="tag">${escapeHtml(UI.issue_open_document || "Open document")}</span>` : ""}
              </div>
              ${
                item.document_name
                  ? `
                    <div class="row" style="margin-top:10px;">
                      <button data-action="open-document" data-name="${escapeHtml(item.document_name)}">${escapeHtml(UI.issue_open_document || "Open document")}</button>
                    </div>
                  `
                  : ""
              }
            </div>
          `;
        }).join("")
      : `<div class="empty">${escapeHtml(UI.doc_health_empty)}</div>`;
  }

  function renderLinkedIssues() {
    const node = document.getElementById("admin-doc-linked-issues");
    if (!node) return;
    const name = state.selectedDocumentName;
    const issues = (state.documents?.health_issues || []).filter((item) => item.document_name === name);
    node.innerHTML = issues.length
      ? issues.map((item) => `
          <div class="card">
            <div class="row spread">
              <strong>${escapeHtml(item.type || "")}</strong>
              <span class="tag">${escapeHtml(item.severity || "")}</span>
            </div>
            <div class="subtle">${escapeHtml(item.summary || "")}</div>
          </div>
        `).join("")
      : `<div class="empty">${escapeHtml(UI.editor_linked_issues_empty)}</div>`;
  }

  function syncReviewActionState() {
    const hasSelection = Boolean(state.selectedReviewId);
    const approveButton = document.getElementById("approve-review-button");
    const rejectButton = document.getElementById("reject-review-button");
    if (approveButton) approveButton.disabled = !hasSelection;
    if (rejectButton) rejectButton.disabled = !hasSelection;
  }

  async function loadOverview() {
    const overview = await fetchAdmin("/api/admin/overview");
    renderStats(overview);
  }

  async function loadIssues() {
    const payload = await fetchAdmin("/api/admin/health/issues");
    renderIssueList(payload.issues || []);
  }

  async function loadAuditLogs() {
    const payload = await fetchAdmin("/api/admin/audit?limit=12");
    renderAuditLogs(payload.logs || []);
  }

  async function loadSubmissions() {
    const payload = await fetchAdmin("/api/admin/submissions");
    renderSubmissions(payload.submissions || []);
  }

  function hideFileSuggestions() {
    const node = document.getElementById("admin-file-suggestions");
    const input = document.getElementById("admin-file-search");
    if (node) {
      node.hidden = true;
      node.innerHTML = "";
    }
    if (input) input.setAttribute("aria-expanded", "false");
  }

  function renderFileSuggestions(suggestions) {
    const node = document.getElementById("admin-file-suggestions");
    const input = document.getElementById("admin-file-search");
    if (!node || !input) return;
    const items = Array.isArray(suggestions) ? suggestions : [];
    if (!items.length) {
      hideFileSuggestions();
      return;
    }
    node.hidden = false;
    input.setAttribute("aria-expanded", "true");
    node.innerHTML = `
      <div class="list">
        ${items.map((item) => `
          <button
            type="button"
            class="search-suggestion"
            data-action="open-document"
            data-name="${escapeHtml(item.name || "")}"
          >
            <span class="doc-button-label">
              <span class="doc-button-title">${escapeHtml(item.title || item.name || "")}</span>
              <span class="doc-button-meta">${escapeHtml(item.relative_path || "-")} · ${escapeHtml(docGroupLabel(item.group || item.kind || ""))}</span>
            </span>
          </button>
        `).join("")}
      </div>
    `;
  }

  async function updateFileSuggestions() {
    const input = document.getElementById("admin-file-search");
    if (!input) return;
    const query = String(input.value || "").trim();
    window.clearTimeout(fileSearchAutoLoadTimer);
    fileSuggestionRequestId += 1;
    const requestId = fileSuggestionRequestId;
    if (!query) {
      state.fileSuggestions = [];
      hideFileSuggestions();
      setSectionStatus("admin-file-search-status", UI.file_search_hint || "");
      return;
    }
    const payload = await fetchAdmin(`/api/admin/files/suggest?q=${encodeURIComponent(query)}`);
    if (requestId !== fileSuggestionRequestId) return;
    state.fileSuggestions = payload.suggestions || [];
    renderFileSuggestions(state.fileSuggestions);
    if (!state.fileSuggestions.length) {
      setSectionStatus("admin-file-search-status", UI.file_search_empty || "");
      return;
    }
    setSectionStatus(
      "admin-file-search-status",
      `${state.fileSuggestions.length} ${UI.file_search_matches || "matches"}`
    );
    const normalizedQuery = query.toLowerCase();
    const exactMatch = state.fileSuggestions.find((item) => {
      const candidates = [item.name, item.title].filter(Boolean).map((value) => String(value).toLowerCase());
      return candidates.includes(normalizedQuery);
    });
    if (exactMatch && exactMatch.name !== state.selectedDocumentName) {
      setSectionStatus(
        "admin-file-search-status",
        `${UI.file_search_auto_loading || "Exact match detected, loading: "}${exactMatch.name}`
      );
      fileSearchAutoLoadTimer = window.setTimeout(() => {
        const latestQuery = String(document.getElementById("admin-file-search")?.value || "").trim().toLowerCase();
        if (latestQuery === normalizedQuery) {
          openDocument(exactMatch.name).catch(showAdminError);
        }
      }, 180);
    }
  }

  async function loadFileManager() {
    const payload = await fetchAdmin("/api/admin/files");
    state.documents = payload;
    if (state.selectedDocumentName) {
      const known = Boolean(payload.documents_by_name?.[state.selectedDocumentName]);
      if (!known) {
        state.selectedDocumentName = null;
        state.selectedDocumentDetail = null;
      }
    }
    renderFileCounts();
    renderFileIndexTree();
    renderDocHealthList();
    renderDocumentMeta();
    renderLinkedIssues();
    syncFileEditorState();
  }

  async function loadReviews() {
    const payload = await fetchAdmin("/api/admin/reviews?decision=pending");
    const reviews = payload.reviews || [];
    if (state.selectedReviewId && !reviews.some((item) => item.id === state.selectedReviewId)) {
      state.selectedReviewId = null;
    }
    if (!state.selectedReviewId && reviews.length) {
      state.selectedReviewId = String(reviews[0].id || "");
    }
    renderReviews(reviews);
    if (state.selectedReviewId) {
      await selectReview(state.selectedReviewId, { announce: false });
      return;
    }
    renderReviewDetail(null);
  }

  async function loadJobs() {
    const payload = await fetchAdmin("/api/admin/jobs");
    renderJobs(payload.jobs || []);
  }

  async function loadQuartzStatus() {
    if (!document.getElementById("quartz-status")) {
      renderQuartzStatus(INITIAL_QUARTZ);
      return;
    }
    renderQuartzStatus(await fetchAdmin("/api/admin/quartz/status"));
  }

  function renderSettingsPayload(payload) {
    const rawNode = document.getElementById("settings-raw-text");
    const effectiveNode = document.getElementById("settings-effective-text");
    const pathNode = document.getElementById("settings-config-path");
    if (rawNode) rawNode.value = payload.raw_text || "";
    if (effectiveNode) effectiveNode.textContent = payload.effective_config_text || "";
    if (pathNode) pathNode.textContent = payload.config_path || "";
    renderSystemStatus(payload.status || {});
  }

  async function loadSettingsConfig() {
    if (!document.getElementById("settings-raw-text")) return;
    renderSettingsPayload(await fetchAdmin("/api/admin/settings/config"));
  }

  async function restartSettingsService() {
    await fetchAdmin("/api/admin/settings/restart", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    setSectionStatus("settings-status", UI.settings_restart_scheduled);
    setAdminMessage(UI.settings_restart_scheduled);
    window.setTimeout(() => window.location.reload(), 2500);
  }

  async function loadUsers() {
    const node = document.getElementById("user-list");
    if (!node) return;
    const payload = await fetchAdmin("/api/admin/users");
    renderUserList(payload.users || []);
  }

  async function runQuartzBuild() {
    const payload = await fetchAdmin("/api/admin/quartz/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    renderQuartzStatus(payload);
    setAdminMessage(UI.quartz_build_success);
  }

  async function runExplore() {
    const question = (document.getElementById("admin-explore-input")?.value || "").trim();
    const payload = await fetchAdmin("/api/admin/explore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const node = document.getElementById("admin-explore-result");
    if (!node) return;
    node.innerHTML = `
      <div class="card">
        <div class="row spread">
          <strong>${escapeHtml(UI.explore_answer)}</strong>
          <span class="tag">${escapeHtml(payload.confidence || "")}</span>
        </div>
        <div class="subtle">${escapeHtml(UI.explore_confidence)}: ${escapeHtml(payload.confidence || "")}</div>
        <div class="markdown">${renderMarkdown(payload.answer || "")}</div>
        <div class="subtle">${escapeHtml(UI.explore_sources)}: ${escapeHtml((payload.sources || []).join(", ") || "-")}</div>
        <div class="subtle">${escapeHtml(UI.explore_gaps)}: ${escapeHtml((payload.gaps || []).join(" | ") || "-")}</div>
      </div>
    `;
    setAdminMessage((payload.answer || "").slice(0, 140));
  }

  async function triageSubmission(id, status) {
    await fetchAdmin(`/api/admin/submissions/${encodeURIComponent(id)}/triage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    setAdminMessage(`${UI.triaged} · ${id.slice(0, 8)}`);
    await refreshCurrentPage();
  }

  async function runIngest(id) {
    const job = await fetchAdmin(`/api/admin/submissions/${encodeURIComponent(id)}/run-ingest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    setAdminMessage(`${UI.ingest_done}${(job.id || "").slice(0, 8)}`);
    await refreshCurrentPage();
  }

  async function runTidy(options = {}) {
    const job = await fetchAdmin("/api/admin/tidy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options),
    });
    setAdminMessage(`${UI.tidy_done}${(job.id || "").slice(0, 8)}`);
    await refreshCurrentPage();
  }

  async function selectReview(reviewId, options = {}) {
    const normalizedId = String(reviewId || "").trim();
    if (!normalizedId) {
      state.selectedReviewId = null;
      renderReviews(state.reviews);
      renderReviewDetail(null);
      return;
    }
    state.selectedReviewId = normalizedId;
    renderReviews(state.reviews);
    if (!state.reviewDetails[normalizedId]) {
      state.reviewDetails[normalizedId] = await fetchAdmin(`/api/admin/reviews/${encodeURIComponent(normalizedId)}`);
    }
    renderReviewDetail(state.reviewDetails[normalizedId]);
    if (options.announce !== false) {
      setAdminMessage(`${UI.review_selected || UI.review_loaded}${normalizedId.slice(0, 8)}`);
    }
  }

  async function approveReview(reviewId) {
    const comment = (document.getElementById("review-comment")?.value || "").trim() || UI.review_comment_approve;
    await fetchAdmin(`/api/admin/reviews/${encodeURIComponent(reviewId)}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment }),
    });
    setAdminMessage(`${UI.review_approved}${reviewId.slice(0, 8)}`);
    await refreshCurrentPage();
  }

  async function rejectReview(reviewId) {
    const comment = (document.getElementById("review-comment")?.value || "").trim() || UI.review_comment_reject;
    await fetchAdmin(`/api/admin/reviews/${encodeURIComponent(reviewId)}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment }),
    });
    setAdminMessage(`${UI.review_rejected}${reviewId.slice(0, 8)}`);
    await refreshCurrentPage();
  }

  async function retryJob(jobId) {
    await fetchAdmin(`/api/admin/jobs/${encodeURIComponent(jobId)}/retry`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    setAdminMessage(`${UI.job_retried}${jobId.slice(0, 8)}`);
    await refreshCurrentPage();
  }

  async function cancelJob(jobId) {
    await fetchAdmin(`/api/admin/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "Cancelled from admin UI" }),
    });
    setAdminMessage(`${UI.job_cancelled}${jobId.slice(0, 8)}`);
    await refreshCurrentPage();
  }

  async function openDocument(nameOverride) {
    const name = String(nameOverride || "").trim();
    if (!name) {
      throw new Error(UI.doc_select_prompt || (isZh ? "请先选择文档。" : "Select a document first."));
    }
    const payload = await fetchAdmin(`/api/admin/entries/${encodeURIComponent(name)}`);
    state.selectedDocumentName = payload.name || name;
    state.selectedDocumentDetail = payload;
    const searchInput = document.getElementById("admin-file-search");
    if (searchInput) searchInput.value = payload.name || name;
    const editor = document.getElementById("editor-content");
    if (editor) {
      editor.value = payload.content || "";
      editor.dataset.hash = payload.content_hash || "";
    }
    hideFileSuggestions();
    updateEditorPreview(payload.content || "");
    renderFileIndexTree();
    renderDocumentMeta();
    renderLinkedIssues();
    syncFileEditorState();
    document.getElementById("editor-status").textContent = `${UI.editor_loaded} ${payload.name} · hash=${String(payload.content_hash || "").slice(0, 12)}`;
    setAdminMessage(`${UI.doc_selected || UI.editor_loaded} ${payload.name}`);
  }

  async function saveEntry() {
    const name = String(state.selectedDocumentName || "").trim();
    if (!name) {
      throw new Error(UI.doc_select_prompt || (isZh ? "请先选择文档。" : "Select a document first."));
    }
    const content = document.getElementById("editor-content")?.value || "";
    const expectedHash = document.getElementById("editor-content")?.dataset.hash || null;
    const payload = await fetchAdmin(`/api/admin/entries/${encodeURIComponent(name)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, expected_hash: expectedHash }),
    });
    state.selectedDocumentName = payload.name || name;
    state.selectedDocumentDetail = payload;
    document.getElementById("editor-status").textContent = `${UI.editor_saved}: ${payload.name}`;
    document.getElementById("editor-content").dataset.hash = payload.content_hash || "";
    updateEditorPreview(payload.content || "");
    renderDocumentMeta();
    renderLinkedIssues();
    syncFileEditorState();
    setAdminMessage(`${UI.editor_saved} ${payload.name}`);
    if (UI.section === "files") {
      await loadFileManager();
    }
  }

  function currentIngestFiles() {
    if (state.ingestFiles.length) return [...state.ingestFiles];
    const directFiles = Array.from(document.getElementById("admin-ingest-file")?.files || []);
    const folderFiles = Array.from(document.getElementById("admin-ingest-folder")?.files || []);
    return [...folderFiles, ...directFiles];
  }

  function updateIngestSelection() {
    const files = currentIngestFiles();
    const node = document.getElementById("admin-ingest-selection");
    if (!node) return;
    if (!files.length) {
      node.textContent = isZh ? "还没有选择任何文档。" : "No documents selected yet.";
      return;
    }
    const sample = files.slice(0, 3).map((file) => file.webkitRelativePath || file.name).join(" · ");
    const suffix = files.length > 3 ? ` +${files.length - 3}` : "";
    node.textContent = `${UI.ingest_selected_prefix || "Selected"} ${files.length} ${UI.ingest_selected_suffix || "files"} · ${sample}${suffix}`;
  }

  async function uploadAndIngest() {
    const files = currentIngestFiles();
    if (!files.length) throw new Error(UI.ingest_file_required);
    const uploads = await collectUploads(files);
    const payload = await fetchAdmin("/api/admin/ingest/document", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        files: uploads,
        filename: files.length === 1 ? files[0].name : "admin-upload-bundle.zip",
        mime_type: files.length === 1 ? (files[0].type || "application/octet-stream") : "application/zip",
      }),
    });
    setSectionStatus(
      "admin-ingest-status",
      `${UI.ingest_uploaded}${(payload.job?.id || "").slice(0, 8)} · ${UI.ingest_submission_prefix || "submission"} ${(payload.submission?.id || "").slice(0, 8)}`
    );
    setAdminMessage(`${UI.ingest_uploaded}${(payload.job?.id || "").slice(0, 8)}`);
    state.ingestFiles = [];
    if (document.getElementById("admin-ingest-file")) document.getElementById("admin-ingest-file").value = "";
    if (document.getElementById("admin-ingest-folder")) document.getElementById("admin-ingest-folder").value = "";
    updateIngestSelection();
    await refreshCurrentPage();
  }

  async function runManualTidy() {
    const reason = (document.getElementById("tidy-reason")?.value || "").trim();
    if (!reason) throw new Error(UI.manual_tidy_reason_required);
    await runTidy({ scope: "health_blocking", reason });
  }

  async function createUser() {
    const name = (document.getElementById("user-name")?.value || "").trim();
    const payload = await fetchAdmin("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (payload.user?.id && payload.token) {
      state.revealedTokens[String(payload.user.id)] = String(payload.token);
    }
    document.getElementById("user-name").value = "";
    setAdminMessage(`${UI.user_created}${payload.user?.name || ""}`);
    await loadUsers();
  }

  async function showUserToken(userId) {
    const normalizedId = String(userId || "");
    if (state.revealedTokens[normalizedId]) {
      delete state.revealedTokens[normalizedId];
      renderUserList(state.users);
      return;
    }
    const payload = await fetchAdmin(`/api/admin/users/${encodeURIComponent(userId)}/token`);
    state.revealedTokens[normalizedId] = String(payload.token || "");
    renderUserList(state.users);
    setAdminMessage(UI.token_revealed);
  }

  async function disableUser(userId) {
    await fetchAdmin(`/api/admin/users/${encodeURIComponent(userId)}/disable`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    delete state.revealedTokens[String(userId || "")];
    setAdminMessage(`${UI.user_disabled}${userId}`);
    await loadUsers();
  }

  async function reloadSettingsFromDisk() {
    await loadSettingsConfig();
    setSectionStatus("settings-status", UI.settings_loaded);
    setAdminMessage(UI.settings_loaded);
  }

  async function saveSettingsConfig() {
    const rawText = document.getElementById("settings-raw-text")?.value || "";
    const payload = await fetchAdmin("/api/admin/settings/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_text: rawText }),
    });
    renderSettingsPayload(payload);
    setSectionStatus("settings-status", UI.settings_saved);
    setAdminMessage(UI.settings_saved);
    await loadQuartzStatus();
  }

  async function logout() {
    await fetchAdmin("/api/admin/session", { method: "DELETE" });
    setAdminMessage(UI.logout_done);
    window.location.href = "/admin/overview";
  }

  async function refreshCurrentPage() {
    if (UI.section === "overview") {
      await Promise.all([loadOverview(), loadIssues(), loadAuditLogs()]);
      return;
    }
    if (UI.section === "kb") {
      await Promise.all([loadSubmissions()]);
      return;
    }
    if (UI.section === "files") {
      await Promise.all([loadFileManager()]);
      return;
    }
    if (UI.section === "reviews") {
      await Promise.all([loadReviews(), loadJobs()]);
      return;
    }
    if (UI.section === "users") {
      await Promise.all([loadUsers()]);
      return;
    }
    if (UI.section === "system") {
      await Promise.all([loadSettingsConfig(), loadQuartzStatus()]);
    }
  }

  function bindClick(containerId, handler) {
    const node = document.getElementById(containerId);
    if (!node) return;
    node.addEventListener("click", (event) => handler(event).catch(showAdminError));
  }

  bindClick("submission-list", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.dataset.action === "triage-submission") {
      await withBusyButton(button, UI.busy_loading, () =>
        triageSubmission(button.dataset.submissionId || "", button.dataset.status || "triaged")
      );
      return;
    }
    if (button.dataset.action === "run-ingest") {
      await withBusyButton(button, UI.busy_queue, () => runIngest(button.dataset.submissionId || ""));
    }
  });

  bindClick("review-list", async (event) => {
    const button = event.target.closest("button[data-action='select-review']");
    if (!button) return;
    await withBusyButton(button, UI.busy_loading, () => selectReview(button.dataset.reviewId || ""));
  });

  bindClick("job-list", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.dataset.action === "retry-job") {
      await withBusyButton(button, UI.busy_queue, () => retryJob(button.dataset.jobId || ""));
      return;
    }
    if (button.dataset.action === "cancel-job") {
      await withBusyButton(button, UI.busy_loading, () => cancelJob(button.dataset.jobId || ""));
    }
  });

  bindClick("user-list", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.dataset.action === "show-token") {
      await withBusyButton(button, UI.busy_loading, () => showUserToken(button.dataset.userId || ""));
      return;
    }
    if (button.dataset.action === "disable-user") {
      await withBusyButton(button, UI.busy_loading, () => disableUser(button.dataset.userId || ""));
    }
  });

  bindClick("admin-file-index-tree", async (event) => {
    const button = event.target.closest('button[data-action="open-document"]');
    if (!button) return;
    await withBusyButton(button, UI.busy_loading, () => openDocument(button.dataset.name || ""));
  });

  bindClick("admin-doc-health-list", async (event) => {
    const button = event.target.closest('button[data-action="open-document"]');
    if (!button) return;
    await withBusyButton(button, UI.busy_loading, () => openDocument(button.dataset.name || ""));
  });

  bindClick("admin-file-suggestions", async (event) => {
    const button = event.target.closest('button[data-action="open-document"]');
    if (!button) return;
    await withBusyButton(button, UI.busy_loading, () => openDocument(button.dataset.name || ""));
  });

  document.getElementById("admin-logout-button")?.addEventListener("click", () => logout().catch(showAdminError));
  document.getElementById("admin-explore-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("admin-explore-button"), UI.busy_loading, runExplore).catch(showAdminError)
  );
  document.getElementById("manual-tidy-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("manual-tidy-button"), UI.busy_queue, runManualTidy).catch(showAdminError)
  );
  document.getElementById("save-entry-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("save-entry-button"), UI.busy_saving, saveEntry).catch(showAdminError)
  );
  document.getElementById("create-user-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("create-user-button"), UI.busy_saving, createUser).catch(showAdminError)
  );
  document.getElementById("approve-review-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("approve-review-button"), UI.busy_approve, async () => {
      if (!state.selectedReviewId) throw new Error(UI.review_select_prompt || "Select a review first.");
      await approveReview(state.selectedReviewId);
    }).catch(showAdminError)
  );
  document.getElementById("reject-review-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("reject-review-button"), UI.busy_reject, async () => {
      if (!state.selectedReviewId) throw new Error(UI.review_select_prompt || "Select a review first.");
      await rejectReview(state.selectedReviewId);
    }).catch(showAdminError)
  );
  document.getElementById("admin-quartz-build-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("admin-quartz-build-button"), UI.busy_queue, runQuartzBuild).catch(showAdminError)
  );
  document.getElementById("admin-ingest-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("admin-ingest-button"), UI.busy_queue, uploadAndIngest).catch(showAdminError)
  );
  document.getElementById("settings-reload-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("settings-reload-button"), UI.busy_loading, reloadSettingsFromDisk).catch(showAdminError)
  );
  document.getElementById("settings-save-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("settings-save-button"), UI.busy_saving, saveSettingsConfig).catch(showAdminError)
  );
  document.getElementById("settings-restart-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("settings-restart-button"), UI.busy_loading, restartSettingsService).catch(showAdminError)
  );
  document.getElementById("editor-content")?.addEventListener("input", (event) => {
    updateEditorPreview(event.target.value || "");
  });
  document.getElementById("admin-file-search")?.addEventListener("input", () => {
    updateFileSuggestions().catch(showAdminError);
  });
  document.getElementById("admin-file-search")?.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      hideFileSuggestions();
      return;
    }
    if (event.key !== "Enter") return;
    event.preventDefault();
    const query = String(event.target.value || "").trim().toLowerCase();
    const exactMatch = state.fileSuggestions.find((item) => {
      const candidates = [item.name, item.title].filter(Boolean).map((value) => String(value).toLowerCase());
      return candidates.includes(query);
    });
    const selected = exactMatch || state.fileSuggestions[0];
    if (selected) {
      openDocument(selected.name).catch(showAdminError);
    }
  });
  document.getElementById("admin-file-search")?.addEventListener("blur", () => {
    window.setTimeout(() => hideFileSuggestions(), 120);
  });
  document.getElementById("admin-file-search")?.addEventListener("focus", () => {
    if (state.fileSuggestions.length) renderFileSuggestions(state.fileSuggestions);
  });
  document.getElementById("admin-ingest-file")?.addEventListener("change", () => {
    state.ingestFiles = [];
    updateIngestSelection();
  });
  document.getElementById("admin-ingest-folder")?.addEventListener("change", () => {
    state.ingestFiles = [];
    updateIngestSelection();
  });

  const ingestDropzone = document.getElementById("admin-ingest-dropzone");
  if (ingestDropzone) {
    ["dragenter", "dragover"].forEach((eventName) => {
      ingestDropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        ingestDropzone.classList.add("dragover");
      });
    });
    ["dragleave", "drop"].forEach((eventName) => {
      ingestDropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        ingestDropzone.classList.remove("dragover");
      });
    });
    ingestDropzone.addEventListener("drop", (event) => {
      const files = Array.from(event.dataTransfer?.files || []);
      if (!files.length) return;
      state.ingestFiles = files;
      if (document.getElementById("admin-ingest-file")) document.getElementById("admin-ingest-file").value = "";
      if (document.getElementById("admin-ingest-folder")) document.getElementById("admin-ingest-folder").value = "";
      updateIngestSelection();
    });
  }

  refreshCurrentPage()
    .then(() => {
      updateIngestSelection();
      syncFileEditorState();
      updateEditorPreview(document.getElementById("editor-content")?.value || "");
      setAdminMessage(isZh ? "管理台已就绪。" : "Admin ready.");
    })
    .catch(showAdminError);
})();
