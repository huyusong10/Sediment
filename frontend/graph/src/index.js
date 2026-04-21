import "./graph.css";

const NODE_COLORS = {
  cluster_anchor: "#84b9ff",
  canonical_entry: "#f2c879",
  insight_proposal: "#ffb36c",
  query_cluster: "#8ed9ff",
  index_segment: "#c2cffb",
};

const EDGE_COLORS = {
  weak_affinity: "rgba(119, 141, 181, 0.28)",
  ask_reinforcement: "rgba(122, 222, 255, 0.78)",
  supports: "rgba(126, 233, 188, 0.82)",
  routes_to: "rgba(246, 195, 122, 0.82)",
  belongs_to_cluster: "rgba(146, 167, 212, 0.24)",
};

const STAGE_LEVEL = {
  dormant: 0.12,
  stable: 0.22,
  stirring: 0.48,
  condensing: 0.68,
  bursting: 1,
};

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

function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

function edgeColor(edge) {
  return EDGE_COLORS[String(edge.edge_type || "").trim()] || "rgba(135, 156, 187, 0.32)";
}

function nodeColor(node) {
  return NODE_COLORS[String(node.node_type || "").trim()] || "#9bc2ff";
}

function stageLevel(node) {
  return STAGE_LEVEL[String(node.formation_stage || "").trim()] || 0.3;
}

function nodeRadius(node) {
  if (node.node_type === "cluster_anchor") return 10;
  return clamp(
    5.5 +
      Number(node.energy || 0) * 5.2 +
      stageLevel(node) * 3.6 +
      (1 - Number(node.stability || 0.6)) * 1.4,
    5.2,
    12.4,
  );
}

function buildAdjacency(payload) {
  const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  const edges = Array.isArray(payload?.edges) ? payload.edges : [];
  const nodeMap = new Map(nodes.map((node) => [String(node.id || ""), node]));
  const adjacency = new Map(nodes.map((node) => [String(node.id || ""), new Map()]));
  edges.forEach((edge) => {
    const source = String(edge.source || "");
    const target = String(edge.target || "");
    if (!source || !target) return;
    if (!adjacency.has(source)) adjacency.set(source, new Map());
    if (!adjacency.has(target)) adjacency.set(target, new Map());
    adjacency.get(source).set(target, edge);
    adjacency.get(target).set(source, edge);
  });
  return { nodeMap, adjacency };
}

function computeHopMap(rootId, adjacencyBundle, maxDepth = 3) {
  const start = String(rootId || "");
  if (!start) return new Map();
  const hopMap = new Map([[start, 0]]);
  const queue = [{ id: start, depth: 0 }];
  while (queue.length) {
    const current = queue.shift();
    if (!current || current.depth >= maxDepth) continue;
    const neighbors = adjacencyBundle.adjacency.get(current.id);
    if (!neighbors) continue;
    neighbors.forEach((_edge, neighborId) => {
      if (hopMap.has(neighborId)) return;
      hopMap.set(neighborId, current.depth + 1);
      queue.push({ id: neighborId, depth: current.depth + 1 });
    });
  }
  return hopMap;
}

function focusBundle(rootNode, adjacencyBundle, depth = 1) {
  const rootId = String(rootNode?.id || "");
  if (!rootId) return { nodes: [], radius: 48, center: { x: 0, y: 0, z: 0 } };
  const hopMap = computeHopMap(rootId, adjacencyBundle, depth);
  const nodes = Array.from(hopMap.keys())
    .map((id) => adjacencyBundle.nodeMap.get(id))
    .filter(Boolean);
  const center = nodes.reduce(
    (accumulator, node) => ({
      x: accumulator.x + Number(node.x || 0),
      y: accumulator.y + Number(node.y || 0),
      z: accumulator.z + Number(node.z || 0),
    }),
    { x: 0, y: 0, z: 0 },
  );
  center.x /= Math.max(nodes.length, 1);
  center.y /= Math.max(nodes.length, 1);
  center.z /= Math.max(nodes.length, 1);
  const radius = nodes.reduce((maxRadius, node) => {
    const distance = Math.hypot(
      Number(node.x || 0) - center.x,
      Number(node.y || 0) - center.y,
      Number(node.z || 0) - center.z,
    );
    return Math.max(maxRadius, distance);
  }, 42);
  return { nodes, radius: Math.max(radius, 42), center };
}

function worldBounds(nodes) {
  const safeNodes = Array.isArray(nodes) ? nodes : [];
  const initial = {
    minX: Infinity,
    maxX: -Infinity,
    minY: Infinity,
    maxY: -Infinity,
    minZ: Infinity,
    maxZ: -Infinity,
  };
  const bounds = safeNodes.reduce((accumulator, node) => {
    const x = Number(node.x || 0);
    const y = Number(node.y || 0);
    const z = Number(node.z || 0);
    return {
      minX: Math.min(accumulator.minX, x),
      maxX: Math.max(accumulator.maxX, x),
      minY: Math.min(accumulator.minY, y),
      maxY: Math.max(accumulator.maxY, y),
      minZ: Math.min(accumulator.minZ, z),
      maxZ: Math.max(accumulator.maxZ, z),
    };
  }, initial);
  const width = Math.max(bounds.maxX - bounds.minX, 120);
  const height = Math.max(bounds.maxY - bounds.minY, 90);
  return {
    ...bounds,
    width,
    height,
    centerX: bounds.minX + width / 2,
    centerY: bounds.minY + height / 2,
    centerZ: bounds.minZ + (bounds.maxZ - bounds.minZ) / 2,
  };
}

function shouldShowLabel(node, state, projection) {
  if (node.node_type === "cluster_anchor") return false;
  const id = String(node.id || "");
  if (state.selectedNodeId) {
    return state.hopMap.has(id);
  }
  if (state.searchMatches.size) {
    return state.searchMatches.has(id);
  }
  const priority =
    Number(node.energy || 0) +
    Number(node.recentness || 0) +
    stageLevel(node) +
    Number(node.importance_rank || 0) * 0.04;
  const inCenter =
    projection.x >= projection.width * 0.25 &&
    projection.x <= projection.width * 0.75 &&
    projection.y >= projection.height * 0.25 &&
    projection.y <= projection.height * 0.75;
  return priority >= 1.32 || (inCenter && priority >= 0.62);
}

class CanvasGraphRuntime {
  constructor(container, payload, options = {}) {
    this.container = container;
    this.payload = deepClone(payload);
    this.options = options;
    this.variant = options.variant || "portal";
    this.sceneMode = options.sceneMode || (this.variant === "admin" ? "admin" : "portal");
    this.motionProfile = options.motionProfile === "reduced" ? "reduced" : "full";
    this.nodes = Array.isArray(this.payload.nodes) ? this.payload.nodes.map((node) => ({ ...node })) : [];
    this.edges = Array.isArray(this.payload.edges)
      ? this.payload.edges.map((edge, index) => ({
          ...edge,
          id: edge.id || `edge-${index}-${edge.source}-${edge.target}`,
        }))
      : [];
    this.bounds = worldBounds(this.nodes);
    this.adjacencyBundle = buildAdjacency({ nodes: this.nodes, edges: this.edges });
    this.canvas = document.createElement("canvas");
    this.canvas.className = "sediment-graph-canvas";
    this.canvas.setAttribute("aria-hidden", "true");
    this.container.textContent = "";
    this.container.appendChild(this.canvas);
    this.context = this.canvas.getContext("2d");
    this.devicePixelRatio = Math.max(window.devicePixelRatio || 1, 1);
    this.pointer = { x: 0, y: 0, down: false, dragging: false, startX: 0, startY: 0 };
    this.starField = this.buildStarField(String(this.payload.ambient_seed || "ambient"));
    this.hoveredNodeId = "";
    this.selectedNodeId = "";
    this.previewNodeId = "";
    this.viewMode = "roam";
    this.searchMatches = new Set();
    this.hopMap = new Map();
    this.animationFrame = 0;
    this.disposed = false;
    this.camera = {
      x: this.bounds.centerX,
      y: this.bounds.centerY,
      zoom: 1,
      tilt: 0.18,
    };
    this.targetCamera = { ...this.camera };
    this.baseRoam = { x: this.bounds.centerX, y: this.bounds.centerY, zoom: 1, tilt: 0.18 };
    this.baseSurvey = { x: this.bounds.centerX, y: this.bounds.centerY, zoom: 0.68, tilt: 0.02 };
    this.resize = this.resize.bind(this);
    this.tick = this.tick.bind(this);
    this.onPointerMove = this.onPointerMove.bind(this);
    this.onPointerDown = this.onPointerDown.bind(this);
    this.onPointerUp = this.onPointerUp.bind(this);
    this.onWheel = this.onWheel.bind(this);
    this.bind();
    this.setViewMode("roam", { immediate: true });
    this.stageInitialNode();
    this.resize();
    this.tick();
  }

  buildStarField(seed) {
    const count = this.variant === "admin" ? 140 : 240;
    return Array.from({ length: count }, (_value, index) => {
      const hash = hashString(`${seed}:${index}`);
      return {
        x: (hash % 1000) / 1000,
        y: ((hash / 11) % 1000) / 1000,
        size: 0.4 + (((hash / 17) % 1000) / 1000) * 1.6,
        alpha: 0.14 + (((hash / 23) % 1000) / 1000) * 0.56,
        drift: (((hash / 29) % 1000) / 1000) * 0.08,
      };
    });
  }

  bind() {
    this.container.addEventListener("pointermove", this.onPointerMove);
    this.container.addEventListener("pointerdown", this.onPointerDown);
    window.addEventListener("pointerup", this.onPointerUp);
    this.container.addEventListener("wheel", this.onWheel, { passive: false });
    window.addEventListener("resize", this.resize);
  }

  prefersReducedMotion() {
    return this.motionProfile === "reduced";
  }

  resize() {
    const width = Math.max(this.container.clientWidth || 0, 320);
    const height = Math.max(this.container.clientHeight || 0, 320);
    this.width = width;
    this.height = height;
    this.canvas.width = Math.round(width * this.devicePixelRatio);
    this.canvas.height = Math.round(height * this.devicePixelRatio);
    this.canvas.style.width = `${width}px`;
    this.canvas.style.height = `${height}px`;
    this.context.setTransform(this.devicePixelRatio, 0, 0, this.devicePixelRatio, 0, 0);
    this.baseScale =
      Math.min(width / this.bounds.width, height / this.bounds.height) *
      (this.viewMode === "survey" ? 0.82 : this.variant === "admin" ? 0.74 : 0.66);
  }

  stageInitialNode() {
    const candidate =
      this.nodes.find((node) => String(node.id || "") === String(this.payload.focus_seed || "")) ||
      this.nodes.find((node) => String(node.node_type || "") !== "cluster_anchor") ||
      this.nodes[0];
    if (candidate) {
      this.previewNodeId = String(candidate.id || "");
      this.centerOnNode(candidate, { select: false, immediate: true, depth: 1 });
    }
  }

  onPointerMove(event) {
    const rect = this.canvas.getBoundingClientRect();
    this.pointer.x = event.clientX - rect.left;
    this.pointer.y = event.clientY - rect.top;
    if (this.pointer.down) {
      const dx = this.pointer.x - this.pointer.startX;
      const dy = this.pointer.y - this.pointer.startY;
      if (Math.abs(dx) + Math.abs(dy) > 3) this.pointer.dragging = true;
      this.camera.x -= dx / Math.max(this.baseScale * this.camera.zoom, 0.001);
      this.camera.y -= dy / Math.max(this.baseScale * this.camera.zoom, 0.001);
      this.targetCamera.x = this.camera.x;
      this.targetCamera.y = this.camera.y;
      this.pointer.startX = this.pointer.x;
      this.pointer.startY = this.pointer.y;
      return;
    }
    const hovered = this.pickNodeAt(this.pointer.x, this.pointer.y);
    this.hoveredNodeId = hovered ? String(hovered.id || "") : "";
    this.container.style.cursor = hovered ? "pointer" : this.pointer.down ? "grabbing" : "grab";
  }

  onPointerDown(event) {
    event.preventDefault();
    const rect = this.canvas.getBoundingClientRect();
    this.pointer.down = true;
    this.pointer.dragging = false;
    this.pointer.startX = event.clientX - rect.left;
    this.pointer.startY = event.clientY - rect.top;
    this.container.style.cursor = "grabbing";
  }

  onPointerUp(event) {
    if (!this.pointer.down) return;
    const rect = this.canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    this.pointer.down = false;
    this.container.style.cursor = "grab";
    if (this.pointer.dragging) return;
    const picked = this.pickNodeAt(x, y);
    if (picked) {
      this.selectNodeById(String(picked.id || ""));
      return;
    }
    this.clearSelection();
  }

  onWheel(event) {
    event.preventDefault();
    const direction = event.deltaY > 0 ? 0.94 : 1.06;
    this.camera.zoom = clamp(this.camera.zoom * direction, 0.28, 4.2);
    this.targetCamera.zoom = this.camera.zoom;
  }

  setViewMode(mode, options = {}) {
    this.viewMode = mode === "survey" ? "survey" : mode === "cruise" ? "cruise" : "roam";
    this.resize();
    const target =
      this.viewMode === "survey"
        ? { ...this.baseSurvey }
        : this.viewMode === "cruise"
          ? { ...this.baseRoam, zoom: Math.max(this.baseRoam.zoom, 1.08), tilt: 0.22 }
          : { ...this.baseRoam };
    const immediate = Boolean(options.immediate) || this.prefersReducedMotion();
    if (this.selectedNodeId) {
      const node = this.adjacencyBundle.nodeMap.get(this.selectedNodeId);
      if (node) {
        this.centerOnNode(node, { select: true, notify: false, immediate });
        return;
      }
    }
    this.targetCamera = target;
    if (immediate) this.camera = { ...target };
  }

  getViewMode() {
    return this.viewMode;
  }

  centerOnNode(node, options = {}) {
    const focus = focusBundle(node, this.adjacencyBundle, options.depth || 1);
    const selectedZoom = clamp(
      Math.min(this.width / (focus.radius * 4.1), this.height / (focus.radius * 3.5)) /
        Math.max(this.baseScale, 0.001),
      0.82,
      this.viewMode === "survey" ? 1.6 : 2.6,
    );
    const target = {
      x: focus.center.x,
      y: focus.center.y,
      zoom: this.viewMode === "survey" ? Math.max(selectedZoom, 1.1) : selectedZoom,
      tilt: this.viewMode === "survey" ? 0.04 : this.viewMode === "cruise" ? 0.24 : 0.18,
    };
    this.targetCamera = target;
    if (options.immediate || this.prefersReducedMotion()) this.camera = { ...target };
    if (options.select) {
      this.selectedNodeId = String(node.id || "");
      this.previewNodeId = "";
      this.hopMap = computeHopMap(this.selectedNodeId, this.adjacencyBundle, 3);
      if (this.viewMode === "survey") {
        this.viewMode = "roam";
      }
      if (options.notify !== false && typeof this.options.onSelect === "function") {
        this.options.onSelect({ ...node });
      }
    }
  }

  selectNodeById(nodeId) {
    const node = this.adjacencyBundle.nodeMap.get(String(nodeId || ""));
    if (!node) return false;
    this.centerOnNode(node, { select: true });
    return true;
  }

  stageNodeById(nodeId) {
    const node = this.adjacencyBundle.nodeMap.get(String(nodeId || ""));
    if (!node) return false;
    this.previewNodeId = String(node.id || "");
    if (!this.selectedNodeId) {
      this.centerOnNode(node, { select: false, immediate: this.prefersReducedMotion(), depth: 1 });
    }
    return true;
  }

  clearSelection() {
    const hadSelection = Boolean(this.selectedNodeId);
    this.selectedNodeId = "";
    this.hopMap = new Map();
    this.targetCamera = this.viewMode === "survey" ? { ...this.baseSurvey } : { ...this.baseRoam };
    if (hadSelection && typeof this.options.onBackgroundSelect === "function") {
      this.options.onBackgroundSelect();
    }
  }

  setSearchMatches(matches) {
    this.searchMatches = new Set((Array.isArray(matches) ? matches : []).map((item) => String(item || "")));
  }

  setMotionProfile(profile) {
    this.motionProfile = profile === "reduced" ? "reduced" : "full";
    if (this.prefersReducedMotion()) {
      this.camera = { ...this.targetCamera };
    }
  }

  nodesSnapshot() {
    return this.nodes.map((node) => ({ ...node }));
  }

  project(node, camera = this.camera) {
    const x = Number(node.x || 0);
    const y = Number(node.y || 0);
    const z = Number(node.z || 0);
    const scale = this.baseScale * camera.zoom;
    const dx = x - camera.x;
    const dy = y - camera.y;
    const dz = z - this.bounds.centerZ;
    const tilt = camera.tilt;
    return {
      x: this.width / 2 + dx * scale + dz * scale * 0.08,
      y: this.height / 2 + dy * scale * (this.viewMode === "survey" ? 0.92 : 0.84) - dz * scale * tilt * 0.24,
      radius: nodeRadius(node) * clamp(scale / 11, 0.42, 1.36),
      width: this.width,
      height: this.height,
    };
  }

  pickNodeAt(x, y) {
    const candidates = this.nodes
      .map((node) => ({ node, projection: this.project(node) }))
      .filter(({ node }) => String(node.node_type || "") !== "cluster_anchor")
      .sort((left, right) => right.projection.radius - left.projection.radius);
    return (
      candidates.find(({ projection }) => Math.hypot(projection.x - x, projection.y - y) <= projection.radius + 8)
        ?.node || null
    );
  }

  edgeOpacity(edge) {
    const sourceId = String(edge.source || "");
    const targetId = String(edge.target || "");
    if (this.selectedNodeId) {
      const leftHop = this.hopMap.get(sourceId);
      const rightHop = this.hopMap.get(targetId);
      if (leftHop == null || rightHop == null) return 0.025;
      return clamp(0.88 - Math.min(leftHop, rightHop) * 0.24, 0.16, 0.9);
    }
    if (this.searchMatches.size && !this.searchMatches.has(sourceId) && !this.searchMatches.has(targetId)) {
      return 0.04;
    }
    return clamp(0.16 + Number(edge.activation || 0) * 0.48 + Number(edge.pulse_level || 0) * 0.32, 0.08, 0.84);
  }

  edgeWidth(edge) {
    const sourceId = String(edge.source || "");
    const targetId = String(edge.target || "");
    if (this.selectedNodeId) {
      const leftHop = this.hopMap.get(sourceId);
      const rightHop = this.hopMap.get(targetId);
      if (leftHop == null || rightHop == null) return 0.8;
      return clamp(2.9 - Math.min(leftHop, rightHop) * 0.72, 0.9, 3.2);
    }
    return clamp(0.8 + Number(edge.strength || 0) * 2.2 + Number(edge.pulse_level || 0) * 1.2, 0.6, 3.2);
  }

  nodeOpacity(node) {
    const nodeId = String(node.id || "");
    if (this.selectedNodeId) {
      const hop = this.hopMap.get(nodeId);
      if (hop == null) return 0.08;
      return clamp(1 - hop * 0.28, 0.34, 1);
    }
    if (this.searchMatches.size && !this.searchMatches.has(nodeId)) return 0.24;
    return 1;
  }

  drawStars(time) {
    this.starField.forEach((star) => {
      const x = (star.x + star.drift * Math.sin(time * 0.00012 + star.x * 9)) * this.width;
      const y = (star.y + star.drift * Math.cos(time * 0.0001 + star.y * 12)) * this.height;
      this.context.fillStyle = `rgba(235, 242, 255, ${star.alpha})`;
      this.context.beginPath();
      this.context.arc(x % this.width, y % this.height, star.size, 0, Math.PI * 2);
      this.context.fill();
    });
  }

  drawEdges() {
    this.edges.forEach((edge) => {
      const source = this.adjacencyBundle.nodeMap.get(String(edge.source || ""));
      const target = this.adjacencyBundle.nodeMap.get(String(edge.target || ""));
      if (!source || !target) return;
      const left = this.project(source);
      const right = this.project(target);
      const opacity = this.edgeOpacity(edge);
      if (opacity <= 0.03) return;
      const pulse = 0.14 * Math.sin(performance.now() * 0.003 + hashString(edge.id || "") / 10);
      this.context.strokeStyle = edgeColor(edge).replace(/[\d.]+\)$/, `${clamp(opacity + pulse, 0.02, 0.92)})`);
      this.context.lineWidth = this.edgeWidth(edge);
      this.context.beginPath();
      const curvature = Number(edge.pulse_level || 0) * 12;
      const midX = (left.x + right.x) / 2 + curvature;
      const midY = (left.y + right.y) / 2 - curvature * 0.25;
      this.context.moveTo(left.x, left.y);
      this.context.quadraticCurveTo(midX, midY, right.x, right.y);
      this.context.stroke();
    });
  }

  drawNode(node, time) {
    const projection = this.project(node);
    const opacity = this.nodeOpacity(node);
    const color = nodeColor(node);
    const radius = projection.radius;
    const highlight =
      String(node.id || "") === this.selectedNodeId ||
      String(node.id || "") === this.hoveredNodeId ||
      this.searchMatches.has(String(node.id || ""));
    const pulse = 1 + Math.sin(time * 0.002 + hashString(node.id || "") / 50) * (0.04 + stageLevel(node) * 0.07);

    if (node.node_type === "cluster_anchor") {
      this.context.strokeStyle = `rgba(148, 182, 238, ${0.18 * opacity})`;
      this.context.lineWidth = 1.5;
      this.context.beginPath();
      this.context.arc(projection.x, projection.y, radius * 2.6 * pulse, 0, Math.PI * 2);
      this.context.stroke();
      return;
    }

    const halo = this.context.createRadialGradient(
      projection.x,
      projection.y,
      radius * 0.2,
      projection.x,
      projection.y,
      radius * 3.6 * pulse,
    );
    halo.addColorStop(0, `${color}B8`);
    halo.addColorStop(0.32, `${color}32`);
    halo.addColorStop(1, "rgba(0, 0, 0, 0)");
    this.context.fillStyle = halo;
    this.context.beginPath();
    this.context.arc(projection.x, projection.y, radius * 3.6 * pulse, 0, Math.PI * 2);
    this.context.fill();

    this.context.fillStyle = color;
    this.context.globalAlpha = opacity;
    this.context.beginPath();
    this.context.arc(projection.x, projection.y, radius * pulse, 0, Math.PI * 2);
    this.context.fill();

    this.context.strokeStyle = highlight ? "rgba(255, 244, 214, 0.72)" : "rgba(255, 255, 255, 0.24)";
    this.context.lineWidth = highlight ? 2 : 1;
    this.context.beginPath();
    this.context.arc(projection.x, projection.y, radius * (highlight ? 1.18 : 1.04), 0, Math.PI * 2);
    this.context.stroke();
    this.context.globalAlpha = 1;

    if (!shouldShowLabel(node, this, projection)) return;
    const text = String(node.label || node.id || "");
    const paddingX = 8;
    const paddingY = 6;
    this.context.font = `600 ${clamp(radius * 2.05, 12, 18)}px "IBM Plex Sans", "SF Pro Display", "Segoe UI", sans-serif`;
    const textWidth = this.context.measureText(text).width;
    const boxWidth = textWidth + paddingX * 2;
    const boxHeight = clamp(radius * 2.1, 24, 34);
    const boxX = projection.x - boxWidth / 2;
    const boxY = projection.y - radius - boxHeight - 10;
    this.context.fillStyle = `rgba(5, 12, 23, ${this.selectedNodeId ? 0.86 : 0.7})`;
    this.context.beginPath();
    this.context.roundRect(boxX, boxY, boxWidth, boxHeight, 999);
    this.context.fill();
    this.context.strokeStyle = "rgba(195, 214, 243, 0.16)";
    this.context.lineWidth = 1;
    this.context.beginPath();
    this.context.roundRect(boxX, boxY, boxWidth, boxHeight, 999);
    this.context.stroke();
    this.context.fillStyle = "rgba(246, 251, 255, 0.96)";
    this.context.textBaseline = "middle";
    this.context.fillText(text, boxX + paddingX, boxY + boxHeight / 2 + 0.5);
  }

  tick() {
    if (this.disposed) return;
    this.camera.x += (this.targetCamera.x - this.camera.x) * 0.09;
    this.camera.y += (this.targetCamera.y - this.camera.y) * 0.09;
    this.camera.zoom += (this.targetCamera.zoom - this.camera.zoom) * 0.08;
    this.camera.tilt += (this.targetCamera.tilt - this.camera.tilt) * 0.08;
    if (this.prefersReducedMotion()) {
      this.camera = { ...this.targetCamera };
    }

    const time = performance.now();
    this.context.clearRect(0, 0, this.width, this.height);
    this.drawStars(time);
    this.drawEdges();
    this.nodes
      .slice()
      .sort((left, right) => Number(left.z || 0) - Number(right.z || 0))
      .forEach((node) => this.drawNode(node, time));
    this.animationFrame = window.requestAnimationFrame(this.tick);
  }

  api() {
    return {
      selectNodeById: (nodeId) => this.selectNodeById(nodeId),
      stageNodeById: (nodeId) => this.stageNodeById(nodeId),
      clearSelection: () => this.clearSelection(),
      nodeIds: () => this.nodes.map((node) => String(node.id || "")),
      nodes: () => this.nodesSnapshot(),
      setSearchMatches: (matches) => this.setSearchMatches(matches),
      setViewMode: (mode) => this.setViewMode(mode),
      getViewMode: () => this.getViewMode(),
      setMotionProfile: (profile) => this.setMotionProfile(profile),
      projectNode: (nodeId) => {
        const node = this.adjacencyBundle.nodeMap.get(String(nodeId || ""));
        return node ? this.project(node) : null;
      },
    };
  }

  destroy() {
    this.disposed = true;
    window.cancelAnimationFrame(this.animationFrame);
    this.container.removeEventListener("pointermove", this.onPointerMove);
    this.container.removeEventListener("pointerdown", this.onPointerDown);
    window.removeEventListener("pointerup", this.onPointerUp);
    this.container.removeEventListener("wheel", this.onWheel);
    window.removeEventListener("resize", this.resize);
    delete this.container.__sedimentGraphApi;
    delete this.container.dataset.graphReady;
    delete this.container.dataset.graphNodeCount;
    this.container.textContent = "";
  }
}

function mountGraph(container, payload, options) {
  if (typeof container.__sedimentGraphCleanup === "function") {
    container.__sedimentGraphCleanup();
  }
  const runtime = new CanvasGraphRuntime(container, payload, options);
  container.dataset.graphReady = "true";
  container.dataset.graphNodeCount = String(runtime.nodes.length);
  container.__sedimentGraphApi = runtime.api();
  container.__sedimentGraphCleanup = () => runtime.destroy();
  return {
    resize() {
      runtime.resize();
    },
    destroy() {
      runtime.destroy();
    },
  };
}

async function fetchGraphPayload(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${response.status}`);
  return response.json();
}

function readPageData() {
  const node = document.getElementById("sediment-page-data");
  if (!node) return {};
  try {
    return JSON.parse(node.textContent || "{}");
  } catch (_error) {
    return {};
  }
}

function mountPortalGraph(container, payload, options = {}) {
  return mountGraph(container, payload, {
    ...options,
    variant: "portal",
    sceneMode: options.sceneMode || payload.scene_mode || "portal",
  });
}

function mountAdminGraph(container, payload, options = {}) {
  return mountGraph(container, payload, {
    ...options,
    variant: "admin",
    sceneMode: options.sceneMode || payload.scene_mode || "admin",
  });
}

window.SedimentGraph = {
  mountPortalGraph,
  mountAdminGraph,
};

async function autoBoot() {
  const pageData = readPageData();
  if (pageData.graphBoot === "manual" || !pageData.graphApi) return;
  const container = document.getElementById("portal-insights-graph");
  if (!container) return;
  try {
    const payload = await fetchGraphPayload(pageData.graphApi);
    mountPortalGraph(container, payload, { pageData });
  } catch (_error) {
    container.innerHTML = '<div class="sediment-graph-empty">Graph unavailable.</div>';
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", autoBoot, { once: true });
} else {
  autoBoot();
}
