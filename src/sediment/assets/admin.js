(function () {
  const shell = window.SedimentShell;
  const pageData = shell.readJsonScript("sediment-page-data") || {};
  const UI = pageData.ui || {};
  const INITIAL_QUARTZ = pageData.quartz || {};
  const {
    clearSessionStatePrefix,
    collectUploads,
    escapeHtml,
    fetchJson,
    readSessionState,
    renderMarkdown,
    shellLabel,
    syncFilePickerState,
    writeSessionState,
  } = shell;
  const locale = document.documentElement.dataset.locale || "en";
  const WORKBENCH_STATUS_IDS = {
    ingest: "admin-ingest-status",
    tidy: "admin-tidy-status",
    explore: "admin-explore-status",
  };
  const ADMIN_SESSION_PREFIX = "sediment-admin-ui:";
  const ADMIN_PAGE_SESSION_KEY = `${ADMIN_SESSION_PREFIX}${locale}:${String(UI.section || "unknown")}`;
  const MAX_PERSISTED_TEXT_CHARS = 120000;
  const state = {
    reviews: [],
    reviewDetails: {},
    selectedReviewId: null,
    kbPane: "operations",
    insights: [],
    selectedInsightId: null,
    selectedInsightDetail: null,
    adminGraphPayload: null,
    adminGraphController: null,
    inbox: null,
    users: [],
    revealedTokens: {},
    documents: { counts: {}, documents_by_name: {}, top_indexes: [], unindexed_documents: [], health_issues: [] },
    fileSuggestions: [],
    activeFileSuggestionIndex: -1,
    selectedDocumentName: null,
    selectedDocumentDetail: null,
    ingestFiles: [],
    versionStatus: null,
    activeFileEntryTab: "index",
    activeFileConsoleTab: "meta",
    fileLoadedContent: "",
    fileDirty: false,
    pendingFileNavigation: null,
  };
  let fileSuggestionRequestId = 0;
  let persistStateTimer = 0;
  let fileConsoleFocusTimer = 0;

  function trimPersistedText(value, limit = MAX_PERSISTED_TEXT_CHARS) {
    const text = String(value || "");
    return text.length > limit ? text.slice(text.length - limit) : text;
  }

  function nodeText(id) {
    return String(document.getElementById(id)?.textContent || "");
  }

  function nodeValue(id) {
    return String(document.getElementById(id)?.value || "");
  }

  function setNodeText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = String(value || "");
  }

  function setNodeValue(id, value) {
    const node = document.getElementById(id);
    if (node) node.value = String(value || "");
  }

  function queuePersistAdminPageState() {
    if (!ADMIN_PAGE_SESSION_KEY) return;
    window.clearTimeout(persistStateTimer);
    persistStateTimer = window.setTimeout(() => persistAdminPageState(), 40);
  }

  function captureAdminPageState() {
    const base = {
      adminMessage: trimPersistedText(nodeText("admin-message"), 4000),
    };

    if (UI.section === "kb") {
      const resultNode = runtimeResultNode();
      return {
        ...base,
        kbPane: state.kbPane,
        selectedInsightId: String(state.selectedInsightId || ""),
        tidyReason: trimPersistedText(nodeValue("tidy-reason"), 12000),
        exploreQuestion: trimPersistedText(nodeValue("admin-explore-input"), 12000),
        ingestStatus: trimPersistedText(nodeText("admin-ingest-status"), 4000),
        tidyStatus: trimPersistedText(nodeText("admin-tidy-status"), 4000),
        exploreStatus: trimPersistedText(nodeText("admin-explore-status"), 4000),
        ingestSelection: trimPersistedText(nodeText("admin-ingest-selection"), 4000),
        liveStatus: trimPersistedText(nodeText("admin-kb-live-status"), 4000),
        liveLog: trimPersistedText(nodeValue("admin-kb-live-log")),
        resultStatus: trimPersistedText(nodeText("admin-kb-result-status"), 4000),
        resultHtml: trimPersistedText(resultNode?.innerHTML || ""),
        resultClassName: String(resultNode?.className || "runtime-result-view markdown empty"),
      };
    }

    if (UI.section === "system") {
      return {
        ...base,
        rawText: trimPersistedText(nodeValue("settings-raw-text")),
        settingsStatus: trimPersistedText(nodeText("settings-status"), 4000),
        configPath: trimPersistedText(nodeText("settings-config-path"), 4000),
        effectiveConfigText: trimPersistedText(nodeText("settings-effective-text")),
      };
    }

    if (UI.section === "files") {
      return {
        ...base,
        fileSearchQuery: trimPersistedText(nodeValue("admin-file-search"), 4000),
        activeFileEntryTab: state.activeFileEntryTab,
        activeFileConsoleTab: state.activeFileConsoleTab,
        selectedDocumentName: String(state.selectedDocumentName || ""),
      };
    }

    return null;
  }

  function persistAdminPageState() {
    writeSessionState(ADMIN_PAGE_SESSION_KEY, captureAdminPageState());
  }

  async function restoreAdminPageState() {
    const snapshot = readSessionState(ADMIN_PAGE_SESSION_KEY, null);
    if (!snapshot || typeof snapshot !== "object") return false;
    setNodeText("admin-message", snapshot.adminMessage || "");

    if (UI.section === "kb") {
      state.kbPane = normalizeKbPane(snapshot.kbPane || state.kbPane);
      setActiveKbPane(state.kbPane, { persist: false });
      state.selectedInsightId = String(snapshot.selectedInsightId || "").trim() || null;
      setNodeValue("tidy-reason", snapshot.tidyReason || "");
      setNodeValue("admin-explore-input", snapshot.exploreQuestion || "");
      setNodeText("admin-ingest-status", snapshot.ingestStatus || nodeText("admin-ingest-status"));
      setNodeText("admin-tidy-status", snapshot.tidyStatus || nodeText("admin-tidy-status"));
      setNodeText("admin-explore-status", snapshot.exploreStatus || nodeText("admin-explore-status"));
      setNodeText("admin-ingest-selection", snapshot.ingestSelection || nodeText("admin-ingest-selection"));
      setNodeText("admin-kb-live-status", snapshot.liveStatus || nodeText("admin-kb-live-status"));
      setNodeValue(
        "admin-kb-live-log",
        sanitizePersistedLiveLog(snapshot.liveLog || nodeValue("admin-kb-live-log"))
      );
      setNodeText("admin-kb-result-status", snapshot.resultStatus || nodeText("admin-kb-result-status"));
      const resultNode = runtimeResultNode();
      if (resultNode && snapshot.resultHtml && !looksLikeRuntimeLeak(snapshot.resultHtml)) {
        resultNode.className = String(snapshot.resultClassName || "runtime-result-view markdown");
        resultNode.innerHTML = snapshot.resultHtml;
      } else if (resultNode && snapshot.resultHtml) {
        renderExploreFailure(UI.explore_invalid_output || UI.explore_failed_hint || "");
      }
      return true;
    }

    if (UI.section === "system") {
      setNodeValue("settings-raw-text", snapshot.rawText || "");
      setNodeText("settings-status", snapshot.settingsStatus || nodeText("settings-status"));
      setNodeText("settings-config-path", snapshot.configPath || nodeText("settings-config-path"));
      setNodeText("settings-effective-text", snapshot.effectiveConfigText || nodeText("settings-effective-text"));
      return true;
    }

    if (UI.section === "files") {
      setNodeValue("admin-file-search", snapshot.fileSearchQuery || "");
      state.activeFileEntryTab = normalizeFileEntryTab(snapshot.activeFileEntryTab);
      state.activeFileConsoleTab = normalizeFileConsoleTab(snapshot.activeFileConsoleTab);
      syncFileEntryTabState();
      syncFileConsoleTabState();
      const selectedDocumentName = String(snapshot.selectedDocumentName || "").trim();
      if (selectedDocumentName && state.documents?.documents_by_name?.[selectedDocumentName]) {
        await performOpenDocument(selectedDocumentName, {
          announce: false,
          scrollEditor: false,
          entryTab: state.activeFileEntryTab,
        });
      }
      return Boolean(snapshot.fileSearchQuery || selectedDocumentName || snapshot.adminMessage);
    }

    return Boolean(snapshot.adminMessage);
  }

  function setAdminMessage(message) {
    const node = document.getElementById("admin-message");
    if (node) node.textContent = String(message || "");
    queuePersistAdminPageState();
  }

  function setSectionStatus(id, message) {
    const node = document.getElementById(id);
    if (node) node.textContent = String(message || "");
    queuePersistAdminPageState();
  }

  function workbenchStatusId(section) {
    return WORKBENCH_STATUS_IDS[String(section || "")] || "";
  }

  function setWorkbenchStatus(section, message) {
    const id = workbenchStatusId(section);
    if (id) setSectionStatus(id, message);
  }

  function liveLogNode() {
    return document.getElementById("admin-kb-live-log");
  }

  function setLiveStatus(message) {
    const node = document.getElementById("admin-kb-live-status");
    if (node) node.textContent = String(message || "");
  }

  function setExploreStatus(message) {
    setWorkbenchStatus("explore", message);
  }

  function normalizeKbPane(value) {
    const normalized = String(value || "").trim().toLowerCase();
    return ["operations", "insights", "graph", "live"].includes(normalized)
      ? normalized
      : "operations";
  }

  function setActiveKbPane(pane, { persist = true } = {}) {
    state.kbPane = normalizeKbPane(pane);
    document.querySelectorAll("[data-kb-pane]").forEach((node) => {
      node.hidden = node.dataset.kbPane !== state.kbPane;
    });
    document.querySelectorAll('[data-action="switch-kb-pane"]').forEach((button) => {
      const active = button.dataset.pane === state.kbPane;
      button.classList.toggle("primary", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    if (state.kbPane === "graph") {
      window.requestAnimationFrame(() => {
        if (typeof state.adminGraphController?.resize === "function") {
          state.adminGraphController.resize();
        }
      });
    }
    if (persist) queuePersistAdminPageState();
  }

  function runtimeResultNode() {
    return document.getElementById("admin-kb-result");
  }

  function setRuntimeResultStatus(message) {
    const node = document.getElementById("admin-kb-result-status");
    if (node) node.textContent = String(message || "");
  }

  function resetRuntimeResult(message) {
    const node = runtimeResultNode();
    if (!node) return;
    node.className = "runtime-result-view markdown empty";
    node.textContent = String(message || UI.result_ready || "");
    queuePersistAdminPageState();
  }

  const RUNTIME_LEAK_MARKERS = [
    "claude -p",
    "--json-schema",
    "you are the internal sediment explore runtime",
    "prepared context",
    "sediment explore skill",
    '"additionalproperties": false',
    '"exploration_summary"',
    '"entries_scanned"',
    '"links_followed"',
    "return json only",
  ];

  function looksLikeRuntimeLeak(text) {
    const normalized = String(text || "").trim().toLowerCase();
    if (!normalized) return false;
    const hitCount = RUNTIME_LEAK_MARKERS.reduce(
      (count, marker) => count + (normalized.includes(marker) ? 1 : 0),
      0
    );
    return hitCount >= 2;
  }

  function safeExploreFailureMessage(message) {
    const normalized = String(message || "").trim().toLowerCase();
    if (
      looksLikeRuntimeLeak(message) ||
      normalized.includes("prompt/schema leakage") ||
      normalized.includes("internal runtime content")
    ) {
      return UI.explore_invalid_output || UI.explore_failed_hint || UI.explore_failed || "";
    }
    return String(message || "");
  }

  function sanitizePersistedLiveLog(value) {
    return String(value || "")
      .split("\n")
      .map((line) => {
        const normalized = line.toLowerCase();
        if (
          looksLikeRuntimeLeak(line) ||
          normalized.includes("claude -p") ||
          normalized.includes("--json-schema")
        ) {
          const separatorIndex = line.indexOf(":");
          const prefix = separatorIndex >= 0 ? line.slice(0, separatorIndex + 1) : "";
          return `${prefix} ${UI.live_command_redacted || ""}`.trim();
        }
        return line;
      })
      .join("\n");
  }

  function formatLiveTimestamp() {
    return new Date().toLocaleTimeString();
  }

  function appendLiveLog(label, message) {
    const node = liveLogNode();
    const text = String(message || "").trim();
    if (!node || !text) return;
    const readyText = String(UI.live_ready || "").trim();
    const existing = String(node.value || "").trim();
    const prefix = String(label || UI.live_status_label || "").trim();
    const line = `[${formatLiveTimestamp()}] ${prefix}: ${text}`;
    node.value = !existing || existing === readyText
      ? line
      : `${node.value}\n${line}`;
    node.scrollTop = node.scrollHeight;
    queuePersistAdminPageState();
  }

  function clearLiveLog() {
    const node = liveLogNode();
    if (!node) return;
    node.value = UI.live_ready || "";
    setLiveStatus(UI.live_ready || "");
    setAdminMessage(UI.live_cleared || "");
    queuePersistAdminPageState();
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

  function showAdminError(error, options = {}) {
    const message =
      error instanceof Error && error.message
        ? error.message
        : shellLabel("unknownError", UI.unknown_error || "");
    const statusIds = Array.isArray(options.statusIds)
      ? options.statusIds.map((value) => String(value || "")).filter(Boolean)
      : [];
    if (options.diff) {
      const diffNode = document.getElementById("diff-view");
      if (diffNode) diffNode.textContent = message;
    }
    if (options.live && options.appendLive !== false) {
      appendLiveLog(UI.live_error_label || "", message);
    }
    if (options.live) {
      setLiveStatus(message);
    }
    statusIds.forEach((id) => setSectionStatus(id, message));
    if (options.adminMessage !== false) setAdminMessage(message);
  }

  function createErrorHandler(options = {}) {
    return (error) => showAdminError(error, options);
  }

  function workbenchErrorOptions(section, extra = {}) {
    const statusId = workbenchStatusId(section);
    return {
      ...extra,
      live: true,
      statusIds: statusId ? [statusId] : [],
    };
  }

  function logWorkbenchRequest(section, message, options = {}) {
    appendLiveLog(UI.live_request_label || "", message);
    if (options.liveStatus) setLiveStatus(options.liveStatus);
    if (options.sectionStatus) setWorkbenchStatus(section, options.sectionStatus);
  }

  function completeWorkbenchAction(section, message, options = {}) {
    if (options.logResponse !== false) {
      appendLiveLog(UI.live_response_label || "", message);
    }
    setWorkbenchStatus(section, options.sectionStatus || message);
    setLiveStatus(options.liveStatus || message);
    setAdminMessage(options.adminMessage || message);
  }

  function sleep(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  function jobStateLabel(job) {
    return String(job?.status || "").trim() || "-";
  }

  function renderManagedJobResult(job) {
    const node = runtimeResultNode();
    if (!node) return;
    const result = job?.result_payload || {};
    const applyResult = result.apply_result || {};
    const operations = Array.isArray(applyResult.operations)
      ? applyResult.operations
      : Array.isArray(result.operations)
        ? result.operations
        : [];
    const commitSha = String(result.commit_sha || job?.commit_sha || "").trim();
    const changedItems = operations
      .map((item) => ({
        name: String(item?.name || "").trim(),
        path: String(item?.relative_path || "").trim(),
        changeType: String(item?.change_type || "").trim(),
      }))
      .filter((item) => item.name || item.path);
    const summary =
      String(result.summary || "").trim() ||
      String(job?.error_message || "").trim() ||
      (UI.job_result_empty || "");
    const isFailure = ["failed", "cancelled"].includes(String(job?.status || ""));
    node.className = `runtime-result-view markdown${isFailure ? " danger" : ""}`;
    node.innerHTML = `
      <div class="card">
        <div class="row spread">
          <strong>${escapeHtml(summary)}</strong>
          <span class="tag">${escapeHtml(jobStateLabel(job))}</span>
        </div>
        <div class="subtle">${escapeHtml(shellLabel("jobTypeLabel", UI.job_type_label || ""))}: ${escapeHtml(String(job?.job_type || "-"))}</div>
        <div class="subtle">${escapeHtml(shellLabel("jobChangeCountLabel", UI.job_change_count_label || ""))}: ${escapeHtml(String(operations.length || 0))}</div>
        ${commitSha ? `<div class="subtle">${escapeHtml(shellLabel("jobCommitLabel", UI.job_commit_label || ""))}: <span class="mono">${escapeHtml(commitSha)}</span></div>` : ""}
        ${
          changedItems.length
            ? `
              <div class="subtle">${escapeHtml(shellLabel("jobChangedItemsLabel", UI.job_changed_items_label || ""))}:</div>
              <ul class="job-change-list">
                ${changedItems.map((item) => `
                  <li>
                    <span class="mono">${escapeHtml(item.path || item.name)}</span>
                    ${item.name && item.path && item.name !== item.path ? `<span> · ${escapeHtml(item.name)}</span>` : ""}
                    ${item.changeType ? `<span class="tag">${escapeHtml(item.changeType)}</span>` : ""}
                  </li>
                `).join("")}
              </ul>
            `
            : ""
        }
        ${isFailure ? `<div class="subtle">${escapeHtml(String(job?.error_message || ""))}</div>` : ""}
        ${
          commitSha && ["ingest", "tidy"].includes(String(job?.job_type || ""))
            ? `<div class="action-row"><button type="button" data-action="revert-job-commit" data-commit-sha="${escapeHtml(commitSha)}">${escapeHtml(UI.version_revert || "")}</button></div>`
            : ""
        }
      </div>
    `;
    queuePersistAdminPageState();
  }

  async function waitForManagedJob(jobId, section) {
    const normalizedId = String(jobId || "").trim();
    if (!normalizedId) {
      throw new Error(UI.job_monitor_missing || "");
    }
    const deadline = Date.now() + 30000;
    let lastStatus = "";
    while (Date.now() < deadline) {
      const job = await fetchAdmin(`/api/admin/jobs/${encodeURIComponent(normalizedId)}`);
      const status = String(job.status || "").trim();
      if (status && status !== lastStatus) {
        lastStatus = status;
        appendLiveLog(UI.live_status_label || "", `${normalizedId.slice(0, 8)} · ${status}`);
        setWorkbenchStatus(section, `${UI.job_running_prefix || ""}${status}`);
      }
      if (["succeeded", "failed", "cancelled"].includes(status)) {
        renderManagedJobResult(job);
        setRuntimeResultStatus(
          status === "succeeded"
            ? `${UI.job_completed_prefix || ""}${String(job.result_payload?.commit_sha || job.commit_sha || "").slice(0, 8)}`
            : (job.error_message || status)
        );
        return job;
      }
      await sleep(500);
    }
    throw new Error(UI.job_monitor_timeout || "");
  }

  function roleLabel(role) {
    if (role === "owner") return UI.role_owner || "";
    if (role === "committer") return UI.role_committer || "";
    return role || "-";
  }

  function scopeLabel(scope) {
    if (scope === "full") return UI.scope_full || "";
    if (scope === "graph") return UI.scope_graph || "";
    if (scope === "indexes") return UI.scope_indexes || "";
    if (scope === "health_blocking") return UI.scope_health_blocking || "";
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
    if (action === "run_tidy") return UI.action_run_tidy || "";
    if (action === "edit_entry") return UI.action_edit_entry || "";
    if (action === "promote_placeholder") return UI.action_promote_placeholder || "";
    if (action === "review_entry") return UI.action_review_entry || "";
    return action || "-";
  }

  function insightStateLabel(reviewState) {
    const normalized = String(reviewState || "").trim();
    if (normalized === "proposed") return UI.insight_state_proposed || normalized;
    if (normalized === "observing") return UI.insight_state_observing || normalized;
    if (normalized === "promoted") return UI.insight_state_promoted || normalized;
    if (normalized === "merged") return UI.insight_state_merged || normalized;
    if (normalized === "rejected") return UI.insight_state_rejected || normalized;
    if (normalized === "archived") return UI.insight_state_archived || normalized;
    return normalized || "-";
  }

  function insightKindLabel(kind) {
    const normalized = String(kind || "").trim();
    if (normalized === "concept") return UI.insight_kind_concept || normalized;
    if (normalized === "workflow") return UI.insight_kind_workflow || normalized;
    if (normalized === "lesson") return UI.insight_kind_lesson || normalized;
    if (normalized === "mapping") return UI.insight_kind_mapping || normalized;
    return normalized || "-";
  }

  function insightRecommendedActionLabel(action) {
    const normalized = String(action || "").trim();
    if (normalized === "promote") return UI.insight_action_promote || normalized;
    if (normalized === "merge") return UI.insight_action_merge || normalized;
    if (normalized === "keep_observing") return UI.insight_action_keep_observing || normalized;
    return normalized || "-";
  }

  function docGroupLabel(group) {
    if (group === "formal") return UI.doc_group_formal || "";
    if (group === "placeholder") return UI.doc_group_placeholder || "";
    if (group === "index") return UI.doc_group_index || "";
    return group || "-";
  }

  function normalizeFileEntryTab(value) {
    return value === "health" ? "health" : "index";
  }

  function normalizeFileConsoleTab(value) {
    return value === "issues" ? "issues" : "meta";
  }

  function selectedDocumentRecord() {
    return state.documents?.documents_by_name?.[state.selectedDocumentName] || null;
  }

  function activeEditorContent() {
    return String(document.getElementById("editor-content")?.value || "");
  }

  function resolveIssueDocumentName(issue) {
    const explicitName = String(issue?.document_name || "").trim();
    if (explicitName) return explicitName;
    const target = String(issue?.target || "").trim();
    return state.documents?.documents_by_name?.[target] ? target : "";
  }

  function currentDocumentIssues() {
    const name = String(state.selectedDocumentName || "").trim();
    if (!name) return [];
    return (state.documents?.health_issues || []).filter((item) => resolveIssueDocumentName(item) === name);
  }

  function renderTagMarkup(text, variant = "") {
    const classes = variant ? `tag ${variant}` : "tag";
    return `<span class="${classes}">${escapeHtml(text)}</span>`;
  }

  function syncFileEntryTabState() {
    const activeTab = normalizeFileEntryTab(state.activeFileEntryTab);
    state.activeFileEntryTab = activeTab;
    document
      .querySelectorAll('#admin-file-entry-tabs [data-tab-group="file-entry"]')
      .forEach((button) => {
        const selected = button.dataset.tab === activeTab;
        button.setAttribute("aria-selected", selected ? "true" : "false");
      });
    document.querySelectorAll("[data-tab-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.tabPanel !== activeTab;
    });
  }

  function setActiveFileEntryTab(value, { persist = true } = {}) {
    state.activeFileEntryTab = normalizeFileEntryTab(value);
    syncFileEntryTabState();
    if (persist) queuePersistAdminPageState();
  }

  function syncFileConsoleTabState() {
    const activeTab = normalizeFileConsoleTab(state.activeFileConsoleTab);
    state.activeFileConsoleTab = activeTab;
    document
      .querySelectorAll('#admin-file-console-tabs [data-console-tab]')
      .forEach((button) => {
        const selected = button.dataset.consoleTab === activeTab;
        button.setAttribute("aria-selected", selected ? "true" : "false");
      });
    document.querySelectorAll("[data-console-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.consolePanel !== activeTab;
    });
  }

  function setActiveFileConsoleTab(value, { persist = true } = {}) {
    state.activeFileConsoleTab = normalizeFileConsoleTab(value);
    syncFileConsoleTabState();
    if (persist) queuePersistAdminPageState();
  }

  function renderEditorHeaderSummary() {
    const detail = state.selectedDocumentDetail;
    const record = selectedDocumentRecord();
    const pathNode = document.getElementById("admin-file-current-path");
    const tagsNode = document.getElementById("admin-file-current-tags");
    if (pathNode) {
      pathNode.textContent =
        record?.relative_path ||
        detail?.path ||
        (hasSelectedDocument()
          ? "-"
          : (UI.file_current_path_empty || ""));
    }
    if (!tagsNode) return;
    if (!detail && !record) {
      tagsNode.innerHTML = "";
      return;
    }
    const linkedIssues = currentDocumentIssues();
    const tags = [
      detail?.structured?.kind || record?.kind
        ? `${UI.doc_kind_label || ""}: ${detail?.structured?.kind || record?.kind || "-"}`
        : "",
      detail?.structured?.status || record?.status
        ? `${UI.doc_status_label || ""}: ${detail?.structured?.status || record?.status || "-"}`
        : "",
      linkedIssues.length
        ? `${linkedIssues.length} ${UI.doc_issues_label || ""}`
        : "",
    ].filter(Boolean);
    tagsNode.innerHTML = tags.map((item) => renderTagMarkup(item)).join("");
  }

  function syncPreviewDocumentLabel() {
    const node = document.getElementById("admin-file-preview-name");
    if (!node) return;
    const detail = state.selectedDocumentDetail;
    const record = selectedDocumentRecord();
    node.textContent =
      detail?.structured?.title ||
      record?.title ||
      state.selectedDocumentName ||
      UI.doc_select_prompt ||
      "";
  }

  function hasSelectedDocument() {
    return Boolean(state.selectedDocumentName);
  }

  function updateFileDirtyState({ persist = true } = {}) {
    state.fileDirty = hasSelectedDocument() && activeEditorContent() !== state.fileLoadedContent;
    const dirtyNode = document.getElementById("admin-file-dirty-indicator");
    const resetButton = document.getElementById("reset-entry-button");
    if (dirtyNode) {
      if (!hasSelectedDocument()) {
        dirtyNode.hidden = true;
      } else {
        dirtyNode.hidden = false;
        dirtyNode.className = `tag ${state.fileDirty ? "warn" : "ok"}`;
        dirtyNode.textContent = state.fileDirty ? UI.file_dirty || "" : UI.file_clean || "";
      }
    }
    if (resetButton) resetButton.disabled = !hasSelectedDocument() || !state.fileDirty;
    renderEditorHeaderSummary();
    if (persist) queuePersistAdminPageState();
  }

  function updateEditorPreview(content) {
    const node = document.getElementById("editor-preview");
    if (!node) return;
    const text = String(content || "");
    const previewText = text.replace(/^\uFEFF?---\r?\n[\s\S]*?\r?\n---\r?\n?/, "");
    if (!previewText.trim()) {
      node.className = "markdown empty";
      node.textContent = UI.editor_preview_empty || "";
      return;
    }
    node.className = "markdown";
    node.innerHTML = renderMarkdown(previewText);
  }

  function renderFileCounts() {
    const node = document.getElementById("admin-file-counts");
    if (!node) return;
    const counts = state.documents?.counts || {};
    const stats = [
      [UI.file_counts_formal || "", counts.formal || 0],
      [UI.file_counts_placeholder || "", counts.placeholder || 0],
      [UI.file_counts_index || "", counts.index || 0],
      [UI.file_counts_indexed || "", counts.indexed || 0],
      [UI.file_counts_unindexed || "", counts.unindexed || 0],
    ];
    node.innerHTML = stats
      .map(
        ([label, value]) =>
          `<div class="file-count-chip"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`
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
      "";
    syncPreviewDocumentLabel();
  }

  function syncFileEditorState() {
    const editor = document.getElementById("editor-content");
    const previewButton = document.getElementById("admin-file-preview-button");
    const resetButton = document.getElementById("reset-entry-button");
    const reloadButton = document.getElementById("reload-entry-button");
    const saveButton = document.getElementById("save-entry-button");
    const hasSelection = hasSelectedDocument();
    if (editor) {
      editor.disabled = !hasSelection;
      if (!hasSelection) {
        editor.value = "";
        editor.dataset.hash = "";
        state.fileLoadedContent = "";
      }
    }
    if (previewButton) previewButton.disabled = !hasSelection;
    if (resetButton) resetButton.disabled = !hasSelection || !state.fileDirty;
    if (reloadButton) reloadButton.disabled = !hasSelection;
    if (saveButton) saveButton.disabled = !hasSelection;
    if (!hasSelection) {
      closeFilePreviewModal();
      updateEditorPreview("");
      setSectionStatus("editor-status", UI.doc_select_prompt || "");
    }
    setCurrentDocumentLabel();
    renderEditorHeaderSummary();
    updateFileDirtyState({ persist: false });
  }

  function renderStats(overview) {
    const node = document.getElementById("admin-stats");
    if (!node) return;
    const stats = [
      [UI.stats_pending, overview.submission_counts?.pending || 0],
      [UI.stats_queue, overview.queued_jobs || 0],
      [UI.stats_running, overview.running_jobs || 0],
      [UI.stats_reviews, overview.open_feedback ?? (overview.pending_reviews || 0)],
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

    const healthNode = document.getElementById("admin-health-summary-note");
    if (healthNode && overview.health_summary?.cluster_coverage != null) {
      const coverage = Math.round(Number(overview.health_summary.cluster_coverage || 0) * 100);
      healthNode.textContent = `${UI.health_cluster_coverage || ""} ${coverage}%`.trim();
    }
  }

  function renderInsightsList(payload) {
    const node = document.getElementById("admin-insights-list");
    const summaryNode = document.getElementById("admin-insights-summary");
    if (summaryNode) {
      const counts = payload.summary?.counts || {};
      const pending = payload.summary?.pending || 0;
      summaryNode.textContent = [
        `${UI.insight_summary_pending || ""} ${pending}`.trim(),
        `${UI.insight_summary_proposed || ""} ${counts.proposed || 0}`.trim(),
        `${UI.insight_summary_observing || ""} ${counts.observing || 0}`.trim(),
      ].join(" · ");
    }
    if (!node) return;
    const items = Array.isArray(payload.items) ? payload.items : [];
    state.insights = items;
    node.innerHTML = items.length
      ? items
          .map((item) => `
            <button type="button" class="card insight-list-item" data-action="select-insight" data-insight-id="${escapeHtml(item.id || "")}">
              <div class="row spread">
                <strong>${escapeHtml(item.title || item.id || "")}</strong>
                <span class="tag">${escapeHtml(insightStateLabel(item.review_state))}</span>
              </div>
              <div class="subtle">${escapeHtml(insightKindLabel(item.kind))} · ${escapeHtml((item.supporting_entries || []).length)} ${escapeHtml(UI.insight_sources_suffix || "")}</div>
            </button>
          `)
          .join("")
      : `<div class="empty">${escapeHtml(UI.insight_empty || "")}</div>`;
  }

  function renderInsightDetail(payload) {
    const node = document.getElementById("admin-insight-detail");
    if (!node) return;
    if (!payload?.proposal) {
      node.innerHTML = `<div class="empty">${escapeHtml(UI.insight_detail_empty || "")}</div>`;
      return;
    }
    const proposal = payload.proposal;
    const triggerQueries = Array.isArray(proposal.trigger_queries) ? proposal.trigger_queries : [];
    const entries = Array.isArray(proposal.supporting_entries) ? proposal.supporting_entries : [];
    node.innerHTML = `
      <div class="card">
        <div class="row spread">
          <strong>${escapeHtml(proposal.title || proposal.id || "")}</strong>
          <span class="tag">${escapeHtml(insightStateLabel(proposal.review_state))}</span>
        </div>
        <div class="subtle">${escapeHtml(insightKindLabel(proposal.kind))} · ${escapeHtml(insightRecommendedActionLabel(payload.recommended_action))}</div>
        <div class="markdown">${renderMarkdown(`## ${UI.insight_hypothesis_title || ""}\n${proposal.hypothesis || "-"}\n\n## ${UI.insight_proposed_answer_title || ""}\n${proposal.proposed_answer || "-"}\n\n## ${UI.insight_supporting_entries_title || ""}\n${entries.map((item) => `- ${item}`).join("\n") || "-"}\n\n## ${UI.insight_trigger_queries_title || ""}\n${triggerQueries.map((item) => `- ${item}`).join("\n") || "-"}`)}</div>
      </div>
    `;
    setNodeValue("admin-insight-target", entries[0] || "");
    setNodeValue("admin-insight-title", proposal.title || "");
  }

  async function selectInsight(insightId) {
    const normalized = String(insightId || "").trim();
    if (!normalized) {
      state.selectedInsightId = null;
      state.selectedInsightDetail = null;
      renderInsightDetail(null);
      return;
    }
    state.selectedInsightId = normalized;
    state.selectedInsightDetail = await fetchAdmin(`/api/admin/insights/${encodeURIComponent(normalized)}`);
    renderInsightDetail(state.selectedInsightDetail);
    queuePersistAdminPageState();
  }

  async function loadInsights() {
    const payload = await fetchAdmin("/api/admin/insights");
    renderInsightsList(payload);
    if (state.selectedInsightId) {
      try {
        await selectInsight(state.selectedInsightId);
        return;
      } catch (_error) {
        state.selectedInsightId = null;
      }
    }
    if (payload.items?.length) {
      await selectInsight(payload.items[0].id);
    } else {
      renderInsightDetail(null);
    }
  }

  function renderAdminGraphDetail(node) {
    const detailNode = document.getElementById("admin-graph-detail");
    if (!detailNode) return;
    if (!node) {
      detailNode.innerHTML = `<div class="empty">${escapeHtml(UI.graph_detail_empty || "")}</div>`;
      return;
    }
    const details = node.details || {};
    const relatedItems = Array.isArray(details.related_links)
      ? details.related_links
      : Array.isArray(details.supporting_entries)
        ? details.supporting_entries
        : Array.isArray(details.source_entries)
          ? details.source_entries
          : [];
    const triggerQueries = Array.isArray(details.trigger_queries) ? details.trigger_queries : [];
    const eventLabel = (() => {
      const labels = {
        ask_reinforced: UI.graph_event_ask_reinforced || "",
        proposal_materialized: UI.graph_event_proposal_materialized || "",
        insight_promoted: UI.graph_event_insight_promoted || "",
        insight_merged: UI.graph_event_insight_merged || "",
        ingest_created: UI.graph_event_ingest_created || "",
        ingest_updated: UI.graph_event_ingest_updated || "",
      };
      return labels[String(node.event_type || "")] || (UI.graph_event_empty || "");
    })();
    const metrics = [
      [UI.graph_metric_energy || "", Number(node.energy || 0).toFixed(2)],
      [UI.graph_metric_stability || "", Number(node.stability || 0).toFixed(2)],
      [UI.graph_metric_role || "", node.visual_role || node.node_type || "-"],
      [UI.graph_metric_state || "", node.status || node.state || "-"],
    ];
    detailNode.innerHTML = `
      <div class="card">
        <div class="row spread">
          <strong>${escapeHtml(node.label || node.id || "")}</strong>
          <span class="tag">${escapeHtml(node.node_type || node.kind || "")}</span>
        </div>
        <div class="subtle">${escapeHtml(eventLabel)}</div>
        <div class="graph-metric-grid">
          ${metrics
            .map(
              ([label, value]) => `
                <div class="graph-metric">
                  <strong>${escapeHtml(value)}</strong>
                  <span>${escapeHtml(label)}</span>
                </div>
              `
            )
            .join("")}
        </div>
        <div class="markdown">${renderMarkdown(node.summary || details.proposed_answer || details.hypothesis || "")}</div>
        ${
          details.hypothesis
            ? `<div><strong>${escapeHtml(UI.graph_hypothesis_title || "")}</strong><div class="subtle">${escapeHtml(details.hypothesis)}</div></div>`
            : ""
        }
        ${
          relatedItems.length
            ? `<div><strong>${escapeHtml(UI.graph_supporting_links_title || "")}</strong><ul class="graph-list">${relatedItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>`
            : ""
        }
        ${
          triggerQueries.length
            ? `<div><strong>${escapeHtml(UI.graph_trigger_queries_title || "")}</strong><ul class="graph-list">${triggerQueries.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>`
            : ""
        }
        ${
          node.entry_target
            ? `<div class="graph-chip-row"><a class="button" href="/entries/${encodeURIComponent(node.entry_target)}?lang=${encodeURIComponent(locale)}" target="_blank" rel="noopener noreferrer">${escapeHtml(UI.graph_open_entry || "")}</a></div>`
            : ""
        }
      </div>
    `;
  }

  async function loadAdminGraph() {
    const graphNode = document.getElementById("admin-insights-graph");
    const statsNode = document.getElementById("admin-graph-stats");
    if (!graphNode) return;
    const payload = await fetchAdmin("/api/admin/graph");
    state.adminGraphPayload = payload;
    if (statsNode) {
      const stats = payload.stats || {};
      const coverage = Math.round(Number(stats.cluster_coverage || 0) * 100);
      statsNode.textContent = `${stats.node_count || 0} ${UI.graph_stats_nodes_suffix || ""} · ${stats.edge_count || 0} ${UI.graph_stats_edges_suffix || ""} · ${UI.graph_stats_coverage_prefix || ""} ${coverage}%`;
    }
    if (window.SedimentGraph?.mountAdminGraph) {
      state.adminGraphController = window.SedimentGraph.mountAdminGraph(graphNode, payload, {
        onSelect(node) {
          renderAdminGraphDetail(node);
          if (node?.node_type === "insight_proposal" && node.id?.startsWith("insight::")) {
            selectInsight(node.id.slice("insight::".length)).catch(createErrorHandler());
          }
        },
      });
      if (state.kbPane === "graph") {
        window.requestAnimationFrame(() => {
          if (typeof state.adminGraphController?.resize === "function") {
            state.adminGraphController.resize();
          }
        });
      }
    } else {
      graphNode.textContent = UI.graph_renderer_unavailable || "";
    }
    renderAdminGraphDetail(null);
  }

  async function reviewInsight(action) {
    if (!state.selectedInsightId) {
      throw new Error(UI.insight_select_prompt || "");
    }
    const payload = await fetchAdmin(`/api/admin/insights/${encodeURIComponent(state.selectedInsightId)}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action,
        target_name: nodeValue("admin-insight-target"),
        new_title: nodeValue("admin-insight-title"),
        note: nodeValue("admin-insight-note"),
      }),
    });
    setSectionStatus("admin-insight-status", UI.insight_job_created || "");
    setAdminMessage(`${action} · ${(payload.job?.id || "").slice(0, 8)}`);
    if (payload.job?.id) {
      await waitForManagedJob(payload.job.id, "tidy");
    }
    await Promise.all([loadInsights(), loadAdminGraph(), loadOverview(), loadIssues(), loadAuditLogs()]);
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
                <span class="tag">${escapeHtml(UI.issue_target_label || "")}: ${escapeHtml(item.target || "-")}</span>
                <span class="tag">${escapeHtml(UI.issue_action_label || "")}: ${escapeHtml(actionLabel(item.suggested_action || ""))}</span>
                ${
                  item.suggested_action === "run_tidy"
                    ? `<span class="tag">${escapeHtml(UI.issue_scope_label || "")}: ${escapeHtml(scopeLabel(scopeForIssue(item)))}</span>`
                    : ""
                }
              </div>
            </div>
          `;
        }).join("")
      : `<div class="empty">${escapeHtml(UI.issue_empty)}</div>`;
  }

  function renderEmergingClusters(items) {
    const node = document.getElementById("emerging-clusters-list");
    if (!node) return;
    const list = Array.isArray(items) ? items : [];
    node.innerHTML = list.length
      ? list
          .map((item) => `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(item.display_query || item.normalized_subject || "")}</strong>
                <span class="tag">${escapeHtml(item.status || "")}</span>
              </div>
              <div class="subtle">${escapeHtml(item.intent || UI.emerging_intent_default || "-")} · ${escapeHtml(UI.emerging_metric_demand || "")} ${escapeHtml(item.demand_score || 0)} · ${escapeHtml(UI.emerging_metric_maturity || "")} ${escapeHtml(item.maturity_score || 0)}</div>
            </div>
          `)
          .join("")
      : `<div class="empty">${escapeHtml(UI.emerging_empty || "")}</div>`;
  }

  function renderStressPoints(items) {
    const node = document.getElementById("stress-points-list");
    if (!node) return;
    const list = Array.isArray(items) ? items : [];
    node.innerHTML = list.length
      ? list
          .map((item) => `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(item.entry || "")}</strong>
                <span class="tag">${escapeHtml(item.signal_count || 0)}</span>
              </div>
              <div class="subtle">${escapeHtml((item.query_examples || []).join(" · ") || "")}</div>
            </div>
          `)
          .join("")
      : `<div class="empty">${escapeHtml(UI.stress_empty || "")}</div>`;
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
            <div class="action-row">
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
                ${item.submission?.status ? `<span class="tag">${escapeHtml(UI.review_submission_status || "")}: ${escapeHtml(item.submission.status)}</span>` : ""}
                <span class="tag">${escapeHtml(UI.review_patch_count || "")}: ${escapeHtml((item.job?.result_payload?.operations || []).length || 0)}</span>
                <span class="tag">${escapeHtml(UI.review_created_at || "")}: ${escapeHtml(formatDateTime(item.created_at || item.job?.created_at || ""))}</span>
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
          <strong>${escapeHtml(UI.review_summary || "")}</strong>
          <p>${escapeHtml(payload.job?.result_payload?.summary || "-")}</p>
        </div>
        <div class="detail-block">
          <strong>${escapeHtml(UI.review_job_type || "")}</strong>
          <p>${escapeHtml(payload.job?.job_type || "-")} · ${escapeHtml((payload.job?.id || "").slice(0, 8))}</p>
        </div>
        <div class="detail-block">
          <strong>${escapeHtml(UI.review_decision || "")}</strong>
          <p>${escapeHtml(payload.review?.decision || "-")}</p>
        </div>
        <div class="detail-block">
          <strong>${escapeHtml(UI.review_patch_count || "")}</strong>
          <p>${escapeHtml(operations.length || 0)}</p>
        </div>
        <div class="detail-block">
          <strong>${escapeHtml(UI.review_created_at || "")}</strong>
          <p>${escapeHtml(formatDateTime(payload.review?.created_at || payload.job?.created_at || ""))}</p>
        </div>
        ${
          submission
            ? `
              <div class="detail-block">
                <strong>${escapeHtml(UI.review_source_submission || "")}</strong>
                <p>${escapeHtml(submission.title || submission.id || "-")}</p>
              </div>
              <div class="detail-block">
                <strong>${escapeHtml(UI.review_submission_author || "")}</strong>
                <p>${escapeHtml(submission.submitter_name || "-")}</p>
              </div>
              <div class="detail-block">
                <strong>${escapeHtml(UI.review_submission_status || "")}</strong>
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
            <div class="action-row">
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
    const stateLabel = (value) =>
      value ? (UI.system_state_enabled || "") : (UI.system_state_disabled || "");
    node.innerHTML = `
      <div class="card">
        <div class="row spread"><strong>${escapeHtml(payload.instance?.name || "")}</strong><span class="tag">${escapeHtml(payload.worker_mode || "")}</span></div>
        <div class="subtle">${escapeHtml(UI.system_auth_label || "")}: ${escapeHtml(stateLabel(payload.auth_required))}</div>
        <div class="subtle">${escapeHtml(UI.system_proxy_label || "")}: ${escapeHtml(stateLabel(payload.proxy?.trust_proxy_headers))}</div>
        <div class="subtle">${escapeHtml(UI.system_rate_label || "")}: ${escapeHtml(payload.limits?.submission_rate_limit_count || 0)} / ${escapeHtml(payload.limits?.submission_rate_limit_window_seconds || 0)}s</div>
        <div class="subtle">${escapeHtml(UI.system_text_label || "")}: ${escapeHtml(payload.limits?.max_text_submission_chars || 0)}</div>
        <div class="subtle">${escapeHtml(UI.system_upload_label || "")}: ${escapeHtml(bytesMb.toFixed(1))} MiB</div>
        <div class="subtle">${escapeHtml(UI.system_retry_label || "")}: ${escapeHtml(payload.limits?.job_max_attempts || 0)}</div>
        <div class="subtle">${escapeHtml(UI.system_stale_label || "")}: ${escapeHtml(payload.limits?.job_stale_after_seconds || 0)}s</div>
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
          const tokenActionLabel = token ? (UI.token_hide || "") : (UI.token_show || "");
          return `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(user.name || user.id || "")}</strong>
                <span class="tag ${user.disabled ? "warn" : "ok"}">${escapeHtml(roleLabel(user.role || ""))}${user.disabled ? ` · ${escapeHtml(UI.user_disabled_label || "")}` : ""}</span>
              </div>
              <div class="subtle">${escapeHtml(user.id || "")} · ${escapeHtml(user.token_fingerprint || "")}</div>
              <div class="subtle">${escapeHtml(formatDateTime(user.created_at))}</div>
              <div class="user-card-meta">
                ${isCurrent ? `<span class="tag">${escapeHtml(UI.current_session || "")}</span>` : ""}
              </div>
              <div class="action-row">
                <button data-action="show-token" data-user-id="${escapeHtml(userId)}">${escapeHtml(tokenActionLabel)}</button>
                ${user.disabled ? "" : `<button data-action="disable-user" data-user-id="${escapeHtml(userId)}">${escapeHtml(UI.disable_user || "")}</button>`}
              </div>
              ${
                token
                  ? `
                    <div class="inline-token">
                      <strong>${escapeHtml(UI.token_label || "")}</strong>
                      <div class="mono">${escapeHtml(token)}</div>
                    </div>
                  `
                  : ""
              }
            </div>
          `;
        }).join("")
      : `<div class="empty">${escapeHtml(UI.users_empty || "")}</div>`;
  }

  function renderDocumentButton(doc) {
    const issueBadge = doc.issue_count
      ? `<span class="doc-count-badge">${escapeHtml(doc.issue_count)}</span>`
      : "";
    return `
      <button
        type="button"
        class="button doc-button ${doc.name === state.selectedDocumentName ? "active" : ""}"
        data-action="open-document"
        data-name="${escapeHtml(doc.name)}"
      >
        <span class="doc-button-label">
          <span class="doc-tree-heading">
            <span class="doc-button-title">${escapeHtml(doc.title || doc.name)}</span>
            ${issueBadge}
          </span>
          <span class="doc-button-meta">
            ${escapeHtml(doc.relative_path || "-")}
            ${doc.issue_count ? ` · ${escapeHtml(doc.issue_count)} ${escapeHtml(UI.doc_issues_label || "")}` : ""}
          </span>
        </span>
      </button>
    `;
  }

  function renderIndexNode(node, level = 0) {
    const directDocuments = Array.isArray(node.direct_documents) ? node.direct_documents : [];
    const childIndexes = Array.isArray(node.child_indexes) ? node.child_indexes : [];
    const childResults = childIndexes.map((child) => renderIndexNode(child, level + 1));
    const childMarkup = childResults.map((child) => child.markup).join("");
    const directDocMarkup = directDocuments.map((doc) => renderDocumentButton(doc)).join("");
    const itemCount = Number(node.reachable_document_count || 0);
    const tokenCount = Number(node.estimated_tokens || 0);
    const isSelectedIndex = node.name === state.selectedDocumentName;
    const containsSelectedDirectDoc = directDocuments.some(
      (doc) => doc.name === state.selectedDocumentName
    );
    const containsSelectedChild = childResults.some((child) => child.containsSelection);
    const containsSelection = isSelectedIndex || containsSelectedDirectDoc || containsSelectedChild;
    const issueTag = Number(node.issue_count || 0)
      ? renderTagMarkup(`${node.issue_count} ${UI.doc_issues_label || ""}`, "warn")
      : "";
    return {
      containsSelection,
      markup: `
      <details class="doc-tree-group index-tree-group ${isSelectedIndex ? "selected" : ""}" ${level < 1 || containsSelection ? "open" : ""}>
        <summary>
          <span class="doc-tree-summary">
            <span class="doc-tree-heading">
              <strong>${escapeHtml(node.title || node.name)}</strong>
              <span class="doc-tree-tags">
                ${renderTagMarkup(node.name || "")}
                ${issueTag}
              </span>
            </span>
            <span class="doc-button-meta">
              ${escapeHtml(node.name || "")}
              · ${escapeHtml(itemCount)} ${escapeHtml(UI.file_counts_indexed || "")}
              · ${escapeHtml(tokenCount)} ${escapeHtml(UI.file_tokens_label || "")}
            </span>
          </span>
        </summary>
        <div class="doc-tree-list">
          ${
            childMarkup
              ? `
                <div class="stack">
                  <div class="tabs-note">${escapeHtml(UI.file_index_child_indexes || "")}</div>
                  ${childMarkup}
                </div>
              `
              : ""
          }
          ${
            directDocMarkup
              ? `
                <div class="stack">
                  <div class="tabs-note">${escapeHtml(UI.file_index_direct_docs || "")}</div>
                  <div class="doc-tree-list">${directDocMarkup}</div>
                </div>
              `
              : ""
          }
        </div>
      </details>
    `,
    };
  }

  function renderFileIndexTree() {
    const node = document.getElementById("admin-file-index-tree");
    if (!node) return;
    const topIndexes = Array.isArray(state.documents?.top_indexes) ? state.documents.top_indexes : [];
    const unindexed = Array.isArray(state.documents?.unindexed_documents) ? state.documents.unindexed_documents : [];
    const sections = topIndexes.map((item) => renderIndexNode(item).markup);
    const hasSelectedUnindexed = unindexed.some((doc) => doc.name === state.selectedDocumentName);
    if (unindexed.length) {
      sections.push(`
        <details class="doc-tree-group ${hasSelectedUnindexed ? "selected" : ""}" ${state.activeFileEntryTab === "index" || hasSelectedUnindexed ? "open" : ""}>
          <summary>
            <span class="doc-tree-summary">
              <span class="doc-tree-heading">
                <strong>${escapeHtml(UI.file_unindexed_group || "")}</strong>
                <span class="doc-tree-tags">${renderTagMarkup(String(unindexed.length))}</span>
              </span>
            </span>
          </summary>
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
    const linkedIssues = currentDocumentIssues();
    const blocks = [
      [UI.doc_path_label || "", doc?.relative_path || detail?.path || "-"],
      [UI.doc_kind_label || "", detail?.structured?.kind || doc?.kind || "-"],
      [UI.doc_status_label || "", detail?.structured?.status || doc?.status || "-"],
      [UI.doc_issues_label || "", linkedIssues.length || 0],
      [UI.doc_indexes_label || "", indexes.length ? indexes.join(" · ") : "-"],
      [UI.doc_aliases_label || "", aliases.length ? aliases.join(" · ") : "-"],
      [UI.doc_links_label || "", links.length ? links.join(" · ") : "-"],
      [UI.doc_updated_label || "", doc?.updated_at ? formatDateTime(doc.updated_at) : "-"],
    ];
    node.innerHTML = blocks
      .map(
        ([label, value]) => `
          <div class="file-meta-row">
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
    const severityWeight = { blocking: 4, high: 3, medium: 2, low: 1 };
    const grouped = new Map();
    issues.forEach((item) => {
      const documentName = resolveIssueDocumentName(item);
      if (!documentName) return;
      if (!grouped.has(documentName)) {
        grouped.set(documentName, {
          name: documentName,
          title: state.documents?.documents_by_name?.[documentName]?.title || documentName,
          relative_path: state.documents?.documents_by_name?.[documentName]?.relative_path || "-",
          highestSeverity: "low",
          issues: [],
        });
      }
      const bucket = grouped.get(documentName);
      bucket.issues.push(item);
      if ((severityWeight[item.severity] || 0) > (severityWeight[bucket.highestSeverity] || 0)) {
        bucket.highestSeverity = item.severity || bucket.highestSeverity;
      }
    });
    const cards = [...grouped.values()].sort((left, right) => {
      const severityDiff =
        (severityWeight[right.highestSeverity] || 0) - (severityWeight[left.highestSeverity] || 0);
      if (severityDiff) return severityDiff;
      const issueDiff = right.issues.length - left.issues.length;
      if (issueDiff) return issueDiff;
      return String(left.title || left.name).localeCompare(String(right.title || right.name));
    });
    node.innerHTML = cards.length
      ? cards.map((item) => {
          const severityClass =
            item.highestSeverity === "blocking" || item.highestSeverity === "high"
              ? "danger"
              : item.highestSeverity === "medium"
                ? "warn"
                : "ok";
          const selected = item.name === state.selectedDocumentName ? "selected" : "";
          const firstIssue = item.issues[0] || {};
          const typeSummary = item.issues
            .slice(0, 3)
            .map((issue) => String(issue.type || "").trim())
            .filter(Boolean)
            .join(" · ");
          return `
            <button
              type="button"
              class="health-document-card ${selected}"
              data-action="open-document"
              data-name="${escapeHtml(item.name)}"
              data-source-tab="health"
              data-focus-console-section="issues"
            >
              <div class="card interactive ${selected}">
                <div class="row spread">
                  <strong>${escapeHtml(item.title || item.name)}</strong>
                  <span class="tag ${severityClass}">${escapeHtml(item.highestSeverity || "")}</span>
                </div>
                <div class="subtle">${escapeHtml(item.relative_path || "-")}</div>
                <div class="subtle">${escapeHtml(firstIssue.summary || "")}</div>
                <div class="issue-card-meta">
                  ${renderTagMarkup(`${item.issues.length} ${UI.doc_issues_label || ""}`)}
                  ${typeSummary ? renderTagMarkup(typeSummary) : ""}
                </div>
              </div>
            </button>
          `;
        }).join("")
      : `<div class="empty">${escapeHtml(UI.doc_health_empty)}</div>`;
  }

  function renderLinkedIssues() {
    const node = document.getElementById("admin-doc-linked-issues");
    if (!node) return;
    const issues = currentDocumentIssues();
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

  function focusFileConsoleSection(sectionName) {
    const normalizedSection = normalizeFileConsoleTab(sectionName);
    setActiveFileConsoleTab(normalizedSection, { persist: false });
    const node = document.getElementById(
      normalizedSection === "issues" ? "admin-file-console-issues" : "admin-file-console-meta"
    );
    if (!node) return;
    window.clearTimeout(fileConsoleFocusTimer);
    document.querySelectorAll(".file-console-section").forEach((section) => {
      section.classList.remove("console-section-focus");
      section.removeAttribute("data-highlighted");
    });
    node.classList.add("console-section-focus");
    node.setAttribute("data-highlighted", "true");
    node.scrollIntoView({
      block: window.innerWidth > 960 ? "center" : "start",
      behavior: "auto",
    });
    fileConsoleFocusTimer = window.setTimeout(() => {
      node.classList.remove("console-section-focus");
      node.removeAttribute("data-highlighted");
    }, 1800);
  }

  function syncReviewActionState() {
    const hasSelection = Boolean(state.selectedReviewId);
    const approveButton = document.getElementById("approve-review-button");
    const rejectButton = document.getElementById("reject-review-button");
    if (approveButton) approveButton.disabled = !hasSelection;
    if (rejectButton) rejectButton.disabled = !hasSelection;
  }

  function inboxActionButton(action, itemId, version, label, extra = "") {
    return `
      <button
        type="button"
        data-action="${escapeHtml(action)}"
        data-item-id="${escapeHtml(String(itemId || ""))}"
        data-version="${escapeHtml(String(version || 0))}"
        ${extra}
      >${escapeHtml(label)}</button>
    `;
  }

  function renderInboxSimpleList(nodeId, items, renderItem, emptyText) {
    const node = document.getElementById(nodeId);
    if (!node) return;
    const list = Array.isArray(items) ? items : [];
    node.innerHTML = list.length
      ? list.map(renderItem).join("")
      : `<div class="empty">${escapeHtml(emptyText || UI.inbox_empty || "")}</div>`;
  }

  function renderInbox(payload) {
    state.inbox = payload || { items: {} };
    const items = state.inbox.items || {};
    renderInboxSimpleList(
      "inbox-open-feedback-list",
      items.open_feedback || [],
      (item) => `
        <div class="card">
          <div class="row spread">
            <strong>${escapeHtml(item.title || "")}</strong>
            <span class="tag">${escapeHtml(formatDateTime(item.created_at || ""))}</span>
          </div>
          <div class="subtle">${escapeHtml(item.submitter_name || "")}</div>
          <p>${escapeHtml(item.body_text || "")}</p>
          <div class="action-row">
            ${inboxActionButton("resolve-feedback", item.id, item.version, UI.inbox_resolve || "")}
          </div>
        </div>
      `,
      UI.inbox_feedback_empty
    );
    renderInboxSimpleList(
      "inbox-staged-documents-list",
      items.staged_documents || [],
      (item) => `
        <div class="card">
          <div class="row spread">
            <strong>${escapeHtml(item.title || item.original_filename || "")}</strong>
            <span class="tag">${escapeHtml(item.mime_type || "")}</span>
          </div>
          <div class="subtle">${escapeHtml(item.original_filename || "")}</div>
          <div class="action-row">
            ${inboxActionButton("download-document", item.id, item.version, UI.inbox_download || "")}
            ${inboxActionButton("mark-ready", item.id, item.version, UI.inbox_mark_ready || "")}
            ${inboxActionButton("remove-document", item.id, item.version, UI.inbox_remove || "")}
          </div>
        </div>
      `,
      UI.inbox_documents_empty
    );
    renderInboxSimpleList(
      "inbox-ready-documents-list",
      items.ready_documents || [],
      (item) => `
        <label class="card">
          <div class="row spread">
            <strong>${escapeHtml(item.title || item.original_filename || "")}</strong>
            <input
              type="checkbox"
              data-action="select-ready-document"
              data-item-id="${escapeHtml(String(item.id || ""))}"
              data-version="${escapeHtml(String(item.version || 0))}"
            />
          </div>
          <div class="subtle">${escapeHtml(item.original_filename || "")}</div>
          <div class="action-row">
            ${inboxActionButton("download-document", item.id, item.version, UI.inbox_download || "")}
            ${inboxActionButton("move-to-staged", item.id, item.version, UI.inbox_move_to_staged || "")}
          </div>
        </label>
      `,
      UI.inbox_ready_empty
    );
    renderInboxSimpleList(
      "inbox-ingesting-documents-list",
      items.ingesting_documents || [],
      (item) => `
        <div class="card">
          <div class="row spread">
            <strong>${escapeHtml(item.title || item.original_filename || "")}</strong>
            <span class="tag">${escapeHtml(item.ingest_batch_id || "")}</span>
          </div>
          <div class="subtle">${escapeHtml(item.job_id || "")}</div>
        </div>
      `,
      UI.inbox_ingesting_empty
    );
    const historyItems = [...(items.resolved_feedback || []), ...(items.history_documents || [])];
    renderInboxSimpleList(
      "inbox-history-list",
      historyItems,
      (item) => `
        <div class="card">
          <div class="row spread">
            <strong>${escapeHtml(item.title || item.original_filename || "")}</strong>
            <span class="tag">${escapeHtml(item.status || "")}</span>
          </div>
          <div class="subtle">${escapeHtml(formatDateTime(item.updated_at || item.created_at || ""))}</div>
          <div class="action-row">
            ${item.item_type === "text_feedback"
              ? inboxActionButton("reopen-feedback", item.id, item.version, UI.inbox_reopen || "")
              : ""}
            ${item.item_type === "uploaded_document"
              ? inboxActionButton("download-document", item.id, item.version, UI.inbox_download || "")
              : ""}
          </div>
        </div>
      `,
      UI.inbox_history_empty
    );
  }

  function renderVersionStatus(payload) {
    state.versionStatus = payload || {};
    const summaryNode = document.getElementById("version-status-summary");
    if (summaryNode) {
      summaryNode.innerHTML = `
        <div class="card">
          <strong>${escapeHtml(UI.version_repo_root || "")}</strong>
          <div class="subtle">${escapeHtml(payload.repo_root || "")}</div>
        </div>
        <div class="card">
          <strong>${escapeHtml(UI.version_branch || "")}</strong>
          <div class="subtle">${escapeHtml(payload.current_branch || "-")}</div>
        </div>
        <div class="card">
          <strong>${escapeHtml(UI.version_upstream || "")}</strong>
          <div class="subtle">${payload.has_upstream ? escapeHtml(UI.version_upstream_ready || "") : escapeHtml(UI.version_upstream_missing || "")}</div>
        </div>
        <div class="card">
          <strong>${escapeHtml(UI.version_repo_lock || "")}</strong>
          <div class="subtle">${payload.repo_lock ? escapeHtml(payload.repo_lock.owner_name || "") : escapeHtml(UI.version_repo_lock_free || "")}</div>
        </div>
      `;
    }
    const changesNode = document.getElementById("version-tracked-changes-list");
    if (changesNode) {
      const changes = Array.isArray(payload.tracked_changes) ? payload.tracked_changes : [];
      changesNode.innerHTML = changes.length
        ? changes.map((item) => `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(item.path || "")}</strong>
                <span class="tag">${escapeHtml(`${item.index_status || " "}${item.worktree_status || " "}`.trim() || "M")}</span>
              </div>
            </div>
          `).join("")
        : `<div class="empty">${escapeHtml(UI.version_no_changes || "")}</div>`;
    }
    const commitsNode = document.getElementById("version-commits-list");
    if (commitsNode) {
      const commits = Array.isArray(payload.recent_commits) ? payload.recent_commits : [];
      commitsNode.innerHTML = commits.length
        ? commits.map((item) => `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(item.subject || "")}</strong>
                <span class="tag">${escapeHtml(String(item.sha || "").slice(0, 8))}</span>
              </div>
              <div class="subtle">${escapeHtml(item.author_name || "")} · ${escapeHtml(formatDateTime(item.authored_at || ""))}</div>
              <div class="action-row">
                ${item.revertible
                  ? `<button type="button" data-action="revert-commit" data-commit-sha="${escapeHtml(item.sha || "")}">${escapeHtml(UI.version_revert || "")}</button>`
                  : ""}
              </div>
            </div>
          `).join("")
        : `<div class="empty">${escapeHtml(UI.version_commits_empty || "")}</div>`;
    }
    const pushButton = document.getElementById("version-push-button");
    if (pushButton) pushButton.disabled = !payload.has_upstream || Boolean(payload.repo_lock);
  }

  async function loadOverview() {
    const overview = await fetchAdmin("/api/admin/overview");
    renderStats(overview);
    renderEmergingClusters(overview.emerging_clusters || []);
    renderStressPoints(overview.canonical_stress_points || []);
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
    if (input) {
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
    }
  }

  function activeFileSuggestion() {
    if (!state.fileSuggestions.length) return null;
    const index =
      state.activeFileSuggestionIndex >= 0 ? state.activeFileSuggestionIndex : 0;
    return state.fileSuggestions[index] || null;
  }

  function renderFileSuggestions(suggestions, { preserveSelection = false } = {}) {
    const node = document.getElementById("admin-file-suggestions");
    const input = document.getElementById("admin-file-search");
    if (!node || !input) return;
    const items = Array.isArray(suggestions) ? suggestions : [];
    const keepSelection =
      preserveSelection &&
      items.length === state.fileSuggestions.length &&
      items.every((item, index) => item.name === state.fileSuggestions[index]?.name);
    state.fileSuggestions = items;
    if (!items.length) {
      state.activeFileSuggestionIndex = -1;
      hideFileSuggestions();
      return;
    }
    if (keepSelection && state.activeFileSuggestionIndex >= 0) {
      state.activeFileSuggestionIndex = Math.min(
        state.activeFileSuggestionIndex,
        items.length - 1
      );
    } else {
      state.activeFileSuggestionIndex = 0;
    }
    node.hidden = false;
    input.setAttribute("aria-expanded", "true");
    input.setAttribute(
      "aria-activedescendant",
      `admin-file-suggestion-${state.activeFileSuggestionIndex}`
    );
    node.innerHTML = `
      <div class="list">
        ${items.map((item, index) => `
          <button
            type="button"
            class="search-suggestion"
            id="admin-file-suggestion-${index}"
            data-action="open-document"
            data-name="${escapeHtml(item.name || "")}"
            data-index="${index}"
            role="option"
            aria-selected="${index === state.activeFileSuggestionIndex ? "true" : "false"}"
          >
            <span class="doc-button-label">
              <span class="doc-button-title">${escapeHtml(item.title || item.name || "")}</span>
              <span class="doc-button-meta">${escapeHtml(item.relative_path || "-")} · ${escapeHtml(docGroupLabel(item.group || item.kind || ""))}</span>
            </span>
          </button>
        `).join("")}
      </div>
    `;
    window.requestAnimationFrame(() => {
      document
        .getElementById(`admin-file-suggestion-${state.activeFileSuggestionIndex}`)
        ?.scrollIntoView({ block: "nearest" });
    });
  }

  function moveActiveFileSuggestion(step) {
    if (!state.fileSuggestions.length) return;
    const total = state.fileSuggestions.length;
    const current = state.activeFileSuggestionIndex >= 0 ? state.activeFileSuggestionIndex : 0;
    state.activeFileSuggestionIndex = (current + step + total) % total;
    renderFileSuggestions(state.fileSuggestions, { preserveSelection: true });
  }

  async function updateFileSuggestions() {
    const input = document.getElementById("admin-file-search");
    if (!input) return;
    const query = String(input.value || "").trim();
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
    renderFileSuggestions(payload.suggestions || []);
    if (!state.fileSuggestions.length) {
      setSectionStatus("admin-file-search-status", UI.file_search_empty || "");
      return;
    }
    setSectionStatus(
      "admin-file-search-status",
      `${state.fileSuggestions.length} ${UI.file_search_matches || ""}`
    );
  }

  async function loadFileManager() {
    const payload = await fetchAdmin("/api/admin/files");
    state.documents = payload;
    if (state.selectedDocumentName) {
      const known = Boolean(payload.documents_by_name?.[state.selectedDocumentName]);
      if (!known) {
        state.selectedDocumentName = null;
        state.selectedDocumentDetail = null;
        state.fileLoadedContent = "";
        state.fileDirty = false;
      }
    }
    renderFileCounts();
    syncFileEntryTabState();
    syncFileConsoleTabState();
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

  async function loadInbox() {
    renderInbox(await fetchAdmin("/api/admin/inbox"));
  }

  async function loadVersionControl() {
    renderVersionStatus(await fetchAdmin("/api/admin/version/status"));
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
    queuePersistAdminPageState();
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

  function renderExploreResult(payload) {
    if (looksLikeRuntimeLeak(payload?.answer || "")) {
      renderExploreFailure(UI.explore_invalid_output || UI.explore_failed_hint || "");
      return;
    }
    const node = runtimeResultNode();
    if (!node) return;
    node.className = "runtime-result-view markdown";
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
    setRuntimeResultStatus(UI.explore_completed || "");
    queuePersistAdminPageState();
  }

  function renderExploreFailure(message) {
    const node = runtimeResultNode();
    if (!node) return;
    const safeMessage = safeExploreFailureMessage(message);
    node.className = "runtime-result-view markdown";
    node.innerHTML = `
      <div class="card">
        <div class="row spread">
          <strong>${escapeHtml(UI.explore_failed || "")}</strong>
          <span class="tag danger">${escapeHtml(UI.live_error_label || "")}</span>
        </div>
        <div class="subtle">${escapeHtml(safeMessage || "")}</div>
        <div class="subtle">${escapeHtml(UI.explore_failed_hint || "")}</div>
      </div>
    `;
    setRuntimeResultStatus(UI.explore_failed || "");
    queuePersistAdminPageState();
  }

  async function readResponseError(response) {
    const rawText = await response.text();
    try {
      const payload = JSON.parse(rawText);
      return payload.error || payload.message || rawText || `HTTP ${response.status}`;
    } catch {
      return rawText || `HTTP ${response.status}`;
    }
  }

  function liveLabelForExploreEvent(event) {
    if (event.type === "command") return UI.live_command_label || "";
    if (event.type === "cli-output" && event.stream === "stderr") return UI.live_stderr_label || "";
    if (event.type === "cli-output") return UI.live_stdout_label || "";
    if (event.type === "retry") return UI.live_retry_label || "";
    if (event.type === "error") return UI.live_error_label || "";
    if (event.type === "result") return UI.live_result_label || "";
    if (event.type === "done") return UI.live_done_label || "";
    return UI.live_status_label || "";
  }

  function liveMessageForExploreEvent(event) {
    const excerpt = String(event.raw_excerpt || "").trim();
    if (event.type === "command") {
      const summary = String(event.message || "").trim();
      if (
        looksLikeRuntimeLeak(summary) ||
        summary.toLowerCase().includes("--json-schema") ||
        summary.toLowerCase().includes("claude -p")
      ) {
        return event.command_summary || UI.live_command_redacted || summary;
      }
      return summary;
    }
    if (event.type === "result") {
      const payload = event.payload || {};
      const sources = Array.isArray(payload.sources) && payload.sources.length
        ? payload.sources.join(", ")
        : "-";
      return `${UI.explore_completed || ""} sources=${sources}`;
    }
    if (excerpt) {
      const safeExcerpt = looksLikeRuntimeLeak(excerpt)
        ? (UI.live_excerpt_redacted || excerpt)
        : excerpt;
      return `${event.message || ""} | ${safeExcerpt}`;
    }
    return event.message || "";
  }

  async function consumeNdjsonStream(response, onEvent) {
    const reader = response.body?.getReader();
    if (!reader) {
      const fallback = await response.text();
      for (const line of fallback.split(/\n+/)) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        onEvent(JSON.parse(trimmed));
      }
      return;
    }

    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      while (buffer.includes("\n")) {
        const newlineIndex = buffer.indexOf("\n");
        const line = buffer.slice(0, newlineIndex).trim();
        buffer = buffer.slice(newlineIndex + 1);
        if (!line) continue;
        onEvent(JSON.parse(line));
      }
      if (done) break;
    }
    const tail = buffer.trim();
    if (tail) onEvent(JSON.parse(tail));
  }

  async function runExplore() {
    const question = (document.getElementById("admin-explore-input")?.value || "").trim();
    if (!question) throw new Error(UI.explore_question_required || "");
    resetRuntimeResult(UI.result_running || UI.explore_running || "");
    setRuntimeResultStatus(UI.result_running || UI.explore_running || "");
    setExploreStatus(UI.explore_running || "");
    setLiveStatus(UI.live_running || "");
    logWorkbenchRequest("explore", `POST /api/admin/explore/live · question="${question}"`, {
      liveStatus: UI.live_running || "",
      sectionStatus: UI.explore_running || "",
    });

    let finalPayload = null;
    let finalError = "";
    const response = await fetch("/api/admin/explore/live", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      credentials: "same-origin",
    });
    if (!response.ok) {
      finalError = await readResponseError(response);
      renderExploreFailure(finalError);
      showAdminError(finalError, workbenchErrorOptions("explore"));
      return;
    }

    await consumeNdjsonStream(response, (event) => {
      appendLiveLog(liveLabelForExploreEvent(event), liveMessageForExploreEvent(event));
      if (["status", "retry", "command", "heartbeat"].includes(event.type)) {
        setExploreStatus(event.message || UI.explore_running || "");
      }
      if (event.type === "result") {
        finalPayload = event.payload || null;
        renderExploreResult(finalPayload || {});
        setWorkbenchStatus("explore", UI.explore_completed || "");
        setAdminMessage(String((finalPayload?.answer || "")).slice(0, 140));
        return;
      }
      if (event.type === "error") {
        finalError = event.message || UI.explore_failed || "";
        renderExploreFailure(finalError);
        showAdminError(finalError, { ...workbenchErrorOptions("explore"), appendLive: false });
        return;
      }
      if (event.type === "done") {
        setLiveStatus(event.ok ? (UI.explore_completed || "") : (finalError || UI.explore_failed || ""));
      }
    });

    if (!finalPayload && !finalError) {
      finalError = UI.explore_no_result || "";
      renderExploreFailure(finalError);
      showAdminError(finalError, workbenchErrorOptions("explore"));
    }
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
    logWorkbenchRequest("ingest", `POST /api/admin/submissions/${id}/run-ingest`, {
      liveStatus: UI.live_running || "",
    });
    const job = await fetchAdmin(`/api/admin/submissions/${encodeURIComponent(id)}/run-ingest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    completeWorkbenchAction("ingest", `${UI.ingest_done}${(job.id || "").slice(0, 8)}`);
    await waitForManagedJob(job.id, "ingest");
  }

  async function runTidy(options = {}) {
    logWorkbenchRequest("tidy", `POST /api/admin/tidy · ${JSON.stringify(options)}`, {
      liveStatus: UI.live_running || "",
    });
    const job = await fetchAdmin("/api/admin/tidy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options),
    });
    completeWorkbenchAction("tidy", `${UI.tidy_done}${(job.id || "").slice(0, 8)}`);
    await waitForManagedJob(job.id, "tidy");
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

  async function updateInboxItem(actionPath, version) {
    await fetchAdmin(`/api/admin/inbox/${actionPath}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version }),
    });
    await loadInbox();
  }

  async function resolveFeedback(itemId, version) {
    await updateInboxItem(`text/${encodeURIComponent(itemId)}/resolve`, version);
    setSectionStatus("inbox-status", UI.inbox_resolved || "");
  }

  async function reopenFeedback(itemId, version) {
    await updateInboxItem(`text/${encodeURIComponent(itemId)}/reopen`, version);
    setSectionStatus("inbox-status", UI.inbox_reopened || "");
  }

  async function markReady(itemId, version) {
    await updateInboxItem(`document/${encodeURIComponent(itemId)}/mark-ready`, version);
    setSectionStatus("inbox-status", UI.inbox_marked_ready || "");
  }

  async function moveToStaged(itemId, version) {
    await updateInboxItem(`document/${encodeURIComponent(itemId)}/move-to-staged`, version);
    setSectionStatus("inbox-status", UI.inbox_moved_to_staged || "");
  }

  async function removeDocument(itemId, version) {
    await updateInboxItem(`document/${encodeURIComponent(itemId)}/remove`, version);
    setSectionStatus("inbox-status", UI.inbox_removed || "");
  }

  function downloadDocument(itemId) {
    window.location.href = `/api/admin/inbox/document/${encodeURIComponent(itemId)}/download`;
  }

  async function createIngestBatch() {
    const selections = Array.from(
      document.querySelectorAll('#inbox-ready-documents-list input[data-action="select-ready-document"]:checked')
    ).map((input) => ({
      id: input.dataset.itemId || "",
      version: Number(input.dataset.version || 0),
    })).filter((item) => item.id);
    if (!selections.length) {
      throw new Error(UI.inbox_select_ready_required || "");
    }
    const payload = await fetchAdmin("/api/admin/inbox/ingest-batches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: selections }),
    });
    setSectionStatus("inbox-status", UI.inbox_batch_created || "");
    if (payload.redirect_url) {
      window.location.href = payload.redirect_url;
      return;
    }
    await loadInbox();
  }

  async function commitTrackedChanges() {
    const reason = (document.getElementById("version-commit-reason")?.value || "").trim();
    const payload = await fetchAdmin("/api/admin/version/commit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    });
    setSectionStatus("version-status-line", `${UI.version_commit_done || ""}${String(payload.commit_sha || "").slice(0, 8)}`);
    await loadVersionControl();
  }

  async function pushTrackedBranch() {
    const payload = await fetchAdmin("/api/admin/version/push", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    setSectionStatus("version-status-line", `${UI.version_push_done || ""}${payload.branch || ""}`);
    await loadVersionControl();
  }

  async function revertManagedCommit(commitSha) {
    const payload = await fetchAdmin("/api/admin/version/revert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ commit_sha: commitSha }),
    });
    setSectionStatus("version-status-line", `${UI.version_revert_done || ""}${String(payload.revert_commit_sha || "").slice(0, 8)}`);
    await loadVersionControl();
    setAdminMessage(`${UI.version_revert_done || ""}${String(payload.revert_commit_sha || "").slice(0, 8)}`);
  }

  async function autoStartBatchIngestFromQuery() {
    if (UI.section !== "kb") return;
    const params = new URLSearchParams(window.location.search);
    const batchId = String(params.get("ingest_batch") || "").trim();
    const autostart = String(params.get("autostart") || "").trim() === "1";
    if (!batchId || !autostart) return;
    const sessionKey = `sediment-autostart-batch:${batchId}`;
    if (window.sessionStorage.getItem(sessionKey)) return;
    window.sessionStorage.setItem(sessionKey, "1");
    try {
      const payload = await fetchAdmin("/api/admin/ingest/document", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ingest_batch_id: batchId }),
      });
      setWorkbenchStatus("ingest", `${UI.ingest_done || ""}${String(payload.job?.id || "").slice(0, 8)}`);
      setAdminMessage(`${UI.inbox_batch_redirected || ""}${batchId.slice(0, 8)}`);
      if (payload.job?.id) {
        await waitForManagedJob(payload.job.id, "ingest");
      }
    } finally {
      params.delete("autostart");
      const query = params.toString();
      window.history.replaceState({}, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
    }
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

  function openFileSwitchModal(targetName, options = {}) {
    state.pendingFileNavigation = {
      name: String(targetName || "").trim(),
      options,
    };
    const modal = document.getElementById("admin-file-switch-modal");
    const target = document.getElementById("admin-file-switch-target");
    if (target) target.textContent = String(options.targetLabel || targetName || "");
    if (modal) modal.hidden = false;
    document.getElementById("admin-file-switch-confirm")?.focus();
  }

  function closeFileSwitchModal() {
    const modal = document.getElementById("admin-file-switch-modal");
    if (modal) modal.hidden = true;
    state.pendingFileNavigation = null;
  }

  async function confirmFileSwitchModal() {
    const pending = state.pendingFileNavigation;
    closeFileSwitchModal();
    if (!pending?.name) return;
    await performOpenDocument(pending.name, pending.options || {});
  }

  function openFilePreviewModal() {
    if (!hasSelectedDocument()) return;
    updateEditorPreview(activeEditorContent());
    syncPreviewDocumentLabel();
    const modal = document.getElementById("admin-file-preview-modal");
    if (modal) modal.hidden = false;
    document.getElementById("admin-file-preview-close")?.focus();
  }

  function closeFilePreviewModal() {
    const modal = document.getElementById("admin-file-preview-modal");
    if (modal) modal.hidden = true;
  }

  function scrollEditorIntoView() {
    if (window.innerWidth > 960) return;
    document
      .getElementById("admin-file-editor-pane")
      ?.scrollIntoView({ block: "start", behavior: "auto" });
  }

  async function performOpenDocument(nameOverride, options = {}) {
    const name = String(nameOverride || "").trim();
    if (!name) {
      throw new Error(UI.doc_select_prompt || "");
    }
    const payload = await fetchAdmin(`/api/admin/entries/${encodeURIComponent(name)}`);
    state.selectedDocumentName = payload.name || name;
    state.selectedDocumentDetail = payload;
    state.fileLoadedContent = payload.content || "";
    const editor = document.getElementById("editor-content");
    if (editor) {
      editor.value = payload.content || "";
      editor.dataset.hash = payload.content_hash || "";
    }
    hideFileSuggestions();
    if (options.entryTab) setActiveFileEntryTab(options.entryTab, { persist: false });
    updateEditorPreview(payload.content || "");
    renderFileIndexTree();
    renderDocHealthList();
    renderDocumentMeta();
    renderLinkedIssues();
    syncFileEditorState();
    const statusLabel = options.reload ? UI.editor_reloaded || "" : UI.editor_loaded;
    document.getElementById("editor-status").textContent = `${statusLabel} ${payload.name} · hash=${String(payload.content_hash || "").slice(0, 12)}`;
    if (options.announce !== false) {
      setAdminMessage(
        options.reload
          ? `${statusLabel} ${payload.name}`
          : `${UI.doc_selected || UI.editor_loaded} ${payload.name}`
      );
    }
    if (options.focusConsoleSection) {
      focusFileConsoleSection(options.focusConsoleSection);
    } else if (options.scrollEditor !== false) {
      scrollEditorIntoView();
    }
    queuePersistAdminPageState();
    return payload;
  }

  async function requestOpenDocument(nameOverride, options = {}) {
    const name = String(nameOverride || "").trim();
    if (!name) {
      throw new Error(UI.doc_select_prompt || "");
    }
    if (name === state.selectedDocumentName) {
      if (options.entryTab) setActiveFileEntryTab(options.entryTab);
      if (options.focusConsoleSection) {
        focusFileConsoleSection(options.focusConsoleSection);
      } else if (options.scrollEditor !== false) {
        scrollEditorIntoView();
      }
      return;
    }
    if (state.fileDirty) {
      openFileSwitchModal(name, options);
      return;
    }
    await performOpenDocument(name, options);
  }

  async function saveEntry() {
    const name = String(state.selectedDocumentName || "").trim();
    if (!name) {
      throw new Error(UI.doc_select_prompt || "");
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
    state.fileLoadedContent = payload.content || "";
    document.getElementById("editor-status").textContent = `${UI.editor_saved}: ${payload.name}`;
    document.getElementById("editor-content").dataset.hash = payload.content_hash || "";
    updateEditorPreview(payload.content || "");
    renderDocHealthList();
    renderDocumentMeta();
    renderLinkedIssues();
    syncFileEditorState();
    setAdminMessage(`${UI.editor_saved} ${payload.name}`);
    if (UI.section === "files") {
      await loadFileManager();
    }
  }

  function resetEntry() {
    const name = String(state.selectedDocumentName || "").trim();
    if (!name) {
      throw new Error(UI.doc_select_prompt || "");
    }
    const editor = document.getElementById("editor-content");
    if (!editor) return;
    editor.value = state.fileLoadedContent || "";
    updateEditorPreview(editor.value || "");
    updateFileDirtyState({ persist: false });
    setSectionStatus("editor-status", UI.editor_reset || "");
    setAdminMessage(`${UI.editor_reset || ""} · ${name}`);
    editor.focus();
    queuePersistAdminPageState();
  }

  async function reloadEntry() {
    const name = String(state.selectedDocumentName || "").trim();
    if (!name) {
      throw new Error(UI.doc_select_prompt || "");
    }
    if (state.fileDirty) {
      openFileSwitchModal(name, {
        reload: true,
        scrollEditor: false,
        targetLabel: UI.editor_reload_target || "",
      });
      return;
    }
    await performOpenDocument(name, { reload: true, scrollEditor: false });
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
      node.textContent = UI.ingest_selection_empty || "";
      queuePersistAdminPageState();
      return;
    }
    const sample = files.slice(0, 3).map((file) => file.webkitRelativePath || file.name).join(" · ");
    const suffix = files.length > 3 ? ` +${files.length - 3}` : "";
    node.textContent = `${shellLabel("selectedPrefix", UI.ingest_selected_prefix || "")} ${files.length} ${shellLabel("selectedSuffix", UI.ingest_selected_suffix || "")} · ${sample}${suffix}`;
    queuePersistAdminPageState();
  }

  async function uploadAndIngest() {
    const files = currentIngestFiles();
    if (!files.length) throw new Error(UI.ingest_file_required);
    logWorkbenchRequest("ingest", `POST /api/admin/ingest/document · files=${files.length}`, {
      liveStatus: UI.live_running || "",
    });
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
    const uploadedItem = payload.item || payload.submission || null;
    completeWorkbenchAction(
      "ingest",
      `${UI.ingest_uploaded}${(payload.job?.id || "").slice(0, 8)} · ${UI.ingest_item_prefix || UI.ingest_submission_prefix || ""} ${(uploadedItem?.id || "").slice(0, 8)}`,
      {
        liveStatus: UI.ingest_uploaded,
        adminMessage: `${UI.ingest_uploaded}${(payload.job?.id || "").slice(0, 8)}`,
      }
    );
    state.ingestFiles = [];
    if (document.getElementById("admin-ingest-file")) document.getElementById("admin-ingest-file").value = "";
    if (document.getElementById("admin-ingest-folder")) document.getElementById("admin-ingest-folder").value = "";
    syncFilePickerState?.("admin-ingest-file");
    syncFilePickerState?.("admin-ingest-folder");
    updateIngestSelection();
    if (payload.job?.id) {
      await waitForManagedJob(payload.job.id, "ingest");
    }
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
    clearSessionStatePrefix?.(ADMIN_SESSION_PREFIX);
    setAdminMessage(UI.logout_done);
    window.location.href = "/admin/overview";
  }

  async function refreshCurrentPage() {
    if (UI.section === "overview") {
      await Promise.all([loadOverview(), loadIssues(), loadAuditLogs()]);
      return;
    }
    if (UI.section === "kb") {
      await Promise.all([loadInsights(), loadAdminGraph()]);
      return;
    }
    if (UI.section === "files") {
      await Promise.all([loadFileManager()]);
      return;
    }
    if (UI.section === "reviews" || UI.section === "inbox") {
      await Promise.all([loadInbox()]);
      return;
    }
    if (UI.section === "version_control") {
      await Promise.all([loadVersionControl()]);
      return;
    }
    if (UI.section === "reviews_legacy") {
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
    node.addEventListener("click", (event) => handler(event).catch(createErrorHandler()));
  }

  ["inbox-open-feedback-list", "inbox-staged-documents-list", "inbox-ready-documents-list", "inbox-history-list"].forEach((containerId) => {
    bindClick(containerId, async (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      const itemId = button.dataset.itemId || "";
      const version = Number(button.dataset.version || 0);
      if (button.dataset.action === "resolve-feedback") {
        await withBusyButton(button, UI.busy_loading, () => resolveFeedback(itemId, version));
        return;
      }
      if (button.dataset.action === "reopen-feedback") {
        await withBusyButton(button, UI.busy_loading, () => reopenFeedback(itemId, version));
        return;
      }
      if (button.dataset.action === "mark-ready") {
        await withBusyButton(button, UI.busy_loading, () => markReady(itemId, version));
        return;
      }
      if (button.dataset.action === "move-to-staged") {
        await withBusyButton(button, UI.busy_loading, () => moveToStaged(itemId, version));
        return;
      }
      if (button.dataset.action === "remove-document") {
        await withBusyButton(button, UI.busy_loading, () => removeDocument(itemId, version));
        return;
      }
      if (button.dataset.action === "download-document") {
        downloadDocument(itemId);
      }
    });
  });

  bindClick("review-list", async (event) => {
    const button = event.target.closest("button[data-action='select-review']");
    if (!button) return;
    await withBusyButton(button, UI.busy_loading, () => selectReview(button.dataset.reviewId || ""));
  });

  bindClick("version-commits-list", async (event) => {
    const button = event.target.closest("button[data-action='revert-commit']");
    if (!button) return;
    await withBusyButton(button, UI.busy_loading, () => revertManagedCommit(button.dataset.commitSha || ""));
  });

  bindClick("admin-kb-result", async (event) => {
    const button = event.target.closest("button[data-action='revert-job-commit']");
    if (!button) return;
    await withBusyButton(button, UI.busy_loading, async () => {
      await revertManagedCommit(button.dataset.commitSha || "");
      setRuntimeResultStatus(UI.version_revert_done || "");
    });
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

  bindClick("admin-insights-list", async (event) => {
    const button = event.target.closest('[data-action="select-insight"]');
    if (!button) return;
    await withBusyButton(button, UI.busy_loading, () => selectInsight(button.dataset.insightId || ""));
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
    const button = event.target.closest('[data-action="open-document"]');
    if (!button) return;
    await withBusyButton(button, UI.busy_loading, () =>
      requestOpenDocument(button.dataset.name || "", {
        entryTab: button.dataset.sourceTab || "index",
      })
    );
  });

  bindClick("admin-doc-health-list", async (event) => {
    const button = event.target.closest('[data-action="open-document"]');
    if (!button) return;
    await withBusyButton(button, UI.busy_loading, () =>
      requestOpenDocument(button.dataset.name || "", {
        entryTab: button.dataset.sourceTab || "health",
        focusConsoleSection: button.dataset.focusConsoleSection || "issues",
      })
    );
  });

  bindClick("admin-file-suggestions", async (event) => {
    const button = event.target.closest('[data-action="open-document"]');
    if (!button) return;
    await withBusyButton(button, UI.busy_loading, () => requestOpenDocument(button.dataset.name || ""));
  });

  document.getElementById("admin-logout-button")?.addEventListener("click", () => logout().catch(showAdminError));
  document.querySelector('[data-testid="admin-kb-pane-tabs"]')?.addEventListener("click", (event) => {
    const button = event.target.closest('[data-action="switch-kb-pane"]');
    if (!button) return;
    setActiveKbPane(button.dataset.pane || "operations");
  });
  document.querySelector('[data-testid="admin-insight-actions"]')?.addEventListener("click", (event) => {
    const button = event.target.closest('[data-action="review-insight"]');
    if (!button) return;
    withBusyButton(button, UI.busy_queue, () => reviewInsight(button.dataset.reviewAction || "")).catch(
      createErrorHandler({ statusIds: ["admin-insight-status"] })
    );
  });
  document.getElementById("admin-explore-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("admin-explore-button"), UI.busy_loading, runExplore).catch((error) => {
      renderExploreFailure(error && error.message ? error.message : String(error || ""));
      showAdminError(error, workbenchErrorOptions("explore"));
    })
  );
  document.getElementById("manual-tidy-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("manual-tidy-button"), UI.busy_queue, runManualTidy).catch(
      createErrorHandler(workbenchErrorOptions("tidy"))
    )
  );
  document.getElementById("save-entry-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("save-entry-button"), UI.busy_saving, saveEntry).catch(
      createErrorHandler({ statusIds: ["editor-status"] })
    )
  );
  document.getElementById("reset-entry-button")?.addEventListener("click", () => {
    try {
      resetEntry();
    } catch (error) {
      createErrorHandler({ statusIds: ["editor-status"] })(error);
    }
  });
  document.getElementById("reload-entry-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("reload-entry-button"), UI.busy_loading, reloadEntry).catch(
      createErrorHandler({ statusIds: ["editor-status"] })
    )
  );
  document.getElementById("admin-file-preview-button")?.addEventListener("click", openFilePreviewModal);
  document.getElementById("create-user-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("create-user-button"), UI.busy_saving, createUser).catch(showAdminError)
  );
  document.getElementById("inbox-create-batch-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("inbox-create-batch-button"), UI.busy_queue, createIngestBatch).catch(showAdminError)
  );
  document.getElementById("approve-review-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("approve-review-button"), UI.busy_approve, async () => {
      if (!state.selectedReviewId) throw new Error(UI.review_select_prompt || "");
      await approveReview(state.selectedReviewId);
    }).catch(showAdminError)
  );
  document.getElementById("reject-review-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("reject-review-button"), UI.busy_reject, async () => {
      if (!state.selectedReviewId) throw new Error(UI.review_select_prompt || "");
      await rejectReview(state.selectedReviewId);
    }).catch(showAdminError)
  );
  document.getElementById("admin-quartz-build-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("admin-quartz-build-button"), UI.busy_queue, runQuartzBuild).catch(showAdminError)
  );
  document.getElementById("admin-ingest-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("admin-ingest-button"), UI.busy_queue, uploadAndIngest).catch(
      createErrorHandler(workbenchErrorOptions("ingest"))
    )
  );
  document.getElementById("settings-reload-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("settings-reload-button"), UI.busy_loading, reloadSettingsFromDisk).catch(
      createErrorHandler({ statusIds: ["settings-status"] })
    )
  );
  document.getElementById("version-commit-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("version-commit-button"), UI.busy_saving, commitTrackedChanges).catch(showAdminError)
  );
  document.getElementById("version-push-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("version-push-button"), UI.busy_loading, pushTrackedBranch).catch(showAdminError)
  );
  document.getElementById("settings-save-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("settings-save-button"), UI.busy_saving, saveSettingsConfig).catch(
      createErrorHandler({ statusIds: ["settings-status"] })
    )
  );
  document.getElementById("settings-restart-button")?.addEventListener("click", () =>
    withBusyButton(document.getElementById("settings-restart-button"), UI.busy_loading, restartSettingsService).catch(
      createErrorHandler({ statusIds: ["settings-status"] })
    )
  );
  document.getElementById("admin-kb-live-clear")?.addEventListener("click", clearLiveLog);
  document.getElementById("editor-content")?.addEventListener("input", (event) => {
    updateEditorPreview(event.target.value || "");
    updateFileDirtyState({ persist: false });
    queuePersistAdminPageState();
  });
  document.getElementById("admin-file-entry-tabs")?.addEventListener("click", (event) => {
    const button = event.target.closest('[data-tab-group="file-entry"]');
    if (!button) return;
    setActiveFileEntryTab(button.dataset.tab || "index");
  });
  document.getElementById("admin-file-console-tabs")?.addEventListener("click", (event) => {
    const button = event.target.closest('[data-console-tab]');
    if (!button) return;
    setActiveFileConsoleTab(button.dataset.consoleTab || "meta");
  });
  document.getElementById("tidy-reason")?.addEventListener("input", queuePersistAdminPageState);
  document.getElementById("admin-explore-input")?.addEventListener("input", queuePersistAdminPageState);
  document.getElementById("settings-raw-text")?.addEventListener("input", queuePersistAdminPageState);
  document.getElementById("admin-file-search")?.addEventListener("input", () => {
    queuePersistAdminPageState();
    updateFileSuggestions().catch(createErrorHandler({ statusIds: ["admin-file-search-status"] }));
  });
  document.getElementById("admin-file-search")?.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      hideFileSuggestions();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveActiveFileSuggestion(1);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      moveActiveFileSuggestion(-1);
      return;
    }
    if (event.key !== "Enter") return;
    event.preventDefault();
    const selected = activeFileSuggestion();
    if (selected) {
      requestOpenDocument(selected.name).catch(createErrorHandler({ statusIds: ["editor-status"] }));
    }
  });
  document.getElementById("admin-file-search")?.addEventListener("blur", () => {
    window.setTimeout(() => hideFileSuggestions(), 120);
  });
  document.getElementById("admin-file-search")?.addEventListener("focus", () => {
    if (state.fileSuggestions.length) {
      renderFileSuggestions(state.fileSuggestions, { preserveSelection: true });
    }
  });
  document.addEventListener("click", (event) => {
    const root = document.querySelector('#admin-file-source-pane [data-search-popover-root]');
    if (!root || root.contains(event.target)) return;
    hideFileSuggestions();
  });
  document.getElementById("admin-file-switch-cancel")?.addEventListener("click", closeFileSwitchModal);
  document.getElementById("admin-file-switch-confirm")?.addEventListener("click", () => {
    confirmFileSwitchModal().catch(createErrorHandler({ statusIds: ["editor-status"] }));
  });
  document.getElementById("admin-file-preview-close")?.addEventListener("click", closeFilePreviewModal);
  document.getElementById("admin-file-preview-modal")?.addEventListener("click", (event) => {
    if (event.target?.id === "admin-file-preview-modal") closeFilePreviewModal();
  });
  document.getElementById("admin-file-switch-modal")?.addEventListener("click", (event) => {
    if (event.target?.id === "admin-file-switch-modal") closeFileSwitchModal();
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
      syncFilePickerState?.("admin-ingest-file");
      syncFilePickerState?.("admin-ingest-folder");
      updateIngestSelection();
    });
  }

  window.addEventListener("pagehide", persistAdminPageState);
  window.addEventListener("beforeunload", (event) => {
    if (!state.fileDirty) return;
    event.preventDefault();
    event.returnValue = UI.file_exit_warning || "";
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !document.getElementById("admin-file-preview-modal")?.hidden) {
      closeFilePreviewModal();
      return;
    }
    if (event.key === "Escape" && !document.getElementById("admin-file-switch-modal")?.hidden) {
      closeFileSwitchModal();
      return;
    }
    if (!(event.metaKey || event.ctrlKey) || String(event.key).toLowerCase() !== "s") return;
    if (UI.section !== "files" || !hasSelectedDocument()) return;
    event.preventDefault();
    withBusyButton(document.getElementById("save-entry-button"), UI.busy_saving, saveEntry).catch(
      createErrorHandler({ statusIds: ["editor-status"] })
    );
  });

  if (UI.section === "kb") {
    setActiveKbPane(state.kbPane, { persist: false });
  }

  refreshCurrentPage()
    .then(async () => {
      const restored = await restoreAdminPageState();
      await autoStartBatchIngestFromQuery();
      updateIngestSelection();
      syncFileEditorState();
      updateEditorPreview(document.getElementById("editor-content")?.value || "");
      if (!restored) {
        setAdminMessage(UI.admin_ready || "");
      } else {
        queuePersistAdminPageState();
      }
    })
    .catch(createErrorHandler());
})();
