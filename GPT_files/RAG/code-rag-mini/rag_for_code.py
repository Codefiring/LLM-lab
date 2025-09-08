#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAG for Code — 轻量版实现（单文件脚本）
=================================================
功能：
1) 递归解析代码仓库，分块切片（按行数+简单代码边界）
2) 通过 Sentence-Transformers 生成向量，并用 FAISS 建库
3) 提供检索 + 上下文组装，并演示如何调用 LLM 进行 RAG 推理

依赖安装：
    pip install -U "sentence-transformers>=3.0.0" faiss-cpu tqdm rich ujson pydantic
    # 任选其一的 LLM 客户端：
    # a) OpenAI:
    #    pip install "openai>=1.37.0"
    # b) Ollama（本地推理）:
    #    pip install ollama

快速开始：
    # 1) 构建索引
    python rag_code.py build --kb /path/to/your/code --index ./rag_index

    # 2) 仅检索（查看召回片段）
    python rag_code.py query --index ./rag_index "如何在项目里初始化数据库连接？"

    # 3) RAG 问答（示例：OpenAI 或 Ollama）
    # OpenAI：需设置环境变量 OPENAI_API_KEY
    python rag_code.py ask --index ./rag_index --backend openai --model gpt-4o-mini \
        "给我一个添加新 API 路由的步骤，结合仓库中的现有代码"

    # Ollama：需本地已拉取对应模型（如 llama3.1:8b-instruct、qwen2.5:7b 等）
    python rag_code.py ask --index ./rag_index --backend ollama --model llama3.1:8b-instruct \
        "本项目如何进行鉴权？请结合代码回答"

索引持久化目录结构（--index 指定）：
    rag_index/
      ├── faiss.index             # 向量库
      ├── meta.jsonl              # 向量<->片段元数据映射（一行一条）
      └── settings.json           # 模型名、维度、切片策略等配置

注意：
- 本脚本默认使用多语种检索模型 "BAAI/bge-m3"，对中文/英文/代码混合检索表现较稳健。
- BGE/E5 类模型通常推荐加检索提示词前缀（query:/passage:），脚本里可开关。
- 若仓库极大，首次建库会较慢；可调整 --max-lines/--overlap 控制片段大小。
"""

from __future__ import annotations
import os
import re
import sys
import json
import ujson
import time
import math
import faiss
import argparse
import pathlib
import hashlib
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Iterable, Tuple, Optional

import numpy as np
from tqdm import tqdm
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from sentence_transformers import SentenceTransformer

console = Console()

# ----------------------------- 配置与常量 -----------------------------
DEFAULT_MODEL = "BAAI/bge-m3"  # 多语种、对代码也较鲁棒
DEFAULT_MAX_LINES = 120         # 每个切片最大行数
DEFAULT_OVERLAP = 20            # 相邻切片的行重叠数
DEFAULT_TOP_K = 6

# 认为是代码/相关文本的扩展名（可自行扩展）
CODE_EXTS = {
    ".py", ".ipynb", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
    ".cpp", ".hpp", ".c", ".h", ".cs", ".php", ".rb", ".swift", ".kt", ".scala",
    ".sh", ".ps1", ".bash", ".zsh", ".sql", ".r", ".m", ".jl",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env",
    ".md", ".rst", ".txt",
}

# 忽略的目录名
IGNORE_DIRS = {".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__", ".idea", ".vscode", ".mypy_cache"}


# ----------------------------- 数据类 -----------------------------
@dataclass
class CodeChunk:
    chunk_id: str
    file_path: str
    rel_path: str
    start_line: int
    end_line: int
    language: str
    text: str

    @staticmethod
    def make_id(file_path: str, start_line: int, end_line: int) -> str:
        h = hashlib.sha1(f"{file_path}:{start_line}-{end_line}".encode("utf-8")).hexdigest()[:16]
        return h


# ----------------------------- 工具函数 -----------------------------
def detect_language_by_ext(path: str) -> str:
    ext = pathlib.Path(path).suffix.lower()
    mapping = {
        ".py": "python", ".js": "javascript", ".ts": "typescript", ".java": "java",
        ".go": "go", ".rs": "rust", ".cpp": "cpp", ".hpp": "cpp", ".c": "c", ".h": "c",
        ".cs": "csharp", ".php": "php", ".rb": "ruby", ".swift": "swift", ".kt": "kotlin",
        ".scala": "scala", ".sh": "bash", ".ps1": "powershell", ".sql": "sql",
        ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
        ".md": "markdown", ".rst": "restructuredtext", ".txt": "text",
    }
    return mapping.get(ext, ext.lstrip(".")) or "text"


def read_text_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        # 尝试以 latin-1 兜底
        with open(path, "r", encoding="latin-1", errors="ignore") as f:
            return f.read()


def iter_code_files(root: str) -> Iterable[str]:
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        # 过滤隐藏/忽略目录
        parts = set(os.path.basename(dirpath).split(os.sep))
        if any(d in IGNORE_DIRS for d in dirpath.split(os.sep)):
            # 就地修改 dirnames 可以剪枝
            dirnames[:] = []
            continue
        for name in filenames:
            p = os.path.join(dirpath, name)
            ext = pathlib.Path(p).suffix.lower()
            if ext in CODE_EXTS:
                yield p


def chunk_by_lines(text: str, max_lines: int, overlap: int) -> List[Tuple[int, int, str]]:
    """简单按行滑窗切片；同时尽量在常见边界（函数/类定义、# 标题）处切。"""
    lines = text.splitlines()
    n = len(lines)
    idx = 0
    chunks = []

    # 预先标注可作为“柔性边界”的行
    boundary_re = re.compile(r"^(\s*(def |class |#|//|/\*\*|/\*|function |export |public |private |protected |interface |struct |impl |fn |if |for |while ))")

    while idx < n:
        end = min(idx + max_lines, n)
        # 在 [idx+max_lines-30, end) 范围里寻找最近的边界行，以避免把函数/类一刀切断
        search_start = max(idx + max_lines - 30, idx)
        best = None
        for j in range(end - 1, search_start - 1, -1):
            if boundary_re.match(lines[j]):
                best = j
                break
        if best is not None and best > idx + 10:  # 至少保证片段不太短
            end = best
        chunk_text = "\n".join(lines[idx:end])
        chunks.append((idx + 1, end, chunk_text))  # 行号从 1 开始
        if end >= n:
            break
        idx = max(end - overlap, 0)
    return chunks


# ----------------------------- 向量索引器 -----------------------------
class CodeVectorStore:
    def __init__(self, index_dir: str, model_name: str = DEFAULT_MODEL, use_instruction: bool = True):
        self.index_dir = index_dir
        self.model_name = model_name
        self.use_instruction = use_instruction
        self.model: Optional[SentenceTransformer] = None
        self.index: Optional[faiss.IndexFlatIP] = None
        self.emb_dim: Optional[int] = None
        self.meta_path = os.path.join(index_dir, "meta.jsonl")
        self.settings_path = os.path.join(index_dir, "settings.json")
        self.index_path = os.path.join(index_dir, "faiss.index")

    # ---------- 模型/索引 ----------
    def load_model(self):
        if self.model is None:
            console.log(f"加载嵌入模型: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            self.emb_dim = int(self.model.get_sentence_embedding_dimension())

    def _ensure_index(self):
        assert self.emb_dim is not None
        if self.index is None:
            self.index = faiss.IndexFlatIP(self.emb_dim)  # 归一化后用内积≈余弦

    # ---------- 文本编码 ----------
    def _encode_passages(self, texts: List[str]) -> np.ndarray:
        self.load_model()
        assert self.model is not None
        if self.use_instruction:
            texts = [f"passage: {t}" for t in texts]
        emb = self.model.encode(texts, normalize_embeddings=True, batch_size=64, show_progress_bar=True)
        return np.asarray(emb, dtype="float32")

    def _encode_queries(self, texts: List[str]) -> np.ndarray:
        self.load_model()
        assert self.model is not None
        if self.use_instruction:
            texts = [f"query: {t}" for t in texts]
        emb = self.model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
        return np.asarray(emb, dtype="float32")

    # ---------- 建库 ----------
    def build_from_folder(self, kb_root: str, max_lines: int = DEFAULT_MAX_LINES, overlap: int = DEFAULT_OVERLAP):
        os.makedirs(self.index_dir, exist_ok=True)
        all_chunks: List[CodeChunk] = []
        texts: List[str] = []

        kb_root_abs = os.path.abspath(kb_root)
        console.rule(f"[bold green]扫描代码目录: {kb_root_abs}")
        for fp in tqdm(list(iter_code_files(kb_root_abs)), desc="遍历文件"):
            try:
                rel_path = os.path.relpath(fp, kb_root_abs)
                lang = detect_language_by_ext(fp)
                text = read_text_file(fp)
                for (s, e, chunk_text) in chunk_by_lines(text, max_lines=max_lines, overlap=overlap):
                    cid = CodeChunk.make_id(fp, s, e)
                    all_chunks.append(CodeChunk(
                        chunk_id=cid,
                        file_path=fp,
                        rel_path=rel_path,
                        start_line=s,
                        end_line=e,
                        language=lang,
                        text=chunk_text,
                    ))
                    texts.append(chunk_text)
            except Exception as ex:
                console.print(f"[yellow]跳过文件[/yellow] {fp}: {ex}")

        if not texts:
            raise RuntimeError("未发现可用代码文件，请检查目录与后缀过滤。")

        console.rule("[bold green]编码并建立向量索引")
        X = self._encode_passages(texts)
        self._ensure_index()
        assert self.index is not None
        self.index.add(X)

        # 持久化元数据
        with open(self.meta_path, "w", encoding="utf-8") as f:
            for c in all_chunks:
                f.write(ujson.dumps(asdict(c), ensure_ascii=False) + "\n")

        settings = {
            "model_name": self.model_name,
            "emb_dim": self.emb_dim,
            "use_instruction": self.use_instruction,
            "max_lines": max_lines,
            "overlap": overlap,
            "count": len(all_chunks),
            "built_at": int(time.time()),
        }
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        faiss.write_index(self.index, self.index_path)
        console.print(Panel.fit(f"索引完成，共 [bold]{len(all_chunks)}[/bold] 个片段，向量维度 [bold]{self.emb_dim}[/bold]。", title="Done"))

    # ---------- 加载已有索引 ----------
    def load(self):
        if not (os.path.exists(self.index_path) and os.path.exists(self.meta_path) and os.path.exists(self.settings_path)):
            raise FileNotFoundError(f"索引目录不完整: {self.index_dir}")
        with open(self.settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
        self.model_name = settings.get("model_name", self.model_name)
        self.use_instruction = bool(settings.get("use_instruction", True))
        self.load_model()
        self.emb_dim = int(settings.get("emb_dim", self.model.get_sentence_embedding_dimension() if self.model else 1024))
        self.index = faiss.read_index(self.index_path)

    # ---------- 相似检索 ----------
    def search(self, query: str, top_k: int = DEFAULT_TOP_K) -> List[Dict[str, Any]]:
        self.load()
        q = self._encode_queries([query])
        assert self.index is not None
        D, I = self.index.search(q, top_k)
        D = D[0].tolist()
        I = I[0].tolist()

        # 读取对应的 meta 行
        hits: List[Dict[str, Any]] = []
        # 为高效：定位到每一行需要逐行扫描或缓存；此处简单逐行读取（top_k 不大）
        with open(self.meta_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        for score, idx in zip(D, I):
            meta = json.loads(all_lines[idx])
            meta["score"] = float(score)
            hits.append(meta)
        return hits


# ----------------------------- RAG 组装与推理 -----------------------------
RAG_SYSTEM_PROMPT = (
    "你是资深软件工程助手。基于给定的代码片段，\n"
    "请先简要归纳项目里的现有实现/约定，再有条理地回答用户问题。\n"
    "若代码中没有直接答案，也要给出合理推断与下一步建议（文件/模块名、搜索关键词等）。\n"
    "回答务必引用你使用到的文件相对路径与行号范围。"
)


def build_context_block(hits: List[Dict[str, Any]]) -> str:
    blocks = []
    for i, h in enumerate(hits, 1):
        rel = h.get("rel_path")
        s = h.get("start_line")
        e = h.get("end_line")
        lang = h.get("language", "")
        text = h.get("text", "")
        score = h.get("score", 0.0)
        header = f"[ctx {i}] {rel}:{s}-{e} (lang={lang}, score={score:.3f})"
        blocks.append(header + "\n" + text)
    return ("\n\n" + "\n\n".join(blocks)).strip()


def make_rag_prompt(user_query: str, hits: List[Dict[str, Any]], limit_tokens: int = 3500) -> str:
    ctx = build_context_block(hits)
    instr = (
        "请严格遵循以下格式输出：\n"
        "1) 结论（先给要点）\n2) 依据（逐条引用 [ctx i] 文件路径与行号）\n3) 步骤/建议\n4) 可能的风险与注意事项\n"
    )
    prompt = (
        f"<system>\n{RAG_SYSTEM_PROMPT}\n</system>\n"
        f"<question>\n{user_query}\n</question>\n"
        f"<context>\n{ctx}\n</context>\n"
        f"<instruction>\n{instr}\n</instruction>\n"
    )
    # 简单裁剪（按字符数近似控制）
    if len(prompt) > limit_tokens * 4:  # 粗略估计 1 token ≈ 4 chars
        prompt = prompt[-limit_tokens * 4 :]
    return prompt


# ----------------------------- LLM 后端（示例） -----------------------------
class LLMBackend:
    def __init__(self, backend: str, model: str):
        self.backend = backend
        self.model = model
        if backend not in {"openai", "ollama"}:
            raise ValueError("backend 仅支持: openai / ollama")

    def chat(self, prompt: str) -> str:
        if self.backend == "openai":
            return self._chat_openai(prompt)
        else:
            return self._chat_ollama(prompt)

    def _chat_openai(self, prompt: str) -> str:
        try:
            from openai import OpenAI  # pip install openai
        except Exception as e:
            raise RuntimeError("请先安装 openai: pip install openai") from e
        client = OpenAI()
        # 兼容常见 Chat Completions 风格（如 gpt-4o/mini 系列）
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "你是有帮助的工程助手。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()

    def _chat_ollama(self, prompt: str) -> str:
        try:
            import ollama  # pip install ollama
        except Exception as e:
            raise RuntimeError("请先安装 ollama: pip install ollama，并在本机运行 ollama 服务器") from e
        resp = ollama.chat(model=self.model, messages=[{"role": "user", "content": prompt}], options={"temperature": 0.2})
        return resp["message"]["content"].strip()


# ----------------------------- CLI -----------------------------
def cmd_build(args):
    store = CodeVectorStore(index_dir=args.index, model_name=args.model, use_instruction=not args.no_instruction)
    store.build_from_folder(args.kb, max_lines=args.max_lines, overlap=args.overlap)


def _print_hits(hits: List[Dict[str, Any]]):
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", width=3)
    table.add_column("相对路径")
    table.add_column("行号")
    table.add_column("得分", justify="right", width=6)
    for i, h in enumerate(hits, 1):
        table.add_row(str(i), h.get("rel_path", ""), f"{h.get('start_line')}-{h.get('end_line')}", f"{h.get('score', 0.0):.3f}")
    console.print(table)


def cmd_query(args):
    store = CodeVectorStore(index_dir=args.index)
    hits = store.search(args.query, top_k=args.top_k)
    _print_hits(hits)
    if args.show:
        for i, h in enumerate(hits, 1):
            header = f"[bold]#{i}[/bold] {h['rel_path']}:{h['start_line']}-{h['end_line']}  (score={h['score']:.3f})"
            console.rule(header)
            console.print(h["text"])


def cmd_ask(args):
    store = CodeVectorStore(index_dir=args.index)
    hits = store.search(args.question, top_k=args.top_k)
    _print_hits(hits)
    prompt = make_rag_prompt(args.question, hits, limit_tokens=args.max_ctx_tokens)
    backend = LLMBackend(backend=args.backend, model=args.model)
    console.rule("[bold green]LLM 回答")
    answer = backend.chat(prompt)
    console.print(answer)


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="RAG for Code — 轻量版实现")
    sub = p.add_subparsers(dest="command", required=True)

    # build
    p_build = sub.add_parser("build", help="从代码目录构建向量索引")
    p_build.add_argument("--kb", required=True, help="代码根目录")
    p_build.add_argument("--index", default="./rag_index", help="索引输出目录")
    p_build.add_argument("--model", default=DEFAULT_MODEL, help="嵌入模型名（HuggingFace 上的 Sentence-Transformers 模型）")
    p_build.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES, help="切片最大行数")
    p_build.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP, help="相邻切片重叠行数")
    p_build.add_argument("--no-instruction", action="store_true", help="编码/检索时不添加 query:/passage: 前缀")
    p_build.set_defaults(func=cmd_build)

    # query
    p_query = sub.add_parser("query", help="仅相似检索，查看召回片段")
    p_query.add_argument("--index", default="./rag_index", help="索引目录")
    p_query.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="返回片段数")
    p_query.add_argument("--show", action="store_true", help="打印片段内容")
    p_query.add_argument("query", help="查询语句")
    p_query.set_defaults(func=cmd_query)

    # ask
    p_ask = sub.add_parser("ask", help="RAG 问答（调用 LLM）")
    p_ask.add_argument("--index", default="./rag_index", help="索引目录")
    p_ask.add_argument("--backend", choices=["openai", "ollama"], default="openai", help="LLM 后端")
    p_ask.add_argument("--model", required=True, help="LLM 模型名（如 gpt-4o-mini / llama3.1:8b-instruct / qwen2.5:7b 等）")
    p_ask.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="检索片段数")
    p_ask.add_argument("--max-ctx-tokens", type=int, default=3500, help="上下文 token 近似上限（粗略按字符裁剪）")
    p_ask.add_argument("question", help="用户问题")
    p_ask.set_defaults(func=cmd_ask)

    return p


def main(argv=None):
    argv = argv or sys.argv[1:]
    parser = build_argparser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
