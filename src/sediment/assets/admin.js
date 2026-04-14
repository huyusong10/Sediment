(function () {
  const shell = window.SedimentShell;
  const pageData = shell.readJsonScript("sediment-page-data") || {};
  const UI = pageData.ui || {};
  const INITIAL_QUARTZ = pageData.quartz || {};
  const { escapeHtml, fetchJson, renderMarkdown } = shell;

  function setAdminMessage(message) {
    document.getElementById("admin-message").textContent = message;
  }

  async function withBusyButton(button, busyLabel, task) {
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

  function renderStats(overview) {
    const stats = [
      [UI.stats_pending, overview.submission_counts.pending || 0],
      [UI.stats_draft, overview.submission_counts.draft_ready || 0],
      [UI.stats_queue, overview.queued_jobs || 0],
      [UI.stats_running, overview.running_jobs || 0],
      [UI.stats_cancel, overview.cancel_requested_jobs || 0],
      [UI.stats_stale, overview.stale_jobs || 0],
      [UI.stats_reviews, overview.pending_reviews || 0],
      [UI.stats_blocking, overview.severity_counts.blocking || 0],
    ];
    const node = document.getElementById("admin-stats");
    if (!node) return;
    node.innerHTML = stats
      .map(
        ([label, value]) => `<div class="stat"><strong>${value}</strong><span>${label}</span></div>`
      )
      .join("");

    const severityNode = document.getElementById("severity-bars");
    if (!severityNode) return;
    const total =
      Object.values(overview.severity_counts || {}).reduce((sum, value) => sum + value, 0) || 1;
    const severityOrder = ["blocking", "high", "medium", "low"];
    severityNode.innerHTML = severityOrder
      .map((level) => {
        const count = overview.severity_counts[level] || 0;
        const width = Math.round((count / total) * 100);
        return `
          <div class="severity-item">
            <div class="row spread"><strong>${escapeHtml(level)}</strong><span>${count}</span></div>
            <div class="bar"><span style="width:${width}%;"></span></div>
          </div>
        `;
      })
      .join("");
  }

  function renderSubmissionAnalysis(analysis) {
    if (!analysis) return "";
    const related =
      Array.isArray(analysis.related_entries) && analysis.related_entries.length
        ? analysis.related_entries
            .slice(0, 3)
            .map((item) => escapeHtml(item.name))
            .join(" · ")
        : "-";
    return `
      <div class="subtle" style="margin-top:8px;">${escapeHtml(UI.submitted_advice)}: ${escapeHtml(
        analysis.recommended_type || "-"
      )} · ${escapeHtml(analysis.duplicate_risk || "-")} · ${escapeHtml(
        analysis.committer_action || "-"
      )}</div>
      <div class="subtle">${escapeHtml(analysis.summary || "")}</div>
      <div class="subtle">${escapeHtml(UI.submitted_related)}: ${related}</div>
    `;
  }

  function renderQuartzStatus(payload) {
    const node = document.getElementById("quartz-status");
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
          <span class="tag ${payload.site_available ? "ok" : payload.runtime_available ? "warn" : "danger"}">${escapeHtml(
            statusLabel
          )}</span>
        </div>
        <div class="subtle">${escapeHtml(UI.quartz_runtime_path)}: ${escapeHtml(payload.runtime_path)}</div>
        <div class="subtle">${escapeHtml(UI.quartz_site_path)}: ${escapeHtml(payload.site_path)}</div>
        <div class="subtle">${escapeHtml(UI.quartz_built_at)}: ${
          payload.site_last_built_at
            ? new Date(payload.site_last_built_at * 1000).toLocaleString()
            : "-"
        }</div>
      </div>
    `;
  }

  async function loadOverview() {
    const overview = await fetchAdmin("/api/admin/overview");
    renderStats(overview);
  }

  async function loadSystemStatus() {
    const payload = await fetchAdmin("/api/admin/system/status");
    const node = document.getElementById("system-status");
    if (!node) return;
    const bytesMb = (payload.limits.max_upload_bytes / (1024 * 1024)).toFixed(1);
    node.innerHTML = `
      <div class="card">
        <div class="row spread"><strong>${escapeHtml(UI.system_runtime)}</strong><span class="tag">${escapeHtml(
          payload.worker_mode
        )}</span></div>
        <div class="subtle">${escapeHtml(UI.system_auth)}: ${
          payload.auth_required ? UI.system_enabled : UI.system_disabled
        }</div>
        <div class="subtle">${escapeHtml(UI.system_proxy)}: ${
          payload.proxy.trust_proxy_headers ? UI.system_enabled : UI.system_disabled
        }</div>
        <div class="subtle">${escapeHtml(UI.system_rate)}: ${payload.limits.submission_rate_limit_count} / ${
          payload.limits.submission_rate_limit_window_seconds
        }s</div>
        <div class="subtle">${escapeHtml(UI.system_text_limit)}: ${payload.limits.max_text_submission_chars}</div>
        <div class="subtle">${escapeHtml(UI.system_upload_limit)}: ${bytesMb} MiB</div>
        <div class="subtle">${escapeHtml(UI.system_retry_limit)}: ${payload.limits.job_max_attempts}</div>
        <div class="subtle">${escapeHtml(UI.system_stale_limit)}: ${payload.limits.job_stale_after_seconds}s</div>
        <div class="subtle">${escapeHtml(UI.system_portal)}: <a href="${payload.urls.portal}" target="_blank" rel="noreferrer">${escapeHtml(
          payload.urls.portal
        )}</a></div>
        <div class="subtle">${escapeHtml(UI.system_admin)}: <a href="${payload.urls.admin}" target="_blank" rel="noreferrer">${escapeHtml(
          payload.urls.admin
        )}</a></div>
        <div class="subtle">${escapeHtml(UI.system_instance)}: ${escapeHtml(payload.instance.name)}</div>
      </div>
    `;
  }

  async function loadIssues() {
    const payload = await fetchAdmin("/api/admin/health/issues");
    const node = document.getElementById("issue-list");
    if (!node) return;
    node.innerHTML = payload.issues.length
      ? payload.issues
          .slice(0, UI.section === "overview" ? 8 : 20)
          .map(
            (item) => `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(item.target)}</strong>
                <span class="tag ${
                  item.severity === "blocking" || item.severity === "high"
                    ? "danger"
                    : item.severity === "medium"
                      ? "warn"
                      : "ok"
                }">${escapeHtml(item.severity)}</span>
              </div>
              <div class="subtle">${escapeHtml(item.summary)}</div>
              <div class="row" style="margin-top:10px;">
                <button data-action="run-tidy" data-target="${encodeURIComponent(
                  item.target
                )}" data-issue-type="${encodeURIComponent(item.type || "")}">${escapeHtml(
                  UI.run_tidy
                )}</button>
              </div>
            </div>
          `
          )
          .join("")
      : `<div class="empty">${escapeHtml(UI.issue_empty)}</div>`;
  }

  async function loadSubmissions() {
    const payload = await fetchAdmin("/api/admin/submissions");
    const node = document.getElementById("submission-list");
    if (!node) return;
    node.innerHTML = payload.submissions.length
      ? payload.submissions
          .map(
            (item) => `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(item.title)}</strong>
                <span class="tag">${escapeHtml(item.status)}</span>
              </div>
              <div class="subtle">${escapeHtml(item.submitter_name)} · ${escapeHtml(
                item.submission_type
              )} · ${escapeHtml(item.created_at || "")}</div>
              ${renderSubmissionAnalysis(item.analysis)}
              <div class="row" style="margin-top:10px;">
                <button data-action="triage-submission" data-submission-id="${item.id}" data-status="triaged">${escapeHtml(
                  UI.triaged
                )}</button>
                <button data-action="triage-submission" data-submission-id="${item.id}" data-status="rejected">${escapeHtml(
                  UI.reject
                )}</button>
                <button class="primary" data-action="run-ingest" data-submission-id="${item.id}">${escapeHtml(
                  UI.run_ingest
                )}</button>
              </div>
            </div>
          `
          )
          .join("")
      : `<div class="empty">${escapeHtml(UI.submission_empty)}</div>`;
  }

  async function loadReviews() {
    const payload = await fetchAdmin("/api/admin/reviews?decision=pending");
    const node = document.getElementById("review-list");
    if (!node) return;
    node.innerHTML = payload.reviews.length
      ? payload.reviews
          .map(
            (item) => `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(item.job.job_type)} · ${escapeHtml(item.job.id.slice(0, 8))}</strong>
                <span class="tag">${escapeHtml(item.decision)}</span>
              </div>
              <div class="subtle">${escapeHtml(item.job.result_payload?.summary || "")}</div>
              <div class="row" style="margin-top:10px;">
                <button data-action="show-diff" data-review-id="${item.id}">${escapeHtml(
                  UI.show_diff
                )}</button>
                <button class="primary" data-action="approve-review" data-review-id="${item.id}">${escapeHtml(
                  UI.approve
                )}</button>
                <button data-action="reject-review" data-review-id="${item.id}">${escapeHtml(
                  UI.reject_review
                )}</button>
              </div>
            </div>
          `
          )
          .join("")
      : `<div class="empty">${escapeHtml(UI.review_empty)}</div>`;
  }

  async function loadJobs() {
    const payload = await fetchAdmin("/api/admin/jobs");
    const node = document.getElementById("job-list");
    if (!node) return;
    node.innerHTML = payload.jobs.length
      ? payload.jobs
          .map(
            (item) => `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(item.job_type)} · ${escapeHtml(item.id.slice(0, 8))}</strong>
                <span class="tag">${escapeHtml(item.status)}</span>
              </div>
              <div class="subtle">${escapeHtml(
                item.error_message || item.result_payload?.summary || ""
              )}</div>
              <div class="subtle">${item.attempt_count || 0} / ${item.max_attempts || 0}</div>
              <div class="row" style="margin-top:10px;">
                ${
                  ["failed", "cancelled"].includes(item.status)
                    ? `<button data-action="retry-job" data-job-id="${item.id}">${escapeHtml(
                        UI.retry
                      )}</button>`
                    : ""
                }
                ${
                  ["queued", "running", "awaiting_review"].includes(item.status)
                    ? `<button data-action="cancel-job" data-job-id="${item.id}">${escapeHtml(
                        UI.cancel
                      )}</button>`
                    : ""
                }
              </div>
            </div>
          `
          )
          .join("")
      : `<div class="empty">${escapeHtml(UI.job_empty)}</div>`;
  }

  async function loadAuditLogs() {
    const payload = await fetchAdmin("/api/admin/audit?limit=12");
    const node = document.getElementById("audit-log-list");
    if (!node) return;
    node.innerHTML = payload.logs.length
      ? payload.logs
          .map(
            (item) => `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(item.action)}</strong>
                <span class="tag">${escapeHtml(item.actor_role)}</span>
              </div>
              <div class="subtle">${escapeHtml(item.actor_name)} · ${escapeHtml(
                item.target_type
              )} · ${escapeHtml(item.created_at)}</div>
              <div class="subtle">${escapeHtml(JSON.stringify(item.details || {}))}</div>
            </div>
          `
          )
          .join("")
      : `<div class="empty">${escapeHtml(UI.audit_empty)}</div>`;
  }

  async function loadQuartzStatus() {
    const payload = await fetchAdmin("/api/admin/quartz/status");
    renderQuartzStatus(payload);
  }

  async function runQuartzBuild() {
    const payload = await fetchAdmin("/api/admin/quartz/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor_name: "admin-web" }),
    });
    renderQuartzStatus(payload);
    setAdminMessage(`${UI.quartz_build_success} ${UI.quartz_cta}`);
  }

  async function runExplore() {
    const question = document.getElementById("admin-explore-input").value.trim();
    const payload = await fetchAdmin("/api/admin/explore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const node = document.getElementById("admin-explore-result");
    node.innerHTML = `
      <div class="card">
        <div class="row spread">
          <strong>${escapeHtml(UI.explore_answer)}</strong>
          <span class="tag">${escapeHtml(payload.confidence || UI.unknown)}</span>
        </div>
        <div class="subtle">${escapeHtml(UI.explore_confidence)}: ${escapeHtml(
          payload.confidence || UI.unknown
        )}</div>
        <div class="markdown">${renderMarkdown(payload.answer || "")}</div>
        <div class="subtle">${escapeHtml(UI.explore_sources)}: ${escapeHtml(
          (payload.sources || []).join(", ") || "-"
        )}</div>
        <div class="subtle">${escapeHtml(UI.explore_gaps)}: ${escapeHtml(
          (payload.gaps || []).join(" | ") || "-"
        )}</div>
      </div>
    `;
    setAdminMessage((payload.answer || "").slice(0, 140));
  }

  async function triageSubmission(id, status) {
    await fetchAdmin(`/api/admin/submissions/${id}/triage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, actor_name: "admin-web" }),
    });
    setAdminMessage(`${UI.triage_done} ${status} · ${id.slice(0, 8)}`);
    await refreshCurrentPage();
  }

  async function runIngest(id) {
    const job = await fetchAdmin(`/api/admin/submissions/${id}/run-ingest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor_name: "admin-web" }),
    });
    setAdminMessage(`${UI.ingest_done}${job.id.slice(0, 8)}`);
    await refreshCurrentPage();
  }

  async function runTidy(issue) {
    const job = await fetchAdmin("/api/admin/tidy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ issue, actor_name: "admin-web" }),
    });
    setAdminMessage(`${UI.tidy_done}${job.id.slice(0, 8)}`);
    await refreshCurrentPage();
  }

  async function showDiff(reviewId) {
    const payload = await fetchAdmin(`/api/admin/reviews/${reviewId}`);
    const operations = payload.job.result_payload?.operations || [];
    const diffNode = document.getElementById("diff-view");
    if (diffNode) {
      diffNode.textContent = operations.length
        ? operations.map((item) => item.diff).join("\n\n")
        : UI.diff_empty;
    }
    setAdminMessage(`${UI.review_loaded}${reviewId.slice(0, 8)}`);
  }

  async function approveReview(reviewId) {
    await fetchAdmin(`/api/admin/reviews/${reviewId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer_name: "admin-web", comment: "Approved from admin UI" }),
    });
    setAdminMessage(`${UI.review_approved}${reviewId.slice(0, 8)}`);
    await refreshCurrentPage();
  }

  async function rejectReview(reviewId) {
    await fetchAdmin(`/api/admin/reviews/${reviewId}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer_name: "admin-web", comment: "Rejected from admin UI" }),
    });
    setAdminMessage(`${UI.review_rejected}${reviewId.slice(0, 8)}`);
    await refreshCurrentPage();
  }

  async function retryJob(jobId) {
    await fetchAdmin(`/api/admin/jobs/${jobId}/retry`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor_name: "admin-web" }),
    });
    setAdminMessage(`${UI.job_retried}${jobId.slice(0, 8)}`);
    await refreshCurrentPage();
  }

  async function cancelJob(jobId) {
    await fetchAdmin(`/api/admin/jobs/${jobId}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor_name: "admin-web", reason: "Cancelled from admin UI" }),
    });
    setAdminMessage(`${UI.job_cancelled}${jobId.slice(0, 8)}`);
    await refreshCurrentPage();
  }

  async function loadEntryForEdit() {
    const name = document.getElementById("editor-name").value.trim();
    const payload = await fetchAdmin(`/api/admin/entries/${encodeURIComponent(name)}`);
    document.getElementById("editor-content").value = payload.content;
    document.getElementById("editor-content").dataset.hash = payload.content_hash;
    document.getElementById(
      "editor-status"
    ).textContent = `${UI.editor_loaded} ${payload.name} · hash=${payload.content_hash.slice(0, 12)}`;
    setAdminMessage(`${UI.editor_loaded} ${payload.name}`);
  }

  async function saveEntry() {
    const name = document.getElementById("editor-name").value.trim();
    const content = document.getElementById("editor-content").value;
    const expectedHash = document.getElementById("editor-content").dataset.hash || null;
    const payload = await fetchAdmin(`/api/admin/entries/${encodeURIComponent(name)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, expected_hash: expectedHash, actor_name: "admin-web" }),
    });
    document.getElementById("editor-status").textContent = `${UI.editor_saved}：${payload.name}`;
    document.getElementById("editor-content").dataset.hash = payload.content_hash;
    setAdminMessage(`${UI.editor_saved} ${payload.name}`);
  }

  async function runManualTidy() {
    const target = document.getElementById("manual-tidy-target").value.trim();
    if (!target) throw new Error(UI.manual_tidy_target_required);
    await runTidy({ target, type: "manual_tidy_request" });
  }

  async function refreshCurrentPage() {
    const tasks = [loadQuartzStatus(), loadSystemStatus()];
    if (UI.section === "overview") {
      tasks.push(loadOverview(), loadIssues(), loadAuditLogs());
    }
    if (UI.section === "kb") {
      tasks.push(loadSubmissions(), loadIssues());
    }
    if (UI.section === "reviews") {
      tasks.push(loadReviews(), loadJobs(), loadAuditLogs());
    }
    await Promise.all(tasks);
  }

  function showAdminError(error) {
    const diffNode = document.getElementById("diff-view");
    if (diffNode) diffNode.textContent = error.message;
    const exploreNode = document.getElementById("admin-explore-result");
    if (exploreNode && UI.section === "kb") exploreNode.textContent = error.message;
    setAdminMessage(error.message);
  }

  function bindClick(containerId, handler) {
    const node = document.getElementById(containerId);
    if (!node) return;
    node.addEventListener("click", (event) => handler(event).catch(showAdminError));
  }

  bindClick("issue-list", async (event) => {
    const button = event.target.closest('button[data-action="run-tidy"]');
    if (!button) return;
    const issue = {
      target: decodeURIComponent(button.dataset.target),
      type: button.dataset.issueType ? decodeURIComponent(button.dataset.issueType) : null,
    };
    await withBusyButton(button, UI.busy_queue, () => runTidy(issue));
  });

  bindClick("submission-list", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.dataset.action === "triage-submission") {
      await withBusyButton(button, UI.busy_loading, () =>
        triageSubmission(button.dataset.submissionId, button.dataset.status)
      );
    }
    if (button.dataset.action === "run-ingest") {
      await withBusyButton(button, UI.busy_queue, () => runIngest(button.dataset.submissionId));
    }
  });

  bindClick("review-list", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.dataset.action === "show-diff") {
      await withBusyButton(button, UI.busy_loading, () => showDiff(button.dataset.reviewId));
    }
    if (button.dataset.action === "approve-review") {
      await withBusyButton(button, UI.busy_approve, () => approveReview(button.dataset.reviewId));
    }
    if (button.dataset.action === "reject-review") {
      await withBusyButton(button, UI.busy_reject, () => rejectReview(button.dataset.reviewId));
    }
  });

  bindClick("job-list", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.dataset.action === "retry-job") {
      await withBusyButton(button, UI.busy_loading, () => retryJob(button.dataset.jobId));
    }
    if (button.dataset.action === "cancel-job") {
      await withBusyButton(button, UI.busy_loading, () => cancelJob(button.dataset.jobId));
    }
  });

  const refreshButton = document.getElementById("refresh-admin");
  if (refreshButton) {
    refreshButton.addEventListener("click", (event) =>
      withBusyButton(event.currentTarget, UI.refresh_busy, refreshCurrentPage).catch(showAdminError)
    );
  }

  const loadEntryButton = document.getElementById("load-entry-button");
  if (loadEntryButton) {
    loadEntryButton.addEventListener("click", (event) =>
      withBusyButton(event.currentTarget, UI.busy_loading, loadEntryForEdit).catch(showAdminError)
    );
  }
  const saveEntryButton = document.getElementById("save-entry-button");
  if (saveEntryButton) {
    saveEntryButton.addEventListener("click", (event) =>
      withBusyButton(event.currentTarget, UI.busy_saving, saveEntry).catch(showAdminError)
    );
  }
  const exploreButton = document.getElementById("admin-explore-button");
  if (exploreButton) {
    exploreButton.addEventListener("click", (event) =>
      withBusyButton(event.currentTarget, UI.busy_loading, runExplore).catch(showAdminError)
    );
  }
  const quartzButton = document.getElementById("admin-quartz-build-button");
  if (quartzButton) {
    quartzButton.addEventListener("click", (event) =>
      withBusyButton(event.currentTarget, UI.busy_loading, runQuartzBuild).catch(showAdminError)
    );
  }
  const manualTidyButton = document.getElementById("manual-tidy-button");
  if (manualTidyButton) {
    manualTidyButton.addEventListener("click", (event) =>
      withBusyButton(event.currentTarget, UI.busy_queue, runManualTidy).catch(showAdminError)
    );
  }

  renderQuartzStatus(INITIAL_QUARTZ);
  refreshCurrentPage().catch(showAdminError);
  setInterval(() => refreshCurrentPage().catch(showAdminError), 20000);
})();
