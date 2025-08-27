#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ioc_fsm_builder.py
------------------
Reads an IOCTL list (name + analysis text), extracts preconditions and effects
(using an LLM if available, otherwise a heuristic fallback), normalizes them
against a simple ontology, then composes a projected state graph and emits
Graphviz DOT and JSON exports.

Usage:
  python ioc_fsm_builder.py \
    --input sample_ioctls.jsonl \
    --outdir out \
    --projection power,driver \
    [--openai] [--model gpt-4o-mini]
"""

import argparse, json, os, re, sys, hashlib, random, math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional

# ----------------------------- Ontology & Aliases -----------------------------

DEFAULT_ONTOLOGY = {
    "namespaces": ["power","driver","dma","irq"],
    "keys": {
        "power:POWER_STATE": {"type": "enum", "values": ["D0","D1","D3"]},
        "driver:OPENED": {"type": "bool"},
        "driver:INITIALIZED": {"type": "bool"},
        "driver:CONFIGURED": {"type": "bool"},
        "driver:REFCNT": {"type": "int", "abstract": [0, ">0"]},
        "dma:MAPPED": {"type": "bool"},
        "irq:ENABLED": {"type": "bool"}
    },
    "initial_state": {
        "power:POWER_STATE": "D3",
        "driver:OPENED": False,
        "driver:INITIALIZED": False,
        "driver:CONFIGURED": False,
        "driver:REFCNT": 0,
        "dma:MAPPED": False,
        "irq:ENABLED": False
    }
}

DEFAULT_ALIASES = {
    # value-level or key-level aliases
    "POWERED": ("power:POWER_STATE", "D0"),
    "上电": ("power:POWER_STATE", "D0"),
    "通电": ("power:POWER_STATE", "D0"),
    "断电": ("power:POWER_STATE", "D3"),
    "open 成功": ("driver:OPENED", True),
    "已打开": ("driver:OPENED", True),
    "初始化完成": ("driver:INITIALIZED", True),
    "已配置": ("driver:CONFIGURED", True),
    "映射DMA": ("dma:MAPPED", True),
    "启用中断": ("irq:ENABLED", True),
    "禁用中断": ("irq:ENABLED", False),
}

# ------------------------------- LLM Extraction -------------------------------

EXTRACTION_INSTRUCTIONS = """
你将收到某个操作（例如内核 IOCTL）的中文分析文本。请从文本中抽取：
- pre: 操作成功执行所需的条件（全部满足）
- effects: 成功后的状态影响（设置/清除/赋值/递增/递减/切换）
- error_paths: 失败条件与错误码（若有）

使用以下通用 JSON 结构返回（仅此结构，不要多余字段）：
{
  "name": "...",
  "pre": [ {"expr": "driver:OPENED == true"}, {"expr":"power:POWER_STATE == D0"} ],
  "effects": [
    {"kind":"assign", "target":"driver:INITIALIZED", "value": true},
    {"kind":"assign", "target":"power:POWER_STATE", "value":"D0"},
    {"kind":"increase", "target":"driver:REFCNT", "by": 1}
  ],
  "error_paths": [
    {"when": "not driver:OPENED", "code": "-ENODEV"}
  ],
  "notes": "",
  "confidence": 0.8
}

要求：
- 仅使用这些状态键（命名空间:键）：power:POWER_STATE, driver:OPENED, driver:INITIALIZED, driver:CONFIGURED, driver:REFCNT, dma:MAPPED, irq:ENABLED。
- 若文本使用了同义词（如 上电/通电/POWERED），请映射为 power:POWER_STATE == D0。
- 若无法确定，写在 notes 并降低 confidence。
- 仅输出 JSON 对象文本。
"""

def call_openai_structured(text: str, name: str, model: str = "gpt-4o-mini") -> Optional[Dict[str, Any]]:
    """
    Calls OpenAI if OPENAI_API_KEY is present. Returns parsed dict or None on failure.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        # Lazy import to avoid hard dependency if not used
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        msg = [
            {"role":"system","content":EXTRACTION_INSTRUCTIONS},
            {"role":"user","content": f"操作名: {name}\n分析文本:\n{text}"}
        ]
        resp = client.chat.completions.create(
            model=model,
            messages=msg,
            response_format={"type":"json_object"},
            temperature=0.2,
        )
        content = resp.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        sys.stderr.write(f"[WARN] OpenAI call failed: {e}\n")
        return None

# --------------------------- Heuristic Fallback NLP ---------------------------

def heuristic_extract(text: str, name: str) -> Dict[str, Any]:
    """
    Extremely naive extraction to keep pipeline runnable without LLM.
    It scans for alias phrases and fabricates a plausible structure.
    """
    pre, effects, error_paths = [], [], []
    notes = []
    conf = 0.45

    t = text.lower()

    def add_pre(expr): pre.append({"expr": expr})
    def add_eff(kind, target, value=None, by=None):
        d = {"kind": kind, "target": target}
        if value is not None: d["value"] = value
        if by is not None: d["by"] = by
        effects.append(d)

    # crude cues
    if "必须" in text or "需要" in text or "前提" in text:
        if "打开" in text or "open" in t:
            add_pre("driver:OPENED == true")
        if any(k in text for k in ["上电","通电","d0","电源开启"]):
            add_pre("power:POWER_STATE == D0")
        if "初始化" in text and "后" in text:
            add_pre("driver:INITIALIZED == true")

    # effects guesses
    if any(k in text for k in ["打开","open 成功","open()"]):
        add_eff("assign","driver:OPENED",True)
        add_eff("increase","driver:REFCNT", by=1)
        if any(k in text for k in ["上电","通电","D0","电源"]):
            add_eff("assign","power:POWER_STATE","D0")
    if "初始化" in text or "init" in t:
        add_eff("assign","driver:INITIALIZED",True)
    if "配置" in text or "configure" in t:
        add_eff("assign","driver:CONFIGURED",True)
    if "映射" in text and "dma" in t:
        add_eff("assign","dma:MAPPED",True)
    if "启用中断" in text or "enable irq" in t:
        add_eff("assign","irq:ENABLED",True)
    if "禁用中断" in text or "disable irq" in t:
        add_eff("assign","irq:ENABLED",False)
    if "关闭" in text or "close" in t:
        add_eff("assign","driver:OPENED",False)
        add_eff("decrease","driver:REFCNT", by=1)

    # error guess
    if "如果未打开" in text or "未 open" in text:
        error_paths.append({"when":"not driver:OPENED","code":"-ENODEV"})

    return {
        "name": name,
        "pre": pre,
        "effects": effects if effects else [{"kind":"noop","target":"driver:OPENED"}],
        "error_paths": error_paths,
        "notes": "; ".join(notes) if notes else "",
        "confidence": conf
    }

# ----------------------------- Normalization Utils ----------------------------

def normalize_expr(expr: str) -> str:
    # Basic normalization: unify whitespace and booleans
    e = re.sub(r"\s+", " ", expr.strip())
    e = e.replace("True","true").replace("False","false")
    # Alias phrases to canonical keys/values
    for k,(ck,cv) in DEFAULT_ALIASES.items():
        if k in e:
            if isinstance(cv, bool):
                e = e.replace(k, f"{ck} == {str(cv).lower()}")
            else:
                e = e.replace(k, f"{ck} == {cv}")
    return e

def state_satisfies(state: Dict[str, Any], pre: List[Dict[str, Any]]) -> bool:
    for p in pre:
        e = normalize_expr(p["expr"])
        m = re.match(r"^([a-z]+:[A-Za-z0-9_]+)\s*==\s*(true|false|D0|D1|D3|[0-9]+)$", e)
        if not m:
            return False
        key, val = m.group(1), m.group(2)
        if val in ("true","false"):
            val = (val == "true")
        elif val.isdigit():
            val = int(val)
        # enums remain strings
        if state.get(key) != val:
            return False
    return True

def apply_effects(state: Dict[str, Any], effects: List[Dict[str, Any]]) -> Dict[str, Any]:
    s = dict(state)
    for eff in effects:
        kind = eff.get("kind")
        tgt  = eff.get("target")
        if kind == "assign":
            s[tgt] = eff.get("value")
        elif kind == "increase":
            s[tgt] = int(s.get(tgt, 0)) + int(eff.get("by",1))
        elif kind == "decrease":
            s[tgt] = int(s.get(tgt, 0)) - int(eff.get("by",1))
        elif kind in ("set_flag","clear_flag"):
            s[tgt] = (kind=="set_flag")
        elif kind == "noop":
            pass
        # others can be added as needed
    return s

def project_state(state: Dict[str, Any], projection_keys: List[str]) -> Tuple:
    # Optionally abstract integer keys
    out = []
    for k in projection_keys:
        v = state.get(k)
        if k.endswith("REFCNT"):
            v = 0 if not v else (">0" if v>0 else v)
        out.append((k, v))
    return tuple(out)

# --------------------------------- Graph Build --------------------------------

def build_graph(ops: List[Dict[str,Any]], ontology: Dict[str,Any], projection: List[str]):
    init = dict(ontology["initial_state"])
    S = set()
    E: Dict[Tuple, List[Tuple[str, Tuple, Dict[str,Any]]]] = {}
    from collections import deque
    q = deque([init])

    while q:
        s = q.popleft()
        ps = project_state(s, projection)
        if ps in S:
            continue
        S.add(ps)
        E.setdefault(ps, [])
        for op in ops:
            if state_satisfies(s, op.get("pre", [])):
                s2 = apply_effects(s, op.get("effects", []))
                ps2 = project_state(s2, projection)
                E[ps].append((op["name"], ps2, op))
                if ps2 not in S:
                    q.append(s2)
    return S, E

# --------------------------------- DOT Export ---------------------------------

def to_dot(S, E, projection):
    def label_state(ps):
        lines = [f"{k}={v}" for k,v in ps]
        return "\\n".join(lines)
    out = []
    out.append("digraph G {")
    out.append('  rankdir=LR; node [shape=box, fontsize=10];')
    # nodes
    for ps in S:
        out.append(f'  "{ps}" [label="{label_state(ps)}"];')
    # edges
    for ps, edges in E.items():
        for (name, ps2, op) in edges:
            out.append(f'  "{ps}" -> "{ps2}" [label="{name}"];')
    out.append("}")
    return "\n".join(out)

# ----------------------------------- Main -------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="JSONL: {name,text}")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--projection", default="power,driver", help="comma-separated namespaces to include")
    ap.add_argument("--openai", action="store_true", help="use OpenAI to extract if API key is set")
    ap.add_argument("--model", default="gpt-4o-mini")
    args = ap.parse_args()

    projection_ns = [x.strip() for x in args.projection.split(",") if x.strip()]
    # expand projection keys
    projection_keys = [k for k in DEFAULT_ONTOLOGY["keys"].keys() if k.split(":")[0] in projection_ns]

    os.makedirs(args.outdir, exist_ok=True)

    ops = []
    with open(args.input, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            name = rec["name"]
            text = rec["text"]
            item = None
            if args.openai:
                item = call_openai_structured(text, name, model=args.model)
            if not item:
                item = heuristic_extract(text, name)
            ops.append(item)

    # Build graph
    S, E = build_graph(ops, DEFAULT_ONTOLOGY, projection_keys)

    # Exports
    dot = to_dot(S, E, projection_keys)
    dot_path = os.path.join(args.outdir, "fsm.dot")
    with open(dot_path, "w", encoding="utf-8") as f:
        f.write(dot)

    # Save normalized operations & graph JSON
    with open(os.path.join(args.outdir, "operations.json"), "w", encoding="utf-8") as f:
        json.dump(ops, f, ensure_ascii=False, indent=2)

    graph_json = {
        "projection_keys": projection_keys,
        "states": [list(ps) for ps in S],
        "edges": [
            {
                "from": list(ps),
                "to": list(ps2),
                "name": name
            }
            for ps, edges in E.items()
            for (name, ps2, op) in edges
        ]
    }
    with open(os.path.join(args.outdir, "graph.json"), "w", encoding="utf-8") as f:
        json.dump(graph_json, f, ensure_ascii=False, indent=2)

    print(f"[OK] States: {len(S)}, Edges: {sum(len(v) for v in E.values())}")
    print(f"[OK] Wrote: {dot_path}")
    print(f"Render with: dot -Tsvg {dot_path} -o {args.outdir}/fsm.svg")

if __name__ == "__main__":
    main()
