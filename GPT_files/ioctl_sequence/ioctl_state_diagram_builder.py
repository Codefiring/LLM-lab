#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IOCTL 状态顺序图自动建图流水线（批量 10 条、局部推理 + 合并）

功能概览
- 读取包含 N 条（例如 126）ioctl 数据的 JSON/CSV：每条包含 {name, analysis}
- 采用“成组（每组10）局部推理 -> 结果合并”的策略，生成 DOT 时序/顺序图
- 通过“成对覆盖（pairwise coverage）”的 10 元组采样，避免组合爆炸（C(126,10) 不可行）
- 每个 10 元组调用 LLM：
    * 从分析文本中抽取【前置状态/执行条件】与【执行后状态影响】
    * 推理该 10 条 ioctl 之间的先后/使能关系
    * 输出：
        1) Graphviz DOT（仅包含本组）
        2) 同步输出结构化 JSON 边列表：[{src,dst,guard,effect,confidence}]
- 全局合并：
    * 融合多批次的边，聚合置信度，去重与标签合并
    * 生成最终 merged_graph.dot（可含环）

使用方法
1) 准备数据文件（任选其一）：
   - JSON：形如 [{"name":"IOCTL_X","analysis":"..."}, ...]
   - CSV：包含列 name, analysis

2) 准备 OpenAI API（可换成你使用的任何 LLM 提供商 API）：
   - 导出环境变量：OPENAI_API_KEY="sk-..."
   - 如需代理/自定义 base_url、模型名，请用命令行参数覆盖

3) 运行示例：
   python ioctl_state_diagram_builder.py \
       --input data/ioctls.json \
       --input-format json \
       --model gpt-4o-mini \
       --batch-size 10 \
       --out-dir outputs \
       --min-confidence 0.55

4) 输出：
   - outputs/local_graph_000.dot/json ... 每组的 DOT 和 边列表
   - outputs/merged_graph.dot 全量合并图（Graphviz DOT）
   - outputs/merged_edges.json 全量边（含聚合置信度与标签）

注意
- 本脚本默认采用“pairwise coverage”的 10 元组采样：
  * 覆盖所有 ioctl 两两组合至少一次，通常 ~O(N^2/45) 组即可（10 个节点内部有 C(10,2)=45 对）
  * 相比全组合/全排列，数量可控且能提供充分的局部语境给 LLM
- 如果你确实需要穷举或更强覆盖，请自担计算成本，调整 --sampler exhaustive（不建议）。

"""

from __future__ import annotations
import os
import sys
import json
import csv
import math
import argparse
import random
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Any, Optional, Set
from collections import defaultdict, Counter

# -----------------------------
# 数据结构
# -----------------------------

@dataclass
class IoctlItem:
    name: str
    analysis: str

@dataclass
class Edge:
    src: str
    dst: str
    guard: str
    effect: str
    confidence: float

@dataclass
class BatchResult:
    dot: str
    edges: List[Edge]

@dataclass
class MergeEdge:
    src: str
    dst: str
    labels: Counter  # key: (guard,effect) -> count
    confs: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        # 选择出现次数最多的标签作为主标签；同时保留最高置信度
        (ge, cnt) = self.labels.most_common(1)[0]
        guard, effect = ge
        avg_conf = sum(self.confs) / max(1, len(self.confs))
        max_conf = max(self.confs) if self.confs else 0.0
        return {
            "src": self.src,
            "dst": self.dst,
            "guard": guard,
            "effect": effect,
            "count": sum(self.labels.values()),
            "avg_confidence": round(avg_conf, 3),
            "max_confidence": round(max_conf, 3),
        }

# -----------------------------
# 工具函数：读取数据
# -----------------------------

def read_items(path: str, input_format: str) -> List[IoctlItem]:
    items: List[IoctlItem] = []
    if input_format == "json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for row in data:
            items.append(IoctlItem(name=str(row["name"]).strip(), analysis=str(row["analysis"]).strip()))
    elif input_format == "csv":
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                items.append(IoctlItem(name=str(row["name"]).strip(), analysis=str(row["analysis"]).strip()))
    else:
        raise ValueError("Unsupported input_format, use 'json' or 'csv'")
    # 去重（按 name 保留首个）
    seen = set()
    deduped: List[IoctlItem] = []
    for it in items:
        if it.name not in seen:
            seen.add(it.name)
            deduped.append(it)
    return deduped

# -----------------------------
# 10 元组采样：pairwise coverage（默认）
# -----------------------------

def build_pairwise_batches(n: int, batch_size: int, seed: int = 42) -> List[List[int]]:
    """
    返回索引批次列表，每批大小=batch_size，用于覆盖所有(i,j)对（i<j）。
    贪心构造：
      - 维护 uncovered 集合，包含所有 pairs
      - 反复挑选能覆盖最多剩余 pairs 的 10 元组
    复杂度可控，n=126 时实测可在几百批量级内覆盖所有 pairs。
    """
    assert batch_size >= 2
    rng = random.Random(seed)

    all_pairs = set()
    for i in range(n):
        for j in range(i+1, n):
            all_pairs.add((i, j))

    uncovered: Set[Tuple[int,int]] = set(all_pairs)
    batches: List[List[int]] = []

    # 预先随机排列元素，增加多样性
    order = list(range(n))
    rng.shuffle(order)

    # 辅助：计算某个集合内的 pairs 数
    def pair_count(idx_list: List[int]) -> int:
        c = 0
        L = len(idx_list)
        for a in range(L):
            for b in range(a+1, L):
                i, j = sorted((idx_list[a], idx_list[b]))
                if (i, j) in uncovered:
                    c += 1
        return c

    # 主循环
    while uncovered:
        # 选择当前剩余覆盖度最高的“种子”
        # 用一个启发式：挑选与 uncovered 连接度最大的点
        scores = Counter()  # idx -> uncovered pairs 数
        for (i, j) in list(uncovered)[: min(len(uncovered), 50000)]:
            scores[i] += 1
            scores[j] += 1
        seed_idx = max(scores, key=lambda k: scores[k]) if scores else order[0]

        current: List[int] = [seed_idx]
        cand = [x for x in order if x != seed_idx]

        # 逐个加入使 pair_count 增长最大的元素，直到 size=10
        while len(current) < batch_size and cand:
            best_add = None
            best_gain = -1
            for x in cand[:200]:  # 限制考察集合，提升速度
                gain = 0
                for y in current:
                    i, j = sorted((x, y))
                    if (i, j) in uncovered:
                        gain += 1
                if gain > best_gain:
                    best_gain = gain
                    best_add = x
            if best_add is None:
                # 若无增益，随机补齐
                best_add = cand[0]
            current.append(best_add)
            cand.remove(best_add)

        # 标记本批覆盖的 pairs 为已覆盖
        for a in range(len(current)):
            for b in range(a+1, len(current)):
                i, j = sorted((current[a], current[b]))
                if (i, j) in uncovered:
                    uncovered.remove((i, j))

        batches.append(current)

        # 停止条件（保险）：超过某个上限也停（避免极端长尾）
        if len(batches) > math.ceil(n * n / (batch_size * (batch_size - 1) / 2)) * 3:
            break

    return batches

# -----------------------------
# LLM 调用 & 提示词
# -----------------------------

OPENAI_IMPORT_OK = True
try:
    from openai import OpenAI
except Exception:
    OPENAI_IMPORT_OK = False

LLM_PROMPT_SYSTEM = (
    "你是资深的内核驱动与形式化建模工程师。现在给你一批 ioctl（每批 10 条），" 
    "每条包含分析文本，内容含：1) 正确执行所需的状态/前置条件；2) 执行后对驱动状态的影响。" 
    "请完成：\n"
    "(A) 仅基于这一批条目，推理这些 ioctl 在状态机中的可能先后/使能关系。\n"
    "    - 节点 = ioctl 名称。\n"
    "    - 当 A 的 effect 使 B 的前置条件满足（或更容易满足）时，连边 A->B。\n"
    "    - 当 A 的 effect 使 B 的前置条件失效、互斥或需要回滚时，可输出 B->A 或标注冲突（任选其一，但保持自洽）。\n"
    "    - 仅在分析文本能支撑时连边；若不确定可省略。\n"
    "(B) 输出 2 个产物：\n"
    "    1) 该批次的 Graphviz DOT（digraph，节点为 ioctl 名称，边 label 包含【Guard】和【Effect】摘要）；\n"
    "    2) 一份 JSON 边列表 edges=[{src,dst,guard,effect,confidence}]，confidence∈[0,1] 表示你对该边的把握。\n"
    "输出必须是 JSON 对象：{\"dot\": string, \"edges\": Edge[]}，不得包含其他文字。"
)

LLM_PROMPT_USER_TEMPLATE = (
    "以下是本批 ioctl（共 {k} 条）。每条给出 name 与 analysis：\n\n"
    "{items}\n\n"
    "请基于它们，按系统提示完成任务，严格输出 JSON。"
)

def format_batch_for_prompt(items: List[IoctlItem]) -> str:
    rows = []
    for it in items:
        rows.append({"name": it.name, "analysis": it.analysis})
    return json.dumps(rows, ensure_ascii=False, indent=2)


def call_llm(items: List[IoctlItem], model: str, base_url: Optional[str] = None) -> BatchResult:
    if not OPENAI_IMPORT_OK:
        raise RuntimeError("未安装 openai 包。请先 `pip install openai` 或将 --offline 设置为启用离线模式。")
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("未检测到 OPENAI_API_KEY 环境变量。")

    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    user_content = LLM_PROMPT_USER_TEMPLATE.format(k=len(items), items=format_batch_for_prompt(items))

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": LLM_PROMPT_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )

    txt = resp.choices[0].message.content
    try:
        data = json.loads(txt)
    except Exception as e:
        raise RuntimeError(f"LLM 返回不是合法 JSON：{e}\n原文：\n{txt}")

    dot = data.get("dot", "")
    raw_edges = data.get("edges", [])
    edges: List[Edge] = []
    for e in raw_edges:
        try:
            edges.append(Edge(
                src=str(e["src"]),
                dst=str(e["dst"]),
                guard=str(e.get("guard", "")),
                effect=str(e.get("effect", "")),
                confidence=float(e.get("confidence", 0.5)),
            ))
        except Exception:
            continue

    return BatchResult(dot=dot, edges=edges)

# -----------------------------
# 合并逻辑
# -----------------------------

def merge_edges(all_edges: List[Edge], min_conf: float = 0.55) -> Dict[Tuple[str,str], MergeEdge]:
    merged: Dict[Tuple[str,str], MergeEdge] = {}
    for e in all_edges:
        if e.confidence < min_conf:
            continue
        key = (e.src, e.dst)
        ge = (e.guard.strip(), e.effect.strip())
        if key not in merged:
            merged[key] = MergeEdge(src=e.src, dst=e.dst, labels=Counter())
        merged[key].labels[ge] += 1
        merged[key].confs.append(e.confidence)
    return merged


def merged_edges_to_dot(merged: Dict[Tuple[str,str], MergeEdge]) -> str:
    nodes = set()
    for (s, d), me in merged.items():
        nodes.add(s)
        nodes.add(d)

    lines = ["digraph IOCTL_Sequence {", "  rankdir=LR;", "  node [shape=box, fontname=\"Helvetica\"];", "  edge [fontname=\"Helvetica\"]; "]

    # 声明节点
    for n in sorted(nodes):
        lines.append(f"  \"{n}\";")

    # 声明边（用主标签）
    for (s, d), me in sorted(merged.items()):
        info = me.to_dict()
        label = f"Guard: {info['guard']}\nEffect: {info['effect']}\ncount={info['count']}, avgC={info['avg_confidence']}"
        lines.append(f"  \"{s}\" -> \"{d}\" [label=\"{label}\"];")

    lines.append("}")
    return "\n".join(lines)

# -----------------------------
# 主流程
# -----------------------------

def main():
    parser = argparse.ArgumentParser(description="IOCTL 状态顺序图自动建图流水线")
    parser.add_argument("--input", required=True, help="输入文件（json/csv）")
    parser.add_argument("--input-format", choices=["json", "csv"], default="json")
    parser.add_argument("--out-dir", default="outputs")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--sampler", choices=["pairwise", "sliding", "exhaustive"], default="pairwise",
                        help="组合采样策略（pairwise 推荐；sliding 为打乱后滑窗；exhaustive 极不建议）")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--base-url", default=None, help="可选，自定义 LLM API base_url")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-confidence", type=float, default=0.55)
    parser.add_argument("--max-batches", type=int, default=0, help="最多处理多少批（0=不限制）")
    parser.add_argument("--offline", action="store_true", help="离线模式：不调用 LLM，只生成空图用于流程验证")

    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    items = read_items(args.input, args.input_format)
    n = len(items)
    if n < args.batch_size:
        print(f"数据条目 {n} 少于 batch-size {args.batch_size}")
        sys.exit(1)

    # 构造批次索引
    if args.sampler == "pairwise":
        batches = build_pairwise_batches(n, args.batch_size, seed=args.seed)
    elif args.sampler == "sliding":
        order = list(range(n))
        random.Random(args.seed).shuffle(order)
        batches = [order[i:i+args.batch_size] for i in range(0, n, args.batch_size) if len(order[i:i+args.batch_size])==args.batch_size]
    else:
        # 极不建议：这里仅作占位，避免误用
        print("exhaustive 未实现（组合爆炸）。请使用 pairwise 或 sliding。")
        sys.exit(2)

    if args.max_batches and len(batches) > args.max_batches:
        batches = batches[: args.max_batches]

    print(f"将处理批次数：{len(batches)}，每批 {args.batch_size} 条。")

    all_edges: List[Edge] = []

    for bi, batch_idx in enumerate(batches):
        batch_items = [items[i] for i in batch_idx]

        if args.offline:
            # 离线模式：不调用 LLM，产出空图（用于打通流程）
            br = BatchResult(dot="digraph G{}", edges=[])
        else:
            br = call_llm(batch_items, model=args.model, base_url=args.base_url)

        # 保存本批次文件
        dot_path = os.path.join(args.out_dir, f"local_graph_{bi:03}.dot")
        json_path = os.path.join(args.out_dir, f"local_graph_{bi:03}.json")
        with open(dot_path, "w", encoding="utf-8") as f:
            f.write(br.dot.strip() + "\n")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump([e.__dict__ for e in br.edges], f, ensure_ascii=False, indent=2)

        all_edges.extend(br.edges)
        print(f"[batch {bi:03}] 保存 {dot_path}, 边数={len(br.edges)}")

    # 合并
    merged = merge_edges(all_edges, min_conf=args.min_confidence)

    merged_dot = merged_edges_to_dot(merged)
    merged_dot_path = os.path.join(args.out_dir, "merged_graph.dot")
    with open(merged_dot_path, "w", encoding="utf-8") as f:
        f.write(merged_dot)

    merged_edges_path = os.path.join(args.out_dir, "merged_edges.json")
    with open(merged_edges_path, "w", encoding="utf-8") as f:
        json.dump([me.to_dict() for me in merged.values()], f, ensure_ascii=False, indent=2)

    print(f"已生成合并图：{merged_dot_path} 与 {merged_edges_path}")


if __name__ == "__main__":
    main()
