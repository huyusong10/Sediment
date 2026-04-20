import { FILTER_IDS, renderChipGroup } from "./filter-chips.js";
import { STRATEGY_IDS } from "./explore-strategy.js";

function budgetOptions(ui, hiddenBudgets) {
  return ["conservative", "medium", "aggressive"]
    .filter((id) => !hiddenBudgets.includes(id))
    .map((id) => ({
      id,
      label: ui[`hud_budget_${id}`] || id,
    }));
}

export function mountUniverseHud({
  ui,
  defaultStrategy,
  defaultFilter,
  defaultBudget,
  hiddenBudgets,
  onSearchInput,
  onSuggestionSelect,
  onHotspot,
  onHotspotPrev,
  onExplore,
  onHistoryBack,
  onStrategyChange,
  onFilterChange,
  onBudgetChange,
  onTrailRun,
  onTrailClear,
}) {
  const searchInput = document.getElementById("portal-graph-search-input");
  const searchStatus = document.getElementById("portal-graph-search-status");
  const searchSuggestions = document.getElementById("portal-graph-search-suggestions");
  const hotspotButton = document.querySelector('[data-action="graph-hotspot"]');
  const hotspotPrevButton = document.querySelector('[data-action="graph-hotspot-prev"]');
  const exploreButton = document.querySelector('[data-action="graph-explore"]');
  const historyButton = document.querySelector('[data-action="graph-history-back"]');
  const trailRunButton = document.querySelector('[data-action="graph-trail-run"]');
  const trailClearButton = document.querySelector('[data-action="graph-trail-clear"]');
  const trailFrom = document.getElementById("portal-graph-trail-from");
  const trailTo = document.getElementById("portal-graph-trail-to");
  const countNode = document.getElementById("portal-graph-count");
  const statusNode = document.getElementById("portal-graph-status");
  const settingsSummary = document.getElementById("portal-graph-settings-summary");
  const budgetContainer = document.getElementById("portal-graph-budget-options");
  const strategyContainer = document.getElementById("portal-graph-strategies");
  const filterContainer = document.getElementById("portal-graph-filters");

  let activeStrategy = defaultStrategy;
  let activeFilter = defaultFilter;
  let activeBudget = defaultBudget;
  let suggestions = [];
  let activeSuggestionIndex = 0;
  let filterItems = FILTER_IDS.map((id) => ({ id, label: ui[`hud_filter_${id}`] || id }));

  if (searchInput) {
    searchInput.placeholder = ui.hud_search_placeholder || "";
    searchInput.addEventListener("input", () => {
      if (typeof onSearchInput === "function") onSearchInput(searchInput.value);
    });
    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" && suggestions.length) {
        event.preventDefault();
        activeSuggestionIndex = Math.min(activeSuggestionIndex + 1, suggestions.length - 1);
        renderSuggestions();
      } else if (event.key === "ArrowUp" && suggestions.length) {
        event.preventDefault();
        activeSuggestionIndex = Math.max(activeSuggestionIndex - 1, 0);
        renderSuggestions();
      } else if (event.key === "Enter" && suggestions.length) {
        event.preventDefault();
        chooseSuggestion(activeSuggestionIndex);
      } else if (event.key === "Escape") {
        clearSuggestions();
      }
    });
  }

  if (hotspotButton) hotspotButton.textContent = ui.hud_hotspot || "";
  if (hotspotPrevButton) hotspotPrevButton.textContent = ui.hud_hotspot_prev || "";
  if (exploreButton) exploreButton.textContent = ui.hud_explore || "";
  if (historyButton) historyButton.textContent = ui.hud_backtrack || "";
  if (trailRunButton) trailRunButton.textContent = ui.hud_trail_run || "";
  if (trailClearButton) trailClearButton.textContent = ui.hud_trail_clear || "";
  if (settingsSummary) settingsSummary.textContent = ui.hud_settings_title || "";
  if (statusNode) statusNode.textContent = ui.hud_status_default || "";

  hotspotButton?.addEventListener("click", () => {
    if (typeof onHotspot === "function") onHotspot();
  });
  hotspotPrevButton?.addEventListener("click", () => {
    if (typeof onHotspotPrev === "function") onHotspotPrev();
  });
  exploreButton?.addEventListener("click", () => {
    if (typeof onExplore === "function") onExplore();
  });
  historyButton?.addEventListener("click", () => {
    if (typeof onHistoryBack === "function") onHistoryBack();
  });
  trailRunButton?.addEventListener("click", () => {
    if (typeof onTrailRun === "function") onTrailRun();
  });
  trailClearButton?.addEventListener("click", () => {
    if (typeof onTrailClear === "function") onTrailClear();
  });

  function chooseSuggestion(index) {
    const item = suggestions[index];
    if (!item) return;
    if (typeof onSuggestionSelect === "function") onSuggestionSelect(item);
    clearSuggestions();
  }

  function renderSuggestions() {
    if (!searchSuggestions) return;
    searchSuggestions.textContent = "";
    suggestions.forEach((item, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `graph-hud-search-option${index === activeSuggestionIndex ? " is-active" : ""}`;
      const title = document.createElement("strong");
      title.textContent = item.title || item.label || item.name || item.id || "";
      const subtitle = document.createElement("span");
      subtitle.className = "subtle";
      subtitle.textContent = item.cluster_label || item.summary || "";
      button.append(title, subtitle);
      button.addEventListener("click", () => chooseSuggestion(index));
      searchSuggestions.appendChild(button);
    });
    searchSuggestions.hidden = suggestions.length === 0;
  }

  function clearSuggestions() {
    suggestions = [];
    activeSuggestionIndex = 0;
    if (searchSuggestions) {
      searchSuggestions.hidden = true;
      searchSuggestions.textContent = "";
    }
  }

  function renderStrategies() {
    renderChipGroup(
      strategyContainer,
      STRATEGY_IDS.map((id) => ({ id, label: ui[`hud_strategy_${id === "cluster_round_robin" ? "cluster" : id}`] || id })),
      activeStrategy,
      (value) => {
        activeStrategy = value;
        renderStrategies();
        if (typeof onStrategyChange === "function") onStrategyChange(value);
      },
    );
  }

  function renderFilters() {
    renderChipGroup(filterContainer, filterItems, activeFilter, (value) => {
      activeFilter = value;
      renderFilters();
      if (typeof onFilterChange === "function") onFilterChange(value);
    });
  }

  renderStrategies();
  renderFilters();

  function renderBudgets() {
    if (!budgetContainer) return;
    renderChipGroup(budgetContainer, budgetOptions(ui, hiddenBudgets || []), activeBudget, (value) => {
      activeBudget = value;
      renderBudgets();
      if (typeof onBudgetChange === "function") onBudgetChange(value);
    });
  }

  renderBudgets();

  return {
    focusSearch() {
      searchInput?.focus();
    },
    setSearchStatus(value) {
      if (searchStatus) searchStatus.textContent = value || "";
    },
    setStatus(value) {
      if (statusNode) statusNode.textContent = value || "";
    },
    showSuggestions(items) {
      suggestions = Array.isArray(items) ? items.slice() : [];
      activeSuggestionIndex = 0;
      renderSuggestions();
    },
    clearSuggestions,
    setCount(visible, total) {
      if (!countNode) return;
      countNode.textContent = (ui.hud_count_template || "{visible}/{total}")
        .replace("{visible}", String(visible))
        .replace("{total}", String(total));
    },
    setTrail(start, end) {
      if (trailFrom) {
        trailFrom.textContent = `${ui.hud_trail_from || "From"}: ${start?.label || "—"}`;
      }
      if (trailTo) {
        trailTo.textContent = `${ui.hud_trail_to || "To"}: ${end?.label || "—"}`;
      }
    },
    setHistoryEnabled(enabled) {
      if (historyButton) historyButton.disabled = !enabled;
    },
    setHotspotEnabled(enabled) {
      if (hotspotButton) hotspotButton.disabled = !enabled;
      if (hotspotPrevButton) hotspotPrevButton.disabled = !enabled;
    },
    setExploreEnabled(enabled) {
      if (exploreButton) exploreButton.disabled = !enabled;
    },
    setFilterAvailability(nextAvailability, reasons = {}) {
      filterItems = FILTER_IDS.map((id) => ({
        id,
        label: ui[`hud_filter_${id}`] || id,
        disabled: id !== "all" && nextAvailability?.[id] === false,
        description: reasons?.[id] || "",
      }));
      if (activeFilter !== "all" && nextAvailability?.[activeFilter] === false) {
        activeFilter = "all";
      }
      renderFilters();
    },
  };
}
