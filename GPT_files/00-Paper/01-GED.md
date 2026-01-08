```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GED evaluation for triple-graph prediction, ignoring entity names (col1/col3),
using parallel multi-restart + progressive timeouts to fully utilize many CPUs.

Input format per line (quotes required):
"S1", "operator1", "S2"

Usage:
  pip install networkx
  python ged_eval_parallel.py --gt ground_truth.txt --pred prediction.txt \
      --workers 128 --budget-sec 180 \
      --round "256,0.5" --round "256,1.5" --round "256,4.0"

Notes:
- Entities are anonymized for matching (names ignored). Operators are compared strictly.
- Each triple becomes: ent(head) -> op_node(label=operator) -> ent(tail)
- GED is NP-hard; this script uses repeated randomized restarts in parallel to get a strong approximation.
"""

import argparse
import json
import os
import random
import re
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

TRIPLE_RE = re.compile(r'"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"')


# ---------------------------
# Parsing
# ---------------------------
def read_triples(path: str) -> List[Tuple[str, str, str]]:
    triples: List[Tuple[str, str, str]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = TRIPLE_RE.search(line)
            if not m:
                raise ValueError(f"Parse error at {path}:{line_no}: {line}")
            h, op, t = m.group(1), m.group(2), m.group(3)
            triples.append((h, op, t))
    return triples


# ---------------------------
# Graph construction
# ---------------------------
def triples_to_bipartite_digraph(triples: List[Tuple[str, str, str]]) -> nx.DiGraph:
    """
    Convert (h, op, t) to a directed bipartite graph:
      ent(h) -> op_i(label=op) -> ent(t)
    """
    G = nx.DiGraph()

    def ent_id(name: str) -> str:
        # Keep names for identity inside one graph only; matching ignores them.
        return f"E::{name}"

    for i, (h, op, t) in enumerate(triples):
        h_id = ent_id(h)
        t_id = ent_id(t)
        op_id = f"OP::{i}"  # unique per triple (avoids parallel-edge issues)

        G.add_node(h_id, ntype="ent")
        G.add_node(t_id, ntype="ent")
        G.add_node(op_id, ntype="op", label=op)

        G.add_edge(h_id, op_id)
        G.add_edge(op_id, t_id)

    return G


# ---------------------------
# GED costs (ignoring entity names)
# ---------------------------
def node_subst_cost(a: Dict[str, Any], b: Dict[str, Any], op_mismatch_cost: float) -> float:
    ta, tb = a.get("ntype"), b.get("ntype")
    if ta != tb:
        return 1e9  # forbid ent <-> op mapping
    if ta == "ent":
        return 0.0  # ignore entity names entirely
    # op nodes: label must match, otherwise pay cost
    return 0.0 if a.get("label") == b.get("label") else float(op_mismatch_cost)


def node_del_cost(_: Dict[str, Any]) -> float:
    return 1.0


def node_ins_cost(_: Dict[str, Any]) -> float:
    return 1.0


def edge_subst_cost(_: Dict[str, Any], __: Dict[str, Any]) -> float:
    return 0.0


def edge_del_cost(_: Dict[str, Any]) -> float:
    return 1.0


def edge_ins_cost(_: Dict[str, Any]) -> float:
    return 1.0


# ---------------------------
# Parallel randomized GED
# ---------------------------
def _random_relabel_graph(G: nx.DiGraph, seed: int) -> nx.DiGraph:
    """Randomly relabel node ids to perturb GED search path; keep attributes."""
    rng = random.Random(seed)
    nodes = list(G.nodes())
    rng.shuffle(nodes)
    mapping = {old: f"R::{i}" for i, old in enumerate(nodes)}
    return nx.relabel_nodes(G, mapping, copy=True)


def _ged_once(payload: Tuple[nx.DiGraph, nx.DiGraph, int, float, float]) -> float:
    """
    One GED attempt in a worker process.
    payload: (G1, G2, seed, timeout, op_mismatch_cost)
    """
    G1, G2, seed, timeout, op_mismatch_cost = payload
    H1 = _random_relabel_graph(G1, seed)
    H2 = _random_relabel_graph(G2, seed ^ 0x9E3779B1)

    it = nx.algorithms.similarity.optimize_graph_edit_distance(
        H1,
        H2,
        node_subst_cost=lambda a, b: node_subst_cost(a, b, op_mismatch_cost),
        node_del_cost=node_del_cost,
        node_ins_cost=node_ins_cost,
        edge_subst_cost=edge_subst_cost,
        edge_del_cost=edge_del_cost,
        edge_ins_cost=edge_ins_cost,
        timeout=timeout,
    )

    best = None
    try:
        for v in it:
            best = v
    except Exception:
        pass

    return float(best) if best is not None else float("inf")


def parallel_ged_progressive(
    G1: nx.DiGraph,
    G2: nx.DiGraph,
    workers: int,
    rounds: List[Tuple[int, float]],
    budget_sec: float,
    op_mismatch_cost: float,
) -> Tuple[float, Dict[str, Any]]:
    """
    Multi-round progressive deepening:
      rounds = [(restarts, per_try_timeout), ...]
    Runs restarts in parallel, updates best, early-stops on 0 or budget.
    """
    start = time.time()
    best = float("inf")
    stats = {
        "workers": workers,
        "rounds": [{"restarts": r, "timeout": t} for (r, t) in rounds],
        "attempts_scheduled": 0,
        "attempts_completed": 0,
        "early_stop_zero": False,
        "time_sec": None,
    }

    with ProcessPoolExecutor(max_workers=workers) as ex:
        for (restarts, per_try_timeout) in rounds:
            if time.time() - start >= budget_sec:
                break
            if best == 0.0:
                stats["early_stop_zero"] = True
                break

            base_seed = (int(time.time() * 1000) ^ os.getpid()) & 0x7FFFFFFF
            tasks = [
                (G1, G2, base_seed + i * 9973, float(per_try_timeout), float(op_mismatch_cost))
                for i in range(restarts)
            ]
            stats["attempts_scheduled"] += len(tasks)
            futures = [ex.submit(_ged_once, t) for t in tasks]

            for f in as_completed(futures):
                stats["attempts_completed"] += 1
                v = f.result()
                if v < best:
                    best = v
                    if best == 0.0:
                        stats["early_stop_zero"] = True
                        break
                if time.time() - start >= budget_sec:
                    break

    stats["time_sec"] = round(time.time() - start, 4)
    return best, stats


# ---------------------------
# Scoring / normalization
# ---------------------------
def normalized_score_from_ged(ged: float, G1: nx.DiGraph, G2: nx.DiGraph) -> float:
    denom = (G1.number_of_nodes() + G1.number_of_edges() + G2.number_of_nodes() + G2.number_of_edges())
    if denom <= 0:
        return 1.0
    return max(0.0, 1.0 - (ged / denom))


# ---------------------------
# CLI
# ---------------------------
def parse_rounds(round_args: List[str]) -> List[Tuple[int, float]]:
    """
    --round "256,0.5" can be repeated.
    """
    out: List[Tuple[int, float]] = []
    for s in round_args:
        parts = [p.strip() for p in s.split(",")]
        if len(parts) != 2:
            raise ValueError(f"Invalid --round '{s}'. Use 'restarts,timeout' e.g. '256,1.5'")
        r = int(parts[0])
        t = float(parts[1])
        if r <= 0 or t <= 0:
            raise ValueError(f"Invalid --round '{s}': restarts/timeout must be > 0")
        out.append((r, t))
    return out


def main():
    ap = argparse.ArgumentParser(description="Parallel GED evaluator ignoring entity names (col1/col3).")
    ap.add_argument("--gt", required=True, help="Ground truth txt file")
    ap.add_argument("--pred", required=True, help="Prediction txt file")
    ap.add_argument("--workers", type=int, default=128, help="Process workers (e.g., 128 or 192)")
    ap.add_argument("--budget-sec", type=float, default=180.0, help="Total time budget in seconds (minutes-level)")
    ap.add_argument(
        "--round",
        action="append",
        default=None,
        help="One round as 'restarts,timeout'. Repeatable. Default: 256,0.5 256,1.5 256,4.0",
    )
    ap.add_argument(
        "--op-mismatch-cost",
        type=float,
        default=1.0,
        help="Cost when operator labels differ (increase to penalize operator mistakes more)",
    )
    ap.add_argument("--json", action="store_true", help="Output JSON only")
    args = ap.parse_args()

    rounds = parse_rounds(args.round) if args.round else [(256, 0.5), (256, 1.5), (256, 4.0)]
    workers = max(1, int(args.workers))
    budget_sec = float(args.budget_sec)

    gt_triples = read_triples(args.gt)
    pr_triples = read_triples(args.pred)
    G1 = triples_to_bipartite_digraph(gt_triples)
    G2 = triples_to_bipartite_digraph(pr_triples)

    ged, stats = parallel_ged_progressive(
        G1, G2,
        workers=workers,
        rounds=rounds,
        budget_sec=budget_sec,
        op_mismatch_cost=float(args.op_mismatch_cost),
    )
    score = normalized_score_from_ged(ged, G1, G2)

    result = {
        "ged": float(ged),
        "normalized_score": float(score),
        "gt": {"triples": len(gt_triples), "nodes": G1.number_of_nodes(), "edges": G1.number_of_edges()},
        "pred": {"triples": len(pr_triples), "nodes": G2.number_of_nodes(), "edges": G2.number_of_edges()},
        "config": {
            "workers": workers,
            "budget_sec": budget_sec,
            "rounds": [{"restarts": r, "timeout": t} for r, t in rounds],
            "op_mismatch_cost": float(args.op_mismatch_cost),
        },
        "run_stats": stats,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("=== GED Evaluation (entity names ignored) ===")
        print(f"GED distance         : {result['ged']}")
        print(f"Normalized score     : {result['normalized_score']:.6f}")
        print(f"GT   triples/nodes/edges: {result['gt']['triples']}/{result['gt']['nodes']}/{result['gt']['edges']}")
        print(f"PRED triples/nodes/edges: {result['pred']['triples']}/{result['pred']['nodes']}/{result['pred']['edges']}")
        print(f"Workers              : {workers}")
        print(f"Budget (sec)         : {budget_sec}")
        print(f"Rounds               : {', '.join([f'{r}x@{t}s' for r, t in rounds])}")
        print(f"Op mismatch cost     : {args.op_mismatch_cost}")
        print(f"Attempts completed   : {stats['attempts_completed']} / {stats['attempts_scheduled']}")
        print(f"Time used (sec)      : {stats['time_sec']}")
        print("\nJSON:")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

### 你直接这样用（针对你：50 triples、单对图、分钟级）

```bash
pip install networkx

# 建议先用 128 workers（通常比 192 更稳、更少调度开销）
python ged_eval_parallel.py --gt gt.txt --pred pred.txt --workers 128 --budget-sec 180 \
  --round "256,0.5" --round "256,1.5" --round "256,4.0"
```

### 小建议（可选）

* 如果你更在意 operator 的准确性：把 `--op-mismatch-cost` 调大，例如：

```bash
python ged_eval_parallel.py --gt gt.txt --pred pred.txt --workers 128 --budget-sec 180 \
  --op-mismatch-cost 3.0
```

如果你是在集群（SLURM）上跑、192 个 CPU node 是“多节点”而不是单机多核，也可以告诉我你们的调度方式（比如每节点多少核），我给你一个“多节点并行重启”的作业脚本模板（每节点跑一批 restarts，最终汇总取最小 GED）。
