function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(value, maximum));
}

function graphBounds(nodes) {
  const visible = Array.isArray(nodes) ? nodes : [];
  if (!visible.length) {
    return { minX: -1, maxX: 1, minZ: -1, maxZ: 1 };
  }
  return visible.reduce(
    (bounds, node) => ({
      minX: Math.min(bounds.minX, Number(node.x || 0)),
      maxX: Math.max(bounds.maxX, Number(node.x || 0)),
      minZ: Math.min(bounds.minZ, Number(node.z || 0)),
      maxZ: Math.max(bounds.maxZ, Number(node.z || 0)),
    }),
    { minX: Infinity, maxX: -Infinity, minZ: Infinity, maxZ: -Infinity },
  );
}

function project(bounds, width, height, x, z) {
  const spanX = Math.max(bounds.maxX - bounds.minX, 1);
  const spanZ = Math.max(bounds.maxZ - bounds.minZ, 1);
  return {
    x: ((x - bounds.minX) / spanX) * width,
    y: ((z - bounds.minZ) / spanZ) * height,
  };
}

export function mountMiniMap({ titleNode, canvas, frustumNode }) {
  const context = canvas?.getContext("2d");
  if (!context || !canvas) {
    return { update() {}, destroy() {} };
  }

  return {
    update({ payload, cameraTarget, focusNode, title }) {
      if (titleNode) titleNode.textContent = title || "";
      const width = canvas.width;
      const height = canvas.height;
      context.clearRect(0, 0, width, height);
      context.fillStyle = "rgba(7, 14, 26, 0.92)";
      context.fillRect(0, 0, width, height);
      const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
      const bounds = graphBounds(nodes);
      nodes.forEach((node) => {
        const point = project(bounds, width, height, Number(node.x || 0), Number(node.z || 0));
        context.beginPath();
        context.fillStyle =
          focusNode && String(focusNode.id || "") === String(node.id || "")
            ? "rgba(255, 190, 107, 0.96)"
            : "rgba(124, 216, 255, 0.88)";
        context.arc(point.x, point.y, node.node_type === "cluster_anchor" ? 3.5 : 2.2, 0, Math.PI * 2);
        context.fill();
      });
      const targetPoint = project(
        bounds,
        width,
        height,
        Number(cameraTarget?.x || 0),
        Number(cameraTarget?.z || 0),
      );
      if (frustumNode) {
        const boxSize = focusNode ? 42 : 56;
        frustumNode.style.left = `${clamp(targetPoint.x - boxSize / 2, 0, width - boxSize)}px`;
        frustumNode.style.top = `${clamp(targetPoint.y - boxSize / 2, 0, height - boxSize)}px`;
        frustumNode.style.width = `${boxSize}px`;
        frustumNode.style.height = `${boxSize}px`;
      }
    },
    destroy() {
      context.clearRect(0, 0, canvas.width, canvas.height);
    },
  };
}
