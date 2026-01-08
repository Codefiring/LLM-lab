import re
import networkx as nx
from typing import List, Tuple, Dict, Any, Optional

TRIPLE_RE = re.compile(r'"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"')

def read_triples(path: str) -> List[Tuple[str, str, str]]:
    triples = []
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

def triples_to_bipartite_digraph(triples: List[Tuple[str, str, str]]) -> nx.DiGraph:
    """
    将 (h, op, t) 转换为：
      h(ent) -> edge_i(op) -> t(ent)
    - ent 节点：不关心名字（但为了构图仍需要唯一 id）
    - op 节点：关心 operator 标签
    """
    G = nx.DiGraph()

    # 用 "E::<name>" 只是为了让同名实体在同一张图里仍是同一个点
    # 但匹配阶段我们会忽略这个 name
    def ent_id(name: str) -> str:
        return f"E::{name}"

    for i, (h, op, t) in enumerate(triples):
        h_id = ent_id(h)
        t_id = ent_id(t)
        op_id = f"OP::{i}"  # 每条三元组一个独立 op 节点，避免并行边问题

        G.add_node(h_id, ntype="ent")
        G.add_node(t_id, ntype="ent")
        G.add_node(op_id, ntype="op", label=op)

        G.add_edge(h_id, op_id)
        G.add_edge(op_id, t_id)

    return G

# ---------- GED 成本函数（忽略实体名，严格比较 operator） ----------

def node_subst_cost(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    ta, tb = a.get("ntype"), b.get("ntype")
    if ta != tb:
        return 1e9  # 强制不允许 ent <-> op 互换
    if ta == "ent":
        return 0.0   # 忽略实体名：ent 之间替换无成本
    # op 节点：label 不同就算一次替换
    return 0.0 if a.get("label") == b.get("label") else 1.0

def node_del_cost(a: Dict[str, Any]) -> float:
    # 删除一个节点的代价
    return 1.0

def node_ins_cost(b: Dict[str, Any]) -> float:
    # 插入一个节点的代价
    return 1.0

def edge_subst_cost(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    # 在我们构造里边没有 label；通常保持 0 即可
    return 0.0

def edge_del_cost(a: Dict[str, Any]) -> float:
    return 1.0

def edge_ins_cost(b: Dict[str, Any]) -> float:
    return 1.0

def graph_edit_distance_ignored_entities(gt_path: str, pred_path: str, timeout: Optional[float] = 3.0):
    gt_triples = read_triples(gt_path)
    pr_triples = read_triples(pred_path)

    G1 = triples_to_bipartite_digraph(gt_triples)
    G2 = triples_to_bipartite_digraph(pr_triples)

    # NetworkX 的 GED 可能返回一个生成器（不断改进的上界），这里取最小值
    ged_iter = nx.algorithms.similarity.optimize_graph_edit_distance(
        G1, G2,
        node_subst_cost=node_subst_cost,
        node_del_cost=node_del_cost,
        node_ins_cost=node_ins_cost,
        edge_subst_cost=edge_subst_cost,
        edge_del_cost=edge_del_cost,
        edge_ins_cost=edge_ins_cost,
        timeout=timeout,
    )

    best = None
    try:
        for v in ged_iter:
            best = v
    except Exception:
        pass

    if best is None:
        raise RuntimeError("GED computation did not return a result (try increasing timeout).")

    # 一个简单的归一化分数：1 - dist / (|V1|+|E1|+|V2|+|E2|)
    denom = (G1.number_of_nodes() + G1.number_of_edges() + G2.number_of_nodes() + G2.number_of_edges())
    score = 1.0 - (best / denom if denom > 0 else 0.0)

    return {
        "ged": float(best),
        "normalized_score": float(score),
        "gt": {"nodes": G1.number_of_nodes(), "edges": G1.number_of_edges(), "triples": len(gt_triples)},
        "pred": {"nodes": G2.number_of_nodes(), "edges": G2.number_of_edges(), "triples": len(pr_triples)},
    }

if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", required=True, help="ground truth txt")
    ap.add_argument("--pred", required=True, help="prediction txt")
    ap.add_argument("--timeout", type=float, default=3.0, help="GED timeout seconds (increase if needed)")
    args = ap.parse_args()

    res = graph_edit_distance_ignored_entities(args.gt, args.pred, timeout=args.timeout)
    print(json.dumps(res, ensure_ascii=False, indent=2))
