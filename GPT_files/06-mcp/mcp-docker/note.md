从 tasks.md 的依赖结构看，最干净的切法是**按平面切，不按阶段切**——阶段切（A 做 1–4、B 做 5–8）会让 B 前两周没镜像可跑，白等。

## 切法：构建面 / 运行面

**第 0 周，一个人先把地基一次性做完**（另一人同期写契约测试与 fake）：

- 1.1 工程骨架、1.3 领域类型、1.4 `startCommand` 归一化、2.1 SQLite 仓储
- 这四项是两条线的共同上游，**必须单人落笔、一周内冻结**，之后只加不改。

**然后分两条线：**

| | A：构建面 | B：运行 + 数据面 |
| --- | --- | --- |
| 任务 | 2.2–2.5 源码暂存、3.1–3.7 分析 Agent、4.1–4.7 BuildKit | 5.1–5.7 Docker 生命周期、7.1–7.8 鉴权、8.1–8.6 stdio 桥接 |
| 能力规格 | `environment-build-agent`、`server-configuration` | `isolated-server-runtime`、`mcp-transport-proxy`、`mcp-authorization` |
| 管理 API | 6.2 上传、6.3 build/rebuild、6.4 构建日志 | 6.1 CRUD、6.5 生命周期、6.6 运行日志 |
| 部署 | 9.1 的 BuildKit + 包镜像源 | 9.1 的 Docker + 控制面 |

## 两条线之间只有一个契约

B 需要 A 的东西，压缩成一个结构就够了：

```
ImageArtifact { imageDigest, effectiveStartCommand[], workdir, readiness, buildPlanRevision }
```

**第 0 周就把这个类型和 BuildPlan schema（3.1）定死**，B 用一个手工构造的 fixture 镜像（比如预先 `docker build` 好的一个最小 stdio echo server）直接跑 5.x 和 8.x，完全不依赖 A 的进度。A 那边则用假的 runtime controller 断言"产出 digest 即完工"。等双方各自绿了再接真链路——通常只花一两天。

反向依赖只有一条：A 的 4.5 验证容器要用 B 的 Docker adapter（5.1）。让 B 优先交付 5.1，或者 A 先用 docker CLI 起临时容器顶着，后面换实现。

## 合并与冲突

- 规格文件天然按能力分目录，各自只改自己那几个 `specs/*/spec.md`，几乎不撞车。
- **`tasks.md` 是唯一的共享文件**，两人勾选框会反复冲突。约定：只改自己那几节、小步提交、冲突一律 `--ours` 各留各的行。
- 也可以把 `mcp-docker` 拆成两个 OpenSpec change 各自独立 archive，但 proposal/design 要复制一份、共享的地基任务不好归属——两人规模不值得，建议仍用单 change。

## 同步点

只设三个硬同步，其余各跑各的：

1. **第 0 周末**：领域类型、BuildPlan schema、`ImageArtifact` 契约冻结。
2. **中段**：真实镜像首次喂给真实 runtime（A 的 4.x 接 B 的 5.x），这里会暴露 `startCommand` 在镜像里到底可不可执行——4.5 的探针就是为这个存在的。
3. **9.3 端到端冒烟**：两人一起做，Python 和 Node 各一个 stdio 服务从上传跑到 `/mcp`。

## 工期

按之前的估算，全量 12–16 周单人 → 两人并行约 **7–9 周**；只做第一条可用链路（不含 8.7–8.9 两档 HTTP）约 **4–5 周**。压不到一半，因为地基周是串行的，且 7.x 鉴权和 8.x 桥接都在 B 身上——如果中段发现 B 超载，把 7.1–7.4（策略类型、JWKS 校验、元数据端点）这段挪给 A，它对 stdio 桥接的耦合最浅。

前提不变：`design.md` 末尾那三个 Open Question（基础镜像/包源白名单、LLM 供应商、OAuth 签发方）分别卡着 A 的 4.3、A 的 3.5、B 的 7.2，**开工前就要有答案**，否则两条线都会在第二周撞墙。