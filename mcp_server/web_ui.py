# ruff: noqa: E501
from __future__ import annotations


def shared_shell(title: str, body: str, script: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
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


def portal_html() -> str:
    body = """
    <div class="page">
      <section class="hero">
        <div class="nav">
          <a class="button primary" href="/portal">知识门户</a>
          <a class="button" href="/admin">管理台</a>
        </div>
        <h1>Sediment Knowledge Portal</h1>
        <p>查看正式知识层、做全文搜索、浏览概念图谱，并把新的概念、文档和意见稳定送入提交缓冲区。</p>
      </section>

      <section class="panel" style="margin-top:20px;">
        <div class="stats" id="portal-stats"></div>
      </section>

      <section class="grid cols-2">
        <div class="panel">
          <div class="row spread">
            <h2>全文搜索</h2>
            <span class="subtle">标题、别名、摘要、正文</span>
          </div>
          <div class="row">
            <input id="search-input" placeholder="搜索概念、规则、教训，比如：热备份 泄洪 暗流" />
            <button class="primary" id="search-button">搜索</button>
          </div>
          <div class="list" id="search-results" style="margin-top:14px;"></div>
        </div>

        <div class="panel">
          <h2>条目全文</h2>
          <div id="entry-view" class="markdown empty">点击搜索结果或图谱节点后在这里查看。</div>
        </div>
      </section>

      <section class="panel" style="margin-top:20px;">
        <div class="row spread">
          <h2>知识图谱</h2>
          <div class="legend">
            <span style="color:#b85c2d">Concept</span>
            <span style="color:#567d8c">Lesson</span>
            <span style="color:#b39234">Placeholder</span>
            <span style="color:#5a6a41">Index</span>
          </div>
        </div>
        <svg id="graph" class="graph"></svg>
      </section>

      <section class="grid cols-2">
        <div class="panel">
          <h2>最近更新</h2>
          <div class="list" id="recent-updates"></div>
        </div>
        <div class="panel">
          <h2>热门条目</h2>
          <div class="list" id="popular-entries"></div>
        </div>
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
              <button class="primary" id="submit-text-button">提交文本</button>
            </div>
          </div>
          <div class="card">
            <h3>文档上传</h3>
            <div class="grid">
              <label>你的名字<input id="upload-name" placeholder="例如：Alice" /></label>
              <label>上传文件<input id="upload-file" type="file" accept=".txt,.md,.docx,.pptx" /></label>
              <button class="primary" id="submit-file-button">上传文档</button>
              <div id="submit-status" class="subtle">支持 `txt`、`md`、`docx`、`pptx`。</div>
            </div>
          </div>
        </div>
      </section>
    </div>
    """

    script = """
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
            <div class="card">
              <div class="row spread">
                <strong>${escapeHtml(item.name)}</strong>
                <span class="tag">${escapeHtml(item.entry_type)}</span>
              </div>
            </div>`).join('')
        : '<div class="empty">暂无最近更新</div>';

      document.getElementById('popular-entries').innerHTML = payload.popular_entries.length
        ? payload.popular_entries.map(item => `
            <div class="card" onclick="loadEntry('${encodeURIComponent(item.name)}')" style="cursor:pointer;">
              <div class="row spread">
                <strong>${escapeHtml(item.name)}</strong>
                <span class="tag">${item.inbound_count} 入链</span>
              </div>
              <div class="subtle">${escapeHtml(item.summary || '')}</div>
            </div>`).join('')
        : '<div class="empty">暂无条目</div>';
    }

    async function loadEntry(encodedName) {
      const payload = await fetchJson(`/api/portal/entries/${encodedName}`);
      document.getElementById('entry-view').innerHTML = `
        <div class="row spread">
          <h3>${escapeHtml(payload.name)}</h3>
          <span class="tag ${payload.metadata.status === 'fact' ? 'ok' : 'warn'}">${escapeHtml(payload.metadata.status || payload.metadata.kind)}</span>
        </div>
        ${renderMarkdown(payload.content)}
      `;
    }

    async function runSearch() {
      const query = document.getElementById('search-input').value.trim();
      const results = await fetchJson(`/api/portal/search?q=${encodeURIComponent(query)}`);
      document.getElementById('search-results').innerHTML = results.length
        ? results.map(item => `
            <div class="card" onclick="loadEntry('${encodeURIComponent(item.name)}')" style="cursor:pointer;">
              <div class="row spread">
                <strong>${escapeHtml(item.name)}</strong>
                <span class="tag">${escapeHtml(item.entry_type)}</span>
              </div>
              <div class="subtle">${escapeHtml(item.snippet || item.summary || '')}</div>
            </div>`).join('')
        : '<div class="empty">没有搜索到结果</div>';
    }

    async function loadGraph() {
      const payload = await fetchJson('/api/portal/graph');
      drawGraph(document.getElementById('graph'), payload, (name) => loadEntry(encodeURIComponent(name)));
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
      document.getElementById('submit-status').textContent = `文本提交成功，submission_id=${result.id}`;
      document.getElementById('submit-content').value = '';
      await loadHome();
    }

    async function submitFile() {
      const fileInput = document.getElementById('upload-file');
      const file = fileInput.files[0];
      if (!file) throw new Error('请先选择文件');
      const buffer = await file.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      let binary = '';
      for (const byte of bytes) binary += String.fromCharCode(byte);
      const payload = {
        submitter_name: document.getElementById('upload-name').value,
        filename: file.name,
        mime_type: file.type || inferMimeType(file.name),
        content_base64: btoa(binary)
      };
      const response = await fetch('/api/portal/submissions/document', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '上传失败');
      document.getElementById('submit-status').textContent = `文档提交成功，submission_id=${data.id}`;
      fileInput.value = '';
      await loadHome();
    }

    function inferMimeType(filename) {
      const lower = filename.toLowerCase();
      if (lower.endsWith('.md')) return 'text/markdown';
      if (lower.endsWith('.txt')) return 'text/plain';
      if (lower.endsWith('.docx')) return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
      if (lower.endsWith('.pptx')) return 'application/vnd.openxmlformats-officedocument.presentationml.presentation';
      return 'application/octet-stream';
    }

    document.getElementById('search-button').addEventListener('click', () => runSearch().catch(showError));
    document.getElementById('submit-text-button').addEventListener('click', () => submitText().catch(showError));
    document.getElementById('submit-file-button').addEventListener('click', () => submitFile().catch(showError));
    document.getElementById('search-input').addEventListener('keydown', (event) => {
      if (event.key === 'Enter') runSearch().catch(showError);
    });

    function showError(error) {
      document.getElementById('submit-status').textContent = error.message;
    }

    loadHome().catch(showError);
    loadGraph().catch(showError);
    """
    return shared_shell("Sediment Portal", body, script)


def admin_login_html() -> str:
    body = """
    <div class="page">
      <section class="hero">
        <div class="nav">
          <a class="button" href="/portal">知识门户</a>
          <a class="button primary" href="/admin">管理台登录</a>
        </div>
        <h1>Sediment Admin Sign-in</h1>
        <p>管理台只开放给 committer 和平台维护者。登录成功后会建立一个同站受控 session，之后的审核与编辑请求会自动带上权限。</p>
      </section>

      <section class="panel" style="margin-top:20px; max-width:560px;">
        <div class="grid">
          <label>Admin Token<input id="admin-session-token" type="password" placeholder="输入 SEDIMENT_ADMIN_TOKEN" /></label>
          <button class="primary" id="login-button">登录管理台</button>
          <div id="login-status" class="subtle">需要有效 token 才能进入后台。</div>
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
    return shared_shell("Sediment Admin Login", body, script)


def admin_html() -> str:
    body = """
    <div class="page">
      <section class="hero">
        <div class="nav">
          <a class="button" href="/portal">知识门户</a>
          <a class="button primary" href="/admin">管理台</a>
        </div>
        <h1>Sediment Control Room</h1>
        <div class="row">
          <p>审核提交、发起 ingest/tidy、在线修改 Markdown，并把 health、审计和任务恢复变成常驻后台能力。</p>
        </div>
        <div class="row">
          <button class="primary" id="refresh-admin">刷新全部</button>
          <button id="logout-button">退出登录</button>
          <span class="tag ok">Session 已建立</span>
        </div>
      </section>

      <section class="grid cols-3">
        <div class="panel">
          <h2>系统总览</h2>
          <div class="stats" id="admin-stats"></div>
        </div>
        <div class="panel">
          <h2>Health 严重度</h2>
          <div class="severity-bar" id="severity-bars"></div>
        </div>
        <div class="panel">
          <div class="row spread">
            <h2>系统状态</h2>
            <span class="subtle">auth / queue / limits</span>
          </div>
          <div class="list" id="system-status"></div>
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
          <div id="diff-view" class="mono empty">选择待审 patch 后在这里查看。</div>
        </div>
      </section>

      <section class="split">
        <div class="panel">
          <div class="row spread">
            <h2>Health Issues</h2>
            <span class="subtle">可直接发起 tidy</span>
          </div>
          <div class="list" id="issue-list"></div>
        </div>
        <div class="panel">
          <div class="row spread">
            <h2>提交缓冲区</h2>
            <span class="subtle">triage / run ingest</span>
          </div>
          <div class="list" id="submission-list"></div>
        </div>
      </section>

      <section class="split" style="margin-top:20px;">
        <div class="panel">
          <div class="row spread">
            <h2>任务与审阅</h2>
            <span class="subtle">查看运行中和待审结果</span>
          </div>
          <div class="list" id="review-list"></div>
          <div class="list" id="job-list" style="margin-top:12px;"></div>
        </div>
        <div class="panel">
          <h2>在线编辑</h2>
          <div class="grid">
            <label>条目名<input id="editor-name" placeholder="例如：热备份" /></label>
            <button id="load-entry-button">加载条目</button>
            <label>内容<textarea id="editor-content"></textarea></label>
            <button class="primary" id="save-entry-button">保存条目</button>
            <div id="editor-status" class="subtle">这里会显示校验结果和保存反馈。</div>
          </div>
        </div>
      </section>

      <section class="split" style="margin-top:20px;">
        <div class="panel">
          <div class="row spread">
            <h2>审计日志</h2>
            <span class="subtle">最近的后台动作</span>
          </div>
          <div class="list" id="audit-log-list"></div>
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
                <button onclick='runTidy(${JSON.stringify(item).replace(/'/g, "&apos;")})'>发起 Tidy</button>
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
              <div class="row" style="margin-top:10px;">
                <button onclick="triageSubmission('${item.id}', 'triaged')">标记已归类</button>
                <button onclick="triageSubmission('${item.id}', 'rejected')">拒绝提交</button>
                <button class="primary" onclick="runIngest('${item.id}')">运行 Ingest</button>
              </div>
            </div>
          `).join('')
        : '<div class="empty">暂无提交。</div>';
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
                <button onclick="showDiff('${item.id}')">查看 Diff</button>
                <button class="primary" onclick="approveReview('${item.id}')">批准</button>
                <button onclick="rejectReview('${item.id}')">拒绝</button>
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
                ${['failed', 'cancelled'].includes(item.status) ? `<button onclick="retryJob('${item.id}')">重试</button>` : ''}
                ${['queued', 'running', 'awaiting_review'].includes(item.status) ? `<button onclick="cancelJob('${item.id}')">取消</button>` : ''}
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
      await refreshAdmin();
    }

    async function runIngest(id) {
      await fetchAdmin(`/api/admin/submissions/${id}/run-ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actor_name: 'admin-web' })
      });
      await refreshAdmin();
    }

    async function runTidy(issue) {
      await fetchAdmin('/api/admin/tidy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ issue, actor_name: 'admin-web' })
      });
      await refreshAdmin();
    }

    async function showDiff(reviewId) {
      const payload = await fetchAdmin(`/api/admin/reviews/${reviewId}`);
      const operations = payload.job.result_payload?.operations || [];
      document.getElementById('diff-view').textContent = operations.length
        ? operations.map(item => item.diff).join('\\n\\n')
        : '当前 review 没有 diff。';
    }

    async function approveReview(reviewId) {
      await fetchAdmin(`/api/admin/reviews/${reviewId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewer_name: 'admin-web', comment: 'Approved from admin UI' })
      });
      await refreshAdmin();
    }

    async function rejectReview(reviewId) {
      await fetchAdmin(`/api/admin/reviews/${reviewId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewer_name: 'admin-web', comment: 'Rejected from admin UI' })
      });
      await refreshAdmin();
    }

    async function loadEntryForEdit() {
      const name = document.getElementById('editor-name').value.trim();
      const payload = await fetchAdmin(`/api/admin/entries/${encodeURIComponent(name)}`);
      document.getElementById('editor-content').value = payload.content;
      document.getElementById('editor-status').textContent = `已加载 ${payload.name}，hash=${payload.content_hash.slice(0, 12)}`;
      document.getElementById('editor-content').dataset.hash = payload.content_hash;
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
      await refreshAdmin();
    }

    async function retryJob(jobId) {
      await fetchAdmin(`/api/admin/jobs/${jobId}/retry`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actor_name: 'admin-web' })
      });
      await refreshAdmin();
    }

    async function cancelJob(jobId) {
      await fetchAdmin(`/api/admin/jobs/${jobId}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actor_name: 'admin-web', reason: 'Cancelled from admin UI' })
      });
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

    document.getElementById('refresh-admin').addEventListener('click', () => refreshAdmin().catch(showAdminError));
    document.getElementById('refresh-admin-secondary').addEventListener('click', () => refreshAdmin().catch(showAdminError));
    document.getElementById('refresh-health-button').addEventListener('click', () => loadIssues().catch(showAdminError));
    document.getElementById('load-reviews-button').addEventListener('click', () => loadReviews().catch(showAdminError));
    document.getElementById('load-audit-button').addEventListener('click', () => loadAuditLogs().catch(showAdminError));
    document.getElementById('load-entry-button').addEventListener('click', () => loadEntryForEdit().catch(showAdminError));
    document.getElementById('save-entry-button').addEventListener('click', () => saveEntry().catch(showAdminError));
    document.getElementById('logout-button').addEventListener('click', () => logoutAdmin().catch(showAdminError));

    function showAdminError(error) {
      document.getElementById('diff-view').textContent = error.message;
    }

    refreshAdmin().catch(showAdminError);
    setInterval(() => refreshAdmin().catch(showAdminError), 20000);
    """
    return shared_shell("Sediment Admin", body, script)
