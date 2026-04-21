(function () {
  const pageDataNode = document.getElementById("sediment-page-data");
  if (!pageDataNode) return;

  let pageData = {};
  try {
    pageData = JSON.parse(pageDataNode.textContent || "{}");
  } catch (_error) {
    pageData = {};
  }
  if (pageData.pageKind !== "universe") return;

  const locale = document.documentElement.dataset.locale || "en";
  const UI = pageData.ui || {};
  const ROUTES = pageData.routes || {};
  const PREFS = pageData.preferences || {};

  const INTRO_SEEN_KEY = `sediment-universe-intro:${String(pageData.knowledgeName || "default")}`;
  const AUDIO_MUTED_KEY = `sediment-universe-audio-muted:${String(pageData.knowledgeName || "default")}`;
  const SUBMIT_DRAFT_KEY = `sediment-universe-submit:${String(pageData.knowledgeName || "default")}:${locale}`;
  const THEME_KEY = String(PREFS.themeStorageKey || `sediment-universe-theme:${String(pageData.knowledgeName || "default")}`);
  const REDUCED_MOTION_KEY = String(
    PREFS.reducedMotionStorageKey || `sediment-universe-motion:${String(pageData.knowledgeName || "default")}`,
  );
  const BUDGET_KEY = String(
    PREFS.budgetStorageKey || `sediment-universe-budget:${String(pageData.knowledgeName || "default")}`,
  );
  const INTRO_DURATION_MS = 2800;
  const INTRO_REDUCED_MS = 700;
  const IDLE_CRUISE_MS = 18000;
  const CRUISE_STEP_MS = 3600;

  const state = {
    bootstrap: null,
    graphPayload: null,
    homeGraphPayload: null,
    graphController: null,
    graphApi: null,
    currentScene: String(pageData.graphScene || "home"),
    selectedNode: null,
    selectedPayload: null,
    focusRef: "",
    focusSource: "",
    focusSuggestion: null,
    activePanel: "",
    portalState: "booting",
    cruiseQueue: [],
    cruiseIndex: 0,
    cruiseTimer: 0,
    idleTimer: 0,
    suggestionTimer: 0,
    suggestionRequestId: 0,
    suggestions: [],
    suggestionIndex: -1,
    lastSearchQuery: String(pageData.initialQuery || ""),
    lastSearchResults: [],
    pendingFocusMode: "expanded",
    theme: window.localStorage?.getItem(THEME_KEY) || String(PREFS.defaultTheme || "midnight"),
    reducedMotion:
      window.localStorage?.getItem(REDUCED_MOTION_KEY) === "true" ||
      (!(window.localStorage?.getItem(REDUCED_MOTION_KEY)) &&
        (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches || Boolean(PREFS.defaultReducedMotion))),
    budget: normalizeBudget(window.localStorage?.getItem(BUDGET_KEY) || PREFS.defaultBudget || "standard"),
    introPlaying: false,
    introTimers: [],
    cruising: false,
    cruisePaused: false,
    cruiseCurrentNode: null,
    audioContext: null,
    audioNeedsUnlock: false,
    audioMuted: window.localStorage?.getItem(AUDIO_MUTED_KEY) === "true",
    audioPromptDismissed: false,
    capabilities: null,
    runtimeProfile: "standard",
    overlayTrackerFrame: 0,
    suppressBackgroundSelect: false,
  };

  const nodes = {
    page: document.querySelector('[data-testid="portal-universe-page"]'),
    stage: document.getElementById("portal-insights-graph"),
    topbar: document.querySelector('[data-testid="portal-topbar"]'),
    systemToggle: document.getElementById("portal-system-toggle"),
    soundToggle: document.getElementById("portal-sound-toggle"),
    intro: document.getElementById("portal-universe-intro"),
    introLabel: document.getElementById("portal-intro-label"),
    introLine: document.getElementById("portal-intro-line"),
    introPhaseCopy: document.getElementById("portal-intro-phase-copy"),
    introTargetTitle: document.getElementById("portal-intro-target-title"),
    introTargetSummary: document.getElementById("portal-intro-target-summary"),
    introReplayButton: document.getElementById("portal-intro-replay-button"),
    cinematicBars: document.getElementById("portal-cinematic-bars"),
    hud: document.getElementById("portal-hud"),
    hudToggle: document.getElementById("portal-hud-toggle"),
    hudSearch: document.getElementById("portal-hud-search"),
    hudClear: document.getElementById("portal-hud-clear"),
    hudCruise: document.getElementById("portal-hud-cruise"),
    hudSubmit: document.getElementById("portal-hud-submit"),
    hudTutorial: document.getElementById("portal-hud-tutorial"),
    hudSystem: document.getElementById("portal-hud-system"),
    message: document.getElementById("portal-message"),
    survey: document.getElementById("portal-survey"),
    surveyClose: document.getElementById("portal-survey-close"),
    searchInput: document.getElementById("search-input"),
    searchButton: document.getElementById("search-button"),
    searchStatus: document.getElementById("search-status"),
    searchResults: document.getElementById("search-results"),
    searchSuggestions: document.getElementById("search-suggestions"),
    spatialCard: document.getElementById("portal-spatial-card"),
    spatialCardBody: document.getElementById("portal-spatial-card-body"),
    spatialCardTitle: document.getElementById("portal-spatial-card-title"),
    spatialCardSubtitle: document.getElementById("portal-spatial-card-subtitle"),
    spatialCardCompact: document.getElementById("portal-spatial-card-compact"),
    spatialCardExpand: document.getElementById("portal-spatial-card-expand"),
    spatialCardCollapse: document.getElementById("portal-spatial-card-collapse"),
    spatialCardReaderPanel: document.getElementById("portal-spatial-card-reader-panel"),
    entrySections: document.getElementById("portal-entry-sections"),
    entrySignals: document.getElementById("portal-entry-signals"),
    entryView: document.getElementById("portal-entry-view"),
    submitPanel: document.getElementById("portal-submit-panel"),
    tutorialPanel: document.getElementById("portal-tutorial-panel"),
    systemPanel: document.getElementById("portal-system-panel"),
    submitName: document.getElementById("submit-name"),
    submitTitle: document.getElementById("submit-title"),
    submitContent: document.getElementById("submit-content"),
    submitTextButton: document.getElementById("submit-text-button"),
    submitTextStatus: document.getElementById("submit-text-status"),
    submitTextFollowup: document.getElementById("submit-text-followup"),
    submitTextFocus: document.getElementById("submit-text-focus"),
    uploadName: document.getElementById("upload-name"),
    uploadFile: document.getElementById("upload-file"),
    uploadFolder: document.getElementById("upload-folder"),
    submitFileButton: document.getElementById("submit-file-button"),
    submitFileStatus: document.getElementById("submit-file-status"),
    submitFileFollowup: document.getElementById("submit-file-followup"),
    cruiseSummary: document.getElementById("portal-cruise-summary"),
    cruiseTitle: document.getElementById("portal-cruise-title"),
    cruiseText: document.getElementById("portal-cruise-summary-text"),
    cruisePause: document.getElementById("portal-cruise-pause"),
    cruiseNext: document.getElementById("portal-cruise-next"),
    cruiseExit: document.getElementById("portal-cruise-exit"),
    systemLocale: document.getElementById("portal-system-locale"),
    systemThemeMidnight: document.getElementById("portal-system-theme-midnight"),
    systemThemeDawn: document.getElementById("portal-system-theme-dawn"),
    systemMotionFull: document.getElementById("portal-system-motion-full"),
    systemMotionReduced: document.getElementById("portal-system-motion-reduced"),
    systemBudgetSafe: document.getElementById("portal-system-budget-safe"),
    systemBudgetStandard: document.getElementById("portal-system-budget-standard"),
    systemBudgetImmersive: document.getElementById("portal-system-budget-immersive"),
    systemRuntimeMode: document.getElementById("portal-system-runtime-mode"),
    systemCapabilities: document.getElementById("portal-system-capabilities"),
    soundPrompt: document.getElementById("portal-sound-prompt"),
    unsupported: document.getElementById("portal-unsupported-overlay"),
  };

  function normalizeBudget(value) {
    const normalized = String(value || "").trim().toLowerCase();
    return normalized === "safe" || normalized === "immersive" ? normalized : "standard";
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function hashString(value) {
    let hash = 2166136261;
    const text = String(value || "");
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return Math.abs(hash >>> 0);
  }

  function readStoredJson(key, fallback) {
    if (!window.sessionStorage) return fallback;
    try {
      const raw = window.sessionStorage.getItem(key);
      if (!raw) return fallback;
      return JSON.parse(raw);
    } catch (_error) {
      return fallback;
    }
  }

  function writeStoredJson(key, value) {
    if (!window.sessionStorage) return;
    try {
      window.sessionStorage.setItem(key, JSON.stringify(value));
    } catch (_error) {
      // Ignore storage failures.
    }
  }

  function stripFrontmatter(markdown) {
    const text = String(markdown || "");
    if (!text.startsWith("---")) return text;
    const closing = text.indexOf("\n---", 3);
    if (closing < 0) return text;
    return text.slice(closing + 4).trimStart();
  }

  function renderInlineMarkdown(source) {
    return escapeHtml(source)
      .replace(/\[\[([^\]]+)\]\]/g, '<span class="universe-inline-link">$1</span>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>");
  }

  function renderMarkdown(source) {
    const text = stripFrontmatter(source).replace(/\r\n/g, "\n").trim();
    if (!text) return `<div class="universe-empty-state">${escapeHtml(UI.no_content || "")}</div>`;
    const lines = text.split("\n");
    const blocks = [];
    let buffer = [];
    let listItems = [];

    function flushParagraph() {
      if (!buffer.length) return;
      blocks.push(`<p>${renderInlineMarkdown(buffer.join(" "))}</p>`);
      buffer = [];
    }

    function flushList() {
      if (!listItems.length) return;
      blocks.push(`<ul>${listItems.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</ul>`);
      listItems = [];
    }

    lines.forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed) {
        flushParagraph();
        flushList();
        return;
      }
      if (trimmed.startsWith("### ")) {
        flushParagraph();
        flushList();
        blocks.push(`<h3>${renderInlineMarkdown(trimmed.slice(4))}</h3>`);
        return;
      }
      if (trimmed.startsWith("## ")) {
        flushParagraph();
        flushList();
        blocks.push(`<h2>${renderInlineMarkdown(trimmed.slice(3))}</h2>`);
        return;
      }
      if (trimmed.startsWith("# ")) {
        flushParagraph();
        flushList();
        blocks.push(`<h1>${renderInlineMarkdown(trimmed.slice(2))}</h1>`);
        return;
      }
      if (trimmed.startsWith("- ")) {
        flushParagraph();
        listItems.push(trimmed.slice(2));
        return;
      }
      buffer.push(trimmed);
    });

    flushParagraph();
    flushList();
    return blocks.join("");
  }

  function currentUrlForLocale(nextLocale) {
    const url = new URL(window.location.href);
    url.searchParams.set("lang", nextLocale);
    return `${url.pathname}${url.search}`;
  }

  function withQuery(path, params) {
    const url = new URL(path, window.location.origin);
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value == null || value === "") {
        url.searchParams.delete(key);
      } else {
        url.searchParams.set(key, String(value));
      }
    });
    return `${url.pathname}${url.search}`;
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, {
      headers: {
        Accept: "application/json",
        ...(options && options.body ? { "Content-Type": "application/json" } : {}),
      },
      credentials: "same-origin",
      ...options,
    });
    if (!response.ok) throw new Error(`${response.status}`);
    return response.json();
  }

  function setPortalMessage(message) {
    if (nodes.message) nodes.message.textContent = String(message || "");
  }

  function setSearchStatus(message) {
    if (nodes.searchStatus) nodes.searchStatus.textContent = String(message || "");
  }

  function detectCapabilities() {
    return {
      canvas2d: Boolean(document.createElement("canvas").getContext("2d")),
      desktopViewport: window.innerWidth >= 900,
      worker: typeof window.Worker === "function",
      offscreenCanvas: typeof window.OffscreenCanvas === "function",
      webgpu: Boolean(navigator.gpu),
      pointer: window.matchMedia?.("(pointer: fine)").matches ?? false,
      hover: window.matchMedia?.("(hover: hover)").matches ?? false,
      reducedMotion: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false,
    };
  }

  function computeRuntimeProfile() {
    const caps = state.capabilities || detectCapabilities();
    if (!caps.canvas2d || !caps.desktopViewport) return "safe_fallback";
    if (state.reducedMotion || state.budget === "safe") return "safe_fallback";
    if (state.budget === "immersive" && caps.webgpu && caps.worker && caps.offscreenCanvas) return "immersive";
    return "standard";
  }

  function showUnsupportedIfNeeded() {
    state.capabilities = detectCapabilities();
    state.runtimeProfile = computeRuntimeProfile();
    if (nodes.page) {
      nodes.page.dataset.runtimeProfile = state.runtimeProfile;
      nodes.page.dataset.motion = state.reducedMotion ? "reduced" : "full";
      nodes.page.dataset.renderBudget = state.budget;
    }
    if (!nodes.unsupported) return false;
    const unsupported = !state.capabilities.canvas2d || !state.capabilities.desktopViewport;
    nodes.unsupported.hidden = !unsupported;
    return unsupported;
  }

  function applyTheme(theme) {
    state.theme = theme === "dawn" ? "dawn" : "midnight";
    document.documentElement.dataset.theme = state.theme;
    window.localStorage?.setItem(THEME_KEY, state.theme);
    syncSystemControls();
  }

  function applyReducedMotion(enabled) {
    state.reducedMotion = Boolean(enabled);
    document.documentElement.dataset.motion = state.reducedMotion ? "reduced" : "full";
    window.localStorage?.setItem(REDUCED_MOTION_KEY, state.reducedMotion ? "true" : "false");
    state.runtimeProfile = computeRuntimeProfile();
    state.graphApi?.setMotionProfile?.(state.reducedMotion ? "reduced" : "full");
    syncSystemControls();
    renderSystemCapabilities();
  }

  async function applyBudget(budget, { reloadGraph = false } = {}) {
    state.budget = normalizeBudget(budget);
    document.documentElement.dataset.renderBudget = state.budget;
    window.localStorage?.setItem(BUDGET_KEY, state.budget);
    state.runtimeProfile = computeRuntimeProfile();
    syncSystemControls();
    renderSystemCapabilities();
    if (reloadGraph) {
      await reloadGraphForCurrentContext();
    }
  }

  function updateHudState() {
    if (!nodes.hud) return;
    nodes.hud.dataset.expanded = nodes.hud.dataset.expanded === "true" ? "true" : "false";
    nodes.hud.dataset.cruising = state.cruising ? "true" : "false";
    nodes.hud.dataset.portalState = state.portalState;
  }

  function setHudExpanded(expanded) {
    if (!nodes.hud) return;
    nodes.hud.dataset.expanded = expanded ? "true" : "false";
    updateHudState();
  }

  function setPortalState(nextState) {
    state.portalState = String(nextState || "roaming");
    if (nodes.page) nodes.page.dataset.portalState = state.portalState;
    updateHudState();
  }

  function closePanel(panel) {
    if (panel) panel.hidden = true;
  }

  function setActivePanel(panelName) {
    state.activePanel = String(panelName || "");
    if (nodes.page) nodes.page.dataset.activePanel = state.activePanel;
  }

  function setPanelOpen(panelName, panel, portalState) {
    closeOtherPanels({
      keepSurvey: panelName === "survey",
      keepSpatialCard: false,
      keepSystem: panelName === "system",
    });
    stopCruise({ keepPosition: true, immediate: true });
    setActivePanel(panelName);
    if (panel) panel.hidden = false;
    setPortalState(portalState);
    setHudExpanded(true);
  }

  function closeNamedPanel(name, panel) {
    closePanel(panel);
    if (state.activePanel === name) setActivePanel("");
    if (!state.selectedNode) {
      setPortalState("roaming");
      scheduleIdleCruise();
    }
  }

  function closeOtherPanels({ keepSurvey = false, keepSpatialCard = false, keepSystem = false } = {}) {
    if (!keepSurvey) closePanel(nodes.survey);
    closePanel(nodes.submitPanel);
    closePanel(nodes.tutorialPanel);
    if (!keepSystem) closePanel(nodes.systemPanel);
    if (!keepSpatialCard) {
      nodes.spatialCard.hidden = true;
      state.selectedPayload = null;
      state.selectedNode = null;
    }
    if (!keepSurvey && state.graphApi?.getViewMode?.() === "survey") {
      state.graphApi.setViewMode("roam", { immediate: state.reducedMotion });
    }
    if (!keepSurvey && state.activePanel === "survey") setActivePanel("");
    if (!keepSystem && state.activePanel === "system") setActivePanel("");
    if (state.activePanel === "submit" || state.activePanel === "tutorial") setActivePanel("");
  }

  function updateSoundButton() {
    if (!nodes.soundToggle) return;
    nodes.soundToggle.textContent = state.audioMuted ? "…" : "♪";
    nodes.soundToggle.setAttribute("aria-pressed", state.audioMuted ? "true" : "false");
    nodes.soundToggle.setAttribute(
      "aria-label",
      state.audioMuted ? String(UI.sound_enable || "") : String(UI.sound_mute || ""),
    );
  }

  function initAudio() {
    if (!window.AudioContext && !window.webkitAudioContext) {
      nodes.soundToggle?.setAttribute("hidden", "hidden");
      return;
    }
    try {
      const AudioCtor = window.AudioContext || window.webkitAudioContext;
      state.audioContext = new AudioCtor();
      state.audioNeedsUnlock = state.audioContext.state !== "running";
      if (nodes.soundPrompt) nodes.soundPrompt.hidden = !state.audioNeedsUnlock || state.audioPromptDismissed;
    } catch (_error) {
      state.audioContext = null;
      nodes.soundToggle?.setAttribute("hidden", "hidden");
    }
    updateSoundButton();
  }

  function dismissSoundPrompt() {
    state.audioPromptDismissed = true;
    if (nodes.soundPrompt) nodes.soundPrompt.hidden = true;
  }

  async function ensureAudioUnlocked(interactive) {
    if (!state.audioContext || !state.audioNeedsUnlock || state.audioMuted) return false;
    if (!interactive) {
      if (nodes.soundPrompt) nodes.soundPrompt.hidden = state.audioPromptDismissed;
      return false;
    }
    try {
      await state.audioContext.resume();
      state.audioNeedsUnlock = state.audioContext.state !== "running";
      if (!state.audioNeedsUnlock) dismissSoundPrompt();
      else if (nodes.soundPrompt) nodes.soundPrompt.hidden = state.audioPromptDismissed;
      return !state.audioNeedsUnlock;
    } catch (_error) {
      if (nodes.soundPrompt) nodes.soundPrompt.hidden = state.audioPromptDismissed;
      return false;
    }
  }

  function playTone(kind) {
    if (!state.audioContext || state.audioMuted || state.audioContext.state !== "running") return;
    const oscillator = state.audioContext.createOscillator();
    const gain = state.audioContext.createGain();
    const now = state.audioContext.currentTime;
    oscillator.type = kind === "intro" ? "triangle" : "sine";
    oscillator.frequency.value = kind === "cruise" ? 70 : kind === "survey" ? 118 : 154;
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(kind === "intro" ? 0.032 : 0.018, now + 0.03);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + (kind === "intro" ? 0.9 : 0.32));
    oscillator.connect(gain);
    gain.connect(state.audioContext.destination);
    oscillator.start(now);
    oscillator.stop(now + (kind === "intro" ? 0.95 : 0.38));
  }

  function persistSubmitDraft() {
    writeStoredJson(SUBMIT_DRAFT_KEY, {
      submitName: String(nodes.submitName?.value || ""),
      submitTitle: String(nodes.submitTitle?.value || ""),
      submitContent: String(nodes.submitContent?.value || ""),
      uploadName: String(nodes.uploadName?.value || ""),
      textStatus: String(nodes.submitTextStatus?.textContent || ""),
      fileStatus: String(nodes.submitFileStatus?.textContent || ""),
    });
  }

  function restoreSubmitDraft() {
    const snapshot = readStoredJson(SUBMIT_DRAFT_KEY, null);
    if (!snapshot || typeof snapshot !== "object") return;
    if (nodes.submitName) nodes.submitName.value = String(snapshot.submitName || "");
    if (nodes.submitTitle) nodes.submitTitle.value = String(snapshot.submitTitle || "");
    if (nodes.submitContent) nodes.submitContent.value = String(snapshot.submitContent || "");
    if (nodes.uploadName) nodes.uploadName.value = String(snapshot.uploadName || "");
    if (nodes.submitTextStatus) nodes.submitTextStatus.textContent = String(snapshot.textStatus || "");
    if (nodes.submitFileStatus) nodes.submitFileStatus.textContent = String(snapshot.fileStatus || "");
  }

  function enhanceFilePickers() {
    document.querySelectorAll("[data-file-picker]").forEach((picker) => {
      const input = picker.querySelector(".universe-file-input");
      const status = picker.querySelector("[data-file-picker-status]");
      if (!input || !status) return;
      const update = () => {
        const files = Array.from(input.files || []);
        picker.dataset.hasSelection = files.length ? "true" : "false";
        if (!files.length) {
          status.textContent = String(status.dataset.emptyLabel || "");
          return;
        }
        const prefix = String(status.dataset.selectedPrefix || "");
        const suffix = String(status.dataset.selectedSuffix || "");
        const summary = files
          .slice(0, 2)
          .map((file) => file.name)
          .join(", ");
        status.textContent = `${prefix} ${files.length} ${suffix} · ${summary}`;
      };
      input.addEventListener("change", update);
      update();
    });
  }

  function weightedChoice(items) {
    if (!Array.isArray(items) || !items.length) return null;
    const total = items.reduce((sum, item) => sum + Math.max(Number(item.importance || 0), 1), 0);
    let cursor = Math.random() * total;
    for (const item of items) {
      cursor -= Math.max(Number(item.importance || 0), 1);
      if (cursor <= 0) return item;
    }
    return items[0];
  }

  function pickPoeticLine() {
    const lines = Array.isArray(state.bootstrap?.poetic_lines) ? state.bootstrap.poetic_lines : [];
    if (!lines.length) return nodes.introLine?.textContent || "";
    return String(lines[Math.floor(Math.random() * lines.length)] || "");
  }

  function pickIntroCandidate() {
    const candidates = Array.isArray(state.bootstrap?.intro_candidates) ? state.bootstrap.intro_candidates : [];
    return weightedChoice(candidates);
  }

  function applyIntroCandidate(candidate) {
    if (!candidate) return;
    if (nodes.introTargetTitle) nodes.introTargetTitle.textContent = String(candidate.title || candidate.name || "");
    if (nodes.introTargetSummary) nodes.introTargetSummary.textContent = String(candidate.summary || "");
    if (state.graphApi?.stageNodeById) {
      state.graphApi.stageNodeById(String(candidate.graph_ref || candidate.name || ""));
    }
  }

  function setIntroPhase(phase) {
    if (nodes.intro) nodes.intro.dataset.phase = phase;
    if (nodes.introPhaseCopy) {
      const key = `intro_phase_${phase}`;
      nodes.introPhaseCopy.textContent = String(UI[key] || "");
    }
  }

  function clearIntroTimers() {
    state.introTimers.forEach((timer) => window.clearTimeout(timer));
    state.introTimers = [];
  }

  function finishIntro() {
    clearIntroTimers();
    if (!nodes.intro) {
      applyInitialIntent();
      return;
    }
    nodes.intro.hidden = true;
    state.introPlaying = false;
    if (!state.reducedMotion) {
      nodes.cinematicBars.hidden = true;
    }
    window.localStorage?.setItem(INTRO_SEEN_KEY, "true");
    setPortalState("roaming");
    setPortalMessage(UI.home_ready || "");
    applyInitialIntent();
  }

  function playIntro(force) {
    if (!nodes.intro) {
      applyInitialIntent();
      return;
    }
    if (pageData.pagePreset === "immersive" && !force) {
      nodes.intro.hidden = true;
      applyInitialIntent();
      return;
    }
    const seen = window.localStorage?.getItem(INTRO_SEEN_KEY) === "true";
    if (seen && !force) {
      nodes.intro.hidden = true;
      applyInitialIntent();
      return;
    }
    clearIntroTimers();
    state.introPlaying = true;
    setPortalState("intro");
    stopCruise({ keepPosition: true, immediate: true });
    nodes.intro.hidden = false;
    nodes.cinematicBars.hidden = false;
    if (nodes.introLine) nodes.introLine.textContent = pickPoeticLine();
    applyIntroCandidate(pickIntroCandidate());
    if (state.reducedMotion) {
      setIntroPhase("lock");
      state.introTimers.push(window.setTimeout(finishIntro, INTRO_REDUCED_MS));
      return;
    }
    setIntroPhase("void");
    playTone("intro");
    state.introTimers.push(window.setTimeout(() => setIntroPhase("approach"), 240));
    state.introTimers.push(window.setTimeout(() => setIntroPhase("lock"), 1180));
    state.introTimers.push(window.setTimeout(() => setIntroPhase("hud"), 1980));
    state.introTimers.push(window.setTimeout(finishIntro, INTRO_DURATION_MS));
  }

  async function loadBootstrap() {
    state.bootstrap = await fetchJson(pageData.bootstrapApi);
  }

  function homeSceneForBudget() {
    return state.budget === "immersive" ? "full" : "home";
  }

  function focusSceneForBudget() {
    return state.budget === "safe" ? "home" : "full";
  }

  async function requestGraphPayload({ scene, focus } = {}) {
    const url = withQuery(pageData.graphApiBase || pageData.graphApi, {
      scene: scene || undefined,
      focus: focus || undefined,
    });
    return fetchJson(url);
  }

  function mountGraph(payload) {
    if (!window.SedimentGraph?.mountPortalGraph || !nodes.stage || !payload) return;
    state.graphController = window.SedimentGraph.mountPortalGraph(nodes.stage, payload, {
      pageData,
      motionProfile: state.reducedMotion ? "reduced" : "full",
      onSelect: handleGraphSelect,
      onBackgroundSelect: handleBackgroundSelect,
    });
    state.graphApi = nodes.stage.__sedimentGraphApi || null;
    state.graphApi?.setMotionProfile?.(state.reducedMotion ? "reduced" : "full");
  }

  function replaceGraphPayload(payload, { scene, rememberHome = false } = {}) {
    state.graphPayload = payload;
    state.currentScene = String(scene || payload?.scene_mode || "home");
    if (rememberHome) {
      state.homeGraphPayload = payload;
    }
    mountGraph(payload);
    if (state.lastSearchResults.length && state.graphApi?.setSearchMatches) {
      state.graphApi.setSearchMatches(state.lastSearchResults.map((item) => item.graph_ref || ""));
    }
  }

  async function loadInitialGraph() {
    const scene = pageData.pagePreset === "immersive" ? "full" : homeSceneForBudget();
    const payload = await requestGraphPayload({ scene });
    replaceGraphPayload(payload, { scene, rememberHome: true });
  }

  async function restoreHomeGraph() {
    const scene = homeSceneForBudget();
    if (state.homeGraphPayload && state.currentScene === scene) return;
    const payload = state.homeGraphPayload && scene === homeSceneForBudget() ? state.homeGraphPayload : await requestGraphPayload({ scene });
    replaceGraphPayload(payload, { scene, rememberHome: true });
  }

  async function reloadGraphForCurrentContext() {
    const activeFocus = state.focusRef;
    if (activeFocus) {
      await loadFocusedGraph(activeFocus, { reselect: Boolean(state.selectedNode) });
      return;
    }
    state.homeGraphPayload = null;
    await restoreHomeGraph();
  }

  function openSurvey(query, { preserveResults = false } = {}) {
    setPanelOpen("survey", nodes.survey, "survey_open");
    state.graphApi?.setViewMode?.("survey", { immediate: state.reducedMotion });
    if (typeof query === "string" && nodes.searchInput) nodes.searchInput.value = query;
    if (!preserveResults && typeof query === "string") {
      runSearch(query).catch(() => {
        setSearchStatus(UI.unknown_error || "");
      });
    }
    window.setTimeout(() => nodes.searchInput?.focus(), 30);
    playTone("survey");
  }

  function closeSurvey({ preserveResults = true } = {}) {
    closePanel(nodes.survey);
    if (state.activePanel === "survey") setActivePanel("");
    if (state.graphApi?.getViewMode?.() === "survey") {
      state.graphApi.setViewMode("roam", { immediate: state.reducedMotion });
    }
    if (!preserveResults) {
      state.lastSearchResults = [];
      renderSearchResults([]);
      if (state.graphApi?.setSearchMatches) state.graphApi.setSearchMatches([]);
    }
    if (!state.selectedNode && !state.activePanel) {
      setPortalState("roaming");
      scheduleIdleCruise();
    }
  }

  function openSubmitPanel() {
    setPanelOpen("submit", nodes.submitPanel, "submit_open");
  }

  function openTutorialPanel() {
    setPanelOpen("tutorial", nodes.tutorialPanel, "tutorial_open");
  }

  function openSystemPanel() {
    setPanelOpen("system", nodes.systemPanel, "system_overlay_open");
    renderSystemCapabilities();
  }

  function setReaderExpanded(expanded) {
    if (!nodes.spatialCardReaderPanel || !nodes.spatialCardExpand) return;
    nodes.spatialCardReaderPanel.hidden = !expanded;
    nodes.spatialCardExpand.hidden = expanded;
    setPortalState(expanded ? "reader_open" : "focus_active");
  }

  function clearFocusSelection() {
    state.selectedNode = null;
    state.selectedPayload = null;
    state.suppressBackgroundSelect = true;
    state.graphApi?.clearSelection?.();
    window.setTimeout(() => {
      state.suppressBackgroundSelect = false;
    }, 0);
  }

  async function closeFocusedExperience({ restoreSource = true } = {}) {
    cancelOverlayTracking();
    nodes.spatialCard.hidden = true;
    clearFocusSelection();
    const priorSource = state.focusSource;
    state.focusRef = "";
    state.focusSource = "";
    if (state.currentScene !== homeSceneForBudget()) {
      await restoreHomeGraph();
    }
    if (restoreSource && priorSource === "survey") {
      openSurvey(nodes.searchInput?.value || state.lastSearchQuery || "", { preserveResults: true });
      return;
    }
    if (!state.activePanel) {
      setPortalState("roaming");
      scheduleIdleCruise();
    }
  }

  function chip(label) {
    return `<span class="universe-meta-chip">${escapeHtml(label)}</span>`;
  }

  function publicTaxonomy(entry) {
    const nodeType = String(entry?.node_type || "").trim();
    const status = String(entry?.status || entry?.review_state || "").trim().toLowerCase();
    if (nodeType === "cluster_anchor") {
      return { type: UI.public_type_basin || "Knowledge basin", status: UI.public_status_navigation || "Navigation anchor" };
    }
    if (nodeType === "index_segment") {
      return { type: UI.public_type_navigation || "Navigation structure", status: UI.public_status_navigation || "Navigation anchor" };
    }
    if (nodeType === "query_cluster") {
      return { type: UI.public_type_question || "Question constellation", status: UI.public_status_question || "Awaiting response" };
    }
    if (nodeType === "insight_proposal") {
      return { type: UI.public_type_forming || "Forming constellation", status: UI.public_status_forming || "Forming" };
    }
    if (["draft", "proposed", "placeholder", "captured", "soft"].includes(status)) {
      return { type: UI.public_type_forming || "Forming constellation", status: UI.public_status_forming || "Forming" };
    }
    return { type: UI.public_type_stable || "Stable constellation", status: UI.public_status_stable || "Stable" };
  }

  function renderCompactCard(node, detail) {
    const related = Array.isArray(detail?.structured?.related_links) ? detail.structured.related_links : [];
    const aliases = Array.isArray(detail?.structured?.aliases) ? detail.structured.aliases : [];
    const summary = String(detail?.structured?.summary || node?.summary || detail?.summary || "");
    const why = String(node?.reason || summary || "");
    return [
      '<section class="universe-detail-block">',
      `<strong>${escapeHtml(UI.graph_focus_reason || "")}</strong>`,
      `<div class="universe-markdown">${renderMarkdown(why)}</div>`,
      "</section>",
      '<section class="universe-detail-block">',
      `<strong>${escapeHtml(UI.graph_focus_summary || "")}</strong>`,
      `<div class="universe-markdown">${renderMarkdown(summary)}</div>`,
      "</section>",
      related.length
        ? `<section class="universe-detail-block"><strong>${escapeHtml(UI.entry_related || "")}</strong><div class="universe-chip-row">${related.map((item) => chip(item)).join("")}</div></section>`
        : "",
      aliases.length
        ? `<section class="universe-detail-block"><strong>${escapeHtml(UI.entry_aliases || "")}</strong><div class="universe-chip-row">${aliases.map((item) => chip(item)).join("")}</div></section>`
        : "",
    ].join("");
  }

  function renderEntrySections(detail) {
    const sections = Array.isArray(detail?.structured?.canonical_sections) ? detail.structured.canonical_sections : [];
    if (!sections.length) {
      nodes.entrySections.innerHTML = `<div class="universe-empty-state">${escapeHtml(UI.entry_section_empty || "")}</div>`;
      return;
    }
    nodes.entrySections.innerHTML = sections
      .map(
        (section) => `
          <article class="universe-detail-block">
            <strong>${escapeHtml(section.name || "")}</strong>
            <div class="universe-markdown">${renderMarkdown(section.content || "")}</div>
          </article>
        `,
      )
      .join("");
  }

  function renderEntrySignals(detail, node) {
    const blocks = [];
    const structured = detail?.structured || {};
    const metadata = detail?.metadata || {};
    const validation = structured.validation_cues || detail?.validation || {};
    const related = Array.isArray(structured.related_links) ? structured.related_links : [];
    const sources = Array.isArray(structured.sources) ? structured.sources : [];
    const taxonomy = publicTaxonomy({
      node_type: node?.node_type,
      status: structured.status || metadata.status || node?.status,
    });

    blocks.push(
      `<article class="universe-signal-block"><strong>${escapeHtml(UI.detail_type || "")}</strong><span>${escapeHtml(taxonomy.type)}</span></article>`,
    );
    blocks.push(
      `<article class="universe-signal-block"><strong>${escapeHtml(UI.detail_status || "")}</strong><span>${escapeHtml(taxonomy.status)}</span></article>`,
    );
    if (related.length) {
      blocks.push(
        `<article class="universe-signal-block"><strong>${escapeHtml(UI.entry_related || "")}</strong><div class="universe-chip-row">${related.map((item) => chip(item)).join("")}</div></article>`,
      );
    }
    if (sources.length) {
      blocks.push(
        `<article class="universe-signal-block"><strong>${escapeHtml(UI.entry_sources || "")}</strong><div class="universe-chip-row">${sources.map((item) => chip(item)).join("")}</div></article>`,
      );
    }
    blocks.push(
      `<article class="universe-signal-block"><strong>${escapeHtml(UI.entry_validation || "")}</strong><span>${validation.valid ? escapeHtml(UI.detail_valid || "") : escapeHtml(UI.detail_fail || "")}</span></article>`,
    );
    nodes.entrySignals.innerHTML = blocks.join("");
  }

  function populateReader(node, payload) {
    const detail = payload?.detail || payload?.node?.details || {};
    const structured = detail?.structured || {};
    const body = structured.residual_markdown || detail?.content || payload?.node?.summary || "";
    const taxonomy = publicTaxonomy({
      node_type: node?.node_type,
      status: structured.status || detail?.status || node?.status,
    });
    renderEntrySections(detail);
    renderEntrySignals(detail, node);
    nodes.entryView.innerHTML = renderMarkdown(body);
    nodes.spatialCardTitle.textContent = String(structured.title || detail?.name || node?.label || node?.id || "");
    nodes.spatialCardSubtitle.textContent = [taxonomy.type, taxonomy.status].filter(Boolean).join(" · ");
    nodes.spatialCardCompact.innerHTML = renderCompactCard(node, detail);
  }

  async function loadNodeDetail(node) {
    const nodeRef = encodeURIComponent(String(node?.id || node?.node_ref || ""));
    const payload = await fetchJson(`${pageData.nodeApiPrefix}${nodeRef}?lang=${encodeURIComponent(locale)}`);
    state.selectedPayload = payload;
    populateReader(node, payload);
    setReaderExpanded(state.pendingFocusMode !== "compact");
    nodes.spatialCard.hidden = false;
    setPortalMessage(`${UI.entry_open || ""}${String(node?.label || node?.id || "")}`);
    ensureOverlayTracking();
  }

  function focusCandidates(nodeRef) {
    const normalized = String(nodeRef || "").trim();
    if (!normalized) return [];
    if (normalized.includes("::")) return [normalized];
    return [`entry::${normalized}`, normalized];
  }

  async function loadFocusedGraph(nodeRef, { reselect = true } = {}) {
    const normalized = String(nodeRef || "").trim();
    if (!normalized) return false;
    const payload = await requestGraphPayload({
      scene: focusSceneForBudget(),
      focus: normalized,
    });
    replaceGraphPayload(payload, { scene: "focus", rememberHome: false });
    state.focusRef = normalized;
    if (!reselect) return true;
    return focusCandidates(normalized).some((candidate) => state.graphApi?.selectNodeById?.(candidate));
  }

  async function focusNodeFlow(nodeRef, { mode = "expanded", source = "graph" } = {}) {
    const normalized = String(nodeRef || "").trim();
    if (!normalized) return false;
    stopCruise({ keepPosition: true, immediate: true });
    state.focusSource = source;
    state.pendingFocusMode = mode;
    if (state.graphApi?.setSearchMatches) state.graphApi.setSearchMatches([normalized]);
    const selected = focusCandidates(normalized).some((candidate) => state.graphApi?.selectNodeById?.(candidate));
    if (selected) return true;
    return loadFocusedGraph(normalized, { reselect: true });
  }

  async function handleGraphSelect(node) {
    if (!node) return;
    state.selectedNode = node;
    state.focusRef = String(node.id || "");
    if (state.cruising) {
      setPortalState("idle_cruise");
      ensureOverlayTracking();
      return;
    }
    if (state.activePanel === "survey") {
      closeSurvey({ preserveResults: true });
    }
    closeOtherPanels({ keepSpatialCard: true });
    try {
      await loadNodeDetail(node);
    } catch (_error) {
      nodes.spatialCard.hidden = false;
      nodes.spatialCardTitle.textContent = String(node.label || node.id || "");
      nodes.spatialCardSubtitle.textContent = "";
      nodes.spatialCardCompact.innerHTML = `<div class="universe-empty-state">${escapeHtml(UI.detail_empty || "")}</div>`;
      setReaderExpanded(false);
      ensureOverlayTracking();
    } finally {
      state.pendingFocusMode = "expanded";
    }
  }

  function handleBackgroundSelect() {
    if (state.suppressBackgroundSelect) return;
    if (state.activePanel === "survey") return;
    closeFocusedExperience({ restoreSource: true }).catch(() => {
      setPortalMessage(UI.unknown_error || "");
    });
  }

  function renderSearchResults(items) {
    if (!nodes.searchResults) return;
    if (!Array.isArray(items) || !items.length) {
      nodes.searchResults.innerHTML = `<div class="universe-empty-state">${escapeHtml(UI.search_empty || "")}</div>`;
      return;
    }
    nodes.searchResults.innerHTML = items
      .map((item) => {
        const aliases = Array.isArray(item.aliases) ? item.aliases : [];
        const taxonomy = publicTaxonomy(item);
        return `
          <button
            type="button"
            class="universe-result-card"
            data-node-ref="${escapeHtml(item.graph_ref || "")}"
            data-entry-name="${escapeHtml(item.name || "")}"
          >
            <div class="universe-result-heading">
              <strong>${escapeHtml(item.title || item.name || "")}</strong>
              ${chip(taxonomy.type)}
            </div>
            <p class="universe-copy-muted">${escapeHtml(item.summary || item.snippet || "")}</p>
            <div class="universe-chip-row">
              ${chip(taxonomy.status)}
              ${aliases.slice(0, 2).map((alias) => chip(alias)).join("")}
            </div>
          </button>
        `;
      })
      .join("");
  }

  function renderSuggestions(items) {
    if (!nodes.searchSuggestions) return;
    if (!Array.isArray(items) || !items.length) {
      nodes.searchSuggestions.hidden = true;
      nodes.searchSuggestions.innerHTML = "";
      return;
    }
    nodes.searchSuggestions.hidden = false;
    nodes.searchSuggestions.innerHTML = items
      .map((item, index) => {
        const taxonomy = publicTaxonomy(item);
        return `
          <button
            type="button"
            class="universe-search-suggestion"
            data-node-ref="${escapeHtml(item.graph_ref || "")}"
            data-entry-name="${escapeHtml(item.name || "")}"
            aria-selected="${index === state.suggestionIndex ? "true" : "false"}"
          >
            <strong>${escapeHtml(item.title || item.name || "")}</strong>
            <span>${escapeHtml(taxonomy.type)} · ${escapeHtml(item.summary || "")}</span>
          </button>
        `;
      })
      .join("");
  }

  async function requestSuggestions(query) {
    const normalized = String(query || "").trim();
    state.suggestionRequestId += 1;
    const requestId = state.suggestionRequestId;
    if (!normalized) {
      state.suggestions = [];
      state.suggestionIndex = -1;
      renderSuggestions([]);
      return;
    }
    const payload = await fetchJson(`${pageData.searchSuggestApi}&q=${encodeURIComponent(normalized)}`);
    if (requestId !== state.suggestionRequestId) return;
    state.suggestions = Array.isArray(payload.suggestions) ? payload.suggestions : [];
    state.suggestionIndex = -1;
    renderSuggestions(state.suggestions);
  }

  async function runSearch(query) {
    const normalized = String(query || "").trim();
    state.lastSearchQuery = normalized;
    state.suggestionRequestId += 1;
    state.suggestions = [];
    state.suggestionIndex = -1;
    if (nodes.searchSuggestions) nodes.searchSuggestions.hidden = true;
    if (!normalized) {
      setSearchStatus(UI.search_prompt || "");
      state.lastSearchResults = [];
      renderSearchResults([]);
      if (state.graphApi?.setSearchMatches) state.graphApi.setSearchMatches([]);
      return;
    }
    setSearchStatus(UI.search_busy || "");
    const payload = await fetchJson(`${pageData.searchApi}&q=${encodeURIComponent(normalized)}`);
    const items = Array.isArray(payload?.results) ? payload.results : [];
    state.lastSearchResults = items;
    renderSearchResults(items);
    if (state.graphApi?.setSearchMatches) {
      state.graphApi.setSearchMatches(items.map((item) => item.graph_ref || ""));
    }
    setSearchStatus(
      items.length
        ? `${UI.found_prefix || ""} ${items.length} ${UI.found_suffix || ""}`
        : String(UI.search_empty || ""),
    );
  }

  function focusNodeFromSearch(nodeRef) {
    closeSurvey({ preserveResults: true });
    focusNodeFlow(nodeRef, { mode: "expanded", source: "survey" }).catch(() => {
      setPortalMessage(UI.unknown_error || "");
    });
  }

  function buildCruiseQueue() {
    const nodesList = state.graphApi?.nodes ? state.graphApi.nodes() : [];
    const lanes = {
      stable: [],
      forming: [],
      question: [],
      navigation: [],
    };
    nodesList.forEach((node) => {
      if (String(node.node_type || "") === "cluster_anchor") return;
      const taxonomy = publicTaxonomy(node);
      if (taxonomy.type === UI.public_type_forming) lanes.forming.push(node);
      else if (taxonomy.type === UI.public_type_question) lanes.question.push(node);
      else if (taxonomy.type === UI.public_type_navigation) lanes.navigation.push(node);
      else lanes.stable.push(node);
    });
    Object.values(lanes).forEach((items) => {
      items.sort((left, right) => Number(right.energy || 0) - Number(left.energy || 0));
    });
    const queue = [];
    const maxLength = Math.max(...Object.values(lanes).map((items) => items.length), 0);
    for (let index = 0; index < maxLength; index += 1) {
      ["stable", "forming", "question", "navigation"].forEach((lane) => {
        if (lanes[lane][index]) queue.push(lanes[lane][index]);
      });
    }
    state.cruiseQueue = queue.length ? queue : nodesList.filter((node) => String(node.node_type || "") !== "cluster_anchor");
    state.cruiseIndex = 0;
  }

  function showCruiseSummary(node) {
    if (!nodes.cruiseSummary) return;
    const taxonomy = publicTaxonomy(node);
    nodes.cruiseSummary.hidden = false;
    nodes.cruiseTitle.textContent = `${String(node.label || node.id || "")} · ${taxonomy.type}`;
    nodes.cruiseText.textContent = String(node.summary || UI.graph_story_empty || "");
    ensureOverlayTracking();
  }

  function scheduleCruise() {
    window.clearTimeout(state.cruiseTimer);
    if (!state.cruising || state.cruisePaused) return;
    state.cruiseTimer = window.setTimeout(stepCruise, CRUISE_STEP_MS);
  }

  function stepCruise() {
    if (!state.cruising || !state.cruiseQueue.length) return;
    const node = state.cruiseQueue[state.cruiseIndex % state.cruiseQueue.length];
    state.cruiseIndex += 1;
    if (!node) return;
    state.cruiseCurrentNode = node;
    showCruiseSummary(node);
    state.pendingFocusMode = "compact";
    state.graphApi?.setViewMode?.("cruise", { immediate: state.reducedMotion });
    state.graphApi?.selectNodeById(String(node.id || ""));
    playTone("cruise");
    scheduleCruise();
  }

  function startCruise() {
    if (!state.graphApi) return;
    closeOtherPanels();
    buildCruiseQueue();
    state.cruising = true;
    state.cruisePaused = false;
    nodes.cinematicBars.hidden = state.reducedMotion;
    setPortalState("idle_cruise");
    updateHudState();
    stepCruise();
  }

  function stopCruise({ keepPosition = true } = {}) {
    state.cruising = false;
    state.cruisePaused = false;
    state.cruiseCurrentNode = null;
    window.clearTimeout(state.cruiseTimer);
    nodes.cinematicBars.hidden = true;
    if (nodes.cruiseSummary) nodes.cruiseSummary.hidden = true;
    state.graphApi?.setViewMode?.("roam", { immediate: state.reducedMotion });
    if (!keepPosition) clearFocusSelection();
    updateHudState();
    cancelOverlayTracking();
  }

  function toggleCruisePause() {
    state.cruisePaused = !state.cruisePaused;
    if (nodes.cruisePause) {
      nodes.cruisePause.textContent = state.cruisePaused
        ? String(UI.cruise_next || "Resume")
        : String(UI.cruise_pause || "Pause");
    }
    if (!state.cruisePaused) scheduleCruise();
    else window.clearTimeout(state.cruiseTimer);
  }

  function scheduleIdleCruise() {
    window.clearTimeout(state.idleTimer);
    if (state.activePanel || state.introPlaying || state.selectedNode) return;
    state.idleTimer = window.setTimeout(() => {
      if (!state.cruising) startCruise();
    }, IDLE_CRUISE_MS);
  }

  function registerActivity() {
    if (state.cruising) stopCruise({ keepPosition: true });
    if (!state.activePanel && !state.selectedNode) scheduleIdleCruise();
  }

  async function applyInitialIntent() {
    if (pageData.initialIntent === "survey") {
      openSurvey(pageData.initialQuery || "");
      return;
    }
    if (pageData.initialIntent === "submit") {
      openSubmitPanel();
      return;
    }
    if (pageData.initialIntent === "tutorial") {
      openTutorialPanel();
      return;
    }
    if (pageData.initialIntent === "entry" && pageData.entryName) {
      await focusNodeFlow(`entry::${pageData.entryName}`, { mode: "expanded", source: "route" });
      return;
    }
    if (pageData.pagePreset === "immersive") {
      setHudExpanded(false);
    }
    setPortalState("roaming");
    scheduleIdleCruise();
  }

  function formatSubmissionStatus(payload, fallbackMessage) {
    const receipt = String(payload?.id || payload?.item_id || "").trim();
    const parts = [String(fallbackMessage || "").trim()];
    if (receipt) {
      parts.push(`${String(UI.submission_receipt_prefix || "Receipt")} ${receipt}`);
    }
    return parts.filter(Boolean).join(" ");
  }

  async function suggestSubmissionFocus(query) {
    const normalized = String(query || "").trim();
    if (!normalized) return null;
    try {
      const payload = await fetchJson(`${pageData.searchApi}&q=${encodeURIComponent(normalized)}`);
      const results = Array.isArray(payload?.results) ? payload.results : [];
      return results[0] || null;
    } catch (_error) {
      return null;
    }
  }

  function updateSubmitFollowup(container, suggestion) {
    if (!container) return;
    container.hidden = false;
    if (!nodes.submitTextFocus) return;
    if (!suggestion?.graph_ref) {
      nodes.submitTextFocus.hidden = true;
      nodes.submitTextFocus.dataset.nodeRef = "";
      return;
    }
    nodes.submitTextFocus.hidden = false;
    nodes.submitTextFocus.dataset.nodeRef = String(suggestion.graph_ref || "");
    nodes.submitTextFocus.textContent = `${String(UI.submit_action_focus || UI.submission_target_prefix || "")} · ${String(
      suggestion.title || suggestion.name || "",
    )}`;
  }

  async function handleSubmitText() {
    const title = String(nodes.submitTitle?.value || "").trim();
    const content = String(nodes.submitContent?.value || "").trim();
    const submitterName = String(nodes.submitName?.value || "").trim();
    nodes.submitTextStatus.textContent = String(UI.submit_text_busy || "");
    const payload = await fetchJson(pageData.textSubmitApi, {
      method: "POST",
      body: JSON.stringify({
        title,
        content,
        submitter_name: submitterName,
        submission_type: "concept",
      }),
    });
    const suggestion = await suggestSubmissionFocus(`${title}\n${content}`);
    state.focusSuggestion = suggestion;
    nodes.submitTextStatus.textContent = formatSubmissionStatus(payload, UI.submit_text_success || "");
    setPortalMessage(String(UI.submit_text_success || ""));
    updateSubmitFollowup(nodes.submitTextFollowup, suggestion);
    persistSubmitDraft();
  }

  async function handleSubmitFile() {
    const submitterName = String(nodes.uploadName?.value || "").trim();
    const files = [...Array.from(nodes.uploadFile?.files || []), ...Array.from(nodes.uploadFolder?.files || [])];
    if (!files.length) {
      nodes.submitFileStatus.textContent = String(UI.file_required || "");
      return;
    }
    nodes.submitFileStatus.textContent = String(UI.submit_file_busy || "");
    const uploads = await Promise.all(
      files.map(async (file) => {
        const buffer = await file.arrayBuffer();
        let binary = "";
        const bytes = new Uint8Array(buffer);
        for (let index = 0; index < bytes.length; index += 1) {
          binary += String.fromCharCode(bytes[index]);
        }
        return {
          filename: file.name,
          relative_path: file.webkitRelativePath || file.name,
          mime_type: file.type || "",
          content_base64: window.btoa(binary),
        };
      }),
    );
    const payload = await fetchJson(pageData.fileSubmitApi, {
      method: "POST",
      body: JSON.stringify({
        submitter_name: submitterName,
        files: uploads,
      }),
    });
    nodes.submitFileStatus.textContent = formatSubmissionStatus(payload, UI.submit_file_success || "");
    setPortalMessage(String(UI.submit_file_success || ""));
    if (nodes.submitFileFollowup) nodes.submitFileFollowup.hidden = false;
    persistSubmitDraft();
  }

  function syncActionButton(button, active) {
    if (!button) return;
    button.dataset.active = active ? "true" : "false";
    button.setAttribute("aria-pressed", active ? "true" : "false");
  }

  function syncSystemControls() {
    syncActionButton(nodes.systemThemeMidnight, state.theme === "midnight");
    syncActionButton(nodes.systemThemeDawn, state.theme === "dawn");
    syncActionButton(nodes.systemMotionFull, !state.reducedMotion);
    syncActionButton(nodes.systemMotionReduced, state.reducedMotion);
    syncActionButton(nodes.systemBudgetSafe, state.budget === "safe");
    syncActionButton(nodes.systemBudgetStandard, state.budget === "standard");
    syncActionButton(nodes.systemBudgetImmersive, state.budget === "immersive");
  }

  function renderSystemCapabilities() {
    if (!nodes.systemRuntimeMode || !nodes.systemCapabilities) return;
    const labels = {
      immersive: UI.runtime_mode_immersive || "Immersive mode",
      standard: UI.runtime_mode_standard || "Standard mode",
      safe_fallback: UI.runtime_mode_safe_fallback || "Safe fallback",
    };
    nodes.systemRuntimeMode.textContent = String(labels[state.runtimeProfile] || state.runtimeProfile);
    const capabilities = [
      { label: UI.cap_webgpu || "WebGPU", available: Boolean(state.capabilities?.webgpu) },
      { label: UI.cap_worker || "Worker", available: Boolean(state.capabilities?.worker) },
      { label: UI.cap_offscreen || "OffscreenCanvas", available: Boolean(state.capabilities?.offscreenCanvas) },
      { label: UI.cap_pointer || "Pointer", available: Boolean(state.capabilities?.pointer) },
      { label: UI.cap_hover || "Hover", available: Boolean(state.capabilities?.hover) },
      { label: UI.cap_reduced_motion || "Reduced motion", available: state.reducedMotion },
    ];
    nodes.systemCapabilities.innerHTML = capabilities
      .map(
        (item) => `
          <article class="universe-guide-card">
            <strong>${escapeHtml(item.label)}</strong>
            <p class="universe-copy-muted">${escapeHtml(item.available ? UI.cap_available || "Available" : UI.cap_unavailable || "Unavailable")}</p>
          </article>
        `,
      )
      .join("");
  }

  function updateSpatialCardAnchor() {
    if (!state.selectedNode || nodes.spatialCard.hidden) return;
    const projection = state.graphApi?.projectNode?.(String(state.selectedNode.id || ""));
    const side = projection && projection.x > projection.width * 0.58 ? "left" : "right";
    nodes.spatialCard.dataset.side = side;
  }

  function updateCruiseAnchor() {
    if (!state.cruiseCurrentNode || nodes.cruiseSummary.hidden) return;
    const projection = state.graphApi?.projectNode?.(String(state.cruiseCurrentNode.id || ""));
    if (!projection) return;
    const anchorLeft = projection.x > projection.width * 0.58 ? clamp(projection.x - 360, 16, projection.width - 360) : clamp(projection.x + 36, 16, projection.width - 360);
    const anchorTop = clamp(projection.y - 24, 96, projection.height - 240);
    nodes.cruiseSummary.style.setProperty("--universe-summary-left", `${anchorLeft}px`);
    nodes.cruiseSummary.style.setProperty("--universe-summary-top", `${anchorTop}px`);
    nodes.cruiseSummary.dataset.anchor = projection.x > projection.width * 0.58 ? "left-mid" : "right-mid";
  }

  function overlayTrackingTick() {
    updateSpatialCardAnchor();
    updateCruiseAnchor();
    if ((!nodes.spatialCard.hidden && state.selectedNode) || (!nodes.cruiseSummary.hidden && state.cruiseCurrentNode)) {
      state.overlayTrackerFrame = window.requestAnimationFrame(overlayTrackingTick);
    } else {
      state.overlayTrackerFrame = 0;
    }
  }

  function ensureOverlayTracking() {
    if (state.overlayTrackerFrame) return;
    state.overlayTrackerFrame = window.requestAnimationFrame(overlayTrackingTick);
  }

  function cancelOverlayTracking() {
    if (!state.overlayTrackerFrame) return;
    window.cancelAnimationFrame(state.overlayTrackerFrame);
    state.overlayTrackerFrame = 0;
  }

  function bindEvents() {
    nodes.systemToggle?.addEventListener("click", openSystemPanel);
    nodes.systemLocale?.addEventListener("click", () => {
      window.location.assign(currentUrlForLocale(locale === "zh" ? "en" : "zh"));
    });
    nodes.systemThemeMidnight?.addEventListener("click", () => applyTheme("midnight"));
    nodes.systemThemeDawn?.addEventListener("click", () => applyTheme("dawn"));
    nodes.systemMotionFull?.addEventListener("click", () => applyReducedMotion(false));
    nodes.systemMotionReduced?.addEventListener("click", () => applyReducedMotion(true));
    nodes.systemBudgetSafe?.addEventListener("click", () => applyBudget("safe", { reloadGraph: true }).catch(() => {}));
    nodes.systemBudgetStandard?.addEventListener("click", () => applyBudget("standard", { reloadGraph: true }).catch(() => {}));
    nodes.systemBudgetImmersive?.addEventListener("click", () => applyBudget("immersive", { reloadGraph: true }).catch(() => {}));
    nodes.soundToggle?.addEventListener("click", async () => {
      if (state.audioMuted) {
        state.audioMuted = false;
        window.localStorage?.setItem(AUDIO_MUTED_KEY, "false");
        state.audioPromptDismissed = false;
        const unlocked = await ensureAudioUnlocked(true);
        if (!unlocked && nodes.soundPrompt) nodes.soundPrompt.hidden = false;
        playTone("survey");
      } else {
        state.audioMuted = true;
        window.localStorage?.setItem(AUDIO_MUTED_KEY, "true");
        dismissSoundPrompt();
      }
      updateSoundButton();
    });
    nodes.introReplayButton?.addEventListener("click", async () => {
      await ensureAudioUnlocked(true);
      nodes.intro.hidden = false;
      playIntro(true);
    });
    nodes.hudToggle?.addEventListener("click", () => {
      setHudExpanded(nodes.hud?.dataset.expanded !== "true");
    });
    nodes.hudSearch?.addEventListener("click", () => openSurvey(nodes.searchInput?.value || state.lastSearchQuery || ""));
    nodes.hudClear?.addEventListener("click", () => {
      closeOtherPanels();
      closeFocusedExperience({ restoreSource: false }).catch(() => {
        setPortalMessage(UI.unknown_error || "");
      });
    });
    nodes.hudCruise?.addEventListener("click", () => {
      if (state.cruising) stopCruise({ keepPosition: true });
      else startCruise();
    });
    nodes.hudSubmit?.addEventListener("click", openSubmitPanel);
    nodes.hudTutorial?.addEventListener("click", openTutorialPanel);
    nodes.hudSystem?.addEventListener("click", openSystemPanel);
    nodes.surveyClose?.addEventListener("click", () => closeSurvey({ preserveResults: true }));
    nodes.searchButton?.addEventListener("click", () => {
      runSearch(nodes.searchInput?.value || "").catch(() => {
        setSearchStatus(UI.unknown_error || "");
      });
    });
    nodes.searchInput?.addEventListener("input", () => {
      window.clearTimeout(state.suggestionTimer);
      state.suggestionTimer = window.setTimeout(() => {
        requestSuggestions(nodes.searchInput?.value || "").catch(() => {
          renderSuggestions([]);
        });
      }, 120);
    });
    nodes.searchInput?.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (!state.suggestions.length) return;
        state.suggestionIndex = (state.suggestionIndex + 1) % state.suggestions.length;
        renderSuggestions(state.suggestions);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        if (!state.suggestions.length) return;
        state.suggestionIndex = (state.suggestionIndex - 1 + state.suggestions.length) % state.suggestions.length;
        renderSuggestions(state.suggestions);
      } else if (event.key === "Enter") {
        event.preventDefault();
        if (state.suggestionIndex >= 0 && state.suggestions[state.suggestionIndex]) {
          focusNodeFromSearch(state.suggestions[state.suggestionIndex].graph_ref);
        } else {
          runSearch(nodes.searchInput?.value || "").catch(() => {
            setSearchStatus(UI.unknown_error || "");
          });
        }
      }
    });
    nodes.searchSuggestions?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-node-ref]");
      if (!button) return;
      focusNodeFromSearch(button.dataset.nodeRef || "");
      nodes.searchSuggestions.hidden = true;
    });
    nodes.searchResults?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-node-ref]");
      if (!button) return;
      focusNodeFromSearch(button.dataset.nodeRef || "");
    });
    nodes.spatialCard?.addEventListener("click", (event) => {
      const action = event.target.closest("[data-action='close-spatial-card']");
      if (!action) return;
      closeFocusedExperience({ restoreSource: true }).catch(() => {
        setPortalMessage(UI.unknown_error || "");
      });
    });
    nodes.spatialCardExpand?.addEventListener("click", () => setReaderExpanded(true));
    nodes.spatialCardCollapse?.addEventListener("click", () => setReaderExpanded(false));
    nodes.submitTextButton?.addEventListener("click", () => {
      handleSubmitText().catch(() => {
        nodes.submitTextStatus.textContent = String(UI.unknown_error || "");
      });
    });
    nodes.submitFileButton?.addEventListener("click", () => {
      handleSubmitFile().catch(() => {
        nodes.submitFileStatus.textContent = String(UI.unknown_error || "");
      });
    });
    document.querySelectorAll("[data-action='close-submit-panel']").forEach((button) =>
      button.addEventListener("click", () => closeNamedPanel("submit", nodes.submitPanel)),
    );
    document.querySelectorAll("[data-action='close-tutorial-panel']").forEach((button) =>
      button.addEventListener("click", () => closeNamedPanel("tutorial", nodes.tutorialPanel)),
    );
    document.querySelectorAll("[data-action='close-system-panel']").forEach((button) =>
      button.addEventListener("click", () => closeNamedPanel("system", nodes.systemPanel)),
    );
    document.querySelectorAll("[data-action='submit-return-universe']").forEach((button) =>
      button.addEventListener("click", () => {
        closeNamedPanel("submit", nodes.submitPanel);
        scheduleIdleCruise();
      }),
    );
    document.querySelectorAll("[data-action='submit-continue-editing']").forEach((button) =>
      button.addEventListener("click", () => {
        nodes.submitName?.focus();
      }),
    );
    nodes.submitTextFocus?.addEventListener("click", () => {
      const nodeRef = String(nodes.submitTextFocus.dataset.nodeRef || "");
      if (!nodeRef) return;
      closeNamedPanel("submit", nodes.submitPanel);
      focusNodeFlow(nodeRef, { mode: "expanded", source: "submit" }).catch(() => {
        setPortalMessage(UI.unknown_error || "");
      });
    });
    nodes.cruisePause?.addEventListener("click", toggleCruisePause);
    nodes.cruiseNext?.addEventListener("click", stepCruise);
    nodes.cruiseExit?.addEventListener("click", () => stopCruise({ keepPosition: true }));

    [nodes.submitName, nodes.submitTitle, nodes.submitContent, nodes.uploadName].forEach((node) => {
      node?.addEventListener("input", persistSubmitDraft);
    });

    ["pointermove", "pointerdown", "keydown", "wheel", "touchstart"].forEach((eventName) => {
      document.addEventListener(eventName, async () => {
        if (eventName === "pointerdown" || eventName === "touchstart" || eventName === "keydown") {
          const unlocked = await ensureAudioUnlocked(true);
          if (unlocked || eventName !== "pointermove") dismissSoundPrompt();
        }
        registerActivity();
      });
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        if (!nodes.systemPanel.hidden) {
          closeNamedPanel("system", nodes.systemPanel);
          return;
        }
        if (!nodes.tutorialPanel.hidden) {
          closeNamedPanel("tutorial", nodes.tutorialPanel);
          return;
        }
        if (!nodes.submitPanel.hidden) {
          closeNamedPanel("submit", nodes.submitPanel);
          return;
        }
        if (!nodes.spatialCard.hidden) {
          closeFocusedExperience({ restoreSource: true }).catch(() => {
            setPortalMessage(UI.unknown_error || "");
          });
          return;
        }
        if (state.activePanel === "survey") {
          closeSurvey({ preserveResults: true });
          return;
        }
        if (state.cruising) {
          stopCruise({ keepPosition: true });
        }
      }
      if (event.key === "/" && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        openSurvey(nodes.searchInput?.value || state.lastSearchQuery || "");
      }
    });

    window.addEventListener("resize", () => {
      if (showUnsupportedIfNeeded()) return;
      ensureOverlayTracking();
      scheduleIdleCruise();
    });
  }

  async function init() {
    applyTheme(state.theme);
    applyReducedMotion(state.reducedMotion);
    document.documentElement.dataset.renderBudget = state.budget;
    restoreSubmitDraft();
    enhanceFilePickers();
    initAudio();
    syncSystemControls();
    if (showUnsupportedIfNeeded()) return;
    bindEvents();
    await Promise.all([loadBootstrap(), loadInitialGraph()]);
    renderSystemCapabilities();
    playIntro(false);
  }

  init().catch(() => {
    setPortalMessage(UI.unknown_error || "");
  });
})();
