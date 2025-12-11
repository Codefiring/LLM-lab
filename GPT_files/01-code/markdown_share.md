好，我们来把这个小工具升级成“迷你 CherryTree”版：有可折叠 JS 树、编辑、删除整棵子树、标签和搜索。下面我直接给你一套**可运行的完整示例**，你基本上是「替换文件」+「安装前端依赖（其实是 CDN，不用装）」就能用。

---

## 一、后端 `app.py`（Flask + SQLite + Markdown）

> 和你之前的版本一样，用 Flask，只是把功能扩展了一下。
> 支持：
>
> * jsTree 折叠树
> * 新建 / 编辑节点
> * 删除节点 + 整个子树
> * 标签字段（逗号分隔）
> * 标题 / 内容 / 标签 模糊搜索

把原来的 `app.py` 换成下面这个（建议先备份一下）：

```python
import os
import sqlite3
from flask import (
    Flask, request, redirect, url_for, render_template,
    abort, g
)
import markdown

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "notes.db")

app = Flask(__name__)


# ---------- 数据库相关 ----------
def get_db():
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    # 如果是新建表，会包含 tags 字段
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    # 如果是旧表（没有 tags 字段），尝试加一列
    try:
        db.execute("ALTER TABLE nodes ADD COLUMN tags TEXT;")
    except sqlite3.OperationalError:
        # 已经有 tags 字段了就忽略
        pass
    db.commit()


def create_node(title, content, parent_id, tags):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO nodes (parent_id, title, content, tags)
        VALUES (?, ?, ?, ?)
        """,
        (parent_id, title, content, tags),
    )
    db.commit()
    return cursor.lastrowid


def update_node(node_id, title, content, parent_id, tags):
    db = get_db()
    db.execute(
        """
        UPDATE nodes
        SET parent_id = ?, title = ?, content = ?, tags = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (parent_id, title, content, tags, node_id),
    )
    db.commit()


def get_node(node_id):
    db = get_db()
    cur = db.execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
    return cur.fetchone()


def get_all_nodes():
    db = get_db()
    cur = db.execute(
        "SELECT id, parent_id, title, tags FROM nodes ORDER BY id ASC"
    )
    return cur.fetchall()


def build_tree(rows):
    """把扁平的节点列表构造成树结构，用于模板渲染"""
    nodes = {}
    for r in rows:
        nodes[r["id"]] = {
            "id": r["id"],
            "parent_id": r["parent_id"],
            "title": r["title"],
            "tags": r["tags"],
            "children": [],
        }

    roots = []
    for n in nodes.values():
        pid = n["parent_id"]
        if pid and pid in nodes:
            nodes[pid]["children"].append(n)
        else:
            roots.append(n)
    return roots


def get_children_ids(node_id):
    """递归获取所有子节点 id"""
    db = get_db()
    cur = db.execute("SELECT id FROM nodes WHERE parent_id = ?", (node_id,))
    rows = cur.fetchall()
    ids = []
    for r in rows:
        cid = r["id"]
        ids.append(cid)
        ids.extend(get_children_ids(cid))
    return ids


def delete_subtree(node_id):
    """删除一个节点及其整棵子树"""
    db = get_db()
    ids = get_children_ids(node_id)
    ids.append(node_id)
    placeholders = ",".join("?" for _ in ids)
    db.execute(f"DELETE FROM nodes WHERE id IN ({placeholders})", ids)
    db.commit()


# ---------- 全局前置 ----------
@app.before_request
def before_request():
    init_db()


# ---------- 路由 ----------
@app.route("/", methods=["GET", "POST"])
def index():
    db = get_db()
    nodes = get_all_nodes()
    tree = build_tree(nodes)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        text = request.form.get("markdown_text", "").strip()
        tags = request.form.get("tags", "").strip()
        parent_id_raw = request.form.get("parent_id")
        parent_id = int(parent_id_raw) if parent_id_raw else None

        if not title:
            error = "请填写标题"
            return render_template(
                "index.html",
                tree=tree,
                all_nodes=nodes,
                error=error,
            )
        if not text:
            error = "请填写或粘贴 Markdown 文本"
            return render_template(
                "index.html",
                tree=tree,
                all_nodes=nodes,
                error=error,
            )

        node_id = create_node(title, text, parent_id, tags)
        return redirect(url_for("view_node", node_id=node_id))

    return render_template("index.html", tree=tree, all_nodes=nodes)


@app.route("/node/<int:node_id>")
def view_node(node_id):
    node = get_node(node_id)
    if node is None:
        abort(404)

    nodes = get_all_nodes()
    tree = build_tree(nodes)

    html_content = markdown.markdown(
        node["content"],
        extensions=["fenced_code", "tables"],
    )

    return render_template(
        "view.html",
        node=node,
        content_html=html_content,
        tree=tree,
        all_nodes=nodes,
    )


@app.route("/node/<int:node_id>/edit", methods=["POST"])
def edit_node(node_id):
    node = get_node(node_id)
    if node is None:
        abort(404)

    title = request.form.get("title", "").strip()
    text = request.form.get("markdown_text", "").strip()
    tags = request.form.get("tags", "").strip()
    parent_id_raw = request.form.get("parent_id")
    parent_id = int(parent_id_raw) if parent_id_raw else None

    if not title or not text:
        # 简单处理：有问题就回到原页面
        return redirect(url_for("view_node", node_id=node_id))

    update_node(node_id, title, text, parent_id, tags)
    return redirect(url_for("view_node", node_id=node_id))


@app.route("/node/<int:node_id>/delete", methods=["POST"])
def delete_node(node_id):
    node = get_node(node_id)
    if node is None:
        abort(404)
    delete_subtree(node_id)
    return redirect(url_for("index"))


@app.route("/raw/<int:node_id>")
def raw_node(node_id):
    node = get_node(node_id)
    if node is None:
        abort(404)
    return node["content"], 200, {
        "Content-Type": "text/markdown; charset=utf-8"
    }


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    nodes = get_all_nodes()
    tree = build_tree(nodes)
    results = []

    if query:
        db = get_db()
        like = f"%{query}%"
        cur = db.execute(
            """
            SELECT id, title, tags
            FROM nodes
            WHERE title LIKE ?
               OR content LIKE ?
               OR IFNULL(tags, '') LIKE ?
            ORDER BY id DESC
            """,
            (like, like, like),
        )
        results = cur.fetchall()

    return render_template(
        "search.html",
        tree=tree,
        all_nodes=nodes,
        query=query,
        results=results,
    )


if __name__ == "__main__":
    # 开发测试
    app.run(host="0.0.0.0", port=5000, debug=True)
```

> 旧的 `notes.db` 可以继续用；新代码会自动尝试 `ALTER TABLE` 加 `tags` 列。

---

## 二、树组件模板 `_tree.html`（供其他模板引用）

在 `templates/_tree.html`：

```html
{% macro render_tree(nodes) %}
<ul>
  {% for n in nodes %}
    <li data-jstree='{"opened": true}'>
      <a href="{{ url_for('view_node', node_id=n.id) }}">{{ n.title }}</a>
      {% if n.children %}
        {{ render_tree(n.children) }}
      {% endif %}
    </li>
  {% endfor %}
</ul>
{% endmacro %}
```

---

## 三、首页 `index.html`（新建节点 + 左侧 jsTree）

在 `templates/index.html`：

```html
{% from "_tree.html" import render_tree %}
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Markdown 树状共享</title>

  <!-- jsTree 样式 -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/jstree@3.3.15/dist/themes/default/style.min.css">

  <style>
    body { margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .layout { display: flex; height: 100vh; }
    .sidebar { width: 260px; border-right: 1px solid #ddd; padding: 12px; overflow-y: auto; box-sizing: border-box; }
    .content { flex: 1; padding: 16px; box-sizing: border-box; overflow-y: auto; }
    textarea { width: 100%; height: 260px; font-family: monospace; }
    .error { color: red; margin-bottom: 8px; }
    .search-box input { width: 100%; box-sizing: border-box; }
    a { text-decoration: none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <h3>节点树</h3>

    <div class="search-box">
      <form action="{{ url_for('search') }}" method="get">
        <input type="text" name="q" placeholder="搜索标题/内容/标签">
      </form>
    </div>

    <div id="tree">
      {{ render_tree(tree) }}
    </div>
  </aside>

  <main class="content">
    <h2>新建节点（上传 / 粘贴 Markdown）</h2>

    {% if error %}
      <p class="error">{{ error }}</p>
    {% endif %}

    <form method="post">
      <div>
        <label>标题：</label><br>
        <input type="text" name="title" style="width: 100%;" placeholder="请输入标题">
      </div>

      <div style="margin-top: 8px;">
        <label>标签（逗号分隔，可选）：</label><br>
        <input type="text" name="tags" style="width: 100%;" placeholder="例如：项目A,需求,接口">
      </div>

      <div style="margin-top: 8px;">
        <label>父节点（可选）：</label><br>
        <select name="parent_id" style="width: 100%;">
          <option value="">（作为根节点）</option>
          {% for n in all_nodes %}
            <option value="{{ n.id }}">{{ n.id }} - {{ n.title }}</option>
          {% endfor %}
        </select>
      </div>

      <div style="margin-top: 8px;">
        <label>Markdown 内容：</label><br>
        <textarea name="markdown_text" placeholder="在这里粘贴你的 Markdown 文本..."></textarea>
      </div>

      <div style="margin-top: 12px;">
        <button type="submit">保存节点并生成链接</button>
      </div>
    </form>
  </main>
</div>

<!-- jQuery + jsTree -->
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/jstree@3.3.15/dist/jstree.min.js"></script>
<script>
  $(function () {
    $('#tree').jstree({
      "core": {
        "themes": {
          "variant": "large"
        }
      }
    });
  });
</script>
</body>
</html>
```

---

## 四、查看+编辑页面 `view.html`

在 `templates/view.html`：

```html
{% from "_tree.html" import render_tree %}
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{{ node.title }} - Markdown 树状共享</title>

  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/jstree@3.3.15/dist/themes/default/style.min.css">

  <style>
    body { margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .layout { display: flex; height: 100vh; }
    .sidebar { width: 260px; border-right: 1px solid #ddd; padding: 12px; overflow-y: auto; box-sizing: border-box; }
    .content { flex: 1; padding: 16px; box-sizing: border-box; overflow-y: auto; }
    .md-content { line-height: 1.6; margin-top: 16px; }
    pre { background: #f5f5f5; padding: 8px; overflow-x: auto; }
    code { font-family: monospace; }
    .search-box input { width: 100%; box-sizing: border-box; }
    textarea { width: 100%; height: 240px; font-family: monospace; }
    a { text-decoration: none; }
    a:hover { text-decoration: underline; }
    .tag-line { color: #555; font-size: 0.9em; }
  </style>
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <h3>节点树</h3>

    <div class="search-box">
      <form action="{{ url_for('search') }}" method="get">
        <input type="text" name="q" placeholder="搜索标题/内容/标签">
      </form>
    </div>

    <div id="tree">
      {{ render_tree(tree) }}
    </div>

    <p style="margin-top: 12px;">
      <a href="{{ url_for('index') }}">＋ 新建节点</a>
    </p>
  </aside>

  <main class="content">
    <h1>{{ node.title }}</h1>

    {% if node.tags %}
      <p class="tag-line">标签：{{ node.tags }}</p>
    {% endif %}

    <p>
      原始 Markdown 链接：
      <a href="{{ url_for('raw_node', node_id=node.id, _external=True) }}">
        {{ url_for('raw_node', node_id=node.id, _external=True) }}
      </a>
    </p>

    <hr>

    <h3>内容预览</h3>
    <div class="md-content">
      {{ content_html|safe }}
    </div>

    <hr>

    <h3>编辑当前节点</h3>
    <form method="post" action="{{ url_for('edit_node', node_id=node.id) }}">
      <div>
        <label>标题：</label><br>
        <input type="text" name="title" style="width: 100%;" value="{{ node.title }}">
      </div>

      <div style="margin-top: 8px;">
        <label>标签（逗号分隔，可选）：</label><br>
        <input type="text" name="tags" style="width: 100%;" value="{{ node.tags or '' }}">
      </div>

      <div style="margin-top: 8px;">
        <label>父节点（可选）：</label><br>
        <select name="parent_id" style="width: 100%;">
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

      <div style="margin-top: 8px;">
        <label>Markdown 内容：</label><br>
        <textarea name="markdown_text">{{ node.content }}</textarea>
      </div>

      <div style="margin-top: 12px;">
        <button type="submit">保存修改</button>
      </div>
    </form>

    <hr>

    <h3>删除节点</h3>
    <form method="post" action="{{ url_for('delete_node', node_id=node.id) }}" onsubmit="return confirm('确定要删除该节点及其所有子节点吗？');">
      <button type="submit" style="color: white; background: #d9534f; border: none; padding: 6px 12px; cursor: pointer;">
        删除本节点及子节点
      </button>
    </form>
  </main>
</div>

<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/jstree@3.3.15/dist/jstree.min.js"></script>
<script>
  $(function () {
    $('#tree').jstree({
      "core": {
        "themes": {
          "variant": "large"
        }
      }
    });
  });
</script>
</body>
</html>
```

---

## 五、搜索结果页面 `search.html`

在 `templates/search.html`：

```html
{% from "_tree.html" import render_tree %}
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>搜索 - Markdown 树状共享</title>

  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/jstree@3.3.15/dist/themes/default/style.min.css">

  <style>
    body { margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .layout { display: flex; height: 100vh; }
    .sidebar { width: 260px; border-right: 1px solid #ddd; padding: 12px; overflow-y: auto; box-sizing: border-box; }
    .content { flex: 1; padding: 16px; box-sizing: border-box; overflow-y: auto; }
    .search-box input { width: 100%; box-sizing: border-box; }
    a { text-decoration: none; }
    a:hover { text-decoration: underline; }
    .result-item { margin-bottom: 8px; }
    .tags { color: #555; font-size: 0.9em; }
  </style>
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <h3>节点树</h3>

    <div class="search-box">
      <form action="{{ url_for('search') }}" method="get">
        <input type="text" name="q" placeholder="搜索标题/内容/标签" value="{{ query }}">
      </form>
    </div>

    <div id="tree">
      {{ render_tree(tree) }}
    </div>

    <p style="margin-top: 12px;">
      <a href="{{ url_for('index') }}">＋ 新建节点</a>
    </p>
  </aside>

  <main class="content">
    <h1>搜索结果</h1>
    {% if query %}
      <p>关键字：<strong>{{ query }}</strong></p>
    {% else %}
      <p>请输入关键字进行搜索。</p>
    {% endif %}

    <hr>

    {% if query %}
      {% if results %}
        <ul>
          {% for r in results %}
            <li class="result-item">
              <a href="{{ url_for('view_node', node_id=r.id) }}">{{ r.title }}</a>
              {% if r.tags %}
                <span class="tags">（标签：{{ r.tags }}）</span>
              {% endif %}
            </li>
          {% endfor %}
        </ul>
      {% else %}
        <p>没有找到匹配的节点。</p>
      {% endif %}
    {% endif %}
  </main>
</div>

<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/jstree@3.3.15/dist/jstree.min.js"></script>
<script>
  $(function () {
    $('#tree').jstree({
      "core": {
        "themes": {
          "variant": "large"
        }
      }
    });
  });
</script>
</body>
</html>
```

---

## 六、怎么用 / 小总结

1. 保持你的目录结构类似：

   ```text
   mdshare/
   ├─ app.py
   ├─ notes.db        # 第一次运行会自动生成
   └─ templates/
      ├─ _tree.html
      ├─ index.html
      ├─ view.html
      └─ search.html
   ```

2. 保持之前虚拟环境不变，启动：

   ```bash
   cd ~/mdshare
   source venv/bin/activate
   python app.py
   ```

3. 打开 `http://服务器IP:5000/`：

   * 左边是可折叠树（jsTree），可以展开 / 折叠，就像 CherryTree 的左栏
   * 右边可以新建节点，指定父节点、填标签、贴 Markdown
   * 点某个节点 → 右边可以编辑、保存、删除（删除会把整个子树一起删）
   * 左侧搜索框或顶部搜索页 `/search` 可以按标题 / 内容 / 标签模糊搜索

---

如果你贴一下你当前 `templates` 和 `app.py` 的内容，我也可以帮你对比着生成一个“最小改动版”，避免一次性全换掉。现在这个版本是“整合好的一份”，你直接用也可以。
