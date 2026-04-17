(function () {
  function readJsonScript(id) {
    const node = document.getElementById(id);
    if (!node) return null;
    try {
      return JSON.parse(node.textContent || "null");
    } catch (_error) {
      return null;
    }
  }

  const shellData = readJsonScript("sediment-shell-data") || {};

  function nextThemeInfo() {
    return document.documentElement.classList.contains("dark")
      ? {
          icon: shellData.themeLightIcon || "\u2600",
          label: shellData.themeLightLabel || "Light",
        }
      : {
          icon: shellData.themeDarkIcon || "\u25d0",
          label: shellData.themeDarkLabel || "Dark",
        };
  }

  function applyInitialTheme() {
    const savedTheme = localStorage.getItem("theme");
    if (savedTheme === "dark") {
      document.documentElement.classList.add("dark");
      return;
    }
    if (savedTheme === "light") {
      document.documentElement.classList.remove("dark");
      return;
    }
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      document.documentElement.classList.add("dark");
    }
  }

  function attachShellNav() {
    document.querySelectorAll("[data-shell-nav]").forEach((nav) => {
      let utility = nav.parentElement?.querySelector("[data-shell-utility]") || null;
      if (!utility && nav.parentElement) {
        utility = document.createElement("div");
        utility.className = "nav utility-bar";
        utility.setAttribute("data-shell-utility", "");
        nav.parentElement.appendChild(utility);
      }
      if (utility && utility.dataset.enhanced !== "true") {
        const iconGroup = document.createElement("div");
        iconGroup.className = "utility-icons";

        const themeBtn = document.createElement("button");
        themeBtn.className = "utility-icon-button";
        themeBtn.type = "button";
        const applyThemeButton = () => {
          const next = nextThemeInfo();
          themeBtn.innerHTML = `<span aria-hidden="true">${next.icon}</span>`;
          themeBtn.title = next.label;
          themeBtn.setAttribute("aria-label", next.label);
        };
        applyThemeButton();
        themeBtn.addEventListener("click", () => {
          document.documentElement.classList.toggle("dark");
          const isDark = document.documentElement.classList.contains("dark");
          localStorage.setItem("theme", isDark ? "dark" : "light");
          applyThemeButton();
        });

        const langBtn = document.createElement("button");
        langBtn.className = "utility-icon-button";
        langBtn.type = "button";
        langBtn.innerHTML = `<span aria-hidden="true">${shellData.toggleLabel || "EN"}</span>`;
        langBtn.title = shellData.toggleAriaLabel || "Switch language";
        langBtn.setAttribute("aria-label", shellData.toggleAriaLabel || "Switch language");
        langBtn.addEventListener("click", () => {
          const currentUrl = new URL(window.location.href);
          currentUrl.searchParams.set(
            "lang",
            document.documentElement.dataset.locale === "zh" ? "en" : "zh"
          );
          window.location.href = currentUrl.toString();
        });

        iconGroup.append(themeBtn, langBtn);
        utility.append(iconGroup);
        utility.dataset.enhanced = "true";
      }

    });
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function renderMarkdown(text) {
    const lines = String(text || "").split("\n");
    let html = "";
    let inList = false;
    for (const line of lines) {
      if (line.startsWith("### ")) {
        if (inList) {
          html += "</ul>";
          inList = false;
        }
        html += `<h3>${escapeHtml(line.slice(4))}</h3>`;
      } else if (line.startsWith("## ")) {
        if (inList) {
          html += "</ul>";
          inList = false;
        }
        html += `<h2>${escapeHtml(line.slice(3))}</h2>`;
      } else if (line.startsWith("# ")) {
        if (inList) {
          html += "</ul>";
          inList = false;
        }
        html += `<h1>${escapeHtml(line.slice(2))}</h1>`;
      } else if (line.startsWith("- ")) {
        if (!inList) {
          html += "<ul>";
          inList = true;
        }
        html += `<li>${escapeHtml(line.slice(2))}</li>`;
      } else if (!line.trim()) {
        if (inList) {
          html += "</ul>";
          inList = false;
        }
      } else {
        if (inList) {
          html += "</ul>";
          inList = false;
        }
        const withCode = escapeHtml(line).replace(/`([^`]+)`/g, "<code>$1</code>");
        html += `<p>${withCode}</p>`;
      }
    }
    if (inList) {
      html += "</ul>";
    }
    return (
      html ||
      `<div class="empty">${
        document.documentElement.dataset.locale === "zh" ? "暂无内容" : "No content"
      }</div>`
    );
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || response.statusText);
    }
    return data;
  }

  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || "");
        resolve(result.includes(",") ? result.split(",", 2)[1] : result);
      };
      reader.onerror = () => reject(reader.error || new Error("Failed to read file"));
      reader.readAsDataURL(file);
    });
  }

  async function collectUploads(files) {
    const list = Array.from(files || []);
    return Promise.all(
      list.map(async (file) => ({
        filename: file.name,
        relative_path: file.webkitRelativePath || file.name,
        mime_type: file.type || "application/octet-stream",
        content_base64: await fileToBase64(file),
      }))
    );
  }

  function resolveFilePickerRoot(target) {
    if (!target) return null;
    if (typeof target === "string") {
      const input = document.getElementById(target);
      return input ? input.closest("[data-file-picker]") : null;
    }
    if (typeof Element !== "undefined" && target instanceof Element) {
      return target.matches("[data-file-picker]") ? target : target.closest("[data-file-picker]");
    }
    return null;
  }

  function summarizeFileSelection(files, statusNode) {
    const items = Array.from(files || []);
    if (!items.length) {
      return statusNode?.dataset.emptyLabel || "";
    }
    const sample = items
      .slice(0, 3)
      .map((file) => file.webkitRelativePath || file.name || "")
      .filter(Boolean)
      .join(" · ");
    if (items.length === 1) {
      return sample;
    }
    const prefix = statusNode?.dataset.selectedPrefix || "Selected";
    const suffix = statusNode?.dataset.selectedSuffix || "files";
    const overflow = items.length > 3 ? ` +${items.length - 3}` : "";
    return `${prefix} ${items.length} ${suffix} · ${sample}${overflow}`;
  }

  function syncFilePickerState(target) {
    const root = resolveFilePickerRoot(target);
    if (!root) return;
    const input = root.querySelector('input[type="file"]');
    const statusNode = root.querySelector("[data-file-picker-status]");
    if (!input || !statusNode) return;
    const files = Array.from(input.files || []);
    root.dataset.hasSelection = files.length ? "true" : "false";
    statusNode.textContent = summarizeFileSelection(files, statusNode);
  }

  function enhanceLocalizedFilePickers() {
    document.querySelectorAll("[data-file-picker]").forEach((root) => {
      const input = root.querySelector('input[type="file"]');
      if (!input) return;
      if (input.dataset.filePickerBound !== "true") {
        input.addEventListener("change", () => syncFilePickerState(root));
        input.dataset.filePickerBound = "true";
      }
      syncFilePickerState(root);
    });
  }

  function safeSessionStorage() {
    try {
      return window.sessionStorage;
    } catch (_error) {
      return null;
    }
  }

  function readSessionState(key, fallback = null) {
    const storage = safeSessionStorage();
    if (!storage || !key) return fallback;
    try {
      const raw = storage.getItem(String(key));
      if (!raw) return fallback;
      return JSON.parse(raw);
    } catch (_error) {
      return fallback;
    }
  }

  function writeSessionState(key, value) {
    const storage = safeSessionStorage();
    if (!storage || !key) return;
    try {
      if (value == null) {
        storage.removeItem(String(key));
        return;
      }
      storage.setItem(String(key), JSON.stringify(value));
    } catch (_error) {
      // Ignore quota and privacy mode failures.
    }
  }

  function clearSessionStatePrefix(prefix) {
    const storage = safeSessionStorage();
    if (!storage || !prefix) return;
    try {
      const keys = [];
      for (let index = 0; index < storage.length; index += 1) {
        const key = storage.key(index);
        if (key && key.startsWith(String(prefix))) {
          keys.push(key);
        }
      }
      keys.forEach((key) => storage.removeItem(key));
    } catch (_error) {
      // Ignore privacy mode failures.
    }
  }

  window.SedimentShell = {
    clearSessionStatePrefix,
    collectUploads,
    enhanceLocalizedFilePickers,
    escapeHtml,
    fetchJson,
    fileToBase64,
    readSessionState,
    readJsonScript,
    renderMarkdown,
    shellData,
    syncFilePickerState,
    writeSessionState,
  };

  applyInitialTheme();
  document.addEventListener("DOMContentLoaded", () => {
    attachShellNav();
    enhanceLocalizedFilePickers();
  });
})();
