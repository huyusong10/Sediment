(function () {
  const shell = window.SedimentShell;
  const UI = shell.readJsonScript("sediment-page-data") || {};
  const { escapeHtml, fetchJson, renderMarkdown } = shell;

  function setPortalMessage(message) {
    document.getElementById("portal-message").textContent = message;
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
    const payload = await fetchJson("/api/portal/home");
    const stats = [
      [UI.formal_entries, payload.counts.formal_entries],
      [UI.placeholders, payload.counts.placeholders],
      [UI.indexes, payload.counts.indexes],
      [UI.pending, payload.counts.pending_submissions],
      [UI.health, payload.counts.health_issues],
    ];
    document.getElementById("portal-stats").innerHTML = stats
      .map(
        ([label, value]) => `
        <div class="stat">
          <strong>${value}</strong>
          <span>${label}</span>
        </div>
      `
      )
      .join("");

    document.getElementById("recent-updates").innerHTML = payload.recent_updates.length
      ? payload.recent_updates
          .map(
            (item) => `
            <div class="card interactive" data-entry-name="${encodeURIComponent(item.name)}">
              <div class="row spread">
                <strong>${escapeHtml(item.name)}</strong>
                <span class="tag">${escapeHtml(item.entry_type)}</span>
              </div>
            </div>`
          )
          .join("")
      : `<div class="empty">${escapeHtml(UI.updates_empty)}</div>`;
  }

  async function openEntry(encodedName) {
    const payload = await fetchJson(`/api/portal/entries/${encodedName}`);
    document.getElementById("entry-modal-title").textContent = payload.name;
    document.getElementById("entry-view").innerHTML = `
      <div class="row spread">
        <h3>${escapeHtml(payload.name)}</h3>
        <span class="tag ${payload.metadata.status === "fact" ? "ok" : "warn"}">${escapeHtml(
          payload.metadata.status || payload.metadata.kind
        )}</span>
      </div>
      ${renderMarkdown(payload.content)}
    `;
    document.getElementById("entry-modal").hidden = false;
    setPortalMessage(`${UI.opened}${payload.name}`);
  }

  async function runSearch() {
    const query = document.getElementById("search-input").value.trim();
    if (!query) {
      document.getElementById("search-status").textContent = UI.search_prompt;
      document.getElementById(
        "search-results"
      ).innerHTML = `<div class="empty">${escapeHtml(UI.search_empty)}</div>`;
      return;
    }
    const results = await fetchJson(`/api/portal/search?q=${encodeURIComponent(query)}`);
    document.getElementById("search-status").textContent = `${UI.found_prefix} ${results.length} ${UI.found_suffix}`;
    document.getElementById("search-results").innerHTML = results.length
      ? results
          .map(
            (item) => `
            <div class="card interactive" data-entry-name="${encodeURIComponent(item.name)}">
              <div class="row spread">
                <strong>${escapeHtml(item.name)}</strong>
                <span class="tag">${escapeHtml(item.entry_type)}</span>
              </div>
              <div class="subtle">${escapeHtml(item.snippet || item.summary || "")}</div>
            </div>`
          )
          .join("")
      : `<div class="empty">${escapeHtml(UI.search_empty)}</div>`;
  }

  async function submitText() {
    const payload = {
      title: document.getElementById("submit-title").value,
      content: document.getElementById("submit-content").value,
      submitter_name: document.getElementById("submit-name").value,
      submission_type: document.getElementById("submit-type").value,
    };
    const result = await fetchJson("/api/portal/submissions/text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    document.getElementById("submit-text-status").textContent = `${UI.submit_text_success}${result.id}`;
    document.getElementById("submit-text-analysis").innerHTML = renderSubmissionAnalysis(
      result.analysis
    );
    document.getElementById("submit-title").value = "";
    document.getElementById("submit-content").value = "";
    setPortalMessage(`${UI.submitted_text_prefix}${result.title}`);
    await loadHome();
  }

  async function submitFile() {
    const fileInput = document.getElementById("upload-file");
    const folderInput = document.getElementById("upload-folder");
    const files = Array.from(fileInput.files || []);
    const folderFiles = Array.from(folderInput.files || []);
    if (!files.length && !folderFiles.length) throw new Error(UI.file_required);
    const payload = {
      submitter_name: document.getElementById("upload-name").value,
    };
    if (folderFiles.length || files.length > 1) {
      const bundle = await Promise.all(
        (folderFiles.length ? folderFiles : files).map(async (file) => ({
          filename: file.name,
          relative_path: file.webkitRelativePath || file.name,
          mime_type: file.type || inferMimeType(file.name),
          content_base64: await encodeFileAsBase64(file),
        }))
      );
      payload.filename = folderFiles.length ? inferBundleName(bundle) : "document-bundle";
      payload.mime_type = "application/zip";
      payload.files = bundle;
    } else {
      const file = files[0];
      payload.filename = file.name;
      payload.mime_type = file.type || inferMimeType(file.name);
      payload.content_base64 = await encodeFileAsBase64(file);
    }
    const response = await fetch("/api/portal/submissions/document", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Upload failed");
    document.getElementById("submit-file-status").textContent = `${UI.submit_file_success}${data.id}`;
    fileInput.value = "";
    folderInput.value = "";
    setPortalMessage(`${UI.submitted_file_prefix}${data.title}`);
    await loadHome();
  }

  async function encodeFileAsBase64(file) {
    const buffer = await file.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    return btoa(binary);
  }

  function inferBundleName(files) {
    const roots = new Set(
      files
        .map((file) => String(file.relative_path || "").split("/")[0])
        .filter(Boolean)
    );
    if (roots.size === 1) return Array.from(roots)[0];
    return "document-bundle";
  }

  function inferMimeType(filename) {
    const lower = filename.toLowerCase();
    if (lower.endsWith(".md")) return "text/markdown";
    if (lower.endsWith(".txt")) return "text/plain";
    if (lower.endsWith(".docx")) {
      return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    }
    if (lower.endsWith(".pptx")) {
      return "application/vnd.openxmlformats-officedocument.presentationml.presentation";
    }
    if (lower.endsWith(".zip")) return "application/zip";
    return "application/octet-stream";
  }

  function renderSubmissionAnalysis(analysis) {
    if (!analysis) return `<div class="empty">${escapeHtml(UI.analysis_related_empty)}</div>`;
    const related =
      Array.isArray(analysis.related_entries) && analysis.related_entries.length
        ? analysis.related_entries
            .map(
              (item) => `
            <li><strong>${escapeHtml(item.name)}</strong> · ${escapeHtml(item.reason || "")}</li>
          `
            )
            .join("")
        : `<li>${escapeHtml(UI.analysis_related_empty)}</li>`;
    const warnings =
      Array.isArray(analysis.warnings) && analysis.warnings.length
        ? `<div class="subtle">${analysis.warnings.map((item) => escapeHtml(item)).join("；")}</div>`
        : "";
    return `
      <div class="card">
        <div class="row spread">
          <strong>${escapeHtml(UI.analysis_title)}</strong>
          <span class="tag ${analysis.status === "ok" ? "ok" : "warn"}">${escapeHtml(
            analysis.status || UI.unknown
          )}</span>
        </div>
        <div class="subtle">${escapeHtml(analysis.summary || "")}</div>
        <div class="subtle">${escapeHtml(UI.analysis_title_label)}: ${escapeHtml(
          analysis.recommended_title || "-"
        )}</div>
        <div class="subtle">${escapeHtml(UI.analysis_type_label)}: ${escapeHtml(
          analysis.recommended_type || "-"
        )} · ${escapeHtml(UI.analysis_risk_label)}: ${escapeHtml(
          analysis.duplicate_risk || "-"
        )} · ${escapeHtml(UI.analysis_action_label)}: ${escapeHtml(
          analysis.committer_action || "-"
        )}</div>
        <div class="subtle">${escapeHtml(UI.analysis_note_label)}: ${escapeHtml(
          analysis.committer_note || ""
        )}</div>
        <ul>${related}</ul>
        ${warnings}
      </div>
    `;
  }

  function handleEntryClick(event) {
    const card = event.target.closest("[data-entry-name]");
    if (!card) return;
    openEntry(card.dataset.entryName).catch(showError);
  }

  function showError(error) {
    document.getElementById("submit-text-status").textContent = error.message;
    document.getElementById("submit-file-status").textContent = error.message;
    document.getElementById("search-status").textContent = error.message;
    setPortalMessage(error.message);
  }

  document.getElementById("search-results").addEventListener("click", handleEntryClick);
  document.getElementById("recent-updates").addEventListener("click", handleEntryClick);
  document
    .getElementById("search-button")
    .addEventListener("click", () => withBusy("search-button", UI.search_busy, runSearch).catch(showError));
  document
    .getElementById("submit-text-button")
    .addEventListener("click", () =>
      withBusy("submit-text-button", UI.submit_text_busy, submitText).catch(showError)
    );
  document
    .getElementById("submit-file-button")
    .addEventListener("click", () =>
      withBusy("submit-file-button", UI.submit_file_busy, submitFile).catch(showError)
    );
  document.getElementById("entry-close-button").addEventListener("click", () => {
    document.getElementById("entry-modal").hidden = true;
  });
  document.getElementById("entry-modal").addEventListener("click", (event) => {
    if (event.target.id === "entry-modal") {
      document.getElementById("entry-modal").hidden = true;
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      document.getElementById("entry-modal").hidden = true;
    }
  });
  document.getElementById("search-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      withBusy("search-button", UI.search_busy, runSearch).catch(showError);
    }
  });

  loadHome().catch(showError);
})();
