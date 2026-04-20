import "./graph.css";

import ForceGraph3D from "3d-force-graph";
import * as THREE from "three";
import SpriteText from "three-spritetext";

import { installCameraAnchor } from "./camera-anchor.js";
import { pickNextExploreNode } from "./explore-strategy.js";
import { filterCapabilities, filterGraphPayload } from "./filter-chips.js";
import { createHotspotCursor } from "./hotspot-cursor.js";
import { mountUniverseHud } from "./hud.js";
import { installGraphKeyboard } from "./keyboard.js";
import { createKnowledgeTrail } from "./knowledge-trail.js";
import { mountMiniMap } from "./mini-map.js";

const ROLE_COLORS = {
  knowledge_basin: "#92d9ff",
  fresh_ingest: "#6df3ff",
  refreshed_entry: "#8ed1ff",
  recent_canonical: "#90ffe0",
  stable_canonical: "#7ceac8",
  supporting_entry: "#aadfff",
  forming_insight: "#ffbf72",
  forming_context: "#ffd89e",
  reinforced_query: "#ffae63",
  segment_context: "#c8d4ff",
  tacit_pulse: "#ffd37a",
};

const EDGE_COLORS = {
  weak_affinity: "#7f90aa40",
  ask_reinforcement: "#6de3ffcc",
  supports: "#77ffc1cc",
  routes_to: "#ffb56edd",
  belongs_to_cluster: "#7f97c422",
};

const FORMATION_STAGE_LEVEL = {
  dormant: 0.12,
  stable: 0.28,
  stirring: 0.56,
  condensing: 0.74,
  bursting: 1,
};

function readPageData() {
  const script = document.getElementById("sediment-page-data");
  if (!script) return {};
  try {
    return JSON.parse(script.textContent || "{}");
  } catch (_error) {
    return {};
  }
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

function isPortalStaticScene(sceneMode) {
  const mode = String(sceneMode || "");
  return mode.includes("portal") && !mode.includes("admin");
}

function normalizeGraphData(payload, sceneMode) {
  const lockPositions = isPortalStaticScene(sceneMode);
  return {
    nodes: Array.isArray(payload?.nodes)
      ? payload.nodes.map((node) => ({
          ...node,
          ...(lockPositions
            ? {
                fx: Number(node.fx ?? node.x ?? 0),
                fy: Number(node.fy ?? node.y ?? 0),
                fz: Number(node.fz ?? node.z ?? 0),
              }
            : {}),
        }))
      : [],
    links: Array.isArray(payload?.edges)
      ? payload.edges.map((edge, index) => ({
          ...edge,
          id: edge.id || `edge-${index}-${edge.source}-${edge.target}-${edge.edge_type || edge.kind || "link"}`,
        }))
      : [],
  };
}

function roleColor(node) {
  return ROLE_COLORS[node.visual_role] || ROLE_COLORS[node.node_type] || "#8fb4d9";
}

function edgeColor(edge) {
  return EDGE_COLORS[edge.edge_type] || "#86a2c655";
}

function stageLevel(node) {
  return FORMATION_STAGE_LEVEL[String(node.formation_stage || "").trim()] || 0.24;
}

function nodeRadius(node, sceneMode) {
  if (node.node_type === "cluster_anchor") return 5.8;
  const energy = Number(node.energy || 0.25);
  const stability = Number(node.stability || 0.4);
  const stage = stageLevel(node);
  const portalBoost = String(sceneMode || "").includes("portal") ? 0.08 : 0;
  const base = node.node_type === "canonical_entry" ? 1.45 : 1.72;
  return clamp(base + energy * 1.1 + stage * 0.72 + (1 - stability) * 0.42 + portalBoost, 1.3, 4.8);
}

function shouldShowLabel(node, sceneMode) {
  if (node.node_type === "cluster_anchor") return false;
  const energy = Number(node.energy || 0);
  const recentness = Number(node.recentness || 0);
  const stage = stageLevel(node);
  if (String(sceneMode || "").includes("admin")) {
    return energy >= 0.35 || recentness >= 0.45 || node.node_type === "insight_proposal";
  }
  return energy >= 0.44 || recentness >= 0.56 || stage >= 0.56 || ["insight_proposal", "canonical_entry"].includes(node.node_type);
}

function markdownHtml(text) {
  const renderMarkdown = window.SedimentShell?.renderMarkdown;
  if (typeof renderMarkdown === "function") {
    return renderMarkdown(String(text || ""));
  }
  return `<pre>${escapeHtml(String(text || ""))}</pre>`;
}

function graphEventLabel(eventType, ui, locale) {
  const labels = {
    ask_reinforced:
      locale === "zh"
        ? "近期提问正在唤醒多条弱连接，并把它们压缩成更稳定的知识通路。"
        : "Recent questions are waking up weak links and compressing them into a steadier route.",
    proposal_materialized:
      locale === "zh"
        ? "多个碎片刚被压缩成一个新的隐性知识候选。"
        : "Multiple fragments were just compressed into a new latent knowledge proposal.",
    insight_promoted:
      locale === "zh"
        ? "这条知识刚刚稳定下来，进入了正式知识层。"
        : "This knowledge just stabilized and entered the canonical layer.",
    insight_merged:
      locale === "zh"
        ? "这条知识刚被并入既有的稳定结构。"
        : "This knowledge was recently merged into an existing stable structure.",
    ingest_created:
      locale === "zh"
        ? "新知识刚刚被抛入宇宙，正在发光并寻找新的连接。"
        : "New knowledge was just thrown into the universe and is still glowing into place.",
    ingest_updated:
      locale === "zh"
        ? "既有知识刚被刷新，周围的连接也被重新点亮。"
        : "Existing knowledge was refreshed and nearby routes were lit up again.",
  };
  return labels[eventType] || ui.graph_story_empty || "";
}

function localizedNodeType(node, locale) {
  const labels = {
    canonical_entry: locale === "zh" ? "正式知识" : "Canonical knowledge",
    insight_proposal: locale === "zh" ? "形成中的知识" : "Forming insight",
    query_cluster: locale === "zh" ? "问题簇" : "Query cluster",
    index_segment: locale === "zh" ? "索引片段" : "Index segment",
    cluster_anchor: locale === "zh" ? "知识盆地" : "Knowledge basin",
  };
  return labels[String(node?.node_type || "").trim()] || String(node?.node_type || "");
}

function localizedState(node, locale) {
  const raw = String(node?.status || node?.state || node?.formation_stage || "").trim();
  const labels = {
    fact: locale === "zh" ? "事实" : "Fact",
    inferred: locale === "zh" ? "推理成立" : "Inferred",
    proposed: locale === "zh" ? "待确认" : "Proposed",
    observing: locale === "zh" ? "继续观察" : "Observing",
    merged: locale === "zh" ? "已并入" : "Merged",
    promoted: locale === "zh" ? "已提升" : "Promoted",
    captured: locale === "zh" ? "已捕获" : "Captured",
    stable: locale === "zh" ? "已稳定" : "Stable",
    stirring: locale === "zh" ? "正在被唤醒" : "Awakening",
    condensing: locale === "zh" ? "正在凝聚" : "Condensing",
    bursting: locale === "zh" ? "正在迸发" : "Bursting",
  };
  return labels[raw] || raw;
}

function nodeReasonLabel(node, ui, locale) {
  if (String(node.event_type || "").trim()) {
    return graphEventLabel(node.event_type, ui, locale);
  }
  if (node.node_type === "canonical_entry") {
    return locale === "zh"
      ? "这是一条当前仍对附近知识形成有牵引力的稳定知识。"
      : "This is a stable knowledge node that is still pulling nearby formation routes.";
  }
  if (node.node_type === "insight_proposal") {
    return locale === "zh"
      ? "这是一条仍在形成中的候选知识，尚未完全沉淀为正式知识。"
      : "This is a forming insight proposal that has not yet settled into canonical knowledge.";
  }
  return locale === "zh"
    ? "它正在当前的知识形成局部里承担连接或支撑作用。"
    : "It is currently acting as connective or supporting context inside this formation pocket.";
}

function eventHeadline(node, locale) {
  if (node?.event_type) {
    const labels = {
      ask_reinforced: locale === "zh" ? "连接强化中" : "Route reinforcing",
      proposal_materialized: locale === "zh" ? "新知识凝聚中" : "Insight condensing",
      insight_promoted: locale === "zh" ? "正式知识刚形成" : "Recently stabilized",
      insight_merged: locale === "zh" ? "并入稳定结构" : "Merged into stable structure",
      ingest_created: locale === "zh" ? "新知识喷发" : "New knowledge burst",
      ingest_updated: locale === "zh" ? "知识刷新回响" : "Knowledge refreshed",
    };
    return labels[String(node.event_type || "")] || String(node.event_type || "");
  }
  return localizedState(node, locale);
}

function statusLabel(node, locale) {
  return [localizedNodeType(node, locale), localizedState(node, locale)].filter(Boolean).join(" · ");
}

function buildAdjacency(payload) {
  const map = new Map();
  const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  const nodeMap = new Map(nodes.map((node) => [String(node.id || ""), node]));
  (Array.isArray(payload?.edges) ? payload.edges : []).forEach((edge) => {
    const source = String(edge.source || "");
    const target = String(edge.target || "");
    if (!source || !target) return;
    if (!map.has(source)) map.set(source, new Map());
    if (!map.has(target)) map.set(target, new Map());
    map.get(source).set(target, edge);
    map.get(target).set(source, edge);
  });
  return { adjacency: map, nodeMap };
}

function graphLayoutBounds(nodes) {
  const visible = Array.isArray(nodes)
    ? nodes.filter((node) => String(node?.node_type || "") !== "cluster_anchor")
    : [];
  if (!visible.length) {
    return {
      center: { x: 0, y: 0, z: 0 },
      radius: 96,
    };
  }
  const center = visible.reduce(
    (accumulator, node) => ({
      x: accumulator.x + Number(node.x || 0),
      y: accumulator.y + Number(node.y || 0),
      z: accumulator.z + Number(node.z || 0),
    }),
    { x: 0, y: 0, z: 0 },
  );
  center.x /= visible.length;
  center.y /= visible.length;
  center.z /= visible.length;
  const radius =
    visible.reduce((largest, node) => {
      const dx = Number(node.x || 0) - center.x;
      const dy = Number(node.y || 0) - center.y;
      const dz = Number(node.z || 0) - center.z;
      return Math.max(largest, Math.hypot(dx, dy, dz));
    }, 0) + 24;
  return {
    center,
    radius: clamp(radius, 96, 280),
  };
}

function listToChips(items, className = "graph-focus-chip") {
  const values = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!values.length) return "";
  return `<div class="graph-focus-chip-row">${values.map((item) => `<span class="${className}">${escapeHtml(item)}</span>`).join("")}</div>`;
}

function listToBulletList(items) {
  const values = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!values.length) return "";
  return `<ul class="graph-focus-list">${values.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function computeNearbyNodes(node, payload, adjacencyBundle) {
  const currentId = String(node?.id || "");
  if (!currentId) return [];
  const links = adjacencyBundle.adjacency.get(currentId);
  if (!links) return [];
  return Array.from(links.entries())
    .map(([targetId, edge]) => ({
      node: adjacencyBundle.nodeMap.get(targetId),
      edge,
    }))
    .filter((item) => item.node && item.node.node_type !== "cluster_anchor")
    .sort(
      (left, right) =>
        Number(right.edge?.activation || 0) - Number(left.edge?.activation || 0) ||
        Number(right.node?.energy || 0) - Number(left.node?.energy || 0),
    )
    .slice(0, 6)
    .map((item) => item.node?.label || item.node?.id || "")
    .filter(Boolean);
}

function buildFocusBody(node, payload, pageData) {
  const locale = pageData.graphLocale || document.documentElement.dataset.locale || "en";
  const ui = pageData.ui || {};
  const details = node.details || {};
  const adjacencyBundle = buildAdjacency(payload);
  const supportingEntries = Array.isArray(details.supporting_entries) ? details.supporting_entries : [];
  const triggerQueries = Array.isArray(details.trigger_queries) ? details.trigger_queries : [];
  const relatedLinks = Array.isArray(details.related_links) ? details.related_links : [];
  const neighbors = computeNearbyNodes(node, payload, adjacencyBundle);
  const summary = node.summary || details.proposed_answer || details.hypothesis || ui.graph_focus_empty || "";
  const hypothesis = details.hypothesis || "";
  const recentEvent = graphEventLabel(node.event_type, ui, locale);
  const whyItMatters = nodeReasonLabel(node, ui, locale);
  const mergedSupporting = [...supportingEntries, ...relatedLinks].filter(Boolean);

  return `
    <section class="graph-focus-section">
      <div class="graph-focus-section-title">${escapeHtml(ui.graph_focus_reason || (locale === "zh" ? "为什么出现在这里" : "Why it appears here"))}</div>
      <div class="graph-focus-copy">${markdownHtml(whyItMatters)}</div>
    </section>
    ${
      recentEvent
        ? `<section class="graph-focus-section">
            <div class="graph-focus-section-title">${escapeHtml(ui.graph_event || (locale === "zh" ? "最近事件" : "Recent event"))}</div>
            <div class="graph-focus-event">
              <strong>${escapeHtml(eventHeadline(node, locale))}</strong>
              <div class="subtle">${escapeHtml(recentEvent)}</div>
            </div>
          </section>`
        : ""
    }
    <section class="graph-focus-section">
      <div class="graph-focus-section-title">${escapeHtml(ui.graph_focus_summary || (locale === "zh" ? "当前摘要" : "Current summary"))}</div>
      <div class="graph-focus-copy">${markdownHtml(summary || ui.graph_focus_empty || "")}</div>
    </section>
    ${
      hypothesis
        ? `<section class="graph-focus-section">
            <div class="graph-focus-section-title">${escapeHtml(ui.graph_focus_hypothesis || (locale === "zh" ? "形成假设" : "Formation hypothesis"))}</div>
            <div class="graph-focus-copy">${markdownHtml(hypothesis)}</div>
          </section>`
        : ""
    }
    ${
      mergedSupporting.length
        ? `<section class="graph-focus-section">
            <div class="graph-focus-section-title">${escapeHtml(ui.graph_supporting_entries || (locale === "zh" ? "支撑知识" : "Supporting knowledge"))}</div>
            ${listToChips(mergedSupporting)}
          </section>`
        : ""
    }
    ${
      triggerQueries.length
        ? `<section class="graph-focus-section">
            <div class="graph-focus-section-title">${escapeHtml(ui.graph_trigger_queries || (locale === "zh" ? "触发问题" : "Trigger queries"))}</div>
            ${listToBulletList(triggerQueries)}
          </section>`
        : ""
    }
    ${
      neighbors.length
        ? `<section class="graph-focus-section">
            <div class="graph-focus-section-title">${escapeHtml(ui.graph_neighbor_nodes || (locale === "zh" ? "共同形成的邻近节点" : "Nearby co-forming nodes"))}</div>
            ${listToChips(neighbors)}
          </section>`
        : ""
    }
  `;
}

function setupPortalFocusSheet(pageData, payload) {
  const sheet = document.getElementById("portal-graph-focus");
  if (!sheet) {
    return { show() {}, hide() {}, updatePayload() {} };
  }
  const titleNode = document.getElementById("portal-graph-focus-title");
  const subtitleNode = document.getElementById("portal-graph-focus-subtitle");
  const bodyNode = document.getElementById("portal-graph-focus-body");
  const ui = pageData.ui || {};
  let currentPayload = payload;

  function hide() {
    sheet.hidden = true;
  }

  function show(node) {
    if (!node || !titleNode || !subtitleNode || !bodyNode) return;
    titleNode.textContent = String(node.label || node.id || ui.graph_modal_title || "");
    subtitleNode.textContent = statusLabel(node, pageData.graphLocale || document.documentElement.dataset.locale || "en");
    bodyNode.innerHTML = buildFocusBody(node, currentPayload, pageData);
    sheet.hidden = false;
  }

  if (!sheet.dataset.bound) {
    sheet.dataset.bound = "true";
    sheet.addEventListener("click", (event) => {
      if (event.target.closest('[data-action="close-graph-focus"]')) hide();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !sheet.hidden) hide();
    });
  }

  return {
    show,
    hide,
    updatePayload(nextPayload) {
      currentPayload = nextPayload;
    },
  };
}

function createStarField(scene, sceneMode, ambientSeed) {
  const geometry = new THREE.BufferGeometry();
  const count = String(sceneMode || "").includes("immersive") ? 420 : 280;
  const vertices = new Float32Array(count * 3);
  const seedOffset = hashString(String(ambientSeed || sceneMode || "ambient"));
  for (let index = 0; index < count; index += 1) {
    const seed = hashString(`star:${seedOffset}:${index}`);
    vertices[index * 3] = (seed % 280) - 140;
    vertices[index * 3 + 1] = ((seed / 7) % 170) - 85;
    vertices[index * 3 + 2] = ((seed / 13) % 280) - 140;
  }
  geometry.setAttribute("position", new THREE.BufferAttribute(vertices, 3));
  const material = new THREE.PointsMaterial({
    color: 0xc7ecff,
    size: String(sceneMode || "").includes("immersive") ? 1.24 : 1.02,
    transparent: true,
    opacity: 0.72,
    depthWrite: false,
  });
  const points = new THREE.Points(geometry, material);
  scene.add(points);
  return points;
}

function createNodeParticles(node, radius, color, formationLevel, burstLevel) {
  const particles = [];
  const burstCount = burstLevel >= 0.55 ? 14 : 0;
  const cloudCount = formationLevel >= 0.52 ? 9 : formationLevel >= 0.3 ? 5 : 2;

  for (let index = 0; index < burstCount; index += 1) {
    const seed = hashString(`${node.id}:burst:${index}`);
    const particle = new THREE.Mesh(
      new THREE.SphereGeometry(Math.max(0.16, radius * 0.12), 8, 8),
      new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.78,
        depthWrite: false,
      }),
    );
    particle.userData = {
      mode: "burst",
      orbit: (Math.PI * 2 * index) / burstCount,
      phase: (seed % 100) / 100,
      drift: 0.95 + ((seed % 41) / 41) * 1.15,
    };
    particles.push(particle);
  }

  for (let index = 0; index < cloudCount; index += 1) {
    const seed = hashString(`${node.id}:cloud:${index}`);
    const particle = new THREE.Mesh(
      new THREE.SphereGeometry(Math.max(0.1, radius * 0.09), 8, 8),
      new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.3,
        depthWrite: false,
      }),
    );
    particle.userData = {
      mode: "cloud",
      orbit: (Math.PI * 2 * index) / Math.max(cloudCount, 1),
      phase: (seed % 100) / 100,
      drift: 0.42 + ((seed % 31) / 31) * 0.5,
    };
    particles.push(particle);
  }

  return particles;
}

function buildNodeObject(node, sceneMode, animatedNodes) {
  const radius = nodeRadius(node, sceneMode);
  const formationLevel = stageLevel(node);
  const burstLevel = Number(node.burst_level || 0);
  const recentness = Number(node.recentness || 0);
  const staticPortalScene = isPortalStaticScene(sceneMode);
  const color = new THREE.Color(roleColor(node));
  const group = new THREE.Group();
  const core = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 20, 20),
    new THREE.MeshStandardMaterial({
      color,
      emissive: color.clone().multiplyScalar(0.6),
      emissiveIntensity: clamp(0.62 + Number(node.energy || 0) * 0.68, 0.58, 1.36),
      roughness: 0.32,
      metalness: 0.08,
      transparent: true,
      opacity: node.node_type === "cluster_anchor" ? 0.14 : 0.98,
    }),
  );
  const halo = new THREE.Mesh(
    new THREE.SphereGeometry(radius * (node.node_type === "cluster_anchor" ? 1.85 : 2.2), 18, 18),
    new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity:
        node.node_type === "cluster_anchor"
          ? 0.03
          : clamp(0.06 + formationLevel * 0.09 + recentness * 0.07, 0.06, 0.2),
      side: THREE.BackSide,
      depthWrite: false,
    }),
  );
  const vapor = new THREE.Mesh(
    new THREE.SphereGeometry(radius * (node.node_type === "cluster_anchor" ? 2.3 : 2.8), 16, 16),
    new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity:
        node.node_type === "cluster_anchor"
          ? 0.018
          : clamp(0.026 + formationLevel * 0.055 + burstLevel * 0.055, 0.026, 0.11),
      side: THREE.BackSide,
      depthWrite: false,
    }),
  );
  group.add(vapor, halo, core);

  const particles = staticPortalScene ? [] : createNodeParticles(node, radius, color, formationLevel, burstLevel);
  particles.forEach((particle) => group.add(particle));

  let label = null;
  if (shouldShowLabel(node, sceneMode)) {
    label = new SpriteText(String(node.label || ""));
    label.color = "#f5fbff";
    label.textHeight = clamp(radius * 0.92, 2.6, 6.2);
    label.padding = 2;
    label.backgroundColor = "rgba(6, 13, 24, 0)";
    label.position.set(0, radius * 2.75, 0);
    group.add(label);
  }

  animatedNodes.push({
    node,
    group,
    core,
    halo,
    vapor,
    particles,
    label,
    radius,
    formationLevel,
    burstLevel,
    pulseOffset: (hashString(node.id) % 628) / 100,
  });
  return group;
}

function edgeKey(edge) {
  return `${edge.source}|${edge.target}|${edge.edge_type || edge.kind || "link"}`;
}

function styleForceGraph(fg, sceneMode, payload, state) {
  const staticPortalScene = isPortalStaticScene(sceneMode);
  const scene = fg.scene();
  scene.background = new THREE.Color(String(sceneMode || "").includes("admin") ? "#08131f" : "#050d17");
  scene.fog = new THREE.FogExp2(scene.background, String(sceneMode || "").includes("immersive") ? 0.0058 : 0.0067);

  if (!state.sceneDecorated) {
    const ambient = new THREE.AmbientLight(0xe0f5ff, 2.15);
    const hemi = new THREE.HemisphereLight(0xb8e3ff, 0x040b13, 0.85);
    const key = new THREE.DirectionalLight(0x6ddaff, 1.7);
    key.position.set(28, 44, 32);
    const fill = new THREE.PointLight(0xffbb72, 1.45, 420);
    fill.position.set(-34, -18, -16);
    scene.add(ambient, hemi, key, fill, createStarField(scene, sceneMode, payload.ambient_seed));
    state.sceneDecorated = true;
  }

  const controls = fg.controls();
  controls.enableDamping = true;
  controls.dampingFactor = staticPortalScene ? 0.06 : 0.08;
  controls.enablePan = true;
  controls.minDistance = 72;
  controls.maxDistance = String(sceneMode || "").includes("immersive") ? 520 : 430;
  controls.autoRotate = false;
  controls.autoRotateSpeed = 0;
  controls.rotateSpeed = staticPortalScene ? 0.72 : 0.88;
  controls.panSpeed = staticPortalScene ? 0.92 : 0.72;
  controls.zoomSpeed = staticPortalScene ? 0.94 : 1.0;
  controls.screenSpacePanning = false;
  if (controls.mouseButtons) {
    controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
    controls.mouseButtons.MIDDLE = THREE.MOUSE.PAN;
    controls.mouseButtons.RIGHT = staticPortalScene ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
  }
  if ("zoomToCursor" in controls) {
    controls.zoomToCursor = true;
  }

  fg
    .backgroundColor("#000000")
    .showNavInfo(false)
    .nodeLabel((node) => escapeHtml(node.label || ""))
    .linkColor((link) => (state.activeTrailEdgeIds.has(edgeKey(link)) ? "#ffbf72" : edgeColor(link)))
    .linkOpacity((link) =>
      clamp(
        state.activeTrailEdgeIds.has(edgeKey(link))
          ? 0.92
          : link.edge_type === "belongs_to_cluster" && staticPortalScene
            ? 0.035 + Number(link.activation || 0) * 0.05
          : link.edge_type === "weak_affinity" && staticPortalScene
            ? 0.04 + Number(link.activation || 0) * 0.12
          : link.edge_type === "weak_affinity"
            ? 0.08 + Number(link.activation || 0) * 0.18
            : 0.22 + Math.max(Number(link.activation || 0), Number(link.pulse_level || 0)) * 0.62,
        0.02,
        0.96,
      ),
    )
    .linkWidth((link) =>
      clamp(
        state.activeTrailEdgeIds.has(edgeKey(link))
          ? 4.4
          : link.edge_type === "belongs_to_cluster" && staticPortalScene
            ? 0.18 + Number(link.strength || 0) * 0.22
          : link.edge_type === "weak_affinity" && staticPortalScene
            ? 0.22 + Number(link.strength || 0) * 0.55
          : link.edge_type === "weak_affinity"
            ? 0.35 + Number(link.strength || 0) * 0.85
            : 0.9 + Number(link.strength || 0) * 2.1 + Number(link.pulse_level || 0) * 1.6,
        0.12,
        5.4,
      ),
    )
    .linkCurvature((link) =>
      link.edge_type === "weak_affinity" || link.edge_type === "belongs_to_cluster"
        ? 0
        : clamp(Number(link.pulse_level || 0) * 0.12, 0.02, 0.22),
    )
    .linkDirectionalParticles((link) => {
      if (state.activeTrailEdgeIds.has(edgeKey(link))) return 4;
      if (staticPortalScene) return 0;
      if (link.edge_type === "weak_affinity") return 0;
      if (String(sceneMode || "").includes("universe") && Number(link.pulse_level || 0) <= 0.3) return 0;
      return clamp(Math.round(2 + Math.max(Number(link.activation || 0), Number(link.pulse_level || 0)) * 6), 2, 9);
    })
    .linkDirectionalParticleWidth((link) => clamp(0.8 + Number(link.pulse_level || link.activation || 0) * 2.8, 0.8, 4.4))
    .linkDirectionalParticleSpeed((link) => clamp(0.0028 + Number(link.pulse_level || link.activation || 0) * 0.018, 0.0028, 0.032))
    .linkDirectionalParticleColor((link) => (state.activeTrailEdgeIds.has(edgeKey(link)) ? "#ffbf72" : edgeColor(link)))
    .nodeRelSize(1)
    .d3VelocityDecay(staticPortalScene ? 1 : String(sceneMode || "").includes("portal") ? 0.22 : 0.32)
    .cooldownTicks(staticPortalScene ? 0 : String(sceneMode || "").includes("immersive") ? 160 : String(sceneMode || "").includes("portal") ? 125 : 180)
    .graphData(normalizeGraphData(payload, sceneMode));

  try {
    fg.resumeAnimation();
  } catch (_error) {
    // ignore
  }
}

function playbackRefs(event) {
  const refs = new Set();
  const subject = String(event?.subject_ref || "");
  if (subject) refs.add(subject);
  (Array.isArray(event?.related_refs) ? event.related_refs : []).forEach((item) => {
    const value = String(item || "");
    if (value) refs.add(value);
  });
  return refs;
}

function animateGraph(fg, animatedNodes, sceneMode, state, pageData, helpers) {
  const staticPortalScene = isPortalStaticScene(sceneMode);
  let rafId = 0;
  const controls = fg.controls();
  const renderer = fg.renderer();
  const scene = fg.scene();
  const camera = fg.camera();
  let playbackIndex = 0;
  let playbackChangedAt = performance.now();

  function currentPlayback(now) {
    const playbackEvents = Array.isArray(state.payload?.playback_events) ? state.payload.playback_events : [];
    if (!playbackEvents.length || state.selectedNodeId) return null;
    if (now - playbackChangedAt > 4200) {
      playbackIndex = (playbackIndex + 1) % playbackEvents.length;
      playbackChangedAt = now;
    }
    return playbackEvents[playbackIndex];
  }

  function tick() {
    if (state.disposed) return;
    const nowMs = performance.now();
    const now = nowMs / 1000;
    const playback = currentPlayback(nowMs);
    const playbackNodeIds = playback ? playbackRefs(playback) : new Set();

    controls.autoRotate = false;

    animatedNodes.forEach((entry) => {
      const hovered = state.hoveredNodeId === entry.node.id;
      const selected = state.selectedNodeId === entry.node.id;
      const playbackHit = playbackNodeIds.has(String(entry.node.id || ""));
      const trailHit = state.trailNodeIds.has(String(entry.node.id || ""));
      const recentness = Number(entry.node.recentness || 0);
      const energy = Number(entry.node.energy || 0);
      const stage = entry.formationLevel;
      const burst = entry.burstLevel;
      const emphasis = selected ? 1.6 : hovered ? 1.28 : playbackHit || trailHit ? 1.22 : 1;
      const tacitPulse = entry.node.tacit_pulse ? 0.08 : 0;
      const haloPulse = staticPortalScene
        ? 1
        : 1 + Math.sin(now * (1.2 + burst * 1.1) + entry.pulseOffset) * (0.05 + stage * 0.06 + tacitPulse);
      const corePulse = staticPortalScene
        ? 1
        : 1 + Math.sin(now * (2.6 + stage) + entry.pulseOffset) * (0.02 + burst * 0.07 + tacitPulse * 0.6);
      const vaporPulse = staticPortalScene
        ? selected ? 1.08 : 1
        : 1 + Math.sin(now * (0.8 + recentness) + entry.pulseOffset * 0.7) * (0.08 + stage * 0.12 + tacitPulse);
      entry.halo.scale.setScalar(haloPulse * emphasis);
      entry.core.scale.setScalar(corePulse * emphasis);
      entry.vapor.scale.setScalar(vaporPulse * (selected ? 1.06 : 1));
      entry.halo.material.opacity = clamp(
        (entry.node.node_type === "cluster_anchor" ? 0.03 : 0.05) +
          stage * 0.07 +
          recentness * 0.05 +
          burst * 0.06 +
          (trailHit ? 0.09 : 0) +
          (emphasis - 1) * 0.05,
        0.03,
        0.24,
      );
      entry.vapor.material.opacity = clamp(
        (entry.node.node_type === "cluster_anchor" ? 0.018 : 0.024) +
          stage * 0.05 +
          burst * 0.06 +
          (playbackHit ? 0.04 : 0) +
          tacitPulse * 0.45,
        0.018,
        0.12,
      );
      entry.core.material.emissiveIntensity = clamp(
        0.54 + energy * 0.56 + recentness * 0.22 + (playbackHit ? 0.16 : 0) + (trailHit ? 0.14 : 0) + (emphasis - 1) * 0.2,
        0.5,
        1.45,
      );
      if (entry.label) {
        const distance = Math.hypot(
          Number(camera.position.x || 0) - Number(entry.node.x || 0),
          Number(camera.position.y || 0) - Number(entry.node.y || 0),
          Number(camera.position.z || 0) - Number(entry.node.z || 0),
        );
        const labelVisible =
          !String(sceneMode || "").includes("universe") || selected || hovered || playbackHit || distance < 120;
        entry.label.textHeight = clamp(entry.radius * (selected ? 1.04 : 0.92), 2.6, 6.6);
        entry.label.material.opacity = labelVisible
          ? clamp(0.66 + recentness * 0.18 + (hovered || selected || playbackHit ? 0.18 : 0), 0.6, 1)
          : 0;
      }
      entry.particles.forEach((particle, index) => {
        if (particle.userData.mode === "burst") {
          const orbit = particle.userData.orbit + now * particle.userData.drift + index * 0.04;
          const distance = entry.radius * (2.2 + burst * 3.8 + (Math.sin(now * 2.4 + index) + 1) * 0.85);
          particle.position.set(
            Math.cos(orbit) * distance,
            Math.sin(now * 1.65 + index) * entry.radius * (0.7 + burst * 0.7),
            Math.sin(orbit) * distance,
          );
          particle.material.opacity = clamp(0.1 + burst * 0.55 + (playbackHit ? 0.12 : 0), 0.08, 0.92);
        } else {
          const orbit = particle.userData.orbit + now * particle.userData.drift;
          const distance = entry.radius * (1.45 + stage * 1.85 + Math.sin(now * 1.1 + index) * 0.18);
          particle.position.set(
            Math.cos(orbit) * distance,
            Math.sin(now * 0.8 + particle.userData.phase * Math.PI * 2) * entry.radius * (0.34 + stage * 0.56),
            Math.sin(orbit) * distance,
          );
          particle.material.opacity = clamp(0.08 + stage * 0.24 + recentness * 0.12 + (playbackHit ? 0.08 : 0), 0.06, 0.5);
        }
      });
    });

    helpers.cameraAnchor.tick();
    controls.update();
    helpers.miniMap.update({
      payload: state.payload,
      cameraTarget: {
        x: Number(controls.target.x || 0),
        y: Number(controls.target.y || 0),
        z: Number(controls.target.z || 0),
      },
      focusNode: state.nodeIndex.get(String(state.selectedNodeId || "")),
      title: pageData?.ui?.hud_minimap_title || "",
    });
    renderer.render(scene, camera);
    rafId = window.requestAnimationFrame(tick);
  }

  rafId = window.requestAnimationFrame(tick);
  return () => window.cancelAnimationFrame(rafId);
}

function renderStory(payload, pageData, node = null) {
  const locale = pageData.graphLocale || document.documentElement.dataset.locale || "en";
  const ui = pageData.ui || {};
  const captionNode = document.getElementById("portal-graph-caption");
  const storyNode = document.getElementById("portal-graph-story");
  const value = node ? nodeReasonLabel(node, ui, locale) : String(payload?.story_caption || ui.graph_story_empty || "");
  if (captionNode) {
    captionNode.textContent = value || ui.graph_story_empty || "";
  }
  if (storyNode) {
    storyNode.textContent = value || ui.graph_story_empty || "";
  }
}

function renderGraphInfoCard({ payload, pageData, node = null, status = "" }) {
  const card = document.getElementById("portal-graph-info-card");
  if (!card) return;
  const locale = pageData.graphLocale || document.documentElement.dataset.locale || "en";
  const ui = pageData.ui || {};
  const kickerNode = document.getElementById("portal-graph-info-kicker");
  const titleNode = document.getElementById("portal-graph-info-title");
  const bodyNode = document.getElementById("portal-graph-info-body");
  const statusNode = document.getElementById("portal-graph-info-status");
  if (!kickerNode || !titleNode || !bodyNode || !statusNode) return;

  if (!node) {
    kickerNode.textContent = ui.graph_modal_title || "";
    titleNode.textContent = ui.graph_info_guide_title || ui.graph_modal_title || "";
    bodyNode.textContent = ui.graph_info_guide_body || String(payload?.story_caption || ui.graph_story_empty || "");
    statusNode.textContent = status || ui.graph_info_idle_status || ui.hud_status_default || "";
    return;
  }

  kickerNode.textContent = statusLabel(node, locale);
  titleNode.textContent = String(node.label || node.id || "");
  bodyNode.textContent = String(node.summary || nodeReasonLabel(node, ui, locale) || ui.graph_focus_empty || "");
  statusNode.textContent = status || "";
}

function updatePortalStats(payload) {
  const statsNode = document.getElementById("portal-graph-stats");
  if (!statsNode) return;
  const stats = payload?.stats || {};
  const values = [
    String(stats.node_count || 0),
    String(stats.edge_count || 0),
    `${Math.round(Number(stats.cluster_coverage || 0) * 100)}%`,
    String(stats.insight_count || 0),
  ];
  statsNode.querySelectorAll(".stat strong").forEach((node, index) => {
    node.textContent = values[index] || "0";
  });
}

function urlWithParams(url, params) {
  const target = new URL(url, window.location.origin);
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") {
      target.searchParams.delete(key);
    } else {
      target.searchParams.set(key, String(value));
    }
  });
  return target.toString();
}

function navigateToGraphView(pageData, node) {
  const nodeId = String(node?.id || "");
  if (!nodeId) return;
  const target = new URL(pageData?.routes?.graphView || "/portal/graph-view", window.location.origin);
  if (pageData?.graphLocale) {
    target.searchParams.set("lang", pageData.graphLocale);
  }
  target.searchParams.set("focus", nodeId);
  window.location.assign(`${target.pathname}${target.search}`);
}

function mergeGraphPayload(basePayload, incomingPayload) {
  const baseNodes = Array.isArray(basePayload?.nodes) ? basePayload.nodes : [];
  const incomingNodes = Array.isArray(incomingPayload?.nodes) ? incomingPayload.nodes : [];
  const nodes = new Map(baseNodes.map((node) => [String(node.id || ""), { ...node }]));
  incomingNodes.forEach((node) => {
    const key = String(node.id || "");
    const existing = nodes.get(key);
    nodes.set(
      key,
      existing
        ? { ...node, x: existing.x ?? node.x, y: existing.y ?? node.y, z: existing.z ?? node.z }
        : { ...node },
    );
  });
  const edges = new Map();
  [...(Array.isArray(basePayload?.edges) ? basePayload.edges : []), ...(Array.isArray(incomingPayload?.edges) ? incomingPayload.edges : [])].forEach((edge) => {
    edges.set(edgeKey(edge), { ...edge });
  });
  return {
    ...(basePayload || {}),
    ...(incomingPayload || {}),
    stats: {
      ...(basePayload?.stats || {}),
      ...(incomingPayload?.stats || {}),
    },
    nodes: Array.from(nodes.values()),
    edges: Array.from(edges.values()),
    playback_events: Array.isArray(incomingPayload?.playback_events) && incomingPayload.playback_events.length
      ? incomingPayload.playback_events
      : basePayload?.playback_events || [],
    hotspots: Array.isArray(incomingPayload?.hotspots) && incomingPayload.hotspots.length
      ? incomingPayload.hotspots
      : basePayload?.hotspots || [],
  };
}

function historyStorageKey() {
  return `sediment:graph-history:${window.location.pathname}`;
}

function visitedStorageKey() {
  return `sediment:graph-visited:${window.location.pathname}`;
}

function loadSessionArray(key) {
  try {
    return JSON.parse(window.sessionStorage.getItem(key) || "[]");
  } catch (_error) {
    return [];
  }
}

function saveSessionArray(key, value) {
  window.sessionStorage.setItem(key, JSON.stringify(value.slice(0, 10)));
}

function loadLocalObject(key) {
  try {
    return JSON.parse(window.localStorage.getItem(key) || "{}");
  } catch (_error) {
    return {};
  }
}

function saveLocalObject(key, value) {
  window.localStorage.setItem(key, JSON.stringify(value));
}

function mount3DGraph(container, payload, { sceneMode, pageData, onNodeSelect, onBackgroundSelect } = {}) {
  if (typeof container.__sedimentGraphCleanup === "function") {
    container.__sedimentGraphCleanup();
  }
  container.textContent = "";
  const surface = document.createElement("div");
  surface.className = "sediment-graph-stage";
  container.appendChild(surface);

  const graph = ForceGraph3D({ controlType: "orbit" })(surface);
  const animatedNodes = [];
  const state = {
    disposed: false,
    hoveredNodeId: "",
    selectedNodeId: "",
    payload,
    nodeIndex: new Map(),
    activeTrailEdgeIds: new Set(),
    trailNodeIds: new Set(),
    sceneDecorated: false,
  };

  const cameraAnchor = installCameraAnchor({ graph, sceneMode: sceneMode || payload.scene_mode || "portal-story", state });
  const miniMap = mountMiniMap({
    titleNode: document.getElementById("portal-graph-minimap-title"),
    canvas: document.getElementById("portal-graph-minimap-canvas"),
    frustumNode: document.getElementById("portal-graph-minimap-frustum"),
  });

  function focusNode(node, travelMs = 950) {
    state.selectedNodeId = node?.id || "";
    if (typeof onNodeSelect === "function") onNodeSelect(node || null);
    if (!node) return;
    const distance = String(sceneMode || payload.scene_mode || "").includes("immersive") ? 104 : 118;
    const distRatio = 1 + distance / Math.max(Math.hypot(node.x || 0, node.y || 0, node.z || 0), 1);
    graph.cameraPosition(
      {
        x: (node.x || 0) * distRatio,
        y: (node.y || 0) * distRatio + 16,
        z: (node.z || 0) * distRatio + 24,
      },
      { x: node.x || 0, y: node.y || 0, z: node.z || 0 },
      travelMs,
    );
  }

  function clearSelection() {
    state.selectedNodeId = "";
    if (typeof onBackgroundSelect === "function") onBackgroundSelect();
  }

  function refreshPayload(nextPayload) {
    state.payload = nextPayload || state.payload;
    animatedNodes.length = 0;
    state.nodeIndex = new Map((Array.isArray(state.payload?.nodes) ? state.payload.nodes : []).map((node) => [String(node.id || ""), node]));
    graph.graphData(normalizeGraphData(state.payload, sceneMode || state.payload.scene_mode || "portal-story"));
    cameraAnchor.updateCenter(Array.isArray(state.payload?.nodes) ? state.payload.nodes : []);
    container.dataset.graphNodeCount = String(Array.isArray(state.payload?.nodes) ? state.payload.nodes.length : 0);
  }

  graph.nodeThreeObject((node) => buildNodeObject(node, sceneMode || payload.scene_mode || "portal-story", animatedNodes));
  graph.onNodeHover((node) => {
    state.hoveredNodeId = node?.id || "";
    surface.style.cursor = node ? "pointer" : "grab";
  });
  graph.onNodeClick((node) => {
    focusNode(node || null);
  });
  if (typeof graph.onBackgroundClick === "function") {
    graph.onBackgroundClick(() => clearSelection());
  }

  styleForceGraph(graph, sceneMode || payload.scene_mode || "portal-story", payload, state);
  refreshPayload(payload);

  const cleanupAnimation = animateGraph(
    graph,
    animatedNodes,
    sceneMode || payload.scene_mode || "portal-story",
    state,
    pageData,
    { cameraAnchor, miniMap },
  );

  const resize = () => {
    graph.width(Math.max(container.clientWidth, 320));
    graph.height(Math.max(container.clientHeight, 320));
  };
  resize();
  window.addEventListener("resize", resize);
  container.dataset.graphReady = "true";

  const layoutBounds = graphLayoutBounds(Array.isArray(payload?.nodes) ? payload.nodes : []);
  const focusSeedNode = Array.isArray(payload?.nodes)
    ? payload.nodes.find((node) => node.id === payload.focus_seed) ||
      payload.nodes.find((node) => node.node_type !== "cluster_anchor") ||
      payload.nodes[0]
    : null;
  const focusPreferred =
    Boolean(pageData?.initialFocus) || String(sceneMode || payload.scene_mode || "").includes("focus");
  const cameraTarget =
    focusPreferred && focusSeedNode
      ? { x: focusSeedNode.x || 0, y: focusSeedNode.y || 0, z: focusSeedNode.z || 0 }
      : {
          x: layoutBounds.center.x,
          y: layoutBounds.center.y + clamp(layoutBounds.radius * 0.16, 16, 48),
          z: layoutBounds.center.z,
        };
  const cameraDistance = clamp(
    layoutBounds.radius * (String(sceneMode || payload.scene_mode || "").includes("portal-universe-lite") ? 1.24 : 1.44) + 58,
    138,
    340,
  );
  if (focusSeedNode || layoutBounds.radius) {
    graph.controls().target.set(cameraTarget.x, cameraTarget.y, cameraTarget.z);
    graph.cameraPosition(
      {
        x: cameraTarget.x + layoutBounds.radius * 0.54,
        y: cameraTarget.y + clamp(layoutBounds.radius * 0.3, 24, 92),
        z: cameraTarget.z + cameraDistance,
      },
      cameraTarget,
      0,
    );
  }

  container.__sedimentGraphApi = {
    selectNodeById(nodeId) {
      const node = state.nodeIndex.get(String(nodeId || ""));
      if (!node) return false;
      focusNode(node);
      return true;
    },
    clearSelection,
    nodeIds() {
      return Array.from(state.nodeIndex.keys());
    },
    getNode(nodeId) {
      return state.nodeIndex.get(String(nodeId || "")) || null;
    },
    updatePayload(nextPayload) {
      refreshPayload(nextPayload);
      if (state.selectedNodeId && !state.nodeIndex.has(state.selectedNodeId)) {
        clearSelection();
      }
    },
    debugCameraState() {
      return cameraAnchor.debugState();
    },
    setTrailEdges(edges) {
      state.activeTrailEdgeIds = new Set((Array.isArray(edges) ? edges : []).map((edge) => edgeKey(edge)));
      state.trailNodeIds = new Set(
        (Array.isArray(edges) ? edges : []).flatMap((edge) => [String(edge.source || ""), String(edge.target || "")]),
      );
    },
    trailEdgeIds() {
      return Array.from(state.activeTrailEdgeIds);
    },
    payload() {
      return state.payload;
    },
  };

  container.__sedimentGraphCleanup = () => {
    state.disposed = true;
    cleanupAnimation();
    window.removeEventListener("resize", resize);
    delete container.__sedimentGraphApi;
    delete container.dataset.graphReady;
    delete container.dataset.graphNodeCount;
    miniMap.destroy();
    try {
      graph.pauseAnimation();
    } catch (_error) {
      // ignore
    }
    container.textContent = "";
  };

  return {
    resize,
    focusNodeById(nodeId) {
      return container.__sedimentGraphApi?.selectNodeById(nodeId) || false;
    },
    clearSelection,
    updatePayload(nextPayload) {
      container.__sedimentGraphApi?.updatePayload(nextPayload);
    },
    setTrailEdges(edges) {
      container.__sedimentGraphApi?.setTrailEdges(edges);
    },
    getNode(nodeId) {
      return container.__sedimentGraphApi?.getNode(nodeId) || null;
    },
    getPayload() {
      return container.__sedimentGraphApi?.payload() || payload;
    },
    destroy() {
      if (typeof container.__sedimentGraphCleanup === "function") {
        container.__sedimentGraphCleanup();
      }
    },
  };
}

function mountPortalGraph(container, payload, options = {}) {
  const pageData = options.pageData || readPageData();
  const ui = pageData.ui || {};
  const isHomePreview = pageData.pageKind === "home";

  if (isHomePreview) {
    renderStory(payload, pageData, null);
    updatePortalStats(payload);
    const graph = mount3DGraph(container, payload, {
      pageData,
      sceneMode: payload.scene_mode || options.sceneMode || "portal-universe-lite",
      onNodeSelect(node) {
        if (!node || String(node.node_type || "") === "cluster_anchor") return;
        navigateToGraphView(pageData, node);
      },
      onBackgroundSelect() {},
    });
    return {
      destroy() {
        graph.destroy();
      },
    };
  }

  const focusSheet = setupPortalFocusSheet(pageData, payload);
  const trail = createKnowledgeTrail();
  const state = {
    fullPayload: payload,
    displayedPayload: payload,
    filterId: "all",
    strategyId: pageData.defaultStrategy || "edge_walk",
    budget: payload.budget || pageData.defaultBudget || "medium",
    currentNode: null,
    history: loadSessionArray(historyStorageKey()),
    visited: loadLocalObject(visitedStorageKey()),
    neighborhoodLoaded: new Set(),
    capabilityStatus: ui.hud_status_default || "",
    hotspotMode: "empty",
  };
  updatePortalStats(state.fullPayload);

  const graph = mount3DGraph(container, payload, {
    pageData,
    sceneMode: payload.scene_mode || options.sceneMode || "portal-universe",
    onNodeSelect(node) {
      state.currentNode = node;
      if (!node) {
        focusSheet.hide();
        renderGraphInfoCard({ payload: state.fullPayload, pageData, node: null, status: state.capabilityStatus });
        return;
      }
      state.visited[node.id] = Number(state.visited[node.id] || 0) + 1;
      saveLocalObject(visitedStorageKey(), state.visited);
      renderGraphInfoCard({ payload: state.fullPayload, pageData, node, status: state.capabilityStatus });
      focusSheet.show(node);
      updateTrailButtons();
      ensureNeighborhood(node.id).catch(() => {});
      if (typeof options.onSelect === "function") options.onSelect(node);
    },
    onBackgroundSelect() {
      state.currentNode = null;
      focusSheet.hide();
      renderGraphInfoCard({ payload: state.fullPayload, pageData, node: null, status: state.capabilityStatus });
      updateTrailButtons();
    },
  });

  const hud = mountUniverseHud({
    ui,
    defaultStrategy: state.strategyId,
    defaultFilter: state.filterId,
    defaultBudget: state.budget,
    hiddenBudgets: Array.isArray(pageData.hiddenBudgets) ? pageData.hiddenBudgets : [],
    onSearchInput: debounceSearch,
    onSuggestionSelect: async (item) => {
      await focusNodeById(item.id || `entry::${item.name || item.title || ""}`);
    },
    onHotspot: () => {
      if (state.hotspotMode === "empty") return;
      hotspotCursor.next();
    },
    onHotspotPrev: () => {
      if (state.hotspotMode === "empty") return;
      hotspotCursor.prev();
    },
    onExplore: () => exploreNext(),
    onHistoryBack: () => backtrack(),
    onStrategyChange: (value) => {
      state.strategyId = value;
    },
    onFilterChange: (value) => {
      state.filterId = value;
      applyDisplayedPayload();
    },
    onBudgetChange: async (value) => {
      state.budget = value;
      const nextPayload = await fetchJson(urlWithParams(pageData.graphApi, { scene: "universe", budget: value }));
      state.fullPayload = nextPayload;
      focusSheet.updatePayload(state.fullPayload);
      applyDisplayedPayload();
      if (state.currentNode) {
        await focusNodeById(state.currentNode.id, { recordHistory: false });
      }
      refreshHotspots().catch(() => {});
    },
    onTrailRun: () => runTrail(),
    onTrailClear: () => clearTrail(),
  });

  const hotspotCursor = createHotspotCursor({
    loadQueue: async () => {
      return fetchJson(urlWithParams(pageData.hotspotsApi, { kind: "all", budget: state.budget }));
    },
    onSelect: async (item) => {
      if (item?.id) await focusNodeById(item.id);
    },
  });

  const keyboardCleanup = installGraphKeyboard({
    onSearch: () => hud.focusSearch(),
    onHotspotPrev: () => {
      if (state.hotspotMode === "empty") return;
      hotspotCursor.prev();
    },
    onHotspotNext: () => {
      if (state.hotspotMode === "empty") return;
      hotspotCursor.next();
    },
    onExplore: () => exploreNext(),
    onEscape: () => {
      graph.clearSelection();
    },
  });

  let searchTimer = 0;

  function setHistory(value) {
    state.history = value.slice(0, 10);
    saveSessionArray(historyStorageKey(), state.history);
    hud.setHistoryEnabled(state.history.length > 0);
  }

  function setCapabilityStatus(message) {
    state.capabilityStatus = String(message || ui.hud_status_default || "");
    hud.setStatus(state.capabilityStatus);
    renderGraphInfoCard({
      payload: state.fullPayload,
      pageData,
      node: state.currentNode,
      status: state.capabilityStatus,
    });
  }

  function pushHistory(nodeId) {
    const value = String(nodeId || "");
    if (!value) return;
    const next = [value, ...state.history.filter((item) => item !== value)].slice(0, 10);
    setHistory(next);
  }

  function refreshControlStates() {
    const capabilities = filterCapabilities(state.fullPayload);
    const filterReasons = {
      tacit: capabilities.tacit.enabled ? "" : ui.hud_status_no_tacit || "",
      canonical: "",
      cluster: capabilities.cluster.enabled ? "" : ui.hud_status_no_cluster || "",
    };
    hud.setFilterAvailability(
      {
        all: true,
        tacit: capabilities.tacit.enabled,
        canonical: capabilities.canonical.enabled,
        cluster: capabilities.cluster.enabled,
      },
      filterReasons,
    );
    hud.setHotspotEnabled(state.hotspotMode !== "empty");
    const selectableNodes = (Array.isArray(state.displayedPayload?.nodes) ? state.displayedPayload.nodes : []).filter(
      (node) => String(node?.node_type || "") !== "cluster_anchor",
    );
    hud.setExploreEnabled(selectableNodes.length > 0);

    const nextStatus = [
      state.hotspotMode === "recommended"
        ? ui.hud_status_hotspot_fallback || ""
        : state.hotspotMode === "empty"
          ? ui.hud_status_hotspot_empty || ""
          : "",
      capabilities.tacit.enabled ? "" : ui.hud_status_no_tacit || "",
      capabilities.cluster.enabled ? "" : ui.hud_status_no_cluster || "",
    ]
      .filter(Boolean)
      .join(" · ") || ui.hud_status_default || "";
    setCapabilityStatus(nextStatus);
  }

  function applyDisplayedPayload() {
    const capabilities = filterCapabilities(state.fullPayload);
    if (state.filterId !== "all" && capabilities[state.filterId] && !capabilities[state.filterId].enabled) {
      state.filterId = "all";
    }
    state.displayedPayload = filterGraphPayload(state.fullPayload, state.filterId);
    graph.updatePayload(state.displayedPayload);
    focusSheet.updatePayload(state.displayedPayload);
    updatePortalStats(state.fullPayload);
    renderGraphInfoCard({
      payload: state.fullPayload,
      pageData,
      node: state.currentNode,
      status: state.capabilityStatus,
    });
    const visible = state.displayedPayload?.stats?.visible_node_count || state.displayedPayload?.nodes?.length || 0;
    const total = state.fullPayload?.stats?.total_node_count || state.fullPayload?.nodes?.length || visible;
    hud.setCount(visible, total);
    if (state.currentNode && !graph.getNode(state.currentNode.id)) {
      state.currentNode = null;
      focusSheet.hide();
      updateTrailButtons();
    }
    refreshControlStates();
  }

  async function ensureNeighborhood(nodeId) {
    const key = String(nodeId || "");
    if (!key || state.neighborhoodLoaded.has(key) || !pageData.neighborhoodApi) return;
    state.neighborhoodLoaded.add(key);
    const incoming = await fetchJson(urlWithParams(pageData.neighborhoodApi, { id: key, depth: 2, budget: state.budget }));
    state.fullPayload = mergeGraphPayload(state.fullPayload, incoming);
    applyDisplayedPayload();
    if (state.currentNode?.id === key) {
      const refreshed = graph.getNode(key);
      if (refreshed) {
        state.currentNode = refreshed;
        focusSheet.show(refreshed);
      }
    }
  }

  async function focusNodeById(nodeId, { recordHistory = true } = {}) {
    const targetId = String(nodeId || "");
    if (!targetId) return false;
    if (recordHistory && state.currentNode?.id && state.currentNode.id !== targetId) {
      pushHistory(state.currentNode.id);
    }
    let selected = graph.focusNodeById(targetId);
    if (!selected) {
      const focusedPayload = await fetchJson(
        urlWithParams(pageData.graphApi, {
          scene: "universe_focus",
          focus: targetId,
          budget: state.budget,
        }),
      );
      state.fullPayload = mergeGraphPayload(state.fullPayload, focusedPayload);
      applyDisplayedPayload();
      selected = graph.focusNodeById(targetId);
    }
    if (selected) {
      hud.setSearchStatus(ui.hud_you_arrived || "");
      await ensureNeighborhood(targetId);
    }
    return selected;
  }

  async function runTrail() {
    const current = trail.state();
    if (!current.start?.id || !current.end?.id || !pageData.pathApi) return;
    const result = await fetchJson(urlWithParams(pageData.pathApi, { from: current.start.id, to: current.end.id }));
    trail.setEdges(result.edges || []);
    graph.setTrailEdges(result.edges || []);
  }

  function clearTrail() {
    trail.clear();
    graph.setTrailEdges([]);
    hud.setTrail(null, null);
  }

  function updateTrailButtons() {
    const startButton = document.getElementById("portal-graph-trail-start-button");
    const endButton = document.getElementById("portal-graph-trail-end-button");
    if (startButton) {
      startButton.textContent = ui.hud_trail_set_start || "";
      startButton.disabled = !state.currentNode;
      startButton.onclick = () => {
        trail.setStart(state.currentNode);
        hud.setTrail(trail.state().start, trail.state().end);
      };
    }
    if (endButton) {
      endButton.textContent = ui.hud_trail_set_end || "";
      endButton.disabled = !state.currentNode;
      endButton.onclick = () => {
        trail.setEnd(state.currentNode);
        hud.setTrail(trail.state().start, trail.state().end);
      };
    }
  }

  async function exploreNext() {
    const nextNodeId = pickNextExploreNode({
      payload: state.displayedPayload,
      strategyId: state.strategyId,
      selectedNodeId: state.currentNode?.id || "",
      visited: state.visited,
    });
    if (nextNodeId) {
      await focusNodeById(nextNodeId);
      return;
    }
    setCapabilityStatus(ui.hud_status_explore_empty || ui.hud_status_default || "");
  }

  function backtrack() {
    const [nextId, ...rest] = state.history;
    setHistory(rest);
    if (nextId) {
      focusNodeById(nextId, { recordHistory: false }).catch(() => {});
    }
  }

  async function debounceSearch(value) {
    window.clearTimeout(searchTimer);
    const query = String(value || "").trim();
    if (!query) {
      hud.setSearchStatus("");
      hud.clearSuggestions();
      return;
    }
    hud.setSearchStatus(ui.hud_search_loading || "");
    searchTimer = window.setTimeout(async () => {
      const response = await fetchJson(urlWithParams(pageData.searchSuggestApi, { q: query }));
      const suggestions = (response.suggestions || []).map((item) => ({
        ...item,
        id: item.id || `entry::${item.name || item.title || ""}`,
      }));
      if (!suggestions.length) {
        hud.setSearchStatus(ui.hud_search_empty || "");
        hud.clearSuggestions();
        return;
      }
      hud.setSearchStatus("");
      hud.showSuggestions(suggestions);
    }, 160);
  }

  async function refreshHotspots() {
    await hotspotCursor.refresh();
    state.hotspotMode = hotspotCursor.mode();
    refreshControlStates();
  }

  setHistory(state.history);
  updateTrailButtons();
  focusSheet.updatePayload(state.fullPayload);
  renderGraphInfoCard({ payload: state.fullPayload, pageData, node: null, status: state.capabilityStatus });
  applyDisplayedPayload();
  refreshHotspots().catch(() => {});

  container.__sedimentGraphPortalCleanup = () => {
    keyboardCleanup();
  };

  return {
    destroy() {
      keyboardCleanup();
      graph.destroy();
    },
  };
}

function mountAdminGraph(container, payload, options = {}) {
  return mount3DGraph(container, payload, {
    pageData: options.pageData || readPageData(),
    sceneMode: payload.scene_mode || options.sceneMode || "admin-governance",
    onNodeSelect(node) {
      if (typeof options.onSelect === "function") options.onSelect(node);
    },
    onBackgroundSelect() {
      if (typeof options.onSelect === "function") options.onSelect(null);
    },
  });
}

async function fetchJson(url) {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`Failed to load ${url}: ${response.status}`);
  }
  return response.json();
}

async function bootPortalSurface() {
  const pageData = readPageData();
  const container = document.getElementById("portal-insights-graph");
  if (!container || !pageData.graphApi) return;
  try {
    const payload = await fetchJson(pageData.graphApi);
    renderStory(payload, pageData, null);
    await mountPortalGraph(container, payload, { pageData });
  } catch (error) {
    container.innerHTML = `<div class="sediment-graph-empty">${escapeHtml(
      pageData.graphLocale === "zh" ? `图谱暂时不可用：${error.message}` : `Graph unavailable: ${error.message}`,
    )}</div>`;
  }
}

window.SedimentGraph = {
  mountPortalGraph,
  mountAdminGraph,
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootPortalSurface, { once: true });
} else {
  bootPortalSurface();
}
