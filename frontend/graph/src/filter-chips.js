export const FILTER_IDS = ["all", "tacit", "canonical", "cluster"];

export function nodeMatchesFilter(node, filterId) {
  const nodeType = String(node?.node_type || "");
  if (filterId === "tacit") {
    return nodeType === "insight_proposal" || String(node?.formation_stage || "") === "condensing";
  }
  if (filterId === "canonical") {
    return nodeType === "canonical_entry";
  }
  if (filterId === "cluster") {
    return nodeType === "query_cluster";
  }
  return true;
}

export function filterCapabilities(payload) {
  const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  const counts = {
    all: nodes.filter((node) => String(node?.node_type || "") !== "cluster_anchor").length,
    tacit: nodes.filter((node) => nodeMatchesFilter(node, "tacit")).length,
    canonical: nodes.filter((node) => nodeMatchesFilter(node, "canonical")).length,
    cluster: nodes.filter((node) => nodeMatchesFilter(node, "cluster")).length,
  };
  return {
    all: { count: counts.all, enabled: counts.all > 0 },
    tacit: { count: counts.tacit, enabled: counts.tacit > 0 },
    canonical: { count: counts.canonical, enabled: counts.canonical > 0 },
    cluster: { count: counts.cluster, enabled: counts.cluster > 0 },
  };
}

export function filterGraphPayload(payload, filterId) {
  if (filterId === "all") return payload;
  const allNodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  const matches = allNodes.filter((node) => nodeMatchesFilter(node, filterId));
  const anchorIds = new Set(matches.map((node) => String(node?.anchor_id || "")).filter(Boolean));
  const nodes = allNodes.filter((node) => {
    const nodeId = String(node?.id || "");
    if (nodeMatchesFilter(node, filterId)) return true;
    return String(node?.node_type || "") === "cluster_anchor" && anchorIds.has(nodeId);
  });
  const visible = new Set(nodes.map((node) => String(node.id || "")));
  const edges = (Array.isArray(payload?.edges) ? payload.edges : []).filter(
    (edge) => visible.has(String(edge.source || "")) && visible.has(String(edge.target || "")),
  );
  return {
    ...payload,
    nodes,
    edges,
    stats: {
      ...(payload?.stats || {}),
      visible_node_count: nodes.length,
      visible_edge_count: edges.length,
    },
  };
}

export function renderChipGroup(container, items, activeId, onSelect) {
  if (!container) return;
  container.textContent = "";
  items.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `graph-hud-chip${item.id === activeId ? " is-active" : ""}`;
    button.textContent = item.label;
    button.dataset.id = item.id;
    button.disabled = Boolean(item.disabled);
    if (item.description) button.title = item.description;
    button.addEventListener("click", () => {
      if (item.disabled) return;
      if (typeof onSelect === "function") onSelect(item.id);
    });
    container.appendChild(button);
  });
}
