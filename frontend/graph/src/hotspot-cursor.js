export function createHotspotCursor({ loadQueue, onSelect }) {
  let queue = [];
  let cursor = -1;
  let queueMode = "empty";

  async function refresh(kind = "all") {
    const previousId = queue[cursor]?.id || "";
    const response = await loadQueue(kind);
    const items = Array.isArray(response?.items) ? response.items : Array.isArray(response) ? response : [];
    queue = items.filter((item) => item?.id);
    queueMode = String(response?.mode || (queue.length ? "hotspot" : "empty"));
    cursor = previousId ? queue.findIndex((item) => item.id === previousId) : -1;
    if (cursor < 0 && queue.length) cursor = -1;
    return queue.slice();
  }

  async function move(step) {
    if (!queue.length) {
      await refresh();
    }
    if (!queue.length) return null;
    cursor = (cursor + step + queue.length) % queue.length;
    const item = queue[cursor];
    if (typeof onSelect === "function") {
      await onSelect(item);
    }
    return item;
  }

  return {
    refresh,
    next() {
      return move(1);
    },
    prev() {
      return move(-1);
    },
    current() {
      return queue[cursor] || null;
    },
    items() {
      return queue.slice();
    },
    mode() {
      return queueMode;
    },
  };
}
