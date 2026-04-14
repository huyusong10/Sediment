import re

with open("src/sediment/web_ui.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace theme-color
content = re.sub(
    r'<meta name="theme-color" content="#2B1F16" />',
    r'<meta name="theme-color" content="#030712" />',
    content
)

# Replace <style> block
new_style = """  <style>
    :root {
      --bg: #030712;
      --panel: rgba(17, 24, 39, 0.7);
      --ink: #e2e8f0;
      --muted: #9ca3af;
      --line: rgba(59, 130, 246, 0.2);
      --accent: #3b82f6;
      --accent-soft: rgba(59, 130, 246, 0.15);
      --ok: #10b981;
      --warn: #f59e0b;
      --danger: #ef4444;
      --shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(59, 130, 246, 0.1), transparent 30%),
        radial-gradient(circle at top right, rgba(147, 197, 253, 0.05), transparent 25%),
        linear-gradient(180deg, #111827 0%, #030712 100%);
      min-height: 100vh;
    }
    a { color: inherit; }
    .page {
      width: min(1280px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }
    .hero {
      display: grid;
      gap: 18px;
      padding: 28px;
      border: 1px solid var(--line);
      border-radius: 28px;
      background: linear-gradient(135deg, rgba(31, 41, 55, 0.8), rgba(17, 24, 39, 0.95));
      box-shadow: var(--shadow);
      overflow: hidden;
      position: relative;
    }
    .hero::after {
      content: "";
      position: absolute;
      inset: auto -40px -40px auto;
      width: 220px;
      height: 220px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(59, 130, 246, 0.15), transparent 70%);
    }
    .hero h1 {
      margin: 0;
      font-size: clamp(32px, 4vw, 56px);
      line-height: 1.02;
      max-width: 12ch;
      background: linear-gradient(to right, #93c5fd, #3b82f6);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .hero p {
      margin: 0;
      color: var(--muted);
      max-width: 72ch;
      font-size: 16px;
      line-height: 1.6;
    }
    .hero-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 18px;
      flex-wrap: wrap;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 14px;
      min-width: 0;
    }
    .brand-mark {
      width: 62px;
      height: 62px;
      flex: none;
      filter: drop-shadow(0 12px 20px rgba(0, 0, 0, 0.3));
    }
    .brand-copy {
      display: grid;
      gap: 4px;
    }
    .brand-copy span {
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .brand-copy strong {
      font-size: 18px;
      line-height: 1.1;
      color: #e2e8f0;
    }
    .nav {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }
    .chip, button, .button {
      border: 1px solid var(--line);
      border-radius: 999px;
      background: rgba(31, 41, 55, 0.6);
      color: #e2e8f0;
      padding: 10px 16px;
      font: inherit;
      cursor: pointer;
      text-decoration: none;
      transition: transform 150ms ease, background 150ms ease, box-shadow 150ms ease;
      backdrop-filter: blur(4px);
    }
    button.primary, .button.primary {
      background: linear-gradient(135deg, #2563eb, #1d4ed8);
      color: white;
      border-color: transparent;
      box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
    }
    .chip:hover, button:hover, .button:hover {
      transform: translateY(-1px);
      background: rgba(55, 65, 81, 0.8);
    }
    button.primary:hover, .button.primary:hover {
      background: linear-gradient(135deg, #3b82f6, #2563eb);
      box-shadow: 0 6px 16px rgba(37, 99, 235, 0.4);
    }
    .grid {
      display: grid;
      gap: 18px;
      margin-top: 20px;
    }
    .grid.cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .grid.cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 20px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }
    .panel h2, .panel h3 {
      margin-top: 0;
      margin-bottom: 10px;
      color: #f8fafc;
    }
    .subtle {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
    }
    .stats {
      display: grid;
      gap: 14px;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    }
    .stat {
      padding: 14px 16px;
      border-radius: 18px;
      background: rgba(31, 41, 55, 0.5);
      border: 1px solid rgba(59, 130, 246, 0.15);
    }
    .stat strong {
      display: block;
      font-size: 28px;
      margin-bottom: 4px;
      color: #60a5fa;
    }
    .list {
      display: grid;
      gap: 10px;
    }
    .card {
      border: 1px solid rgba(59, 130, 246, 0.15);
      border-radius: 18px;
      padding: 14px 16px;
      background: rgba(31, 41, 55, 0.4);
      backdrop-filter: blur(8px);
    }
    .card.interactive {
      cursor: pointer;
      transition: transform 150ms ease, border-color 150ms ease, background 150ms ease;
    }
    .card.interactive:hover {
      transform: translateY(-2px);
      border-color: rgba(96, 165, 250, 0.4);
      background: rgba(55, 65, 81, 0.6);
    }
    .row {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }
    .row.spread { justify-content: space-between; }
    input, textarea, select {
      width: 100%;
      border: 1px solid rgba(59, 130, 246, 0.2);
      border-radius: 16px;
      padding: 12px 14px;
      font: inherit;
      color: #f1f5f9;
      background: rgba(15, 23, 42, 0.6);
      transition: border-color 150ms ease;
    }
    input:focus, textarea:focus, select:focus {
      outline: none;
      border-color: #3b82f6;
      background: rgba(15, 23, 42, 0.8);
    }
    textarea { min-height: 140px; resize: vertical; }
    label {
      display: grid;
      gap: 8px;
      font-size: 14px;
      color: var(--muted);
    }
    .markdown {
      white-space: normal;
      line-height: 1.7;
    }
    .markdown h1, .markdown h2, .markdown h3 {
      margin-top: 18px;
      margin-bottom: 10px;
      color: #f8fafc;
    }
    .markdown p {
      margin: 10px 0;
    }
    .markdown ul {
      padding-left: 20px;
      margin: 10px 0;
    }
    .markdown code {
      padding: 2px 6px;
      border-radius: 8px;
      background: rgba(59, 130, 246, 0.15);
      font-family: "SFMono-Regular", Menlo, Monaco, Consolas, monospace;
      color: #93c5fd;
    }
    .graph {
      width: 100%;
      height: 520px;
      border-radius: 20px;
      background:
        radial-gradient(circle at center, rgba(31, 41, 55, 0.6), rgba(15, 23, 42, 0.8));
      border: 1px solid rgba(59, 130, 246, 0.15);
    }
    .legend {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 10px;
      font-size: 14px;
      color: var(--muted);
    }
    .legend span::before {
      content: "";
      display: inline-block;
      width: 10px;
      height: 10px;
      margin-right: 8px;
      border-radius: 50%;
      vertical-align: middle;
      background: currentColor;
    }
    .severity-bar {
      display: grid;
      gap: 10px;
    }
    .severity-item {
      display: grid;
      gap: 6px;
    }
    .bar {
      height: 10px;
      border-radius: 999px;
      overflow: hidden;
      background: rgba(59, 130, 246, 0.1);
    }
    .bar > span {
      display: block;
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, #3b82f6, #60a5fa);
    }
    .tag {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      background: rgba(59, 130, 246, 0.15);
      color: #93c5fd;
    }
    .tag.ok { background: rgba(16, 185, 129, 0.15); color: var(--ok); }
    .tag.warn { background: rgba(245, 158, 11, 0.15); color: var(--warn); }
    .tag.danger { background: rgba(239, 68, 68, 0.15); color: var(--danger); }
    .notice {
      margin-top: 14px;
      padding: 12px 14px;
      border-radius: 16px;
      border: 1px solid rgba(59, 130, 246, 0.2);
      background: rgba(31, 41, 55, 0.5);
      color: #cbd5e1;
      line-height: 1.5;
    }
    button:disabled {
      cursor: wait;
      opacity: 0.7;
      transform: none;
    }
    .split {
      display: grid;
      gap: 18px;
      grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
    }
    .mono {
      font-family: "SFMono-Regular", Menlo, Monaco, Consolas, monospace;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 13px;
      line-height: 1.6;
    }
    .empty {
      padding: 20px;
      border-radius: 16px;
      border: 1px dashed rgba(59, 130, 246, 0.3);
      color: var(--muted);
      text-align: center;
    }
    .modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(3, 7, 18, 0.6);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
      z-index: 30;
      backdrop-filter: blur(4px);
    }
    .modal-backdrop[hidden] {
      display: none;
    }
    .modal-card {
      width: min(980px, 100%);
      max-height: min(88vh, 920px);
      overflow: auto;
      padding: 22px;
      border-radius: 24px;
      background: rgba(17, 24, 39, 0.95);
      border: 1px solid var(--line);
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.6);
    }
    .upload-grid {
      display: grid;
      gap: 12px;
    }
    .quartz-frame {
      width: 100%;
      min-height: 78vh;
      border: 1px solid rgba(59, 130, 246, 0.2);
      border-radius: 24px;
      background: rgba(17, 24, 39, 0.6);
    }
    @media (max-width: 960px) {
      .grid.cols-3,
      .grid.cols-2,
      .split {
        grid-template-columns: 1fr;
      }
      .page {
        width: min(100vw - 20px, 1280px);
      }
      .graph {
        height: 420px;
      }
    }
  </style>"""

content = re.sub(r'  <style>.*?</style>', new_style, content, flags=re.DOTALL)

# Replace Javascript colors
content = re.sub(
    r'const kindColors = {[^}]*};',
    '''const kindColors = {
      concept: '#3b82f6',
      lesson: '#10b981',
      placeholder: '#f59e0b',
      index: '#8b5cf6'
    };''',
    content
)

content = content.replace("edge.kind === 'related' ? 'rgba(86,125,140,0.26)' : 'rgba(90,106,65,0.24)'", "edge.kind === 'related' ? 'rgba(59,130,246,0.3)' : 'rgba(16,185,129,0.3)'")
content = content.replace("kindColors[node.kind] || '#b85c2d'", "kindColors[node.kind] || '#3b82f6'")
content = content.replace("label.setAttribute('fill', '#3a2c20')", "label.setAttribute('fill', '#e2e8f0')")

with open("src/sediment/web_ui.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Patch applied to web_ui.py")
