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
