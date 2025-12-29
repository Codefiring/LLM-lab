下面是一套 **一键可跑的图片共享网站** 实现方案，满足：

✅ 用户按 **Ctrl+V 直接粘贴图片上传**
✅ 图片按 **日期分组展示**
✅ 用访问者的 **IP 区分用户**
✅ 用户可 **删除自己的图片**
✅ 支持设置 **哪些 IP 不可见自己的图片**
✅ 风格参考 **Apple 官网极简风格**
✅ 完整前后端代码，用 **Python（Flask）** 实现

---

## 🧠 系统设计

### 🧱 数据模型（SQLite 简单版）

| 表        | 字段            | 说明            |
| -------- | ------------- | ------------- |
| `images` | `id`          | 主键            |
|          | `filename`    | 存储文件名         |
|          | `uploaded_at` | 上传时间          |
|          | `uploader_ip` | 上传者 IP        |
|          | `hidden_ips`  | 不可见列表（JSON数组） |

---

## 🏗 文件结构

```
image_share/
├── app.py
├── static/
│   ├── css/
│   │   └── style.css
│   └── uploads/
├── templates/
│   ├── index.html
│   └── images.html
├── requirements.txt
└── init_db.py
```

---

## 📌 安装与一键运行

**1. 创建虚拟环境并安装依赖**

```bash
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
pip install -r requirements.txt
```

**2. 初始化数据库**

```bash
python init_db.py
```

**3. 启动网站**

```bash
python app.py
```

浏览器打开： [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## 📦 requirements.txt

```text
Flask
pillow
```

---

## 📍 init_db.py

```python
import sqlite3
import json

conn = sqlite3.connect('images.db')
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    uploaded_at TEXT,
    uploader_ip TEXT,
    hidden_ips TEXT
)
''')

conn.commit()
conn.close()

print("数据库初始化完成 🎉")
```

---

## 📍 app.py

```python
import os
import json
import uuid
from datetime import datetime
from flask import Flask, request, render_template, jsonify, send_from_directory

import sqlite3
from PIL import Image
from io import BytesIO
import base64

app = Flask(__name__)
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db():
    conn = sqlite3.connect("images.db")
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    data = request.json.get('image')
    ip = request.remote_addr

    # 解码Base64
    header, encoded = data.split(",", 1)
    img_data = base64.b64decode(encoded)

    # 存储文件
    filename = f"{uuid.uuid4().hex}.png"
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    image = Image.open(BytesIO(img_data))
    image.save(filepath)

    # 存数据库
    conn = get_db()
    conn.execute("INSERT INTO images (filename, uploaded_at, uploader_ip, hidden_ips) VALUES (?,?,?,?)",
                 (filename, datetime.utcnow().isoformat(), ip, json.dumps([])))
    conn.commit()

    return jsonify(success=True)

@app.route('/images')
def images():
    ip = request.remote_addr
    conn = get_db()

    rows = conn.execute("SELECT * FROM images ORDER BY uploaded_at DESC").fetchall()
    grouped = {}
    for row in rows:
        hidden = json.loads(row["hidden_ips"])
        if ip in hidden:
            continue

        date = row["uploaded_at"].split("T")[0]
        grouped.setdefault(date, []).append(dict(row))

    return render_template('images.html', groups=grouped, my_ip=ip)

@app.route('/delete/<int:image_id>', methods=['POST'])
def delete(image_id):
    ip = request.remote_addr
    conn = get_db()
    row = conn.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()
    if not row:
        return jsonify(error="不存在"), 404

    if row["uploader_ip"] != ip:
        return jsonify(error="无权限删除"), 403

    # 删除文件
    try:
        os.remove(os.path.join(UPLOAD_FOLDER, row["filename"]))
    except:
        pass

    conn.execute("DELETE FROM images WHERE id=?", (image_id,))
    conn.commit()
    return jsonify(success=True)

@app.route('/hide/<int:image_id>', methods=['POST'])
def hide(image_id):
    ip = request.remote_addr
    target_ip = request.json.get('hide_ip')
    conn = get_db()
    row = conn.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()
    if not row:
        return jsonify(error="不存在"), 404
    if row["uploader_ip"] != ip:
        return jsonify(error="无权限设置"), 403

    hidden = json.loads(row["hidden_ips"])
    if target_ip not in hidden:
        hidden.append(target_ip)
    conn.execute("UPDATE images SET hidden_ips=? WHERE id=?",
                 (json.dumps(hidden), image_id))
    conn.commit()
    return jsonify(success=True)

if __name__ == "__main__":
    app.run(debug=True)
```

---

## 🎨 templates/index.html

用户粘贴上传页面

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>📸 图片共享</title>
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
<div class="container">
    <h1>📸 直接粘贴上传你的图片</h1>
    <div id="dropzone">按 <b>Ctrl+V</b> 在这里粘贴图片</div>
    <p><a href="/images">查看所有图片</a></p>
</div>

<script>
document.addEventListener('paste', function (e) {
    const items = e.clipboardData.items;
    for (let item of items) {
        if (item.type.indexOf("image") !== -1) {
            const file = item.getAsFile();
            const reader = new FileReader();
            reader.onload = function (evt) {
                fetch("/upload", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({image: evt.target.result})
                }).then(r => location.reload());
            };
            reader.readAsDataURL(file);
        }
    }
});
</script>
</body>
</html>
```

---

## 🎨 templates/images.html

展示所有图片，按日期分组

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>🖼 图片展示</title>
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
<div class="container">
    <h1>🖼 所有图片</h1>
    <p>你的IP: {{ my_ip }}</p>

    {% for date, imgs in groups.items() %}
    <div class="group">
        <h2>{{ date }}</h2>
        <div class="gallery">
            {% for img in imgs %}
            <div class="item">
                <img src="/static/uploads/{{ img['filename'] }}">
                {% if img['uploader_ip']== my_ip %}
                <button onclick="deleteImg({{ img['id'] }})">删除</button>

                <input type="text" id="hideip-{{ img['id'] }}" placeholder="隐藏某个 IP">
                <button onclick="hideIp({{ img['id'] }})">隐藏</button>
                {% endif %}
            </div>
            {% endfor %}
        </div>
    </div>
    {% endfor %}
</div>

<script>
function deleteImg(id) {
    fetch(`/delete/${id}`, {method: "POST"}).then(r=>location.reload());
}

function hideIp(id) {
    const ip = document.getElementById(`hideip-${id}`).value;
    fetch(`/hide/${id}`, {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify({hide_ip:ip})
    }).then(r=>location.reload());
}
</script>
</body>
</html>
```

---

## 🎨 static/css/style.css

借鉴 Apple 风格：极简、留白、圆角

```css
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: #f5f5f7;
    color: #1d1d1f;
    margin: 0;
    padding: 0;
}

.container {
    max-width: 800px;
    margin: 40px auto;
    padding: 0 20px;
}

h1 {
    font-size: 2.5rem;
    font-weight: 600;
    text-align: center;
}

#dropzone {
    margin: 40px auto;
    padding: 60px;
    border: 2px dashed #d2d2d7;
    text-align: center;
    font-size: 1.2rem;
    color: #6e6e73;
    background: white;
    border-radius: 12px;
}

.group h2 {
    font-size: 1.6rem;
    margin-top: 30px;
}

.gallery {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
}

.item {
    width: 120px;
    text-align: center;
    background: white;
    padding: 8px;
    border-radius: 8px;
}

.item img {
    max-width: 100%;
    border-radius: 6px;
}

button {
    margin-top: 6px;
    padding: 6px 10px;
    border: none;
    background: #0071e3;
    color: white;
    border-radius: 6px;
    font-size: 0.9rem;
    cursor: pointer;
}

input {
    width: 100%;
    margin-top: 6px;
    padding: 4px;
    border: 1px solid #ccc;
    border-radius: 6px;
}
```

---

## 🎉 功能验证

### ✅ Ctrl+V 直接上传

在主页按 Ctrl+V 即可上传图片

### ✅ 按日期分组展示

访问 `/images` 即可查看

### ✅ 删除自己图像

只有上传者（由 IP 识别）看到删除按钮

### ✅ 隐藏对某些 IP 不可见

输入对方 IP 并点击 “隐藏”

---

## ⚙️ 可选拓展（不影响现有代码）

💡 加用户登录（邮箱/验证码）
💡 添加评论功能
💡 图片懒加载/缩略图
💡 更细粒度权限设置

---

如果你想我 **部署到服务器（例如：Render/Heroku）** 或加 **用户登录系统/缩略图优化**，我也可以帮你完善。✨
