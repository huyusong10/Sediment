# ruff: noqa: E501
from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote

from sediment.package_data import read_asset_text


@lru_cache(maxsize=1)
def _logo_mark_svg() -> str:
    return read_asset_text("logo-mark.svg").strip()


@lru_cache(maxsize=1)
def _logo_mark_data_uri() -> str:
    return f"data:image/svg+xml;utf8,{quote(_logo_mark_svg())}"


def _logo_inline(class_name: str = "brand-mark") -> str:
    return _logo_mark_svg().replace("<svg ", f'<svg class="{class_name}" aria-hidden="true" ')


def shared_shell(title: str, body: str, script: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <link rel="icon" type="image/svg+xml" href="{_logo_mark_data_uri()}" />
  <meta name="theme-color" content="#2B1F16" />
  <style>
    :root {{
      --bg: #f4efe4;
      --panel: rgba(255, 250, 241, 0.9);
      --ink: #2e241b;
      --muted: #705b46;
      --line: rgba(91, 70, 48, 0.18);
      --accent: #b85c2d;
      --accent-soft: #f1c7a8;
      --ok: #2f7d5f;
      --warn: #ad7b15;
      --danger: #a43c2b;
      --shadow: 0 24px 60px rgba(54, 34, 13, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(255, 214, 176, 0.6), transparent 28%),
        radial-gradient(circle at top right, rgba(187, 111, 57, 0.16), transparent 24%),
        linear-gradient(180deg, #faf4e9 0%, #f4efe4 100%);
      min-height: 100vh;
    }}
    a {{ color: inherit; }}
    .page {{
      width: min(1280px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}
    .hero {{
      display: grid;
      gap: 18px;
      padding: 28px;
      border: 1px solid var(--line);
      border-radius: 28px;
      background: linear-gradient(135deg, rgba(255, 250, 241, 0.95), rgba(245, 230, 211, 0.88));
      box-shadow: var(--shadow);
      overflow: hidden;
      position: relative;
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -40px -40px auto;
      width: 220px;
      height: 220px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(184, 92, 45, 0.18), transparent 70%);
    }}
    .hero h1 {{
      margin: 0;
      font-size: clamp(32px, 4vw, 56px);
      line-height: 1.02;
      max-width: 12ch;
    }}
    .hero p {{
      margin: 0;
      color: var(--muted);
      max-width: 72ch;
      font-size: 16px;
      line-height: 1.6;
    }}
    .hero-top {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 18px;
      flex-wrap: wrap;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 14px;
      min-width: 0;
    }}
    .brand-mark {{
      width: 62px;
      height: 62px;
      flex: none;
      filter: drop-shadow(0 12px 20px rgba(43, 31, 22, 0.18));
    }}
    .brand-copy {{
      display: grid;
      gap: 4px;
    }}
    .brand-copy span {{
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .brand-copy strong {{
      font-size: 18px;
      line-height: 1.1;
    }}
    .nav {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}
    .chip, button, .button {{
      border: 1px solid var(--line);
      border-radius: 999px;
      background: rgba(255, 250, 241, 0.92);
      color: var(--ink);
      padding: 10px 16px;
      font: inherit;
      cursor: pointer;
      text-decoration: none;
      transition: transform 150ms ease, background 150ms ease;
    }}
    button.primary, .button.primary {{
      background: linear-gradient(135deg, #b85c2d, #cf7d4c);
      color: white;
      border-color: transparent;
    }}
    .chip:hover, button:hover, .button:hover {{
      transform: translateY(-1px);
    }}
    .grid {{
      display: grid;
      gap: 18px;
      margin-top: 20px;
    }}
    .grid.cols-3 {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .grid.cols-2 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 20px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(8px);
    }}
    .panel h2, .panel h3 {{
      margin-top: 0;
      margin-bottom: 10px;
    }}
    .subtle {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
    }}
    .stats {{
      display: grid;
      gap: 14px;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    }}
    .stat {{
      padding: 14px 16px;
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.55);
      border: 1px solid rgba(91, 70, 48, 0.1);
    }}
    .stat strong {{
      display: block;
      font-size: 28px;
      margin-bottom: 4px;
    }}
    .list {{
      display: grid;
      gap: 10px;
    }}
    .card {{
      border: 1px solid rgba(91, 70, 48, 0.1);
      border-radius: 18px;
      padding: 14px 16px;
      background: rgba(255, 255, 255, 0.45);
    }}
    .card.interactive {{
      cursor: pointer;
      transition: transform 150ms ease, border-color 150ms ease, background 150ms ease;
    }}
    .card.interactive:hover {{
      transform: translateY(-1px);
      border-color: rgba(184, 92, 45, 0.26);
      background: rgba(255, 255, 255, 0.62);
    }}
    .row {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}
    .row.spread {{ justify-content: space-between; }}
    input, textarea, select {{
      width: 100%;
      border: 1px solid rgba(91, 70, 48, 0.18);
      border-radius: 16px;
      padding: 12px 14px;
      font: inherit;
      color: var(--ink);
      background: rgba(255, 255, 255, 0.8);
    }}
    textarea {{ min-height: 140px; resize: vertical; }}
    label {{
      display: grid;
      gap: 8px;
      font-size: 14px;
      color: var(--muted);
    }}
    .markdown {{
      white-space: normal;
      line-height: 1.7;
    }}
    .markdown h1, .markdown h2, .markdown h3 {{
      margin-top: 18px;
      margin-bottom: 10px;
    }}
    .markdown p {{
      margin: 10px 0;
    }}
    .markdown ul {{
      padding-left: 20px;
      margin: 10px 0;
    }}
    .markdown code {{
      padding: 2px 6px;
      border-radius: 8px;
      background: rgba(46, 36, 27, 0.08);
      font-family: "SFMono-Regular", Menlo, Monaco, Consolas, monospace;
    }}
    .graph {{
      width: 100%;
      height: 520px;
      border-radius: 20px;
      background:
        radial-gradient(circle at center, rgba(255, 255, 255, 0.68), rgba(241, 220, 195, 0.8));
      border: 1px solid rgba(91, 70, 48, 0.12);
    }}
    .legend {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 10px;
      font-size: 14px;
      color: var(--muted);
    }}
    .legend span::before {{
      content: "";
      display: inline-block;
      width: 10px;
      height: 10px;
      margin-right: 8px;
      border-radius: 50%;
      vertical-align: middle;
      background: currentColor;
    }}
    .severity-bar {{
      display: grid;
      gap: 10px;
    }}
    .severity-item {{
      display: grid;
      gap: 6px;
    }}
    .bar {{
      height: 10px;
      border-radius: 999px;
      overflow: hidden;
      background: rgba(46, 36, 27, 0.08);
    }}
    .bar > span {{
      display: block;
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, #b85c2d, #e09f6c);
    }}
    .tag {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      background: rgba(46, 36, 27, 0.08);
    }}
    .tag.ok {{ background: rgba(47, 125, 95, 0.14); color: var(--ok); }}
    .tag.warn {{ background: rgba(173, 123, 21, 0.14); color: var(--warn); }}
    .tag.danger {{ background: rgba(164, 60, 43, 0.14); color: var(--danger); }}
    .notice {{
      margin-top: 14px;
      padding: 12px 14px;
      border-radius: 16px;
      border: 1px solid rgba(91, 70, 48, 0.14);
      background: rgba(255, 255, 255, 0.5);
      color: var(--muted);
      line-height: 1.5;
    }}
    button:disabled {{
      cursor: wait;
      opacity: 0.7;
      transform: none;
    }}
    .split {{
      display: grid;
      gap: 18px;
      grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
    }}
    .mono {{
      font-family: "SFMono-Regular", Menlo, Monaco, Consolas, monospace;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 13px;
      line-height: 1.6;
    }}
    .empty {{
      padding: 20px;
      border-radius: 16px;
      border: 1px dashed rgba(91, 70, 48, 0.2);
      color: var(--muted);
    }}
    .modal-backdrop {{
      position: fixed;
      inset: 0;
      background: rgba(29, 22, 16, 0.42);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
      z-index: 30;
    }}
    .modal-backdrop[hidden] {{
      display: none;
    }}
    .modal-card {{
      width: min(980px, 100%);
      max-height: min(88vh, 920px);
      overflow: auto;
      padding: 22px;
      border-radius: 24px;
      background: rgba(255, 250, 241, 0.98);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
    }}
    .upload-grid {{
      display: grid;
      gap: 12px;
    }}
    .quartz-frame {{
      width: 100%;
      min-height: 78vh;
      border: 1px solid rgba(91, 70, 48, 0.12);
      border-radius: 24px;
      background: rgba(255, 255, 255, 0.72);
    }}
    @media (max-width: 960px) {{
      .grid.cols-3,
      .grid.cols-2,
      .split {{
        grid-template-columns: 1fr;
      }}
      .page {{
        width: min(100vw - 20px, 1280px);
      }}
      .graph {{
        height: 420px;
      }}
    }}
  </style>
</head>
<body>
  {body}
  <script>
    const kindColors = {{
      concept: '#b85c2d',
      lesson: '#567d8c',
      placeholder: '#b39234',
      index: '#5a6a41'
    }};

    function escapeHtml(value) {{
      return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;');
    }}

    function renderMarkdown(text) {{
      const lines = String(text || '').split('\\n');
      let html = '';
      let inList = false;
      for (const line of lines) {{
        if (line.startsWith('### ')) {{
          if (inList) {{ html += '</ul>'; inList = false; }}
          html += `<h3>${{escapeHtml(line.slice(4))}}</h3>`;
        }} else if (line.startsWith('## ')) {{
          if (inList) {{ html += '</ul>'; inList = false; }}
          html += `<h2>${{escapeHtml(line.slice(3))}}</h2>`;
        }} else if (line.startsWith('# ')) {{
          if (inList) {{ html += '</ul>'; inList = false; }}
          html += `<h1>${{escapeHtml(line.slice(2))}}</h1>`;
        }} else if (line.startsWith('- ')) {{
          if (!inList) {{ html += '<ul>'; inList = true; }}
          html += `<li>${{escapeHtml(line.slice(2))}}</li>`;
        }} else if (!line.trim()) {{
          if (inList) {{ html += '</ul>'; inList = false; }}
        }} else {{
          if (inList) {{ html += '</ul>'; inList = false; }}
          const withCode = escapeHtml(line).replace(/`([^`]+)`/g, '<code>$1</code>');
          html += `<p>${{withCode}}</p>`;
        }}
      }}
      if (inList) {{ html += '</ul>'; }}
      return html || '<div class="empty">暂无内容</div>';
    }}

    async function fetchJson(url, options = {{}}) {{
      const response = await fetch(url, options);
      const data = await response.json();
      if (!response.ok) {{
        throw new Error(data.error || response.statusText);
      }}
      return data;
    }}

    function drawGraph(svg, payload, onSelect) {{
      svg.innerHTML = '';
      const width = svg.clientWidth || 960;
      const height = svg.clientHeight || 520;
      svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
      const centerX = width / 2;
      const centerY = height / 2;
      const groups = {{
        index: [],
        concept: [],
        lesson: [],
        placeholder: []
      }};
      for (const node of payload.nodes) {{
        const bucket = groups[node.kind] || groups.concept;
        bucket.push(node);
      }}
      const radii = {{ index: 90, concept: 180, lesson: 255, placeholder: 330 }};
      const positions = new Map();
      for (const [kind, nodes] of Object.entries(groups)) {{
        nodes.forEach((node, index) => {{
          const angle = (Math.PI * 2 * index) / Math.max(nodes.length, 1) - Math.PI / 2;
          positions.set(node.id, {{
            x: centerX + Math.cos(angle) * radii[kind],
            y: centerY + Math.sin(angle) * radii[kind],
            node
          }});
        }});
      }}

      const edgeLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      const nodeLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      svg.append(edgeLayer, nodeLayer);

      for (const edge of payload.edges) {{
        const from = positions.get(edge.source);
        const to = positions.get(edge.target);
        if (!from || !to) continue;
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', from.x);
        line.setAttribute('y1', from.y);
        line.setAttribute('x2', to.x);
        line.setAttribute('y2', to.y);
        line.setAttribute('stroke', edge.kind === 'related' ? 'rgba(86,125,140,0.26)' : 'rgba(90,106,65,0.24)');
        line.setAttribute('stroke-width', edge.kind === 'related' ? '1.6' : '1.2');
        edgeLayer.append(line);
      }}

      for (const {{ x, y, node }} of positions.values()) {{
        const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        const radius = node.kind === 'index' ? 10 : 14;
        circle.setAttribute('cx', x);
        circle.setAttribute('cy', y);
        circle.setAttribute('r', radius);
        circle.setAttribute('fill', kindColors[node.kind] || '#b85c2d');
        circle.setAttribute('opacity', node.kind === 'placeholder' ? '0.82' : '0.94');
        circle.style.cursor = 'pointer';
        circle.addEventListener('click', () => onSelect(node.id));
        label.setAttribute('x', x + 16);
        label.setAttribute('y', y + 4);
        label.setAttribute('fill', '#3a2c20');
        label.setAttribute('font-size', '12');
        label.textContent = node.label;
        group.append(circle, label);
        nodeLayer.append(group);
      }}
    }}

    {script}
  </script>
</body>
</html>"""


def portal_html(*, knowledge_name: str, instance_name: str) -> str:
    body = f"""
    <div class="page">
      <section class="hero">
        <div class="hero-top">
          <div class="brand">
            {_logo_inline()}
            <div class="brand-copy">
              <span>Sediment</span>
              <strong>{knowledge_name}</strong>
            </div>
          </div>
          <div class="nav">
            <a class="button primary" href="/portal">知识门户</a>
            <a class="button" href="/portal/graph-view">Quartz 图谱</a>
            <a class="button" href="/admin">管理台</a>
          </div>
        </div>
        <h1>{knowledge_name}</h1>
        <p class="subtle">Sediment Knowledge Portal · 实例：{instance_name}</p>
        <p>把主要空间留给全文搜索，把图谱交给独立的 Quartz 页面；门户负责稳定搜索、查看正式知识，并把新概念和文档送入提交缓冲区。</p>
      </section>

      <section class="panel" style="margin-top:20px;">
        <div class="stats" id="portal-stats"></div>
        <div class="notice" id="portal-message" data-testid="portal-message" role="status" aria-live="polite">门户已就绪，可以搜索知识，或把新材料提交到缓冲区。</div>
      </section>

      <section class="panel" style="margin-top:20px;">
        <div class="row spread">
          <h2>全文搜索</h2>
          <span class="subtle">标题、别名、摘要、正文。点击结果可弹出全文。</span>
        </div>
        <div class="row">
          <input id="search-input" data-testid="portal-search-input" placeholder="搜索概念、规则、教训，比如：热备份 泄洪 暗流" />
          <button class="primary" id="search-button" data-testid="portal-search-button">搜索</button>
        </div>
        <div id="search-status" class="subtle" style="margin-top:12px;" role="status" aria-live="polite">输入关键词后即可全文搜索。</div>
        <div class="list" id="search-results" data-testid="portal-search-results" style="margin-top:14px;"></div>
      </section>

      <section class="panel" style="margin-top:20px;">
        <div class="row spread">
          <h2>最近更新</h2>
          <a class="button" href="/portal/graph-view">打开 Quartz 图谱页</a>
        </div>
        <div class="list" id="recent-updates"></div>
      </section>

      <section class="panel" style="margin-top:20px;">
        <h2>提交到缓冲区</h2>
        <p class="subtle">所有提交都会进入缓冲区，由 committer 审核后才能进入正式知识层。系统会记录你的名字与来源 IP，并限制同一 IP 每分钟最多提交 1 次。</p>
        <div class="grid cols-2">
          <div class="card">
            <h3>纯文本概念 / 经验</h3>
            <div class="grid">
              <label>你的名字<input id="submit-name" placeholder="例如：Alice" /></label>
              <label>标题<input id="submit-title" placeholder="例如：泄洪前先确认热备份" /></label>
              <label>类型
                <select id="submit-type">
                  <option value="concept">概念</option>
                  <option value="lesson">经验</option>
                  <option value="feedback">意见</option>
                </select>
              </label>
              <label>内容<textarea id="submit-content" placeholder="写下你的概念、经验、修订建议或问题背景。"></textarea></label>
              <button class="primary" id="submit-text-button" data-testid="portal-submit-text-button">提交文本</button>
              <div id="submit-text-status" class="subtle" role="status" aria-live="polite">文本提交前会先经过 Agent 扫描知识库，并给出 committer 建议。</div>
              <div id="submit-text-analysis" class="empty">这里会显示提交前后的建议摘要，帮助 committer 更快判断。</div>
            </div>
          </div>
          <div class="card">
            <h3>文档上传</h3>
            <div class="grid">
              <label>你的名字<input id="upload-name" placeholder="例如：Alice" /></label>
              <div class="upload-grid">
                <label>上传文件 / 压缩包
                  <input id="upload-file" data-testid="portal-upload-file" type="file" multiple accept=".txt,.md,.docx,.pptx,.zip" />
                </label>
                <label>上传文件夹
                  <input id="upload-folder" data-testid="portal-upload-folder" type="file" webkitdirectory directory multiple />
                </label>
              </div>
              <button class="primary" id="submit-file-button" data-testid="portal-submit-file-button">上传文档</button>
              <div id="submit-file-status" class="subtle" role="status" aria-live="polite">支持单文件、文件夹和 `zip` 压缩包。系统会自动解压并提取其中的文本。</div>
            </div>
          </div>
        </div>
      </section>

      <div id="entry-modal" class="modal-backdrop" hidden>
        <div class="modal-card">
          <div class="row spread">
            <h2 id="entry-modal-title">条目全文</h2>
            <button id="entry-close-button" data-testid="portal-entry-close">关闭</button>
          </div>
          <div id="entry-view" data-testid="portal-entry-view" class="markdown empty">点击搜索结果后在这里查看。</div>
        </div>
      </div>
    </div>
    """

    script = """
    function setPortalMessage(message) {
      document.getElementById('portal-message').textContent = message;
    }

    async function withBusy(buttonId, busyLabel, task) {
      const button = document.getElementById(buttonId);
      const originalLabel = button.textContent;
      button.disabled = true;
      button.textContent = busyLabel;
      try {
        return await task();
      } finally {
        button.disabled = false;
        button.textContent = originalLabel;
      }
    }

    async function loadHome() {
      const payload = await fetchJson('/api/portal/home');
      const stats = [
        ['正式条目', payload.counts.formal_entries],
        ['缺口条目', payload.counts.placeholders],
        ['索引', payload.counts.indexes],
        ['待审提交', payload.counts.pending_submissions],
        ['Health 问题', payload.counts.health_issues]
      ];
      document.getElementById('portal-stats').innerHTML = stats.map(([label, value]) => `
        <div class="stat">
          <strong>${value}</strong>
          <span>${label}</span>
        </div>
      `).join('');

      document.getElementById('recent-updates').innerHTML = payload.recent_updates.length
        ? payload.recent_updates.map(item => `
            <div class="card interactive" data-entry-name="${encodeURIComponent(item.name)}">
              <div class="row spread">
                <strong>${escapeHtml(item.name)}</strong>
                <span class="tag">${escapeHtml(item.entry_type)}</span>
              </div>
            </div>`).join('')
        : '<div class="empty">暂无最近更新</div>';
    }

    async function openEntry(encodedName) {
      const payload = await fetchJson(`/api/portal/entries/${encodedName}`);
      document.getElementById('entry-modal-title').textContent = payload.name;
      document.getElementById('entry-view').innerHTML = `
        <div class="row spread">
          <h3>${escapeHtml(payload.name)}</h3>
          <span class="tag ${payload.metadata.status === 'fact' ? 'ok' : 'warn'}">${escapeHtml(payload.metadata.status || payload.metadata.kind)}</span>
        </div>
        ${renderMarkdown(payload.content)}
      `;
      document.getElementById('entry-modal').hidden = false;
      setPortalMessage(`已打开条目：${payload.name}`);
    }

    async function runSearch() {
      const query = document.getElementById('search-input').value.trim();
      if (!query) {
        document.getElementById('search-status').textContent = '请输入关键词后再搜索。';
        document.getElementById('search-results').innerHTML = '<div class="empty">还没有搜索结果。</div>';
        return;
      }
      const results = await fetchJson(`/api/portal/search?q=${encodeURIComponent(query)}`);
      document.getElementById('search-status').textContent = `找到 ${results.length} 条结果。`;
      document.getElementById('search-results').innerHTML = results.length
        ? results.map(item => `
            <div class="card interactive" data-entry-name="${encodeURIComponent(item.name)}">
              <div class="row spread">
                <strong>${escapeHtml(item.name)}</strong>
                <span class="tag">${escapeHtml(item.entry_type)}</span>
              </div>
              <div class="subtle">${escapeHtml(item.snippet || item.summary || '')}</div>
            </div>`).join('')
        : '<div class="empty">没有搜索到结果</div>';
    }

    async function submitText() {
      const payload = {
        title: document.getElementById('submit-title').value,
        content: document.getElementById('submit-content').value,
        submitter_name: document.getElementById('submit-name').value,
        submission_type: document.getElementById('submit-type').value
      };
      const result = await fetchJson('/api/portal/submissions/text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      document.getElementById('submit-text-status').textContent = `文本提交成功，submission_id=${result.id}`;
      document.getElementById('submit-text-analysis').innerHTML = renderSubmissionAnalysis(result.analysis);
      document.getElementById('submit-title').value = '';
      document.getElementById('submit-content').value = '';
      setPortalMessage(`已提交文本草案：${result.title}`);
      await loadHome();
    }

    async function submitFile() {
      const fileInput = document.getElementById('upload-file');
      const folderInput = document.getElementById('upload-folder');
      const files = Array.from(fileInput.files || []);
      const folderFiles = Array.from(folderInput.files || []);
      if (!files.length && !folderFiles.length) throw new Error('请先选择文件、压缩包或文件夹');
      const payload = {
        submitter_name: document.getElementById('upload-name').value
      };
      if (folderFiles.length || files.length > 1) {
        const bundle = await Promise.all((folderFiles.length ? folderFiles : files).map(async (file) => ({
          filename: file.name,
          relative_path: file.webkitRelativePath || file.name,
          mime_type: file.type || inferMimeType(file.name),
          content_base64: await encodeFileAsBase64(file)
        })));
        payload.filename = folderFiles.length ? inferBundleName(bundle) : 'document-bundle';
        payload.mime_type = 'application/zip';
        payload.files = bundle;
      } else {
        const file = files[0];
        payload.filename = file.name;
        payload.mime_type = file.type || inferMimeType(file.name);
        payload.content_base64 = await encodeFileAsBase64(file);
      }
      const response = await fetch('/api/portal/submissions/document', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '上传失败');
      document.getElementById('submit-file-status').textContent = `文档提交成功，submission_id=${data.id}`;
      fileInput.value = '';
      folderInput.value = '';
      setPortalMessage(`已提交文档：${data.title}`);
      await loadHome();
    }

    async function encodeFileAsBase64(file) {
      const buffer = await file.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      let binary = '';
      for (const byte of bytes) binary += String.fromCharCode(byte);
      return btoa(binary);
    }

    function inferBundleName(files) {
      const roots = new Set(files
        .map(file => String(file.relative_path || '').split('/')[0])
        .filter(Boolean));
      if (roots.size === 1) return Array.from(roots)[0];
      return 'document-bundle';
    }

    function inferMimeType(filename) {
      const lower = filename.toLowerCase();
      if (lower.endsWith('.md')) return 'text/markdown';
      if (lower.endsWith('.txt')) return 'text/plain';
      if (lower.endsWith('.docx')) return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
      if (lower.endsWith('.pptx')) return 'application/vnd.openxmlformats-officedocument.presentationml.presentation';
      if (lower.endsWith('.zip')) return 'application/zip';
      return 'application/octet-stream';
    }

    function renderSubmissionAnalysis(analysis) {
      if (!analysis) return '<div class="empty">暂时没有建议。</div>';
      const related = Array.isArray(analysis.related_entries) && analysis.related_entries.length
        ? analysis.related_entries.map(item => `
            <li><strong>${escapeHtml(item.name)}</strong> · ${escapeHtml(item.reason || '')}</li>
          `).join('')
        : '<li>暂无明显关联条目</li>';
      const warnings = Array.isArray(analysis.warnings) && analysis.warnings.length
        ? `<div class="subtle">${analysis.warnings.map(item => escapeHtml(item)).join('；')}</div>`
        : '';
      return `
        <div class="card">
          <div class="row spread">
            <strong>Agent 建议</strong>
            <span class="tag ${analysis.status === 'ok' ? 'ok' : 'warn'}">${escapeHtml(analysis.status || 'unknown')}</span>
          </div>
          <div class="subtle">${escapeHtml(analysis.summary || '')}</div>
          <div class="subtle">建议标题：${escapeHtml(analysis.recommended_title || '-')}</div>
          <div class="subtle">建议类型：${escapeHtml(analysis.recommended_type || '-')} · 风险：${escapeHtml(analysis.duplicate_risk || '-')} · 下一步：${escapeHtml(analysis.committer_action || '-')}</div>
          <div class="subtle">Committer 提示：${escapeHtml(analysis.committer_note || '')}</div>
          <ul>${related}</ul>
          ${warnings}
        </div>
      `;
    }

    function handleEntryClick(event) {
      const card = event.target.closest('[data-entry-name]');
      if (!card) return;
      openEntry(card.dataset.entryName).catch(showError);
    }

    document.getElementById('search-results').addEventListener('click', handleEntryClick);
    document.getElementById('recent-updates').addEventListener('click', handleEntryClick);

    document.getElementById('search-button').addEventListener('click', () => withBusy('search-button', '搜索中...', () => runSearch()).catch(showError));
    document.getElementById('submit-text-button').addEventListener('click', () => withBusy('submit-text-button', '分析中...', () => submitText()).catch(showError));
    document.getElementById('submit-file-button').addEventListener('click', () => withBusy('submit-file-button', '上传中...', () => submitFile()).catch(showError));
    document.getElementById('entry-close-button').addEventListener('click', () => {
      document.getElementById('entry-modal').hidden = true;
    });
    document.getElementById('entry-modal').addEventListener('click', (event) => {
      if (event.target.id === 'entry-modal') {
        document.getElementById('entry-modal').hidden = true;
      }
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        document.getElementById('entry-modal').hidden = true;
      }
    });
    document.getElementById('search-input').addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        withBusy('search-button', '搜索中...', () => runSearch()).catch(showError);
      }
    });

    function showError(error) {
      document.getElementById('submit-text-status').textContent = error.message;
      document.getElementById('submit-file-status').textContent = error.message;
      document.getElementById('search-status').textContent = error.message;
      setPortalMessage(error.message);
    }

    loadHome().catch(showError);
    """
    return shared_shell(f"{knowledge_name} Portal", body, script)


def portal_graph_html(
    *,
    knowledge_name: str,
    instance_name: str,
    quartz_available: bool,
    quartz_runtime_available: bool,
    quartz_path: str,
    quartz_runtime_path: str,
) -> str:
    remote_install = (
        "curl -fsSL https://raw.githubusercontent.com/huyusong10/Sediment/master/install.sh "
        "| bash -s -- --quartz-only"
    )
    local_install = "bash install.sh --quartz-only"
    manual_install = (
        f"git clone https://github.com/jackyzha0/quartz.git \"{quartz_runtime_path}\"\n"
        f"cd \"{quartz_runtime_path}\"\n"
        "npm i"
    )
    content = (
        """
        <div class="panel" style="margin-top:20px;">
          <div class="row spread">
            <h2>Quartz 4 图谱</h2>
            <span class="subtle">嵌入只读 Quartz 页面</span>
          </div>
          <iframe class="quartz-frame" data-testid="portal-quartz-frame" src="/quartz/"></iframe>
        </div>
        """
        if quartz_available
        else (
            """
        <div class="panel" style="margin-top:20px;">
          <div class="row spread">
            <h2>Quartz 4 图谱</h2>
            <span class="subtle">可选增强能力</span>
          </div>
          <div class="markdown">
            <p>当前实例还没有可嵌入的 Quartz 站点，所以这里暂时不显示图谱。</p>
            <p>"""
            + (
                f"Quartz runtime 还没有安装成功。请优先重跑安装脚本：<code>{remote_install}</code>，"
                f"如果你就在 Sediment 仓库目录里，也可以直接运行 <code>{local_install}</code>。"
                if not quartz_runtime_available
                else f"Quartz runtime 已经存在于 <code>{quartz_runtime_path}</code>，"
                "但当前实例还没有准备好静态图谱站点。"
            )
            + f"""</p>
            <p>如果你想手工安装 Quartz runtime，可以按官方方式执行：</p>
            <pre class="mono">{manual_install}</pre>
            <p>Quartz 4 官方文档要求至少 Node v22 和 npm v10.9.2。runtime 安装完成后，把当前实例可供嵌入的静态站点放到 <code>{quartz_path}</code>，Sediment 就会自动在这里嵌入它。</p>
          </div>
        </div>
        """
        )
    )
    body = f"""
    <div class="page">
      <section class="hero">
        <div class="hero-top">
          <div class="brand">
            {_logo_inline()}
            <div class="brand-copy">
              <span>Sediment</span>
              <strong>{knowledge_name}</strong>
            </div>
          </div>
          <div class="nav">
            <a class="button" href="/portal">知识门户</a>
            <a class="button primary" href="/portal/graph-view">Quartz 图谱</a>
            <a class="button" href="/admin">管理台</a>
          </div>
        </div>
        <h1>{knowledge_name}</h1>
        <p class="subtle">Quartz Graph View · 实例：{instance_name}</p>
        <p>这里承载更完整的只读知识图谱体验，让 Portal 首页保持轻量，把主空间留给搜索与提交。</p>
      </section>
      {content}
    </div>
    """
    return shared_shell(f"{knowledge_name} Quartz Graph", body, "")


def admin_login_html(*, knowledge_name: str, instance_name: str) -> str:
    body = f"""
    <div class="page">
      <section class="hero">
        <div class="hero-top">
          <div class="brand">
            {_logo_inline()}
            <div class="brand-copy">
              <span>Sediment</span>
              <strong>{knowledge_name}</strong>
            </div>
          </div>
          <div class="nav">
            <a class="button" href="/portal">知识门户</a>
            <a class="button primary" href="/admin">管理台登录</a>
          </div>
        </div>
        <h1>{knowledge_name}</h1>
        <p class="subtle">Sediment Admin Sign-in · 实例：{instance_name}</p>
        <p>管理台只开放给 committer 和平台维护者。可以使用服务器启动时终端里显示的一次性 token，或 config 中配置的持久 token 登录。</p>
      </section>

      <section class="panel" style="margin-top:20px; max-width:560px;">
        <div class="grid">
          <label>Admin Token<input id="admin-session-token" data-testid="admin-login-token" type="password" placeholder="输入启动时终端显示的 token，或 config.yaml 中配置的 token" /></label>
          <button class="primary" id="login-button" data-testid="admin-login-button">登录管理台</button>
          <div id="login-status" data-testid="admin-login-status" class="subtle" role="status" aria-live="polite">需要有效 token 才能进入后台。</div>
        </div>
      </section>
    </div>
    """

    script = """
    async function signIn() {
      const token = document.getElementById('admin-session-token').value.trim();
      const response = await fetch('/api/admin/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '登录失败');
      window.location.href = '/admin';
    }

    async function checkSession() {
      const response = await fetch('/api/admin/session');
      const data = await response.json();
      if (data.authenticated) {
        window.location.href = '/admin';
      }
    }

    function showError(error) {
      document.getElementById('login-status').textContent = error.message;
    }

    document.getElementById('login-button').addEventListener('click', () => signIn().catch(showError));
    document.getElementById('admin-session-token').addEventListener('keydown', (event) => {
      if (event.key === 'Enter') signIn().catch(showError);
    });

    checkSession().catch(showError);
    """
    return shared_shell(f"{knowledge_name} Admin Login", body, script)


def admin_html(*, knowledge_name: str, instance_name: str) -> str:
    body = f"""
    <div class="page">
      <section class="hero">
        <div class="hero-top">
          <div class="brand">
            {_logo_inline()}
            <div class="brand-copy">
              <span>Sediment</span>
              <strong>{knowledge_name}</strong>
            </div>
          </div>
          <div class="nav">
            <a class="button" href="/portal">知识门户</a>
            <a class="button primary" href="/admin">管理台</a>
          </div>
        </div>
        <h1>{knowledge_name}</h1>
        <p class="subtle">Sediment Control Room · 实例：{instance_name}</p>
        <div class="row">
          <p>审核提交、发起 ingest/tidy、在线修改 Markdown，并把 health、审计和任务恢复变成常驻后台能力。</p>
        </div>
        <div class="row">
          <button class="primary" id="refresh-admin" data-testid="admin-refresh-button">刷新全部</button>
          <button id="logout-button" data-testid="admin-logout-button">退出登录</button>
          <span class="tag ok">Session 已建立</span>
        </div>
        <div class="notice" id="admin-message" data-testid="admin-message" role="status" aria-live="polite">管理台已就绪，可以从这里处理提交、任务、review 和在线编辑。</div>
      </section>

      <section class="grid cols-3">
        <div class="panel">
          <h2>系统总览</h2>
          <div class="stats" id="admin-stats" data-testid="admin-stats"></div>
        </div>
        <div class="panel">
          <h2>Health 严重度</h2>
          <div class="severity-bar" id="severity-bars" data-testid="admin-severity"></div>
        </div>
        <div class="panel">
          <div class="row spread">
            <h2>系统状态</h2>
            <span class="subtle">auth / queue / limits</span>
          </div>
          <div class="list" id="system-status" data-testid="admin-system-status"></div>
        </div>
      </section>

      <section class="grid cols-3">
        <div class="panel">
          <h2>快速入口</h2>
          <div class="grid">
            <button class="primary" id="refresh-health-button">刷新 Health</button>
            <button id="load-reviews-button">查看待审 Patch</button>
            <button id="refresh-admin-secondary">刷新总览</button>
            <button id="load-audit-button">刷新审计日志</button>
          </div>
        </div>
        <div class="panel">
          <h2>运行策略</h2>
          <div class="subtle" id="ops-notes">后台会自动区分公开提交路径和管理写路径；失败任务可重试，卡住的任务会被 worker 按心跳回收。</div>
        </div>
        <div class="panel">
          <h2>Diff 预览</h2>
          <div id="diff-view" data-testid="admin-diff-view" class="mono empty">选择待审 patch 后在这里查看。</div>
        </div>
      </section>

      <section class="split">
        <div class="panel">
          <div class="row spread">
            <h2>Health Issues</h2>
            <span class="subtle">可直接发起 tidy</span>
          </div>
          <div class="list" id="issue-list" data-testid="admin-issue-list"></div>
        </div>
        <div class="panel">
          <div class="row spread">
            <h2>提交缓冲区</h2>
            <span class="subtle">triage / run ingest</span>
          </div>
          <div class="list" id="submission-list" data-testid="admin-submission-list"></div>
        </div>
      </section>

      <section class="split" style="margin-top:20px;">
        <div class="panel">
          <div class="row spread">
            <h2>任务与审阅</h2>
            <span class="subtle">查看运行中和待审结果</span>
          </div>
          <div class="list" id="review-list" data-testid="admin-review-list"></div>
          <div class="list" id="job-list" data-testid="admin-job-list" style="margin-top:12px;"></div>
        </div>
        <div class="panel">
          <h2>在线编辑</h2>
          <div class="grid">
            <label>条目名<input id="editor-name" data-testid="admin-editor-name" placeholder="例如：热备份" /></label>
            <button id="load-entry-button" data-testid="admin-load-entry-button">加载条目</button>
            <label>内容<textarea id="editor-content" data-testid="admin-editor-content"></textarea></label>
            <button class="primary" id="save-entry-button" data-testid="admin-save-entry-button">保存条目</button>
            <div id="editor-status" data-testid="admin-editor-status" class="subtle" role="status" aria-live="polite">这里会显示校验结果和保存反馈。</div>
          </div>
        </div>
      </section>

      <section class="split" style="margin-top:20px;">
        <div class="panel">
          <div class="row spread">
            <h2>审计日志</h2>
            <span class="subtle">最近的后台动作</span>
          </div>
          <div class="list" id="audit-log-list" data-testid="admin-audit-log-list"></div>
        </div>
        <div class="panel">
          <h2>管理提醒</h2>
          <div class="markdown">
            <p>1. 普通提交只进入缓冲区，不能直接写正式知识层。</p>
            <p>2. Review 通过前请先看 diff 和理由，避免把低置信草案直接提升为组织共识。</p>
            <p>3. 任务进入 <code>cancel_requested</code> 后，worker 会在下一个心跳点终止本地 Agent。</p>
          </div>
        </div>
      </section>
    </div>
    """

    script = """
    function setAdminMessage(message) {
      document.getElementById('admin-message').textContent = message;
    }

    async function withBusyButton(button, busyLabel, task) {
      const originalLabel = button.textContent;
      button.disabled = true;
      button.textContent = busyLabel;
      try {
        return await task();
      } finally {
        button.disabled = false;
        button.textContent = originalLabel;
      }
    }

    async function fetchAdmin(url, options = {}) {
      const response = await fetch(url, options);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || response.statusText);
      return data;
    }

    function renderStats(overview) {
      const stats = [
        ['待审提交', overview.submission_counts.pending || 0],
        ['草案待审', overview.submission_counts.draft_ready || 0],
        ['排队任务', overview.queued_jobs || 0],
        ['运行中任务', overview.running_jobs],
        ['取消中任务', overview.cancel_requested_jobs || 0],
        ['陈旧任务', overview.stale_jobs || 0],
        ['待审 Review', overview.pending_reviews],
        ['阻断问题', overview.severity_counts.blocking || 0]
      ];
      document.getElementById('admin-stats').innerHTML = stats.map(([label, value]) => `
        <div class="stat"><strong>${value}</strong><span>${label}</span></div>
      `).join('');

      const total = Object.values(overview.severity_counts).reduce((sum, value) => sum + value, 0) || 1;
      const severityOrder = ['blocking', 'high', 'medium', 'low'];
      document.getElementById('severity-bars').innerHTML = severityOrder.map(level => {
        const count = overview.severity_counts[level] || 0;
        const width = Math.round((count / total) * 100);
        return `
          <div class="severity-item">
            <div class="row spread"><strong>${level}</strong><span>${count}</span></div>
            <div class="bar"><span style="width:${width}%;"></span></div>
          </div>
        `;
      }).join('');
    }

    async function loadOverview() {
      const overview = await fetchAdmin('/api/admin/overview');
      renderStats(overview);
    }

    async function loadSystemStatus() {
      const payload = await fetchAdmin('/api/admin/system/status');
      const bytesMb = (payload.limits.max_upload_bytes / (1024 * 1024)).toFixed(1);
      document.getElementById('system-status').innerHTML = `
        <div class="card">
          <div class="row spread"><strong>运行模式</strong><span class="tag">${escapeHtml(payload.worker_mode)}</span></div>
          <div class="subtle">管理员鉴权：${payload.auth_required ? '开启' : '关闭'}</div>
          <div class="subtle">可信代理头：${payload.proxy.trust_proxy_headers ? '开启' : '关闭'}</div>
          <div class="subtle">速率限制：每 ${payload.limits.submission_rate_limit_window_seconds}s ${payload.limits.submission_rate_limit_count} 次</div>
          <div class="subtle">文本上限：${payload.limits.max_text_submission_chars} 字符</div>
          <div class="subtle">文档上限：${bytesMb} MiB</div>
          <div class="subtle">任务重试上限：${payload.limits.job_max_attempts}</div>
          <div class="subtle">任务过期阈值：${payload.limits.job_stale_after_seconds}s</div>
          <div class="subtle">Portal：<a href="${payload.urls.portal}" target="_blank" rel="noreferrer">打开门户</a></div>
          <div class="subtle">Admin：<a href="${payload.urls.admin}" target="_blank" rel="noreferrer">当前后台</a></div>
          <div class="subtle">实例：${escapeHtml(payload.instance.name)}</div>
        </div>
      `;
      document.getElementById('ops-notes').textContent =
        `KB=${payload.paths.kb_path} | DB=${payload.paths.db_path} | stale=${payload.queue.stale_jobs}`;
    }

    async function loadIssues() {
      const payload = await fetchAdmin('/api/admin/health/issues');
      document.getElementById('issue-list').innerHTML = payload.issues.length
        ? payload.issues.map((item, index) => `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(item.target)}</strong>
                <span class="tag ${item.severity === 'blocking' || item.severity === 'high' ? 'danger' : item.severity === 'medium' ? 'warn' : 'ok'}">${escapeHtml(item.severity)}</span>
              </div>
              <div class="subtle">${escapeHtml(item.summary)}</div>
              <div class="row" style="margin-top:10px;">
                <button data-action="run-tidy" data-target="${encodeURIComponent(item.target)}" data-issue-type="${encodeURIComponent(item.type || '')}">发起 Tidy</button>
              </div>
            </div>
          `).join('')
        : '<div class="empty">当前没有 issue。</div>';
    }

    async function loadSubmissions() {
      const payload = await fetchAdmin('/api/admin/submissions');
      document.getElementById('submission-list').innerHTML = payload.submissions.length
        ? payload.submissions.map(item => `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(item.title)}</strong>
                <span class="tag">${escapeHtml(item.status)}</span>
              </div>
              <div class="subtle">${escapeHtml(item.submitter_name)} · ${escapeHtml(item.submission_type)}</div>
              <div class="subtle">${escapeHtml(item.created_at || '')}</div>
              ${renderAdminSubmissionAnalysis(item.analysis)}
              <div class="row" style="margin-top:10px;">
                <button data-action="triage-submission" data-submission-id="${item.id}" data-status="triaged">标记已归类</button>
                <button data-action="triage-submission" data-submission-id="${item.id}" data-status="rejected">拒绝提交</button>
                <button class="primary" data-action="run-ingest" data-submission-id="${item.id}">运行 Ingest</button>
              </div>
            </div>
          `).join('')
        : '<div class="empty">暂无提交。</div>';
    }

    function renderAdminSubmissionAnalysis(analysis) {
      if (!analysis) return '';
      const related = Array.isArray(analysis.related_entries) && analysis.related_entries.length
        ? analysis.related_entries.slice(0, 3).map(item => escapeHtml(item.name)).join('、')
        : '暂无明显关联条目';
      return `
        <div class="subtle" style="margin-top:8px;">建议：${escapeHtml(analysis.recommended_type || '-')} · ${escapeHtml(analysis.duplicate_risk || '-')} 风险 · ${escapeHtml(analysis.committer_action || '-')}</div>
        <div class="subtle">${escapeHtml(analysis.summary || '')}</div>
        <div class="subtle">关联：${related}</div>
      `;
    }

    async function loadReviews() {
      const payload = await fetchAdmin('/api/admin/reviews?decision=pending');
      document.getElementById('review-list').innerHTML = payload.reviews.length
        ? payload.reviews.map(item => `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(item.job.job_type)} · ${escapeHtml(item.job.id.slice(0, 8))}</strong>
                <span class="tag">${escapeHtml(item.decision)}</span>
              </div>
              <div class="subtle">${escapeHtml(item.job.result_payload?.summary || '')}</div>
              <div class="row" style="margin-top:10px;">
                <button data-action="show-diff" data-review-id="${item.id}">查看 Diff</button>
                <button class="primary" data-action="approve-review" data-review-id="${item.id}">批准</button>
                <button data-action="reject-review" data-review-id="${item.id}">拒绝</button>
              </div>
            </div>
          `).join('')
        : '<div class="empty">暂无待审 patch。</div>';
    }

    async function loadJobs() {
      const payload = await fetchAdmin('/api/admin/jobs');
      document.getElementById('job-list').innerHTML = payload.jobs.length
        ? payload.jobs.map(item => `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(item.job_type)} · ${escapeHtml(item.id.slice(0, 8))}</strong>
                <span class="tag">${escapeHtml(item.status)}</span>
              </div>
              <div class="subtle">${escapeHtml(item.error_message || item.result_payload?.summary || '')}</div>
              <div class="subtle">尝试 ${item.attempt_count || 0}/${item.max_attempts || 0}</div>
              <div class="row" style="margin-top:10px;">
                ${['failed', 'cancelled'].includes(item.status) ? `<button data-action="retry-job" data-job-id="${item.id}">重试</button>` : ''}
                ${['queued', 'running', 'awaiting_review'].includes(item.status) ? `<button data-action="cancel-job" data-job-id="${item.id}">取消</button>` : ''}
              </div>
            </div>
          `).join('')
        : '<div class="empty">暂无任务。</div>';
    }

    async function loadAuditLogs() {
      const payload = await fetchAdmin('/api/admin/audit?limit=20');
      document.getElementById('audit-log-list').innerHTML = payload.logs.length
        ? payload.logs.map(item => `
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(item.action)}</strong>
                <span class="tag">${escapeHtml(item.actor_role)}</span>
              </div>
              <div class="subtle">${escapeHtml(item.actor_name)} · ${escapeHtml(item.target_type)} · ${escapeHtml(item.created_at)}</div>
              <div class="subtle">${escapeHtml(JSON.stringify(item.details || {}))}</div>
            </div>
          `).join('')
        : '<div class="empty">暂无审计日志。</div>';
    }

    async function triageSubmission(id, status) {
      await fetchAdmin(`/api/admin/submissions/${id}/triage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, actor_name: 'admin-web' })
      });
      setAdminMessage(`提交 ${id.slice(0, 8)} 已标记为 ${status}。`);
      await refreshAdmin();
    }

    async function runIngest(id) {
      await fetchAdmin(`/api/admin/submissions/${id}/run-ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actor_name: 'admin-web' })
      });
      setAdminMessage(`已为提交 ${id.slice(0, 8)} 创建 ingest 任务。`);
      await refreshAdmin();
    }

    async function runTidy(issue) {
      await fetchAdmin('/api/admin/tidy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ issue, actor_name: 'admin-web' })
      });
      setAdminMessage(`已为 ${issue.target} 创建 tidy 任务。`);
      await refreshAdmin();
    }

    async function showDiff(reviewId) {
      const payload = await fetchAdmin(`/api/admin/reviews/${reviewId}`);
      const operations = payload.job.result_payload?.operations || [];
      document.getElementById('diff-view').textContent = operations.length
        ? operations.map(item => item.diff).join('\\n\\n')
        : '当前 review 没有 diff。';
      setAdminMessage(`已加载 review ${reviewId.slice(0, 8)} 的 diff。`);
    }

    async function approveReview(reviewId) {
      await fetchAdmin(`/api/admin/reviews/${reviewId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewer_name: 'admin-web', comment: 'Approved from admin UI' })
      });
      setAdminMessage(`Review ${reviewId.slice(0, 8)} 已批准。`);
      await refreshAdmin();
    }

    async function rejectReview(reviewId) {
      await fetchAdmin(`/api/admin/reviews/${reviewId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewer_name: 'admin-web', comment: 'Rejected from admin UI' })
      });
      setAdminMessage(`Review ${reviewId.slice(0, 8)} 已拒绝。`);
      await refreshAdmin();
    }

    async function loadEntryForEdit() {
      const name = document.getElementById('editor-name').value.trim();
      const payload = await fetchAdmin(`/api/admin/entries/${encodeURIComponent(name)}`);
      document.getElementById('editor-content').value = payload.content;
      document.getElementById('editor-status').textContent = `已加载 ${payload.name}，hash=${payload.content_hash.slice(0, 12)}`;
      document.getElementById('editor-content').dataset.hash = payload.content_hash;
      setAdminMessage(`已载入条目：${payload.name}`);
    }

    async function saveEntry() {
      const name = document.getElementById('editor-name').value.trim();
      const content = document.getElementById('editor-content').value;
      const expected_hash = document.getElementById('editor-content').dataset.hash || null;
      const payload = await fetchAdmin(`/api/admin/entries/${encodeURIComponent(name)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, expected_hash, actor_name: 'admin-web' })
      });
      document.getElementById('editor-status').textContent = `保存成功：${payload.name}`;
      document.getElementById('editor-content').dataset.hash = payload.content_hash;
      setAdminMessage(`条目 ${payload.name} 已保存。`);
      await refreshAdmin();
    }

    async function retryJob(jobId) {
      await fetchAdmin(`/api/admin/jobs/${jobId}/retry`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actor_name: 'admin-web' })
      });
      setAdminMessage(`任务 ${jobId.slice(0, 8)} 已重新入队。`);
      await refreshAdmin();
    }

    async function cancelJob(jobId) {
      await fetchAdmin(`/api/admin/jobs/${jobId}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actor_name: 'admin-web', reason: 'Cancelled from admin UI' })
      });
      setAdminMessage(`任务 ${jobId.slice(0, 8)} 已请求取消。`);
      await refreshAdmin();
    }

    async function logoutAdmin() {
      await fetch('/api/admin/session', { method: 'DELETE' });
      window.location.href = '/admin';
    }

    async function refreshAdmin() {
      await Promise.all([
        loadOverview(),
        loadSystemStatus(),
        loadIssues(),
        loadSubmissions(),
        loadReviews(),
        loadJobs(),
        loadAuditLogs()
      ]);
    }

    async function handleIssueAction(event) {
      const button = event.target.closest('button[data-action="run-tidy"]');
      if (!button) return;
      const issue = {
        target: decodeURIComponent(button.dataset.target),
        type: button.dataset.issueType ? decodeURIComponent(button.dataset.issueType) : null
      };
      await withBusyButton(button, '排队中...', () => runTidy(issue));
    }

    async function handleSubmissionAction(event) {
      const button = event.target.closest('button[data-action]');
      if (!button) return;
      if (button.dataset.action === 'triage-submission') {
        await withBusyButton(
          button,
          '处理中...',
          () => triageSubmission(button.dataset.submissionId, button.dataset.status)
        );
        return;
      }
      if (button.dataset.action === 'run-ingest') {
        await withBusyButton(
          button,
          '排队中...',
          () => runIngest(button.dataset.submissionId)
        );
      }
    }

    async function handleReviewAction(event) {
      const button = event.target.closest('button[data-action]');
      if (!button) return;
      const reviewId = button.dataset.reviewId;
      if (button.dataset.action === 'show-diff') {
        await withBusyButton(button, '加载中...', () => showDiff(reviewId));
        return;
      }
      if (button.dataset.action === 'approve-review') {
        await withBusyButton(button, '批准中...', () => approveReview(reviewId));
        return;
      }
      if (button.dataset.action === 'reject-review') {
        await withBusyButton(button, '拒绝中...', () => rejectReview(reviewId));
      }
    }

    async function handleJobAction(event) {
      const button = event.target.closest('button[data-action]');
      if (!button) return;
      const jobId = button.dataset.jobId;
      if (button.dataset.action === 'retry-job') {
        await withBusyButton(button, '重试中...', () => retryJob(jobId));
        return;
      }
      if (button.dataset.action === 'cancel-job') {
        await withBusyButton(button, '取消中...', () => cancelJob(jobId));
      }
    }

    document.getElementById('issue-list').addEventListener('click', (event) => handleIssueAction(event).catch(showAdminError));
    document.getElementById('submission-list').addEventListener('click', (event) => handleSubmissionAction(event).catch(showAdminError));
    document.getElementById('review-list').addEventListener('click', (event) => handleReviewAction(event).catch(showAdminError));
    document.getElementById('job-list').addEventListener('click', (event) => handleJobAction(event).catch(showAdminError));

    document.getElementById('refresh-admin').addEventListener('click', (event) => withBusyButton(event.currentTarget, '刷新中...', () => refreshAdmin()).catch(showAdminError));
    document.getElementById('refresh-admin-secondary').addEventListener('click', (event) => withBusyButton(event.currentTarget, '刷新中...', () => refreshAdmin()).catch(showAdminError));
    document.getElementById('refresh-health-button').addEventListener('click', (event) => withBusyButton(event.currentTarget, '刷新中...', () => loadIssues()).catch(showAdminError));
    document.getElementById('load-reviews-button').addEventListener('click', (event) => withBusyButton(event.currentTarget, '加载中...', () => loadReviews()).catch(showAdminError));
    document.getElementById('load-audit-button').addEventListener('click', (event) => withBusyButton(event.currentTarget, '加载中...', () => loadAuditLogs()).catch(showAdminError));
    document.getElementById('load-entry-button').addEventListener('click', (event) => withBusyButton(event.currentTarget, '加载中...', () => loadEntryForEdit()).catch(showAdminError));
    document.getElementById('save-entry-button').addEventListener('click', (event) => withBusyButton(event.currentTarget, '保存中...', () => saveEntry()).catch(showAdminError));
    document.getElementById('logout-button').addEventListener('click', () => logoutAdmin().catch(showAdminError));

    function showAdminError(error) {
      document.getElementById('diff-view').textContent = error.message;
      setAdminMessage(error.message);
    }

    refreshAdmin().catch(showAdminError);
    setInterval(() => refreshAdmin().catch(showAdminError), 20000);
    """
    return shared_shell(f"{knowledge_name} Admin", body, script)
