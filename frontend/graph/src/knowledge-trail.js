export function createKnowledgeTrail() {
  let start = null;
  let end = null;
  let edges = [];

  return {
    setStart(node) {
      start = node ? { id: String(node.id || ""), label: String(node.label || node.id || "") } : null;
      return start;
    },
    setEnd(node) {
      end = node ? { id: String(node.id || ""), label: String(node.label || node.id || "") } : null;
      return end;
    },
    setEdges(items) {
      edges = Array.isArray(items) ? items.slice() : [];
      return edges.slice();
    },
    clear() {
      start = null;
      end = null;
      edges = [];
    },
    state() {
      return {
        start,
        end,
        edges: edges.slice(),
      };
    },
  };
}
