#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAG for Code — FastAPI Server + 简易前端（单文件）
=================================================
用途：给之前的 rag_code.py 提供一个可视化 Web 界面与 HTTP API。

运行：
    pip install fastapi uvicorn[standard] pydantic ujson rich
    # 还需 rag_code.py 所需依赖（sentence-transformers, faiss-cpu 等）已安装

    # 启动服务（默认 8000 端口）
    python rag_server.py

打开浏览器访问： http://127.0.0.1:8000/

说明：
- 本文件默认从同目录导入 rag_code.py 的实现：CodeVectorStore, LLMBackend, make_rag_prompt
- API 一览：
    POST /api/build   -> 构建/重建索引
    GET  /api/status  -> 查看索引设置
    POST /api/query   -> 相似检索
    POST /api/ask     -> RAG 问答（OpenAI/Ollama）
- 内置一个简易单页前端（原生 HTML+JS）
"""

from __future__ import annotations
import os
import json
import ujson
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

# 导入你上一份实现（确保 rag_code.py 与本文件同目录或可被 PYTHONPATH 找到）
from rag_code import CodeVectorStore, LLMBackend, make_rag_prompt, DEFAULT_TOP_K

app = FastAPI(title="RAG for Code Server", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------- 数据模型 -----------------------------
class BuildReq(BaseModel):
    kb: str = Field(..., description="代码根目录")
    index: str = Field("./rag_index", description="索引目录")
    model: str = Field("BAAI/bge-m3", description="向量模型名")
    max_lines: int = Field(120, ge=20, le=2000)
    overlap: int = Field(20, ge=0, le=500)
    use_instruction: bool = Field(True, description="是否在编码/检索时使用 query:/passage: 提示前缀")

class QueryReq(BaseModel):
    index: str = Field("./rag_index")
    query: str
    top_k: int = Field(DEFAULT_TOP_K, ge=1, le=50)

class AskReq(BaseModel):
    index: str = Field("./rag_index")
    question: str
    top_k: int = Field(DEFAULT_TOP_K, ge=1, le=20)
    backend: str = Field("openai", description="openai 或 ollama")
    model: str = Field(..., description="LLM 模型名，如 gpt-4o-mini / llama3.1:8b-instruct")
    max_ctx_tokens: int = Field(3500, ge=512, le=12000)


# ----------------------------- API 实现 -----------------------------
@app.post("/api/build")
def api_build(req: BuildReq):
    store = CodeVectorStore(index_dir=req.index, model_name=req.model, use_instruction=req.use_instruction)
    store.build_from_folder(req.kb, max_lines=req.max_lines, overlap=req.overlap)
    return {"ok": True, "index": req.index}


@app.get("/api/status")
def api_status(index: str = "./rag_index"):
    settings_path = os.path.join(index, "settings.json")
    meta_path = os.path.join(index, "meta.jsonl")
    exists = os.path.exists(settings_path) and os.path.exists(meta_path)
    if not exists:
        return JSONResponse({"ok": False, "error": "index not found"}, status_code=404)
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)
    # 统计片段数量
    count = 0
    with open(meta_path, "r", encoding="utf-8") as f:
        for _ in f: count += 1
    settings["count"] = count
    return {"ok": True, "settings": settings}


@app.post("/api/query")
def api_query(req: QueryReq):
    store = CodeVectorStore(index_dir=req.index)
    hits = store.search(req.query, top_k=req.top_k)
    # 精简返回：避免把全文都传回前端（可选：只传关键信息 + 片段文本）
    return {
        "ok": True,
        "hits": [
            {
                "rel_path": h.get("rel_path"),
                "start_line": h.get("start_line"),
                "end_line": h.get("end_line"),
                "score": h.get("score"),
                "preview": "\n".join(h.get("text", "").splitlines()[:40]),  # 预览前 40 行
            }
            for h in hits
        ],
    }


@app.post("/api/ask")
def api_ask(req: AskReq):
    store = CodeVectorStore(index_dir=req.index)
    hits = store.search(req.question, top_k=req.top_k)
    prompt = make_rag_prompt(req.question, hits, limit_tokens=req.max_ctx_tokens)
    llm = LLMBackend(backend=req.backend, model=req.model)
    answer = llm.chat(prompt)
    return {
        "ok": True,
        "answer": answer,
        "citations": [
            {
                "rel_path": h.get("rel_path"),
                "start_line": h.get("start_line"),
                "end_line": h.get("end_line"),
                "score": h.get("score"),
            }
            for h in hits
        ],
    }


# ----------------------------- 简易前端 -----------------------------
INDEX_HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>RAG for Code — 控制台</title>
  <style>
    body { font-family: ui-sans-serif, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji"; padding: 20px; max-width: 1100px; margin: 0 auto; }
    h1 { font-size: 20px; margin: 0 0 16px; }
    .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
    label { display:block; font-size: 12px; color:#6b7280; margin-bottom: 6px; }
    input, select, textarea { width: 100%; box-sizing: border-box; padding: 10px; border:1px solid #d1d5db; border-radius: 10px; }
    button { padding: 10px 14px; border: 1px solid #111827; background:#111827; color:#fff; border-radius: 10px; cursor:pointer; }
    button.secondary { background: #fff; color:#111827; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    pre { background:#0b1020; color:#e5e7eb; padding: 12px; border-radius: 10px; overflow:auto; }
    .hits { display:grid; grid-template-columns: 1fr; gap:12px; }
    .hit { border:1px solid #e5e7eb; border-radius:12px; padding:12px; }
    .meta { font-size:12px; color:#6b7280; }
  </style>
</head>
<body>
  <h1>RAG for Code — 控制台</h1>

  <div class="card">
    <h2>索引设置 / 构建</h2>
    <div class="row">
      <div>
        <label>代码目录（kb）</label>
        <input id="kb" placeholder="/path/to/your/repo" />
      </div>
      <div>
        <label>索引目录（index）</label>
        <input id="index" value="./rag_index" />
      </div>
    </div>
    <div class="row" style="margin-top:12px;">
      <div>
        <label>向量模型</label>
        <input id="embed_model" value="BAAI/bge-m3" />
      </div>
      <div>
        <label>切片大小 / 重叠行数</label>
        <div class="row">
          <input id="max_lines" type="number" value="120" />
          <input id="overlap" type="number" value="20" />
        </div>
      </div>
    </div>
    <div style="margin-top:12px; display:flex; gap:8px;">
      <label><input type="checkbox" id="use_instruction" checked /> 使用 query:/passage: 提示前缀</label>
    </div>
    <div style="margin-top:12px; display:flex; gap:8px;">
      <button onclick="buildIndex()">构建 / 重建索引</button>
      <button class="secondary" onclick="getStatus()">查看状态</button>
    </div>
    <pre id="build_out" style="margin-top:12px; min-height: 42px;"></pre>
  </div>

  <div class="card">
    <h2>相似检索</h2>
    <label>你的问题 / 检索语句</label>
    <input id="q" placeholder="例如：如何初始化数据库连接？" />
    <div class="row" style="margin-top:12px;">
      <div>
        <label>Top K</label>
        <input id="topk" type="number" value="6" />
      </div>
      <div style="display:flex; align-items:flex-end;">
        <button onclick="doQuery()">检索</button>
      </div>
    </div>
    <div class="hits" id="hits" style="margin-top:12px;"></div>
  </div>

  <div class="card">
    <h2>RAG 问答</h2>
    <div class="row">
      <div>
        <label>后端</label>
        <select id="backend">
          <option value="openai">openai</option>
          <option value="ollama">ollama</option>
        </select>
      </div>
      <div>
        <label>模型名</label>
        <input id="model" placeholder="gpt-4o-mini 或 llama3.1:8b-instruct" />
      </div>
    </div>
    <label style="margin-top:12px; display:block;">问题</label>
    <input id="ask_q" placeholder="结合仓库，如何新增一个 API 路由？" />
    <div class="row" style="margin-top:12px;">
      <div>
        <label>Top K</label>
        <input id="ask_topk" type="number" value="6" />
      </div>
      <div>
        <label>上下文 Token 近似上限</label>
        <input id="max_ctx" type="number" value="3500" />
      </div>
    </div>
    <div style="margin-top:12px; display:flex; gap:8px;">
      <button onclick="doAsk()">开始推理</button>
    </div>
    <h3>回答</h3>
    <pre id="answer"></pre>
    <h3>引用片段</h3>
    <div class="hits" id="cites"></div>
  </div>

<script>
function val(id){ return document.getElementById(id).value; }
function setText(id, text){ document.getElementById(id).textContent = text; }

async function buildIndex(){
  const payload = {
    kb: val('kb'), index: val('index'), model: val('embed_model'),
    max_lines: parseInt(val('max_lines'), 10), overlap: parseInt(val('overlap'), 10),
    use_instruction: document.getElementById('use_instruction').checked
  };
  setText('build_out', '⏳ 正在构建索引...');
  try {
    const r = await fetch('/api/build', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
    const j = await r.json();
    setText('build_out', JSON.stringify(j, null, 2));
  } catch (e) {
    setText('build_out', '❌ ' + e.message);
  }
}

async function getStatus(){
  const idx = val('index');
  setText('build_out', '⏳ 查询状态...');
  try {
    const r = await fetch('/api/status?index=' + encodeURIComponent(idx));
    const j = await r.json();
    setText('build_out', JSON.stringify(j, null, 2));
  } catch (e) {
    setText('build_out', '❌ ' + e.message);
  }
}

function renderHits(list){
  const box = document.getElementById('hits');
  box.innerHTML = '';
  list.forEach(h => {
    const div = document.createElement('div');
    div.className = 'hit';
    div.innerHTML = `<div class="meta">${h.rel_path}:${h.start_line}-${h.end_line} • score=${h.score?.toFixed(3)}</div>` +
                    `<pre>${h.preview?.replace(/[&<>]/g, s=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[s]))}</pre>`;
    box.appendChild(div);
  });
}

async function doQuery(){
  const payload = { index: val('index'), query: val('q'), top_k: parseInt(val('topk'),10) };
  try {
    const r = await fetch('/api/query', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
    const j = await r.json();
    if(j.ok){ renderHits(j.hits); } else { alert('查询失败'); }
  } catch (e) { alert(e.message); }
}

function renderCites(list){
  const box = document.getElementById('cites');
  box.innerHTML = '';
  list.forEach(h => {
    const div = document.createElement('div');
    div.className = 'hit';
    div.innerHTML = `<div class="meta">${h.rel_path}:${h.start_line}-${h.end_line} • score=${h.score?.toFixed(3)}</div>`;
    box.appendChild(div);
  });
}

async function doAsk(){
  const payload = {
    index: val('index'), question: val('ask_q'), top_k: parseInt(val('ask_topk'),10),
    backend: val('backend'), model: val('model'), max_ctx_tokens: parseInt(val('max_ctx'),10)
  };
  setText('answer', '⏳ 推理中...');
  try {
    const r = await fetch('/api/ask', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
    const j = await r.json();
    if(j.ok){ setText('answer', j.answer); renderCites(j.citations); } else { setText('answer', '❌ 失败'); }
  } catch (e) { setText('answer', '❌ ' + e.message); }
}
</script>

</body>
</html>
"""


@app.get("/")
def index_page():
    return HTMLResponse(INDEX_HTML)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("rag_server:app", host="127.0.0.1", port=8000, reload=True)
