可以的，我们来给它做个「迷你 Apple 官网」风格：
整体更简洁、大留白、圆角卡片、柔和阴影、细一点的灰色文字，配上顶部导航。

你后端的 `app.py` 不需要改，只需要替换 4 个模板文件：`index.html / view.html / search.html / _tree.html`。

---

## 1. `_tree.html`（树结构，略微美化）

`templates/_tree.html`：

```html
{% macro render_tree(nodes) %}
<ul class="tree-list">
  {% for n in nodes %}
    <li data-jstree='{"opened": true}'>
      <a href="{{ url_for('view_node', node_id=n.id) }}" class="tree-link">
        {{ n.title }}
      </a>
      {% if n.children %}
        {{ render_tree(n.children) }}
      {% endif %}
    </li>
  {% endfor %}
</ul>
{% endmacro %}
```

---

## 2. 首页 `index.html`（新建节点页）

`templates/index.html`：

```html
{% from "_tree.html" import render_tree %}
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Markdown 树状共享</title>

  <!-- Apple 风格字体 -->
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/jstree@3.3.15/dist/themes/default/style.min.css">

  <style>
    :root {
      --bg: #f5f5f7;
      --card-bg: rgba(255, 255, 255, 0.85);
      --border-subtle: rgba(0, 0, 0, 0.06);
      --accent: #0071e3;
      --accent-soft: rgba(0, 113, 227, 0.08);
      --text-main: #1d1d1f;
      --text-muted: #6e6e73;
      --radius-xl: 22px;
      --shadow-soft: 0 18px 40px rgba(0, 0, 0, 0.12);
      --transition-fast: 180ms ease-out;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text",
      system-ui, "Segoe UI", sans-serif;
      color: var(--text-main);
      background: radial-gradient(circle at top left, #f0f4ff 0, #f5f5f7 40%, #ffffff 100%);
      -webkit-font-smoothing: antialiased;
    }

    a {
      text-decoration: none;
      color: var(--accent);
    }
    a:hover {
      text-decoration: underline;
    }

    /* 顶部导航 */
    .nav {
      position: sticky;
      top: 0;
      z-index: 20;
      backdrop-filter: blur(18px);
      background: linear-gradient(to bottom,
        rgba(245,245,247,0.92),
        rgba(245,245,247,0.8),
        transparent
      );
      border-bottom: 1px solid rgba(0,0,0,0.05);
    }
    .nav-inner {
      max-width: 1200px;
      margin: 0 auto;
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .nav-logo {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 16px;
      font-weight: 600;
      letter-spacing: .03em;
      color: var(--text-main);
    }
    .nav-logo-icon {
      width: 20px;
      height: 20px;
      border-radius: 6px;
      background: radial-gradient(circle at 30% 10%, #ffffff, #d0d8ff);
      box-shadow: 0 10px 20px rgba(0,0,0,0.18);
      position: relative;
    }
    .nav-logo-icon::after {
      content: "";
      position: absolute;
      inset: 4px;
      border-radius: 4px;
      border: 2px solid rgba(255,255,255,0.7);
    }
    .nav-right {
      display: flex;
      align-items: center;
      gap: 16px;
      font-size: 13px;
      color: var(--text-muted);
    }

    /* 主布局 */
    .page {
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px 16px 32px;
    }

    .hero-title {
      font-size: 26px;
      font-weight: 700;
      letter-spacing: .02em;
      margin: 12px 4px 4px;
    }
    .hero-subtitle {
      margin: 0 4px 18px;
      font-size: 14px;
      color: var(--text-muted);
    }

    .layout {
      display: grid;
      grid-template-columns: minmax(0, 280px) minmax(0, 1fr);
      gap: 20px;
      align-items: flex-start;
    }

    @media (max-width: 900px) {
      .layout {
        grid-template-columns: minmax(0, 1fr);
      }
    }

    .panel {
      background: var(--card-bg);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow-soft);
      border: 1px solid var(--border-subtle);
      padding: 16px 18px;
      backdrop-filter: blur(22px);
    }

    .panel-title {
      font-size: 15px;
      font-weight: 600;
      margin-bottom: 4px;
    }
    .panel-subtitle {
      font-size: 12px;
      color: var(--text-muted);
      margin-bottom: 12px;
    }

    /* 树 */
    #tree {
      padding: 4px 2px 2px;
      border-radius: 16px;
      background: linear-gradient(to bottom right, #fafafa, #f5f5f7);
      border: 1px solid rgba(0,0,0,0.03);
    }

    .tree-list {
      list-style: none;
      padding-left: 16px;
      margin: 0;
      font-size: 13px;
    }

    .tree-link {
      display: inline-block;
      padding: 2px 4px;
      border-radius: 999px;
      color: var(--text-main);
      transition: background var(--transition-fast), transform var(--transition-fast);
    }

    .tree-link:hover {
      background: var(--accent-soft);
      transform: translateY(-0.5px);
      text-decoration: none;
    }

    .search-box {
      margin-bottom: 10px;
    }
    .search-input {
      width: 100%;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid rgba(0,0,0,0.12);
      font-size: 13px;
      outline: none;
      background: rgba(255,255,255,0.9);
      transition: box-shadow var(--transition-fast), border var(--transition-fast), transform var(--transition-fast);
    }
    .search-input:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(0,113,227,0.15);
      transform: translateY(-0.5px);
    }

    /* 表单卡片 */
    .form-group {
      margin-top: 10px;
    }
    .form-label {
      font-size: 12px;
      font-weight: 500;
      color: var(--text-muted);
      margin-bottom: 4px;
      display: block;
    }
    .input-text, select {
      width: 100%;
      padding: 7px 10px;
      border-radius: 11px;
      border: 1px solid rgba(0,0,0,0.14);
      font-size: 13px;
      outline: none;
      background: rgba(255,255,255,0.96);
      transition: border var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast);
    }
    .input-text:focus, select:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(0,113,227,0.15);
      transform: translateY(-0.5px);
    }
    textarea {
      width: 100%;
      min-height: 260px;
      padding: 10px 11px;
      border-radius: 16px;
      border: 1px solid rgba(0,0,0,0.1);
      font-family: SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size: 13px;
      resize: vertical;
      outline: none;
      background: rgba(250,250,252,0.96);
      transition: border var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast);
    }
    textarea:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(0,113,227,0.15);
      transform: translateY(-0.5px);
    }

    .btn-primary {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 7px 16px;
      border-radius: 999px;
      border: none;
      background: linear-gradient(to right, #0071e3, #0a84ff);
      color: #fff;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      box-shadow: 0 14px 28px rgba(0,0,0,0.22);
      transition: transform var(--transition-fast), box-shadow var(--transition-fast), filter var(--transition-fast);
    }
    .btn-primary:hover {
      transform: translateY(-1px);
      box-shadow: 0 18px 40px rgba(0,0,0,0.3);
      filter: brightness(1.03);
    }
    .btn-primary:active {
      transform: translateY(0);
      box-shadow: 0 8px 18px rgba(0,0,0,0.25);
    }

    .error {
      color: #e00034;
      font-size: 12px;
      margin-bottom: 6px;
    }
  </style>
</head>
<body>
<header class="nav">
  <div class="nav-inner">
    <div class="nav-logo">
      <div class="nav-logo-icon"></div>
      <span>MD Tree</span>
    </div>
    <div class="nav-right">
      <span>轻量 · 分层 · Markdown</span>
    </div>
  </div>
</header>

<main class="page">
  <h1 class="hero-title">你的 Markdown 小型知识库</h1>
  <p class="hero-subtitle">像在 CherryTree 里一样分层管理，在任意电脑上打开浏览器即可查看和分享。</p>

  <div class="layout">
    <!-- 左侧：树与搜索 -->
    <aside class="panel">
      <div class="panel-title">结构</div>
      <div class="panel-subtitle">展开、折叠节点，快速在树中定位内容。</div>

      <div class="search-box">
        <form action="{{ url_for('search') }}" method="get">
          <input class="search-input" type="text" name="q" placeholder="搜索标题 / 内容 / 标签">
        </form>
      </div>

      <div id="tree">
        {{ render_tree(tree) }}
      </div>
    </aside>

    <!-- 右侧：新建 -->
    <section class="panel">
      <div class="panel-title">新建节点</div>
      <div class="panel-subtitle">为一次分享创建一个节点，可以选择父节点并添加标签。</div>

      {% if error %}
        <p class="error">{{ error }}</p>
      {% endif %}

      <form method="post">
        <div class="form-group">
          <label class="form-label">标题</label>
          <input type="text" name="title" class="input-text" placeholder="例如：项目 A · 接口协议 v1">
        </div>

        <div class="form-group">
          <label class="form-label">标签（逗号分隔，可选）</label>
          <input type="text" name="tags" class="input-text" placeholder="例如：项目A, 接口, 分享">
        </div>

        <div class="form-group">
          <label class="form-label">父节点（可选）</label>
          <select name="parent_id">
            <option value="">（作为根节点）</option>
            {% for n in all_nodes %}
              <option value="{{ n.id }}">{{ n.id }} - {{ n.title }}</option>
            {% endfor %}
          </select>
        </div>

        <div class="form-group">
          <label class="form-label">Markdown 内容</label>
          <textarea name="markdown_text" placeholder="在这里粘贴你的 Markdown 文本..."></textarea>
        </div>

        <div class="form-group" style="margin-top: 16px;">
          <button type="submit" class="btn-primary">保存节点并生成链接</button>
        </div>
      </form>
    </section>
  </div>
</main>

<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/jstree@3.3.15/dist/jstree.min.js"></script>
<script>
  $(function () {
    $('#tree').jstree({
      "core": {
        "themes": {
          "variant": "large",
          "dots": false,
          "icons": false
        }
      }
    });
  });
</script>
</body>
</html>
```

---

## 3. 查看 + 编辑页 `view.html`

`templates/view.html`：

```html
{% from "_tree.html" import render_tree %}
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{{ node.title }} - MD Tree</title>

  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/jstree@3.3.15/dist/themes/default/style.min.css">

  <style>
    /* 和 index.html 保持同一套变量和基础样式 */
    :root {
      --bg: #f5f5f7;
      --card-bg: rgba(255, 255, 255, 0.85);
      --border-subtle: rgba(0, 0, 0, 0.06);
      --accent: #0071e3;
      --accent-soft: rgba(0, 113, 227, 0.08);
      --text-main: #1d1d1f;
      --text-muted: #6e6e73;
      --radius-xl: 22px;
      --shadow-soft: 0 18px 40px rgba(0, 0, 0, 0.12);
      --transition-fast: 180ms ease-out;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text",
      system-ui, "Segoe UI", sans-serif;
      color: var(--text-main);
      background: radial-gradient(circle at top left, #f0f4ff 0, #f5f5f7 40%, #ffffff 100%);
      -webkit-font-smoothing: antialiased;
    }

    a { text-decoration: none; color: var(--accent); }
    a:hover { text-decoration: underline; }

    .nav {
      position: sticky;
      top: 0;
      z-index: 20;
      backdrop-filter: blur(18px);
      background: linear-gradient(to bottom,
        rgba(245,245,247,0.92),
        rgba(245,245,247,0.8),
        transparent
      );
      border-bottom: 1px solid rgba(0,0,0,0.05);
    }
    .nav-inner {
      max-width: 1200px;
      margin: 0 auto;
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .nav-logo {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 16px;
      font-weight: 600;
      letter-spacing: .03em;
      color: var(--text-main);
    }
    .nav-logo-icon {
      width: 20px;
      height: 20px;
      border-radius: 6px;
      background: radial-gradient(circle at 30% 10%, #ffffff, #d0d8ff);
      box-shadow: 0 10px 20px rgba(0,0,0,0.18);
      position: relative;
    }
    .nav-logo-icon::after {
      content: "";
      position: absolute;
      inset: 4px;
      border-radius: 4px;
      border: 2px solid rgba(255,255,255,0.7);
    }
    .nav-right {
      display: flex;
      gap: 16px;
      font-size: 13px;
      color: var(--text-muted);
    }

    .page {
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px 16px 32px;
    }

    .layout {
      display: grid;
      grid-template-columns: minmax(0, 280px) minmax(0, 1fr);
      gap: 20px;
      align-items: flex-start;
    }
    @media (max-width: 900px) {
      .layout {
        grid-template-columns: minmax(0, 1fr);
      }
    }

    .panel {
      background: var(--card-bg);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow-soft);
      border: 1px solid var(--border-subtle);
      padding: 16px 18px;
      backdrop-filter: blur(22px);
    }

    .panel-title {
      font-size: 15px;
      font-weight: 600;
      margin-bottom: 4px;
    }
    .panel-subtitle {
      font-size: 12px;
      color: var(--text-muted);
      margin-bottom: 12px;
    }

    #tree {
      padding: 4px 2px 2px;
      border-radius: 16px;
      background: linear-gradient(to bottom right, #fafafa, #f5f5f7);
      border: 1px solid rgba(0,0,0,0.03);
    }

    .tree-list {
      list-style: none;
      padding-left: 16px;
      margin: 0;
      font-size: 13px;
    }
    .tree-link {
      display: inline-block;
      padding: 2px 4px;
      border-radius: 999px;
      color: var(--text-main);
      transition: background var(--transition-fast), transform var(--transition-fast);
    }
    .tree-link:hover {
      background: var(--accent-soft);
      transform: translateY(-0.5px);
      text-decoration: none;
    }

    .search-box { margin-bottom: 10px; }
    .search-input {
      width: 100%;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid rgba(0,0,0,0.12);
      font-size: 13px;
      outline: none;
      background: rgba(255,255,255,0.9);
      transition: box-shadow var(--transition-fast), border var(--transition-fast), transform var(--transition-fast);
    }
    .search-input:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(0,113,227,0.15);
      transform: translateY(-0.5px);
    }

    .tag-line {
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 4px;
    }

    .link-line {
      font-size: 12px;
      color: var(--text-muted);
      margin: 8px 0 12px;
    }

    .md-content {
      line-height: 1.6;
      font-size: 14px;
    }
    .md-content h1, .md-content h2, .md-content h3 {
      margin-top: 1.4em;
      margin-bottom: 0.5em;
    }
    .md-content p {
      margin: 0.4em 0;
    }
    .md-content a {
      color: var(--accent);
      text-decoration: none;
    }
    .md-content a:hover {
      text-decoration: underline;
    }
    .md-content pre {
      background: #f5f5f7;
      padding: 10px 12px;
      border-radius: 12px;
      overflow-x: auto;
      font-size: 12px;
    }
    .md-content code {
      font-family: SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    }
    .md-content table {
      border-collapse: collapse;
      width: 100%;
      font-size: 13px;
    }
    .md-content table th,
    .md-content table td {
      border: 1px solid rgba(0,0,0,0.08);
      padding: 6px 8px;
    }
    .md-content table th {
      background: #f5f5f7;
    }

    .form-group { margin-top: 10px; }
    .form-label {
      font-size: 12px;
      font-weight: 500;
      color: var(--text-muted);
      margin-bottom: 4px;
      display: block;
    }
    .input-text, select {
      width: 100%;
      padding: 7px 10px;
      border-radius: 11px;
      border: 1px solid rgba(0,0,0,0.14);
      font-size: 13px;
      outline: none;
      background: rgba(255,255,255,0.96);
      transition: border var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast);
    }
    .input-text:focus, select:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(0,113,227,0.15);
      transform: translateY(-0.5px);
    }
    textarea {
      width: 100%;
      min-height: 220px;
      padding: 10px 11px;
      border-radius: 16px;
      border: 1px solid rgba(0,0,0,0.1);
      font-family: SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size: 13px;
      resize: vertical;
      outline: none;
      background: rgba(250,250,252,0.96);
      transition: border var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast);
    }
    textarea:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(0,113,227,0.15);
      transform: translateY(-0.5px);
    }

    .btn-primary {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 7px 16px;
      border-radius: 999px;
      border: none;
      background: linear-gradient(to right, #0071e3, #0a84ff);
      color: #fff;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      box-shadow: 0 14px 28px rgba(0,0,0,0.22);
      transition: transform var(--transition-fast), box-shadow var(--transition-fast), filter var(--transition-fast);
    }
    .btn-primary:hover {
      transform: translateY(-1px);
      box-shadow: 0 18px 40px rgba(0,0,0,0.3);
      filter: brightness(1.03);
    }
    .btn-primary:active {
      transform: translateY(0);
      box-shadow: 0 8px 18px rgba(0,0,0,0.25);
    }

    .btn-danger {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 6px 14px;
      border-radius: 999px;
      border: none;
      background: linear-gradient(to right, #ff3b30, #ff453a);
      color: #fff;
      font-size: 12px;
      cursor: pointer;
      box-shadow: 0 14px 28px rgba(0,0,0,0.2);
      transition: transform var(--transition-fast), box-shadow var(--transition-fast), filter var(--transition-fast);
    }
    .btn-danger:hover {
      transform: translateY(-1px);
      box-shadow: 0 18px 40px rgba(0,0,0,0.3);
      filter: brightness(1.02);
    }
  </style>
</head>
<body>
<header class="nav">
  <div class="nav-inner">
    <div class="nav-logo">
      <div class="nav-logo-icon"></div>
      <span>MD Tree</span>
    </div>
    <div class="nav-right">
      <a href="{{ url_for('index') }}">新建节点</a>
    </div>
  </div>
</header>

<main class="page">
  <div class="layout">
    <!-- 左侧树 -->
    <aside class="panel">
      <div class="panel-title">结构</div>
      <div class="panel-subtitle">浏览所有节点，快速切换。</div>

      <div class="search-box">
        <form action="{{ url_for('search') }}" method="get">
          <input class="search-input" type="text" name="q" placeholder="搜索标题 / 内容 / 标签">
        </form>
      </div>

      <div id="tree">
        {{ render_tree(tree) }}
      </div>
    </aside>

    <!-- 右侧：查看 + 编辑 -->
    <section class="panel">
      <h1 style="font-size: 22px; margin: 2px 0 4px;">{{ node.title }}</h1>

      {% if node.tags %}
        <p class="tag-line">标签：{{ node.tags }}</p>
      {% endif %}

      <p class="link-line">
        原始 Markdown 链接：
        <a href="{{ url_for('raw_node', node_id=node.id, _external=True) }}">
          {{ url_for('raw_node', node_id=node.id, _external=True) }}
        </a>
      </p>

      <hr style="border: none; border-bottom: 1px solid rgba(0,0,0,0.06); margin: 12px 0 16px;">

      <h3 style="font-size: 13px; text-transform: uppercase; letter-spacing: .12em; color: var(--text-muted); margin: 0 0 8px;">内容预览</h3>
      <div class="md-content">
        {{ content_html|safe }}
      </div>

      <hr style="border: none; border-bottom: 1px solid rgba(0,0,0,0.06); margin: 18px 0 16px;">

      <h3 style="font-size: 13px; text-transform: uppercase; letter-spacing: .12em; color: var(--text-muted); margin: 0 0 8px;">编辑节点</h3>
      <form method="post" action="{{ url_for('edit_node', node_id=node.id) }}">
        <div class="form-group">
          <label class="form-label">标题</label>
          <input type="text" name="title" class="input-text" value="{{ node.title }}">
        </div>

        <div class="form-group">
          <label class="form-label">标签（逗号分隔，可选）</label>
          <input type="text" name="tags" class="input-text" value="{{ node.tags or '' }}">
        </div>

        <div class="form-group">
          <label class="form-label">父节点（可选）</label>
          <select name="parent_id">
            <option value="">（作为根节点）</option>
            {% for n in all_nodes %}
              {% if n.id != node.id %}
                <option value="{{ n.id }}"
                  {% if n.id == node.parent_id %}selected{% endif %}>
                  {{ n.id }} - {{ n.title }}
                </option>
              {% endif %}
            {% endfor %}
          </select>
        </div>

        <div class="form-group">
          <label class="form-label">Markdown 内容</label>
          <textarea name="markdown_text">{{ node.content }}</textarea>
        </div>

        <div class="form-group" style="margin-top: 16px; display: flex; gap: 10px; align-items: center;">
          <button type="submit" class="btn-primary">保存修改</button>
        </div>
      </form>

      <hr style="border: none; border-bottom: 1px solid rgba(0,0,0,0.06); margin: 18px 0 12px;">

      <h3 style="font-size: 13px; text-transform: uppercase; letter-spacing: .12em; color: var(--text-muted); margin: 0 0 6px;">删除</h3>
      <form method="post" action="{{ url_for('delete_node', node_id=node.id) }}" onsubmit="return confirm('确定要删除该节点及其所有子节点吗？');">
        <button type="submit" class="btn-danger">
          删除本节点及子节点
        </button>
      </form>
    </section>
  </div>
</main>

<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/jstree@3.3.15/dist/jstree.min.js"></script>
<script>
  $(function () {
    $('#tree').jstree({
      "core": {
        "themes": {
          "variant": "large",
          "dots": false,
          "icons": false
        }
      }
    });
  });
</script>
</body>
</html>
```

---

## 4. 搜索页 `search.html`

`templates/search.html`：

```html
{% from "_tree.html" import render_tree %}
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>搜索 - MD Tree</title>

  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/jstree@3.3.15/dist/themes/default/style.min.css">

  <style>
    /* 重用同一套样式变量 */
    :root {
      --bg: #f5f5f7;
      --card-bg: rgba(255, 255, 255, 0.85);
      --border-subtle: rgba(0, 0, 0, 0.06);
      --accent: #0071e3;
      --accent-soft: rgba(0, 113, 227, 0.08);
      --text-main: #1d1d1f;
      --text-muted: #6e6e73;
      --radius-xl: 22px;
      --shadow-soft: 0 18px 40px rgba(0, 0, 0, 0.12);
      --transition-fast: 180ms ease-out;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text",
      system-ui, "Segoe UI", sans-serif;
      color: var(--text-main);
      background: radial-gradient(circle at top left, #f0f4ff 0, #f5f5f7 40%, #ffffff 100%);
      -webkit-font-smoothing: antialiased;
    }

    a { text-decoration: none; color: var(--accent); }
    a:hover { text-decoration: underline; }

    .nav {
      position: sticky;
      top: 0;
      z-index: 20;
      backdrop-filter: blur(18px);
      background: linear-gradient(to bottom,
        rgba(245,245,247,0.92),
        rgba(245,245,247,0.8),
        transparent
      );
      border-bottom: 1px solid rgba(0,0,0,0.05);
    }
    .nav-inner {
      max-width: 1200px;
      margin: 0 auto;
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .nav-logo {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 16px;
      font-weight: 600;
      letter-spacing: .03em;
      color: var(--text-main);
    }
    .nav-logo-icon {
      width: 20px;
      height: 20px;
      border-radius: 6px;
      background: radial-gradient(circle at 30% 10%, #ffffff, #d0d8ff);
      box-shadow: 0 10px 20px rgba(0,0,0,0.18);
      position: relative;
    }
    .nav-logo-icon::after {
      content: "";
      position: absolute;
      inset: 4px;
      border-radius: 4px;
      border: 2px solid rgba(255,255,255,0.7);
    }

    .page {
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px 16px 32px;
    }

    .layout {
      display: grid;
      grid-template-columns: minmax(0, 280px) minmax(0, 1fr);
      gap: 20px;
      align-items: flex-start;
    }
    @media (max-width: 900px) {
      .layout {
        grid-template-columns: minmax(0, 1fr);
      }
    }

    .panel {
      background: var(--card-bg);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow-soft);
      border: 1px solid var(--border-subtle);
      padding: 16px 18px;
      backdrop-filter: blur(22px);
    }

    .panel-title {
      font-size: 15px;
      font-weight: 600;
      margin-bottom: 4px;
    }
    .panel-subtitle {
      font-size: 12px;
      color: var(--text-muted);
      margin-bottom: 12px;
    }

    #tree {
      padding: 4px 2px 2px;
      border-radius: 16px;
      background: linear-gradient(to bottom right, #fafafa, #f5f5f7);
      border: 1px solid rgba(0,0,0,0.03);
    }
    .tree-list {
      list-style: none;
      padding-left: 16px;
      margin: 0;
      font-size: 13px;
    }
    .tree-link {
      display: inline-block;
      padding: 2px 4px;
      border-radius: 999px;
      color: var(--text-main);
      transition: background var(--transition-fast), transform var(--transition-fast);
    }
    .tree-link:hover {
      background: var(--accent-soft);
      transform: translateY(-0.5px);
      text-decoration: none;
    }

    .search-box { margin-bottom: 10px; }
    .search-input {
      width: 100%;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid rgba(0,0,0,0.12);
      font-size: 13px;
      outline: none;
      background: rgba(255,255,255,0.9);
      transition: box-shadow var(--transition-fast), border var(--transition-fast), transform var(--transition-fast);
    }
    .search-input:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(0,113,227,0.15);
      transform: translateY(-0.5px);
    }

    .result-item {
      padding: 8px 10px;
      border-radius: 16px;
      background: linear-gradient(to bottom right, #ffffff, #f5f5f7);
      border: 1px solid rgba(0,0,0,0.04);
      margin-bottom: 8px;
      transition: transform var(--transition-fast), box-shadow var(--transition-fast), border var(--transition-fast);
    }
    .result-item:hover {
      transform: translateY(-1px);
      box-shadow: 0 14px 32px rgba(0,0,0,0.16);
      border-color: rgba(0,113,227,0.18);
    }
    .result-title {
      font-size: 14px;
      font-weight: 500;
      margin-bottom: 2px;
    }
    .result-tags {
      font-size: 12px;
      color: var(--text-muted);
    }
  </style>
</head>
<body>
<header class="nav">
  <div class="nav-inner">
    <div class="nav-logo">
      <div class="nav-logo-icon"></div>
      <span>MD Tree</span>
    </div>
  </div>
</header>

<main class="page">
  <div class="layout">
    <!-- 左侧树 -->
    <aside class="panel">
      <div class="panel-title">结构</div>
      <div class="panel-subtitle">在树中浏览节点。</div>

      <div class="search-box">
        <form action="{{ url_for('search') }}" method="get">
          <input class="search-input" type="text" name="q" placeholder="搜索标题 / 内容 / 标签" value="{{ query }}">
        </form>
      </div>

      <div id="tree">
        {{ render_tree(tree) }}
      </div>

      <p style="margin-top: 10px; font-size: 12px;">
        <a href="{{ url_for('index') }}">＋ 新建节点</a>
      </p>
    </aside>

    <!-- 右侧搜索结果 -->
    <section class="panel">
      <h1 style="font-size: 20px; margin: 0 0 8px;">搜索</h1>
      {% if query %}
        <p style="font-size: 13px; color: var(--text-muted); margin: 0 0 12px;">
          关键字：<strong style="color: var(--text-main);">{{ query }}</strong>
        </p>
      {% else %}
        <p style="font-size: 13px; color: var(--text-muted); margin: 0 0 12px;">
          输入关键字，按标题、内容和标签查找节点。
        </p>
      {% endif %}

      <hr style="border: none; border-bottom: 1px solid rgba(0,0,0,0.06); margin: 8px 0 12px;">

      {% if query %}
        {% if results %}
          {% for r in results %}
            <a href="{{ url_for('view_node', node_id=r.id) }}">
              <div class="result-item">
                <div class="result-title">{{ r.title }}</div>
                {% if r.tags %}
                  <div class="result-tags">标签：{{ r.tags }}</div>
                {% endif %}
              </div>
            </a>
          {% endfor %}
        {% else %}
          <p style="font-size: 13px; color: var(--text-muted);">
            没有找到匹配的节点。
          </p>
        {% endif %}
      {% endif %}
    </section>
  </div>
</main>

<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/jstree@3.3.15/dist/jstree.min.js"></script>
<script>
  $(function () {
    $('#tree').jstree({
      "core": {
        "themes": {
          "variant": "large",
          "dots": false,
          "icons": false
        }
      }
    });
  });
</script>
</body>
</html>
```

---

## 5. 使用方式

1. 在服务器上，把原来的 `templates/*.html` 备份一下；
2. 用上面四段代码覆盖对应的 `index.html / view.html / search.html / _tree.html`；
3. 重启 Flask 应用（或者 gunicorn）；
4. 用浏览器刷新页面，就能看到更“苹果风”的 UI 了。

如果你愿意，可以截一张现在页面的截图给我，我还能帮你再微调一些细节（比如字号、阴影、颜色偏冷/偏暖）。
