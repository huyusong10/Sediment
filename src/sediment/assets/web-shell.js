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
        utility.className = "nav";
        utility.setAttribute("data-shell-utility", "");
        nav.parentElement.appendChild(utility);
      }
      if (!utility || utility.dataset.enhanced === "true") {
        return;
      }
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

  window.SedimentShell = {
    escapeHtml,
    fetchJson,
    readJsonScript,
    renderMarkdown,
    shellData,
  };

  applyInitialTheme();
  document.addEventListener("DOMContentLoaded", attachShellNav);
})();
