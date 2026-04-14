(function () {
  const shell = window.SedimentShell;
  const pageData = shell.readJsonScript("sediment-page-data") || {};
  const UI = pageData.ui || {};
  const ROUTES = pageData.routes || {};
  const { escapeHtml, fetchJson, renderMarkdown } = shell;
  const isZh = document.documentElement.dataset.locale === "zh";
  const state = {
    suggestions: [],
    activeSuggestionIndex: -1,
    debounceId: null,
  };

  function localeValue() {
    return document.documentElement.dataset.locale || "en";
  }

  function localizedPath(path, searchParams) {
    const url = new URL(path, window.location.origin);
    url.searchParams.set("lang", localeValue());
    if (searchParams) {
      Object.entries(searchParams).forEach(([key, value]) => {
        if (value == null || value === "") {
          url.searchParams.delete(key);
        } else {
          url.searchParams.set(key, String(value));
        }
      });
    }
    return `${url.pathname}${url.search}`;
  }

  function entryUrl(name) {
    const url = new URL(`${ROUTES.entryPrefix || "/entries/"}${encodeURIComponent(name)}`, window.location.origin);
    url.searchParams.set("lang", localeValue());
    return `${url.pathname}${url.search}`;
  }

  function setPortalMessage(message) {
    const node = document.getElementById("portal-message");
    if (node) node.textContent = String(message || "");
  }

  function setSearchStatus(message) {
    const node = document.getElementById("search-status");
    if (node) node.textContent = String(message || "");
  }

  function suggestionNode() {
    return document.getElementById("search-suggestions");
  }

  function setSuggestionVisibility(open) {
    const node = suggestionNode();
    if (!node) return;
    node.hidden = !open;
  }

  function formatDateTime(value) {
    const numeric = Number(value);
    if (Number.isFinite(numeric) && String(value).length <= 12) {
      return new Date(numeric * 1000).toLocaleString();
    }
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value || "") : date.toLocaleString();
  }

  function currentQuery() {
    return (document.getElementById("search-input")?.value || "").trim();
  }

  function renderPortalStats(payload) {
    const node = document.getElementById("portal-stats");
    if (!node) return;
    const counts = payload.counts || {};
    const stats = [
      [UI.formal_entries, counts.formal_entries || 0],
      [UI.placeholders, counts.placeholders || 0],
      [UI.indexes, counts.indexes || 0],
      [UI.pending, counts.pending_submissions || 0],
      [UI.health, counts.health_issues || 0],
    ];
    node.innerHTML = stats
      .map(
        ([label, value]) =>
          `<div class="stat"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`
      )
      .join("");
  }

  function renderRecentUpdates(payload) {
    const node = document.getElementById("recent-updates");
    if (!node) return;
    const items = payload.recent_updates || [];
    node.innerHTML = items.length
      ? items.map((item) => `
          <a class="card" href="${entryUrl(item.name)}">
            <div class="row spread">
              <strong>${escapeHtml(item.name || "")}</strong>
              <span class="tag">${escapeHtml(item.entry_type || "")}</span>
            </div>
            <div class="subtle">${escapeHtml(item.status || "")} · ${escapeHtml(formatDateTime(item.updated_at))}</div>
          </a>
        `).join("")
      : `<div class="empty">${escapeHtml(UI.updates_empty)}</div>`;
  }

  function renderSuggestionList(items, query) {
    const node = suggestionNode();
    if (!node) return;
    const nextSuggestions = Array.isArray(items) ? items : [];
    const keepSelection =
      nextSuggestions.length === state.suggestions.length &&
      nextSuggestions.every((item, index) => item.name === state.suggestions[index]?.name);
    state.suggestions = nextSuggestions;
    if (!state.suggestions.length) {
      state.activeSuggestionIndex = -1;
    } else if (keepSelection && state.activeSuggestionIndex >= 0) {
      state.activeSuggestionIndex = Math.min(state.activeSuggestionIndex, state.suggestions.length - 1);
    } else {
      state.activeSuggestionIndex = 0;
    }
    if (!query) {
      node.innerHTML = "";
      setSuggestionVisibility(false);
      return;
    }
    if (!state.suggestions.length) {
      node.innerHTML = `<div class="empty">${escapeHtml(UI.suggestions_empty)}</div>`;
      setSuggestionVisibility(true);
      return;
    }
    const suggestionsHtml = state.suggestions
      .map((item, index) => `
        <button
          class="card search-suggestion"
          type="button"
          data-action="open-suggestion"
          data-name="${encodeURIComponent(item.name || "")}"
          data-index="${index}"
          role="option"
          aria-selected="${index === state.activeSuggestionIndex ? "true" : "false"}"
        >
          <div class="row spread">
            <strong>${escapeHtml(item.title || item.name || "")}</strong>
            <span class="tag">${escapeHtml(item.matched_field || "")}</span>
          </div>
          <div class="subtle">${escapeHtml(item.summary || "")}</div>
        </button>
      `)
      .join("");
    const footer = `
      <a class="button primary" href="${localizedPath(ROUTES.search || "/search", { q: query })}">
        ${escapeHtml(UI.view_all_results)}
      </a>
    `;
    node.innerHTML = `<div class="list">${suggestionsHtml}</div><div class="search-suggestions-footer">${footer}</div>`;
    setSuggestionVisibility(true);
  }

  function renderSearchResults(results, query) {
    const node = document.getElementById("search-results");
    if (!node) return;
    node.innerHTML = Array.isArray(results) && results.length
      ? results.map((item) => `
          <a class="card" href="${entryUrl(item.name)}">
            <div class="row spread">
              <strong>${escapeHtml(item.title || item.name || "")}</strong>
              <span class="tag">${escapeHtml(item.kind || item.entry_type || "")}</span>
            </div>
            <div class="subtle">${escapeHtml(item.summary || "")}</div>
            <div class="subtle">${escapeHtml(item.snippet || "")}</div>
          </a>
        `).join("")
      : `<div class="empty">${escapeHtml(query ? UI.search_empty : UI.search_prompt)}</div>`;
  }

  function renderEntrySignals(payload) {
    const node = document.getElementById("entry-signals");
    if (!node) return;
    const structured = payload.structured || {};
    const validation = structured.validation_cues || {};
    const validationValue = validation.valid
      ? UI.detail_valid
      : validation.hard_failures?.length
        ? `${UI.detail_fail}: ${validation.hard_failures.join(" | ")}`
        : validation.warnings?.length
          ? `${UI.detail_warn}: ${validation.warnings.join(" | ")}`
          : UI.unknown;
    const cards = [
      { label: UI.detail_type, value: structured.entry_type || UI.unknown, required: true },
      { label: UI.detail_status, value: structured.status || UI.unknown, required: true },
      { label: UI.detail_aliases, value: (structured.aliases || []).join(" · "), required: (structured.aliases || []).length > 0 },
      { label: UI.detail_sources, value: (structured.sources || []).join(" · "), required: (structured.sources || []).length > 0 },
      { label: UI.detail_related, value: (structured.related_links || []).join(" · "), required: (structured.related_links || []).length > 0 },
      { label: UI.detail_validation, value: validationValue, required: validationValue !== UI.unknown },
    ].filter((item) => item.required);
    node.className = cards.length ? "signal-grid" : "empty";
    node.innerHTML = cards.length
      ? cards.map(
          (item) => `
            <div class="signal-card">
              <span class="signal-card-label">${escapeHtml(item.label)}</span>
              <div class="signal-card-value">${escapeHtml(item.value)}</div>
            </div>
          `
        ).join("")
      : escapeHtml(UI.no_content);
  }

  function renderEntrySections(payload) {
    const node = document.getElementById("entry-sections");
    if (!node) return;
    const sections = payload.structured?.canonical_sections || [];
    node.innerHTML = sections.length
      ? sections.map((section) => `
          <div class="card">
            <strong>${escapeHtml(section.name || "")}</strong>
            <div class="markdown">${renderMarkdown(section.content || "")}</div>
          </div>
        `).join("")
      : `<div class="empty">${escapeHtml(UI.no_content)}</div>`;
  }

  function renderEntryMarkdown(payload) {
    const node = document.getElementById("entry-view");
    if (!node) return;
    node.innerHTML = renderMarkdown(payload.structured?.residual_markdown || "");
  }

  async function loadHome() {
    const payload = await fetchJson("/api/portal/home");
    renderPortalStats(payload);
    renderRecentUpdates(payload);
    setPortalMessage(isZh ? "门户已就绪。" : "Portal ready.");
  }

  async function loadSuggestions(query) {
    const trimmed = String(query || "").trim();
    if (!trimmed) {
      renderSuggestionList([], "");
      setSearchStatus("");
      return;
    }
    const payload = await fetchJson(`/api/portal/search/suggest?q=${encodeURIComponent(trimmed)}`);
    renderSuggestionList(payload.suggestions || [], trimmed);
    setSearchStatus(UI.search_hint);
  }

  async function runSearch(options = {}) {
    const query = String(options.query != null ? options.query : currentQuery()).trim();
    if (!query) {
      renderSearchResults([], "");
      setPortalMessage(UI.search_prompt);
      setSuggestionVisibility(false);
      return;
    }
    setSearchStatus(UI.search_busy);
    setSuggestionVisibility(false);
    const results = await fetchJson(`/api/portal/search?q=${encodeURIComponent(query)}`);
    renderSearchResults(results, query);
    setSearchStatus(`${UI.found_prefix} ${results.length} ${UI.found_suffix}`);
    setPortalMessage(`${UI.found_prefix} ${results.length} ${UI.found_suffix}`);
    if (options.pushHistory !== false) {
      window.history.replaceState({}, "", localizedPath(ROUTES.search || "/search", { q: query }));
    }
  }

  async function loadEntry() {
    const name = pageData.entryName || "";
    const payload = await fetchJson(`/api/portal/entries/${encodeURIComponent(name)}`);
    const pageTitleNode = document.getElementById("entry-page-title");
    if (pageTitleNode) pageTitleNode.textContent = payload.structured?.title || name;
    renderEntrySignals(payload);
    renderEntrySections(payload);
    renderEntryMarkdown(payload);
    setPortalMessage(`${UI.entry_open}${payload.structured?.title || name}`);
  }

  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || "");
        resolve(result.includes(",") ? result.split(",", 2)[1] : result);
      };
      reader.onerror = () => reject(reader.error || new Error(UI.file_read_error || "Failed to read file"));
      reader.readAsDataURL(file);
    });
  }

  async function collectUploads(files) {
    const list = Array.from(files || []);
    return Promise.all(
      list.map(async (file) => ({
        filename: file.name,
        relative_path: file.webkitRelativePath || file.name,
        mime_type: file.type || "application/octet-stream",
        content_base64: await fileToBase64(file),
      }))
    );
  }

  function renderSubmissionAnalysis(analysis) {
    const node = document.getElementById("submit-text-analysis");
    if (!node) return;
    if (!analysis) {
      node.innerHTML = "";
      return;
    }
    const related = Array.isArray(analysis.related_entries) && analysis.related_entries.length
      ? analysis.related_entries.map((item) => escapeHtml(item.name || "")).join(" · ")
      : UI.analysis_related_empty;
    node.innerHTML = `
      <div class="card">
        <strong>${escapeHtml(UI.analysis_title)}</strong>
        <div class="subtle">${escapeHtml(UI.analysis_title_label)}: ${escapeHtml(analysis.suggested_title || "-")}</div>
        <div class="subtle">${escapeHtml(UI.analysis_type_label)}: ${escapeHtml(analysis.recommended_type || "-")}</div>
        <div class="subtle">${escapeHtml(UI.analysis_risk_label)}: ${escapeHtml(analysis.duplicate_risk || "-")}</div>
        <div class="subtle">${escapeHtml(UI.analysis_action_label)}: ${escapeHtml(analysis.committer_action || "-")}</div>
        <div class="subtle">${escapeHtml(UI.analysis_note_label)}: ${escapeHtml(analysis.summary || "")}</div>
        <div class="subtle">${related}</div>
      </div>
    `;
  }

  async function submitText() {
    const submitter_name = (document.getElementById("submit-name")?.value || "").trim();
    const title = (document.getElementById("submit-title")?.value || "").trim();
    const submission_type = (document.getElementById("submit-type")?.value || "concept").trim();
    const content = document.getElementById("submit-content")?.value || "";
    document.getElementById("submit-text-status").textContent = UI.submit_text_busy;
    const payload = await fetchJson("/api/portal/submissions/text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ submitter_name, title, submission_type, content }),
    });
    document.getElementById("submit-text-status").textContent = `${UI.submit_text_success}${payload.id}`;
    renderSubmissionAnalysis(payload.analysis || null);
    setPortalMessage(`${UI.submitted_text_prefix}${payload.id}`);
  }

  async function submitFiles() {
    const submitter_name = (document.getElementById("upload-name")?.value || "").trim();
    const directFiles = Array.from(document.getElementById("upload-file")?.files || []);
    const folderFiles = Array.from(document.getElementById("upload-folder")?.files || []);
    const files = [...folderFiles, ...directFiles];
    if (!files.length) {
      throw new Error(UI.file_required);
    }
    document.getElementById("submit-file-status").textContent = UI.submit_file_busy;
    const uploads = await collectUploads(files);
    const payload = await fetchJson("/api/portal/submissions/document", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        submitter_name,
        files: uploads,
        filename: files.length === 1 ? files[0].name : "upload-bundle.zip",
        mime_type: files.length === 1 ? (files[0].type || "application/octet-stream") : "application/zip",
      }),
    });
    document.getElementById("submit-file-status").textContent = `${UI.submit_file_success}${payload.id}`;
    setPortalMessage(`${UI.submitted_file_prefix}${payload.id}`);
  }

  function openActiveSuggestion() {
    if (!state.suggestions.length) {
      const query = currentQuery();
      if (pageData.pageKind === "home") {
        window.location.href = localizedPath(ROUTES.search || "/search", { q: query });
        return;
      }
      runSearch({ query }).catch(showPortalError);
      return;
    }
    const active = state.suggestions[state.activeSuggestionIndex >= 0 ? state.activeSuggestionIndex : 0];
    if (!active) return;
    window.location.href = entryUrl(active.name);
  }

  function handleSearchKeydown(event) {
    if (event.key === "Escape") {
      setSuggestionVisibility(false);
      return;
    }
    if (!["ArrowDown", "ArrowUp", "Enter"].includes(event.key)) return;
    if (event.key === "Enter") {
      event.preventDefault();
      openActiveSuggestion();
      return;
    }
    if (!state.suggestions.length) return;
    event.preventDefault();
    if (event.key === "ArrowDown") {
      state.activeSuggestionIndex = (state.activeSuggestionIndex + 1) % state.suggestions.length;
    } else if (event.key === "ArrowUp") {
      state.activeSuggestionIndex =
        (state.activeSuggestionIndex - 1 + state.suggestions.length) % state.suggestions.length;
    }
    renderSuggestionList(state.suggestions, currentQuery());
  }

  function showPortalError(error) {
    const message = error && error.message ? error.message : (UI.unknown_error || "Unknown error");
    setPortalMessage(message);
    setSearchStatus(message);
    setSuggestionVisibility(false);
  }

  document.getElementById("search-input")?.addEventListener("input", (event) => {
    const value = String(event.target.value || "");
    window.clearTimeout(state.debounceId);
    state.debounceId = window.setTimeout(() => {
      loadSuggestions(value).catch(showPortalError);
    }, 180);
  });
  document.getElementById("search-input")?.addEventListener("focus", () => {
    const node = suggestionNode();
    if (currentQuery() && node?.innerHTML.trim()) {
      setSuggestionVisibility(true);
    }
  });
  document.getElementById("search-input")?.addEventListener("keydown", handleSearchKeydown);
  document.getElementById("search-button")?.addEventListener("click", () => {
    if (pageData.pageKind === "home") {
      window.location.href = localizedPath(ROUTES.search || "/search", { q: currentQuery() });
      return;
    }
    runSearch({ query: currentQuery() }).catch(showPortalError);
  });
  document.getElementById("search-suggestions")?.addEventListener("click", (event) => {
    const button = event.target.closest('button[data-action="open-suggestion"]');
    if (!button) return;
    const name = decodeURIComponent(button.dataset.name || "");
    window.location.href = entryUrl(name);
  });
  document.addEventListener("click", (event) => {
    const root = document.querySelector("[data-search-popover-root]");
    if (!root || root.contains(event.target)) return;
    setSuggestionVisibility(false);
  });
  document.getElementById("submit-text-button")?.addEventListener("click", () => submitText().catch(showPortalError));
  document.getElementById("submit-file-button")?.addEventListener("click", () => submitFiles().catch(showPortalError));

  if (pageData.pageKind === "home") {
    document.getElementById("search-input").value = pageData.initialQuery || "";
    loadHome().catch(showPortalError);
    if (pageData.initialQuery) {
      loadSuggestions(pageData.initialQuery).catch(showPortalError);
    }
  } else if (pageData.pageKind === "search") {
    document.getElementById("search-input").value = pageData.initialQuery || "";
    if (pageData.initialQuery) {
      runSearch({ query: pageData.initialQuery, pushHistory: false }).catch(showPortalError);
    } else {
      renderSearchResults([], "");
      setPortalMessage(UI.search_prompt);
    }
  } else if (pageData.pageKind === "entry") {
    loadEntry().catch(showPortalError);
  }
})();
