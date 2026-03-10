下面我按 **“经典基础 / 理论文章 / 近年LLM多智能体”** 三层给你整理一份可直接入门的文献清单。Multi-Agent System（MAS）通常研究的是：多个自治体在共享环境中如何 **表示目标、协调、通信、协作、竞争、学习与组织**。这一领域最早源自 Distributed AI，后来又与博弈论、控制、优化、强化学习和近年的 LLM Agent 体系结合起来。([cs.ox.ac.uk][1])

## 1）经典奠基论文 / 入门必读

**1. Wooldridge & Jennings (1995), *Intelligent Agents: Theory and Practice***
这是 Agent/MAS 领域最经典的入门文之一，回答了“什么是 agent”“自治、反应性、主动性、社会性分别是什么”，适合当综述开篇引用。([cs.ox.ac.uk][1])

**2. Shoham (1993), *Agent-Oriented Programming***
这是 AOP（面向 Agent 编程）的代表作，把 agent 作为带有“belief / commitment”等心理状态的计算实体来建模，对后续 MAS 编程范式影响很大。([ACM Digital Library][2])

**3. Wooldridge, *An Introduction to MultiAgent Systems*（教材）**
虽然这是教材不是论文，但它几乎是 MAS 最标准的系统化入口，覆盖 agent architecture、communication、coordination、negotiation、organization、game theory 等核心主题。([Wiley][3])

**4. Stone & Veloso (1997/1999 前后), *Multiagent Systems: A Survey from a Machine Learning Perspective***
这篇从机器学习视角理解 MAS，连接了传统分布式 AI 与后来的 multi-agent learning / MARL。([cs.cmu.edu][4])

## 2）MAS 理论文章：做文献综述最值得引用的方向

### A. Agent 理性与 BDI 理论

**5. Rao & Georgeff (1995), *BDI Agents: From Theory to Practice***
BDI（Belief-Desire-Intention）是 MAS 中最有代表性的 agent 理性模型之一。这篇论文把形式化 BDI 理论和工程实现联系起来，是“智能体内部决策模型”方向的核心文献。([AAAI][5])

### B. 协作与团队理论

**6. Cohen & Levesque (1991), *Teamwork***
这是 joint intention / team commitment 理论的经典来源之一，讨论“多个 agent 真正一起做一件事”到底意味着什么，适合写 MAS 协作理论基础。([PhilPapers][6])

**7. Jennings (1993), *Commitments and Conventions: The Foundation of Coordination in Multi-Agent Systems***
这篇论文把“承诺（commitment）与约定（convention）”作为协调基础，是 coordination 理论的经典文献。([Cambridge University Press & Assessment][7])

**8. Grosz & Kraus (1996), *Collaborative Plans for Complex Group Action***
SharedPlans 理论代表作，重点讨论复杂群体行动中的计划共享、角色分配和协同执行。写“协作规划”时非常值得引用。([科学直通车][8])

**9. Pynadath & Tambe (2002), *The Communicative Multiagent Team Decision Problem***
这篇论文把团队协作、通信代价和决策质量统一到 COM-MTDP 框架里，是把团队理论推向可计算分析的重要工作。([cs.cmu.edu][9])

### C. 博弈论 / 机制设计 / 多主体决策

**10. Paccagnan et al. (2022), *Utility and Mechanism Design in Multi-Agent Systems***
如果你想从“激励机制、效率、博弈、价格机制”去理解 MAS，这是非常好的理论综述，说明 game theory 如何进入 MAS 协调问题。([科学直通车][10])

**11. Yi et al. (2022), *A Survey on Noncooperative Games and Distributed Nash Equilibrium Seeking***
偏非合作博弈和分布式纳什均衡求解，适合研究竞争型 MAS 或分布式控制中的策略互动。([SciOpen][11])

### D. 分布式约束优化 / 资源分配

**12. Fioretto, Pontelli & Yeoh (2016/2018), *Distributed Constraint Optimization Problems and Applications: A Survey***
DCOP 是 MAS 里很经典的一条理论与算法路线，特别适合任务分配、调度、传感器网络、资源优化。([arXiv][12])

**13. Doostmohammadian et al. (2025), *Survey of Distributed Algorithms for Resource Allocation over Multi-Agent Systems***
如果你更关心资源分配、分布式调度、协同优化，这篇更贴近现代工程问题。([科学直通车][13])

### E. 共识控制 / 分布式优化

**14. Amirkhani et al. (2022), *Consensus in Multi-Agent Systems: A Review***
“共识（consensus）”是控制论 MAS 的核心主题，广泛用于机器人编队、车联网、无人机集群。([ACM Digital Library][14])

**15. Yang et al. (2019), *A Survey of Distributed Optimization***
这篇是理解“多智能体如何用局部信息求全局最优”的高质量综述，连接 MAS、优化与控制。([OSTI][15])

## 3）MAS 综述类文章

**16. Dorri, Kanhere & Jurdak (2018), *Multi-Agent Systems: A Survey***
比较适合快速扫全景：定义、特征、应用、通信、挑战、评估都有覆盖。([ResearchGate][16])

**17. Vlassis, *Multiagent Systems and Distributed AI***
更像一本系统性讲义/小书，适合从 Distributed AI 脉络理解 MAS。([jmvidal.cse.sc.edu][17])

## 4）近年热点：LLM-based Multi-Agent System

如果你说的 “multi agent system” 是想研究现在很火的 **LLM 多智能体 / agentic AI**，那下面这些更关键。

**18. Guo et al. (2024), *Large Language Model based Multi-Agents: A Survey of Progress and Challenges***
这是目前最常被提到的 LLM-MAS 综述之一，讨论 agent profile、communication、tool use、memory、cooperation、evaluation 等。([arXiv][18])

**19. Li et al. (2024), *A Survey on LLM-based Multi-Agent Systems***
这篇把 LLM-MAS 抽象成 profile、perception、self-action、mutual interaction、evolution 五部分，框架化程度很高，适合拿来搭综述结构。([Springer][19])

**20. Tran et al. (2025), *Multi-Agent Collaboration Mechanisms: A Survey of LLMs***
更聚焦“协作机制”本身，适合研究多 agent 分工、通信协议、协调策略、角色设计。([arXiv][20])

**21. Anthropic (2025), *How We Built Our Multi-Agent Research System***
这不是学术论文，但对工程落地很有价值，展示了现实中如何把规划 agent、并行检索 agent、汇总 agent 组织起来。做系统设计时值得参考。([Anthropic][21])

## 5）如果你想研究“学习型”多智能体：MARL 方向

**22. Huh et al. (2023), *Multi-agent Reinforcement Learning***
这篇从 game theory 与 machine learning 的联系讲 MARL，适合做理论过渡。([arXiv][22])

**23. Ning & Xie (2024), *A Survey on Multi-Agent Reinforcement Learning and Its Application***
较新的 MARL 综述，覆盖挑战、应用与方法谱系，比较适合当现状综述引用。([科学直通车][23])

## 6）你可以怎么组织自己的综述

如果你要写论文/报告，我建议按这条主线展开：

1. **定义层**：什么是 agent，什么是 MAS
   先引 Wooldridge & Jennings、Shoham。([cs.ox.ac.uk][1])

2. **内部模型层**：agent 如何决策
   引 BDI（Rao & Georgeff）。([AAAI][5])

3. **交互层**：agent 如何协调与协作
   引 Cohen & Levesque、Jennings、Grosz & Kraus、Pynadath。([PhilPapers][6])

4. **优化层**：如何实现全局协同
   引 DCOP、mechanism design、consensus、distributed optimization。([arXiv][12])

5. **学习层**：如何让多 agent 通过数据/环境学习
   引 MARL 综述。([arXiv][22])

6. **现代演化层**：LLM-based MAS
   引 2024–2025 的 survey。([arXiv][18])

## 7）给你的精简“必读 10 篇”

如果你时间有限，先读这 10 篇最划算：

1. Wooldridge & Jennings, 1995 — *Intelligent Agents: Theory and Practice* ([cs.ox.ac.uk][1])
2. Shoham, 1993 — *Agent-Oriented Programming* ([ACM Digital Library][2])
3. Rao & Georgeff, 1995 — *BDI Agents: From Theory to Practice* ([AAAI][5])
4. Cohen & Levesque, 1991 — *Teamwork* ([PhilPapers][6])
5. Jennings, 1993 — *Commitments and Conventions* ([Cambridge University Press & Assessment][7])
6. Grosz & Kraus, 1996 — *Collaborative Plans for Complex Group Action* ([Bar-Ilan University][24])
7. Fioretto et al., 2016/2018 — *DCOP Survey* ([arXiv][12])
8. Amirkhani et al., 2022 — *Consensus in Multi-Agent Systems: A Review* ([ACM Digital Library][14])
9. Guo et al., 2024 — *Large Language Model based Multi-Agents: A Survey* ([arXiv][18])
10. Li et al., 2024 — *A Survey on LLM-based Multi-Agent Systems* ([Springer][19])

如果你愿意，我下一条可以继续帮你整理成一份 **按研究主题分类的中英对照参考文献表**，或者直接给你一版 **适合写综述/开题报告的 related work 结构**。

[1]: https://www.cs.ox.ac.uk/people/michael.wooldridge/pubs/ker95.pdf?utm_source=chatgpt.com "Intelligent agents: theory and practice"
[2]: https://dl.acm.org/doi/10.1016/0004-3702%2893%2990034-9?utm_source=chatgpt.com "Agent-oriented programming | Artificial Intelligence"
[3]: https://www.wiley.com/en-us/An%2BIntroduction%2Bto%2BMultiAgent%2BSystems%2C%2B2nd%2BEdition-p-9780470519462?utm_source=chatgpt.com "An Introduction to MultiAgent Systems, 2nd Edition"
[4]: https://www.cs.cmu.edu/afs/cs/usr/pstone/public/papers/96ieee-survey/survey.ps.Z?utm_source=chatgpt.com "Multiagent Systems: A Survey from a Machine Learning ..."
[5]: https://cdn.aaai.org/ICMAS/1995/ICMAS95-042.pdf?utm_source=chatgpt.com "BDI Agents: From Theory to Practice"
[6]: https://philpapers.org/rec/COHT?utm_source=chatgpt.com "Philip R. Cohen & Hector J. Levesque, Teamwork"
[7]: https://www.cambridge.org/core/journals/knowledge-engineering-review/article/commitments-and-conventions-the-foundation-of-coordination-in-multiagent-systems/0413A9561EBA36994A0C465F6A37436F?utm_source=chatgpt.com "The foundation of coordination in multi-agent systems"
[8]: https://www.sciencedirect.com/science/article/pii/0004370295001034?utm_source=chatgpt.com "Collaborative plans for complex group action"
[9]: https://www.cs.cmu.edu/afs/cs/project/jair/pub/volume16/pynadath02a-html/index.html?utm_source=chatgpt.com "The Communicative Multiagent Team Decision Problem"
[10]: https://www.sciencedirect.com/science/article/pii/S1367578822000062?utm_source=chatgpt.com "Utility and mechanism design in multi-agent systems"
[11]: https://www.sciopen.com/article/10.26599/AIR.2022.9150002?utm_source=chatgpt.com "A Survey on Noncooperative Games and Distributed Nash ..."
[12]: https://arxiv.org/abs/1602.06347?utm_source=chatgpt.com "Distributed Constraint Optimization Problems and Applications: A Survey"
[13]: https://www.sciencedirect.com/science/article/abs/pii/S1367578824000518?utm_source=chatgpt.com "Survey of distributed algorithms for resource allocation ..."
[14]: https://dl.acm.org/doi/abs/10.1007/s10462-021-10097-x?utm_source=chatgpt.com "Consensus in multi-agent systems: a review"
[15]: https://www.osti.gov/servlets/purl/1515654?utm_source=chatgpt.com "A survey of distributed optimization"
[16]: https://www.researchgate.net/publication/324847369_Multi-Agent_Systems_A_survey?utm_source=chatgpt.com "(PDF) Multi-Agent Systems: A survey"
[17]: https://jmvidal.cse.sc.edu/library/vlassis03a.pdf?utm_source=chatgpt.com "Multiagent Systems and Distributed AI"
[18]: https://arxiv.org/abs/2402.01680?utm_source=chatgpt.com "[2402.01680] Large Language Model based Multi-Agents"
[19]: https://link.springer.com/article/10.1007/s44336-024-00009-2?utm_source=chatgpt.com "A survey on LLM-based multi-agent systems - Springer Nature"
[20]: https://arxiv.org/abs/2501.06322?utm_source=chatgpt.com "Multi-Agent Collaboration Mechanisms: A Survey of LLMs"
[21]: https://www.anthropic.com/engineering/multi-agent-research-system?utm_source=chatgpt.com "How we built our multi-agent research system"
[22]: https://arxiv.org/abs/2312.10256?utm_source=chatgpt.com "[2312.10256] Multi-agent Reinforcement Learning"
[23]: https://www.sciencedirect.com/science/article/pii/S2949855424000042?utm_source=chatgpt.com "A survey on multi-agent reinforcement learning and its ..."
[24]: https://cris.biu.ac.il/en/publications/collaborative-plans-for-complex-group-action-5/?utm_source=chatgpt.com "Collaborative plans for complex group action"
