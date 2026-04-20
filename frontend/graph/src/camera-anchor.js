function distance(left, right) {
  return Math.hypot(
    Number(left?.x || 0) - Number(right?.x || 0),
    Number(left?.y || 0) - Number(right?.y || 0),
    Number(left?.z || 0) - Number(right?.z || 0),
  );
}

function averageTarget(nodes) {
  const visible = Array.isArray(nodes)
    ? nodes.filter((node) => String(node?.node_type || "") !== "cluster_anchor")
    : [];
  if (!visible.length) return { x: 0, y: 0, z: 0 };
  const sum = visible.reduce(
    (accumulator, node) => ({
      x: accumulator.x + Number(node.x || 0),
      y: accumulator.y + Number(node.y || 0),
      z: accumulator.z + Number(node.z || 0),
    }),
    { x: 0, y: 0, z: 0 },
  );
  return {
    x: sum.x / visible.length,
    y: sum.y / visible.length,
    z: sum.z / visible.length,
  };
}

export function installCameraAnchor({ graph, sceneMode, state }) {
  const controls = graph.controls();
  let centerTarget = { x: 0, y: 0, z: 0 };
  const isStaticPortalScene = String(sceneMode || "").includes("portal") && !String(sceneMode || "").includes("admin");

  function focusTarget() {
    const node = state.nodeIndex?.get(String(state.selectedNodeId || ""));
    if (!node) return null;
    return {
      x: Number(node.x || 0),
      y: Number(node.y || 0),
      z: Number(node.z || 0),
    };
  }

  return {
    updateCenter(nodes) {
      centerTarget = averageTarget(nodes);
    },
    tick() {
      const stickyTarget = focusTarget();
      const target = stickyTarget || centerTarget;
      const current = controls.target;
      const gap = distance(current, target);
      const isSticky = Boolean(stickyTarget);
      const pull = isSticky ? 0.18 : isStaticPortalScene ? 0 : gap > 48 ? 0.07 : 0.02;
      current.x += (target.x - current.x) * pull;
      current.y += (target.y - current.y) * pull;
      current.z += (target.z - current.z) * pull;
      if (isStaticPortalScene) {
        controls.dampingFactor = isSticky ? 0.08 : 0.05;
      } else if (String(sceneMode || "").includes("universe")) {
        controls.dampingFactor = gap > 132 ? 0.02 : 0.08;
      }
    },
    debugState() {
      const target = focusTarget();
      return {
        target: {
          x: Number(controls.target.x || 0),
          y: Number(controls.target.y || 0),
          z: Number(controls.target.z || 0),
        },
        centerTarget,
        focusTarget: target,
        focusDistance: target ? distance(controls.target, target) : distance(controls.target, centerTarget),
        dampingFactor: Number(controls.dampingFactor || 0),
        enablePan: Boolean(controls.enablePan),
        mouseButtons: controls.mouseButtons
          ? {
              left: Number(controls.mouseButtons.LEFT),
              middle: Number(controls.mouseButtons.MIDDLE),
              right: Number(controls.mouseButtons.RIGHT),
            }
          : null,
      };
    },
  };
}
