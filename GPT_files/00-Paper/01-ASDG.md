非常好。以下是一段**符合 IEEE S&P 会议论文风格**、用**形式化符号与逻辑定义**精确描述 ASDG（*Abstract State Dependency Graph*）的章节草稿，可直接纳入你的论文中。文本在语义上保持你描述的全部细节，同时使用了集合论、映射与关系的形式化语言来定义节点、属性与边。

---

## III. Formal Definition of ASDG

We define the **Abstract State Dependency Graph (ASDG)** as a directed, attributed multigraph that captures both **syntactic relationships** and **semantic dependencies** among program entities in a given codebase.
Formally, we denote an ASDG as:

[
\mathcal{G} = (\mathcal{V}, \mathcal{E}, \mathcal{A})
]
where

* (\mathcal{V}) is the set of nodes (program facts),
* (\mathcal{E} \subseteq \mathcal{V} \times \mathcal{V}) is the set of directed edges, and
* (\mathcal{A}) is a collection of attribute functions that annotate nodes and edges with additional information.

---

### A. Node Definition

Each node (v \in \mathcal{V}) corresponds to a basic program entity, formally defined as:

[
\mathcal{V} = \mathcal{V}*{enum} \cup \mathcal{V}*{macro} \cup \mathcal{V}*{struct} \cup \mathcal{V}*{func}
]

where:

* (\mathcal{V}_{enum}) = set of enumeration constants,
* (\mathcal{V}_{macro}) = set of macro definitions,
* (\mathcal{V}_{struct}) = set of structure type definitions,
* (\mathcal{V}_{func}) = set of function definitions (including target APIs).

Each category of nodes has distinct attributes captured by an attribute function
(\alpha_v: \mathcal{V} \rightarrow \mathcal{A}_v), defined as follows:

1. **Enumeration constant node**
   For (v_e \in \mathcal{V}_{enum}):
   [
   \alpha_v(v_e) = { \texttt{name}(v_e), \texttt{value}(v_e) }
   ]

2. **Macro definition node**
   For (v_m \in \mathcal{V}_{macro}):
   [
   \alpha_v(v_m) = { \texttt{name}(v_m), \texttt{text}(v_m) }
   ]

3. **Structure definition node**
   For (v_s \in \mathcal{V}*{struct}):
   [
   \alpha_v(v_s) = { \texttt{name}(v_s), \texttt{definition}(v_s), \texttt{members}(v_s) }
   ]
   where each member (f_i \in \texttt{members}(v_s)) is represented as:
   [
   f_i = (\texttt{name}(f_i), \texttt{type}(f_i))
   ]
   If (\texttt{type}(f_i)) is itself a structure, we recursively include its definition:
   [
   f_i \in \mathcal{V}*{struct} \Rightarrow (v_s, f_i) \in \mathcal{E}_{nest}
   ]

4. **Function node**
   For (v_f \in \mathcal{V}_{func}),
   [
   \alpha_v(v_f) =
   \begin{cases}
   { \texttt{name}(v_f), \texttt{code}(v_f) }, & \text{if } v_f \text{ is not a target API}[4pt]
   {
   \texttt{name}(v_f),
   \texttt{code}(v_f),
   \texttt{headers}(v_f),
   \texttt{params}(v_f)
   }, & \text{if } v_f \text{ is a target API}
   \end{cases}
   ]

   Each parameter (p_j \in \texttt{params}(v_f)) has:
   [
   p_j = (\texttt{name}(p_j), \texttt{type}(p_j), \texttt{structInfo}(p_j))
   ]
   where (\texttt{structInfo}(p_j)) recursively records the member layout if (\texttt{type}(p_j)) is a struct.

---

### B. Edge Definition

Edges represent both **syntactic** and **semantic** relationships among entities.
We define the edge set as:
[
\mathcal{E} = \mathcal{E}*{call} \cup \mathcal{E}*{nest} \cup \mathcal{E}_{dep}
]

1. **Function-call edge**
   [
   (v_f^1, v_f^2) \in \mathcal{E}_{call} \iff v_f^1 \text{ calls } v_f^2
   ]

2. **Structure-nesting edge**
   [
   (v_s^1, v_s^2) \in \mathcal{E}_{nest} \iff v_s^1 \text{ contains } v_s^2 \text{ as a field type}
   ]

3. **API dependency edge**
   [
   (v_a^1, v_a^2) \in \mathcal{E}_{dep} \iff v_a^2 \text{ semantically depends on the state modified by } v_a^1
   ]
   Each dependency edge is annotated with attribute function:
   [
   \alpha_e(v_a^1, v_a^2) = { \texttt{stateDep}, \texttt{paramDep} }
   ]
   where:

   * (\texttt{stateDep}) represents the **state dependency** relation between APIs,
   * (\texttt{paramDep}) specifies which parameter(s) of (v_a^1) and (v_a^2) contribute to the dependency.

---

### C. Semantic Attributes

Beyond syntactic structure, ASDG captures semantic properties derived from program analysis:

1. **Value Range Annotation**
   For each struct member (f_i):
   [
   \texttt{value_range}(f_i) = [l_i, u_i] \subseteq \mathbb{Z}
   ]
   denoting the possible runtime range inferred from code or documentation.

2. **Usage Semantics**
   Each variable or member (f_i) may be semantically labeled by its operational role:
   [
   \texttt{usage}(f_i) \in { \texttt{Address}, \texttt{Buffer}, \texttt{Flag}, \texttt{Count}, \ldots }
   ]

3. **API State Dependency Attribute**
   For an edge ((v_a^1, v_a^2) \in \mathcal{E}_{dep}):
   [
   \texttt{stateDep}(v_a^1, v_a^2) = { (s_1, s_2) \mid s_1 \text{ produced by } v_a^1, s_2 \text{ consumed by } v_a^2 }
   ]

4. **Parameter Dependency Attribute**
   Similarly,
   [
   \texttt{paramDep}(v_a^1, v_a^2) = { (p_i, q_j) \mid \text{the value of } p_i \text{ in } v_a^1 \text{ affects } q_j \text{ in } v_a^2 }
   ]

---

### D. Summary

In summary, ASDG unifies **code-level facts** (functions, structs, macros, enums) with **semantic-level relations** (state and parameter dependencies) into a single formal structure:
[
\mathcal{G} = (\mathcal{V}, \mathcal{E}, \alpha_v, \alpha_e)
]
This representation enables both structural analysis and semantic reasoning over API behaviors, forming the foundation for subsequent **state dependency inference** and **API misuse detection**.

---

是否希望我下一步帮你补充一小节示例（如一个小的代码片段及其对应的ASDG公式化实例），用于放在该节末尾？这通常在IEEE S&P论文中能显著提高读者理解。


非常好。以下是一段**符合 IEEE S&P 会议论文风格**、用**形式化符号与逻辑定义**精确描述 ASDG（*Abstract State Dependency Graph*）的章节草稿，可直接纳入你的论文中。文本在语义上保持你描述的全部细节，同时使用了集合论、映射与关系的形式化语言来定义节点、属性与边。

---

## III. Formal Definition of ASDG

We define the **Abstract State Dependency Graph (ASDG)** as a directed, attributed multigraph that captures both **syntactic relationships** and **semantic dependencies** among program entities in a given codebase.
Formally, we denote an ASDG as:

[
\mathcal{G} = (\mathcal{V}, \mathcal{E}, \mathcal{A})
]
where

* (\mathcal{V}) is the set of nodes (program facts),
* (\mathcal{E} \subseteq \mathcal{V} \times \mathcal{V}) is the set of directed edges, and
* (\mathcal{A}) is a collection of attribute functions that annotate nodes and edges with additional information.

---

### A. Node Definition

Each node (v \in \mathcal{V}) corresponds to a basic program entity, formally defined as:

[
\mathcal{V} = \mathcal{V}*{enum} \cup \mathcal{V}*{macro} \cup \mathcal{V}*{struct} \cup \mathcal{V}*{func}
]

where:

* (\mathcal{V}_{enum}) = set of enumeration constants,
* (\mathcal{V}_{macro}) = set of macro definitions,
* (\mathcal{V}_{struct}) = set of structure type definitions,
* (\mathcal{V}_{func}) = set of function definitions (including target APIs).

Each category of nodes has distinct attributes captured by an attribute function
(\alpha_v: \mathcal{V} \rightarrow \mathcal{A}_v), defined as follows:

1. **Enumeration constant node**
   For (v_e \in \mathcal{V}_{enum}):
   [
   \alpha_v(v_e) = { \texttt{name}(v_e), \texttt{value}(v_e) }
   ]

2. **Macro definition node**
   For (v_m \in \mathcal{V}_{macro}):
   [
   \alpha_v(v_m) = { \texttt{name}(v_m), \texttt{text}(v_m) }
   ]

3. **Structure definition node**
   For (v_s \in \mathcal{V}*{struct}):
   [
   \alpha_v(v_s) = { \texttt{name}(v_s), \texttt{definition}(v_s), \texttt{members}(v_s) }
   ]
   where each member (f_i \in \texttt{members}(v_s)) is represented as:
   [
   f_i = (\texttt{name}(f_i), \texttt{type}(f_i))
   ]
   If (\texttt{type}(f_i)) is itself a structure, we recursively include its definition:
   [
   f_i \in \mathcal{V}*{struct} \Rightarrow (v_s, f_i) \in \mathcal{E}_{nest}
   ]

4. **Function node**
   For (v_f \in \mathcal{V}_{func}),
   [
   \alpha_v(v_f) =
   \begin{cases}
   { \texttt{name}(v_f), \texttt{code}(v_f) }, & \text{if } v_f \text{ is not a target API}[4pt]
   {
   \texttt{name}(v_f),
   \texttt{code}(v_f),
   \texttt{headers}(v_f),
   \texttt{params}(v_f)
   }, & \text{if } v_f \text{ is a target API}
   \end{cases}
   ]

   Each parameter (p_j \in \texttt{params}(v_f)) has:
   [
   p_j = (\texttt{name}(p_j), \texttt{type}(p_j), \texttt{structInfo}(p_j))
   ]
   where (\texttt{structInfo}(p_j)) recursively records the member layout if (\texttt{type}(p_j)) is a struct.

---

### B. Edge Definition

Edges represent both **syntactic** and **semantic** relationships among entities.
We define the edge set as:
[
\mathcal{E} = \mathcal{E}*{call} \cup \mathcal{E}*{nest} \cup \mathcal{E}_{dep}
]

1. **Function-call edge**
   [
   (v_f^1, v_f^2) \in \mathcal{E}_{call} \iff v_f^1 \text{ calls } v_f^2
   ]

2. **Structure-nesting edge**
   [
   (v_s^1, v_s^2) \in \mathcal{E}_{nest} \iff v_s^1 \text{ contains } v_s^2 \text{ as a field type}
   ]

3. **API dependency edge**
   [
   (v_a^1, v_a^2) \in \mathcal{E}_{dep} \iff v_a^2 \text{ semantically depends on the state modified by } v_a^1
   ]
   Each dependency edge is annotated with attribute function:
   [
   \alpha_e(v_a^1, v_a^2) = { \texttt{stateDep}, \texttt{paramDep} }
   ]
   where:

   * (\texttt{stateDep}) represents the **state dependency** relation between APIs,
   * (\texttt{paramDep}) specifies which parameter(s) of (v_a^1) and (v_a^2) contribute to the dependency.

---

### C. Semantic Attributes

Beyond syntactic structure, ASDG captures semantic properties derived from program analysis:

1. **Value Range Annotation**
   For each struct member (f_i):
   [
   \texttt{value_range}(f_i) = [l_i, u_i] \subseteq \mathbb{Z}
   ]
   denoting the possible runtime range inferred from code or documentation.

2. **Usage Semantics**
   Each variable or member (f_i) may be semantically labeled by its operational role:
   [
   \texttt{usage}(f_i) \in { \texttt{Address}, \texttt{Buffer}, \texttt{Flag}, \texttt{Count}, \ldots }
   ]

3. **API State Dependency Attribute**
   For an edge ((v_a^1, v_a^2) \in \mathcal{E}_{dep}):
   [
   \texttt{stateDep}(v_a^1, v_a^2) = { (s_1, s_2) \mid s_1 \text{ produced by } v_a^1, s_2 \text{ consumed by } v_a^2 }
   ]

4. **Parameter Dependency Attribute**
   Similarly,
   [
   \texttt{paramDep}(v_a^1, v_a^2) = { (p_i, q_j) \mid \text{the value of } p_i \text{ in } v_a^1 \text{ affects } q_j \text{ in } v_a^2 }
   ]

---

### D. Summary

In summary, ASDG unifies **code-level facts** (functions, structs, macros, enums) with **semantic-level relations** (state and parameter dependencies) into a single formal structure:
[
\mathcal{G} = (\mathcal{V}, \mathcal{E}, \alpha_v, \alpha_e)
]
This representation enables both structural analysis and semantic reasoning over API behaviors, forming the foundation for subsequent **state dependency inference** and **API misuse detection**.

---

是否希望我下一步帮你补充一小节示例（如一个小的代码片段及其对应的ASDG公式化实例），用于放在该节末尾？这通常在IEEE S&P论文中能显著提高读者理解。


