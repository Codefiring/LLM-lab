我给你把“简单版代码知识库 RAG”做成了一个**单文件 Python 脚本**（就在右侧画布里）。它能：

* 递归解析你的代码仓库，按行数+轻量边界切片
* 用 Sentence-Transformers 生成向量，FAISS 建库与持久化
* 支持相似检索 & 结合检索结果组织成提示词
* 演示两种推理后端：OpenAI 或本地 Ollama（可二选一）

### 怎么用（最少步骤）

1. 安装依赖

```bash
pip install -U "sentence-transformers>=3.0.0" faiss-cpu tqdm rich ujson pydantic
# 任选其一做推理：
pip install openai      # 如果用 OpenAI（需设 OPENAI_API_KEY）
# 或
pip install ollama      # 如果用本地 Ollama（本机需已安装并拉取模型）
```

2. 构建索引

```bash
python rag_code.py build --kb /你的代码目录 --index ./rag_index
```

3. 试试检索

```bash
python rag_code.py query --index ./rag_index "这里写你的问题" --show
```

4. RAG 问答

* OpenAI：

```bash
export OPENAI_API_KEY=xxxx
python rag_code.py ask --index ./rag_index --backend openai --model gpt-4o-mini "结合仓库说明如何新增接口？"
```

* Ollama（本地）：

```bash
python rag_code.py ask --index ./rag_index --backend ollama --model llama3.1:8b-instruct "项目鉴权怎么做？"
```

### 可调参数

* `--max-lines / --overlap`：控制代码分块大小与重叠
* `--model`：向量模型（默认 `BAAI/bge-m3`，中英混合&代码较稳）
* `--no-instruction`：关闭 `query:/passage:` 前缀
* `--top-k`：检索返回片段数
* `--max-ctx-tokens`：粗略限制拼接到提示词中的上下文大小

### 实现要点（概览）

* 文件筛选：常见代码/配置/文档后缀，自动忽略 `.git`/`node_modules` 等
* 切片：按行窗口 + 柔性边界（函数/类/注释等常见起始）避免“一刀切”
* 向量：`SentenceTransformer` 归一化后用 FAISS 内积检索（≈ 余弦）
* 元数据：`meta.jsonl` 逐行存片段映射；`settings.json` 记录模型与切片策略
* RAG 提示：自动把检索片段（含相对路径与行号）拼进上下文，指导模型引用依据

如果你希望我把它改成**支持增量更新**、**代码块语义感知切片（如 tree-sitter）**、**BM25+向量混合检索**、或**重排（Cross-Encoder）**，告诉我你的偏好和代码库大小，我直接给你升级版本。







我已经把一个可直接跑的\*\*后端 Server（FastAPI）+ 简易前端页面（原生 HTML/JS）\*\*做好并放到右侧画布里（单文件：`rag_server.py`）。它基于你前面那份 RAG 实现，提供 HTTP API 和一个小控制台页面。

### 目录与运行

将两份脚本放在同一目录：

```
rag_code.py       # 我之前给你的RAG核心实现
rag_server.py     # 这次新增的server+前端（单文件）
```

安装依赖并启动：

```bash
pip install fastapi uvicorn[standard] pydantic ujson rich
# 还需要 rag_code.py 的依赖（sentence-transformers、faiss-cpu 等）
python rag_server.py
```

打开浏览器访问：`http://127.0.0.1:8000/`

### 能做什么

* 在页面里填：代码目录、索引目录、嵌入模型、切片参数，点击“构建/重建索引”
* 用“相似检索”快速看召回的代码片段预览（含相对路径与行号+score）
* “RAG 问答”支持两种后端：

  * OpenAI：需设置 `OPENAI_API_KEY`，例如 `gpt-4o-mini`
  * 本地 Ollama：如 `llama3.1:8b-instruct` / `qwen2.5:7b`

### HTTP API

* `POST /api/build`：构建索引
  body：

  ```json
  {
    "kb": "/path/to/repo",
    "index": "./rag_index",
    "model": "BAAI/bge-m3",
    "max_lines": 120,
    "overlap": 20,
    "use_instruction": true
  }
  ```
* `GET /api/status?index=./rag_index`：查看索引设置与片段数
* `POST /api/query`：相似检索

  ```json
  { "index": "./rag_index", "query": "如何初始化数据库连接？", "top_k": 6 }
  ```
* `POST /api/ask`：RAG 推理

  ```json
  {
    "index": "./rag_index",
    "question": "结合仓库如何新增API路由？",
    "top_k": 6,
    "backend": "openai",      // 或 "ollama"
    "model": "gpt-4o-mini",   // 或 "llama3.1:8b-instruct"
    "max_ctx_tokens": 3500
  }
  ```

### 小贴士（可按需调整）

* 如果要部署到内网服务器，把 `uvicorn.run` 的 host 改成 `0.0.0.0`，并加上反向代理/鉴权。
* 大仓库初建比较久，可先把 `--max-lines` 调小；后续可以加**增量更新**与**重排（Cross-Encoder）**，我也可以直接给你升级版本。
* 想要更漂亮的 UI（如表格排序、分栏、代码高亮），我可以再给你一个 React + Tailwind 的前端，也对接同一套 API。
