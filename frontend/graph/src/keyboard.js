export function installGraphKeyboard({
  onSearch,
  onHotspotPrev,
  onHotspotNext,
  onExplore,
  onEscape,
}) {
  function handler(event) {
    const tagName = String(event.target?.tagName || "").toLowerCase();
    const isTextInput = ["input", "textarea", "select"].includes(tagName);
    if (event.key === "/" && !isTextInput) {
      event.preventDefault();
      if (typeof onSearch === "function") onSearch();
      return;
    }
    if (event.key === "j" || event.key === "J") {
      if (!isTextInput && typeof onHotspotPrev === "function") onHotspotPrev();
      return;
    }
    if (event.key === "k" || event.key === "K") {
      if (!isTextInput && typeof onHotspotNext === "function") onHotspotNext();
      return;
    }
    if ((event.key === "r" || event.key === "R") && !isTextInput) {
      if (typeof onExplore === "function") onExplore();
      return;
    }
    if (event.key === "Escape" && typeof onEscape === "function") {
      onEscape();
    }
  }

  document.addEventListener("keydown", handler);
  return () => {
    document.removeEventListener("keydown", handler);
  };
}
