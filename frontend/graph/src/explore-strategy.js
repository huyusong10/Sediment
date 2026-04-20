export const STRATEGY_IDS = ["edge_walk", "unvisited", "cluster_round_robin"];

function buildAdjacency(payload) {
  const adjacency = new Map();
  (Array.isArray(payload?.edges) ? payload.edges : []).forEach((edge) => {
    const source = String(edge.source || "");
    const target = String(edge.target || "");
    if (!source || !target) return;
    if (!adjacency.has(source)) adjacency.set(source, []);
    if (!adjacency.has(target)) adjacency.set(target, []);
    adjacency.get(source).push({ nodeId: target, edge });
    adjacency.get(target).push({ nodeId: source, edge });
  });
  return adjacency;
}

export function pickNextExploreNode({
  payload,
  strategyId,
  selectedNodeId,
  visited,
}) {
  const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  const candidates = nodes.filter((node) => String(node?.node_type || "") !== "cluster_anchor");
  if (!candidates.length) return "";
  const visitedCounts = visited || {};
  const adjacency = buildAdjacency(payload);
  const activeId = String(selectedNodeId || "");

  if (strategyId === "cluster_round_robin") {
    const clusterBuckets = new Map();
    candidates.forEach((node) => {
      const clusterId = String(node.cluster_id || "ungrouped");
      if (!clusterBuckets.has(clusterId)) clusterBuckets.set(clusterId, []);
      clusterBuckets.get(clusterId).push(node);
    });
    const bucketOrder = Array.from(clusterBuckets.keys()).sort(
      (left, right) =>
        (clusterBuckets.get(left)?.reduce((sum, node) => sum + Number(visitedCounts[node.id] || 0), 0) || 0) -
        (clusterBuckets.get(right)?.reduce((sum, node) => sum + Number(visitedCounts[node.id] || 0), 0) || 0),
    );
    const nextBucket = clusterBuckets.get(bucketOrder[0]) || [];
    return (
      nextBucket.sort(
        (left, right) =>
          Number(visitedCounts[left.id] || 0) - Number(visitedCounts[right.id] || 0) ||
          Number(right.energy || 0) - Number(left.energy || 0),
      )[0]?.id || ""
    );
  }

  if (strategyId === "unvisited") {
    return (
      candidates.sort(
        (left, right) =>
          Number(visitedCounts[left.id] || 0) - Number(visitedCounts[right.id] || 0) ||
          Number(right.energy || 0) - Number(left.energy || 0),
      )[0]?.id || ""
    );
  }

  const neighbors = adjacency.get(activeId) || [];
  if (!neighbors.length) {
    return (
      candidates.sort(
        (left, right) => Number(right.energy || 0) - Number(left.energy || 0),
      )[0]?.id || ""
    );
  }
  return (
    neighbors
      .map((item) => ({
        id: item.nodeId,
        score:
          Number(item.edge?.activation || 0) * 0.7 +
          Number(item.edge?.pulse_level || 0) * 0.3 -
          Number(visitedCounts[item.nodeId] || 0) * 0.08,
      }))
      .sort((left, right) => right.score - left.score)[0]?.id || ""
  );
}
