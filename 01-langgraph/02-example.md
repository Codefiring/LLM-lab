下面给你一个**可直接运行的完整示例**：
👉 使用 **LangGraph v1.0 + OpenAI（gpt-4o）+ 工具调用 + ReAct Agent 风格**。
代码用英文方便你复制，注释我用中文讲清楚。

---

## 0. 安装依赖

```bash
pip install "langgraph>=1.0.0" "langchain-openai>=0.1.0" "langchain-core>=0.3.0"
```

---

## 1. 准备环境变量

```bash
export OPENAI_API_KEY="你的 OpenAI Key"
```

---

## 2. 定义几个简单工具（Tools）

我们做 2 个示例工具：

* `get_weather`：根据城市返回假天气（示例用）
* `calculate`：执行一个简单的算式

```python
from typing import TypedDict, Annotated, Literal
from pydantic import BaseModel, Field
import operator
import math
```

```python
# 用 Pydantic 定义工具的入参 schema，让 LLM 能正确调用

class GetWeatherInput(BaseModel):
    city: str = Field(..., description="要查询天气的城市名称，例如 '北京'、'上海'")

def get_weather(city: str) -> str:
    # 这里为了示例写死，你可以改成真实 API
    fake_data = {
        "北京": "晴，18~26℃",
        "上海": "多云，20~28℃",
        "深圳": "雷阵雨，25~31℃",
    }
    return fake_data.get(city, f"{city} 的天气数据暂时不可用，假装是晴天 22℃")


class CalculateInput(BaseModel):
    expression: str = Field(
        ...,
        description="一个简单的数学表达式，比如 '2 + 3 * 4'，注意只允许数字和 + - * / () 符号"
    )

def calculate(expression: str) -> str:
    # 非安全 eval，仅示例，生产环境请改为安全解析
    try:
        # 这里只做非常简单的过滤
        allowed_chars = set("0123456789+-*/(). ")
        if not set(expression) <= allowed_chars:
            return "表达式中包含非法字符"
        result = eval(expression)
        return f"{expression} = {result}"
    except Exception as e:
        return f"计算失败: {str(e)}"
```

---

## 3. 用 OpenAI 模型 + Tools 构建 ReAct Agent（核心）

这里用 LangGraph 的预构建方法 **`create_react_agent`**，让它自动做 ReAct：

* 解析用户问题
* 判断是否要调用工具
* 解析工具结果
* 给出最终回答

```python
from langchain_openai import ChatOpenAI
from langchain_core.tools import Tool
from langgraph.prebuilt import create_react_agent
```

```python
# 1. 定义 LLM（OpenAI）
llm = ChatOpenAI(
    model="gpt-4o",          # 也可以用 gpt-4.1 / gpt-4o-mini 等
    temperature=0.2
)

# 2. 把上面的函数包装成 LangChain Tool
tools = [
    Tool(
        name="get_weather",
        func=get_weather,
        description="根据城市名查询当天的天气情况。",
        args_schema=GetWeatherInput,
    ),
    Tool(
        name="calculate",
        func=calculate,
        description="执行一个简单的四则运算表达式，返回结果。",
        args_schema=CalculateInput,
    ),
]

# 3. 用 LangGraph 的预构建 ReAct Agent 创建一个 Graph
app = create_react_agent(
    model=llm,
    tools=tools,
    # 可选参数：如果你想启用 checkpointer / 人类在回路等，可以传入其它参数
)
```

到这一步，`app` 就是一个 **LangGraph Graph 对象**，里面已经帮你搞定了：

* ReAct 推理循环
* Tool 调用选择
* 工具结果解析
* 状态管理

---

## 4. 调用 Agent（普通调用 + 流式）

### 4.1 普通单次调用（`invoke`）

```python
if __name__ == "__main__":
    # 示例 1：让它自动调用 calculate 工具
    result = app.invoke({"messages": [
        ("user", "帮我算一下 (2 + 3) * 4 再加 10 等于多少？")
    ]})
    print("=== 普通调用 ===")
    print(result["messages"][-1].content)
```

### 4.2 流式调用（`stream`，可看到 ReAct 过程）

```python
    print("\n=== 流式调用（含工具调用过程） ===")
    for event in app.stream(
        {"messages": [("user", "帮我查一下上海今天的天气，然后再算 3 * 7 * 2")]}
    ):
        # event 是一个 dict，key 通常是 "agent" / "tools" 等
        print(event)
```

你可以在 `stream` 的输出中看到：

* 模型思考要用哪个工具
* 调用了哪个 tool（`get_weather` 或 `calculate`）
* 工具返回了什么
* 最终给用户的回复是什么

---

## 5. 如果你想启用 Checkpoint（对话可恢复）

只需在创建 `app` 时，传入一个 checkpointer，例如 SQLite：

```python
from langgraph.checkpoint.sqlite import SqliteSaver

checkpointer = SqliteSaver.from_uri("react_agent_state.db")

app = create_react_agent(
    model=llm,
    tools=tools,
    checkpointer=checkpointer,
)
```

然后调用时带上 `config` 中的 `thread_id`，每个 thread 就是一条可恢复的对话：

```python
config = {"configurable": {"thread_id": "user_123"}}

result = app.invoke(
    {"messages": [("user", "从现在开始你帮我做旅行规划。")]},
    config=config
)
```

以后再用同一个 `thread_id` 调用时，它会继续之前的状态。

---

## 6. 完整可运行示例（整合版）

下面是一个**放在一个文件里就能跑**的版本（删掉了一些解释性的注释，但结构完整）：

```python
from typing import TypedDict
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain_core.tools import Tool
from langgraph.prebuilt import create_react_agent


# ---------- 工具定义 ----------

class GetWeatherInput(BaseModel):
    city: str = Field(..., description="要查询天气的城市名称，例如 '北京'、'上海'")


def get_weather(city: str) -> str:
    fake_data = {
        "北京": "晴，18~26℃",
        "上海": "多云，20~28℃",
        "深圳": "雷阵雨，25~31℃",
    }
    return fake_data.get(city, f"{city} 的天气数据暂时不可用，假装是晴天 22℃")


class CalculateInput(BaseModel):
    expression: str = Field(
        ...,
        description="一个简单的数学表达式，比如 '2 + 3 * 4'"
    )


def calculate(expression: str) -> str:
    try:
        allowed_chars = set("0123456789+-*/(). ")
        if not set(expression) <= allowed_chars:
            return "表达式中包含非法字符"
        result = eval(expression)
        return f"{expression} = {result}"
    except Exception as e:
        return f"计算失败: {str(e)}"


# ---------- LLM + ReAct Agent ----------

llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0.2,
)

tools = [
    Tool(
        name="get_weather",
        func=get_weather,
        description="根据城市名查询当天的天气情况。",
        args_schema=GetWeatherInput,
    ),
    Tool(
        name="calculate",
        func=calculate,
        description="执行一个简单的四则运算表达式，返回结果。",
        args_schema=CalculateInput,
    ),
]

app = create_react_agent(
    model=llm,
    tools=tools,
)


# ---------- 演示调用 ----------

if __name__ == "__main__":
    # 普通调用
    result = app.invoke({"messages": [
        ("user", "帮我算一下 (2 + 3) * 4 再加 10 等于多少？")
    ]})
    print("=== 普通调用结果 ===")
    print(result["messages"][-1].content)

    # 流式，展示 ReAct 过程
    print("\n=== 流式调用（含工具调用过程） ===")
    for event in app.stream(
        {"messages": [("user", "帮我查一下上海今天的天气，然后再算 3 * 7 * 2")]}
    ):
        print(event)
```

---

如果你愿意，下一步我可以帮你改造成你实际需要的形态，比如：

* 接入你自己的 HTTP API，当做 Tool
* 做一个 “多工具智囊” （比如：天气 + 汇率 + 自家数据库）
* 接 LangGraph 的 **Web UI / LangSmith** 来可视化整个 ReAct 过程

你可以跟我说一下：你现在想做的是「聊天机器人」「工作流自动化」「RAG 问答」「企业内部助手」里的哪一类，我可以直接按那个场景帮你改这个示例。



下面我给你一个**完整可跑、带并发的 LangGraph v1.0 示例**，展示：

* ✅ 使用 **StateGraph**
* ✅ 多个 LLM 节点并行执行（摘要 / 标题 / 要点）
* ✅ 一个 `combine` 节点收集并合并结果（fan-in）
* ✅ 演示 LangGraph 的并发特性：多个独立节点会自动并行执行

代码用英文方便你直接复制，解释用中文。

---

## 1. 安装依赖

```bash
pip install "langgraph>=1.0.0" "langchain-openai>=0.1.0" "langchain-core>=0.3.0"
```

设置 OpenAI Key：

```bash
export OPENAI_API_KEY="你的 OpenAI Key"
```

---

## 2. 思路结构（先用人话说一下）

我们要做一个图，状态（state）里有这些字段：

```python
class DocState(TypedDict):
    text: str            # 原始输入文本
    summary: str         # 节点1：生成摘要
    title: str           # 节点2：生成标题
    bullets: str         # 节点3：生成要点
    final_answer: str    # combine 节点：汇总上面三个结果
```

图结构：

```text
        ┌──────────┐
        │  start   │
        └────┬─────┘
             │
   ┌────────┼───────────────┐
   │        │               │
┌──▼───┐ ┌──▼───┐       ┌───▼───┐
│summary│ │title │       │bullets│  ← 这三个节点彼此独立，可并发
└──┬───┘ └──┬───┘       └───┬───┘
   │        │               │
   └────────┴───────┬───────┘
                    ▼
                ┌───────┐
                │combine│
                └───┬───┘
                    │
                   END
```

关键点是这一行（fan-in）：

```python
builder.add_edge(["summary", "title", "bullets"], "combine")
```

这表示：`summary`、`title`、`bullets` 三个都跑完后，才进入 `combine`，而三者之间没有依赖 → **可以并行**。

---

## 3. 完整代码示例：LangGraph v1.0 + OpenAI + 多节点并发

```python
from typing import TypedDict

from langgraph.graph import StateGraph
from langchain_openai import ChatOpenAI


# ---------- 1. 定义 State 结构 ----------

class DocState(TypedDict):
    text: str
    summary: str
    title: str
    bullets: str
    final_answer: str


# ---------- 2. 初始化 OpenAI LLM ----------

llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0.2,
)


# ---------- 3. 定义各个节点函数 ----------

def start_node(state: DocState) -> DocState:
    """
    起始节点：这里不做任何处理，只是把输入原样传下去。
    你也可以在这里做预处理，比如清洗文本等。
    """
    return state


def summary_node(state: DocState) -> DocState:
    """
    节点1：生成摘要
    """
    text = state["text"]
    prompt = f"请用中文帮我把下面这段内容总结成 2~3 句话：\n\n{text}"
    resp = llm.invoke(prompt)
    return {**state, "summary": resp.content}


def title_node(state: DocState) -> DocState:
    """
    节点2：生成一个简洁有吸引力的标题
    """
    text = state["text"]
    prompt = f"为下面这段内容起一个简短、吸引人的中文标题（不超过 15 个字）：\n\n{text}"
    resp = llm.invoke(prompt)
    return {**state, "title": resp.content}


def bullets_node(state: DocState) -> DocState:
    """
    节点3：生成 3~5 条要点
    """
    text = state["text"]
    prompt = f"请从下面内容中提炼出 3~5 条关键要点，用项目符号列出：\n\n{text}"
    resp = llm.invoke(prompt)
    return {**state, "bullets": resp.content}


def combine_node(state: DocState) -> DocState:
    """
    汇总节点：把 summary / title / bullets 合成一个最终输出
    注意：这里能拿到并发节点都写回来的字段。
    """
    final = f"""📝 标题：
{state.get("title", "").strip()}

📚 摘要：
{state.get("summary", "").strip()}

🔍 关键要点：
{state.get("bullets", "").strip()}
"""
    return {**state, "final_answer": final}


# ---------- 4. 构建 StateGraph 并配置并发 ----------

builder = StateGraph(DocState)

# 添加节点
builder.add_node("start", start_node)
builder.add_node("summary", summary_node)
builder.add_node("title", title_node)
builder.add_node("bullets", bullets_node)
builder.add_node("combine", combine_node)

# 设置入口
builder.set_entry_point("start")

# 从 start 分成三条支路（fan-out）
builder.add_edge("start", "summary")
builder.add_edge("start", "title")
builder.add_edge("start", "bullets")

# 三个支路汇合到 combine（fan-in）
builder.add_edge(["summary", "title", "bullets"], "combine")

# 结束点
builder.set_finish_point("combine")

# 编译 graph 得到可调用的 app
app = builder.compile()


# ---------- 5. 演示调用 ----------

if __name__ == "__main__":
    input_text = """
LangGraph 是一个用于构建多步骤 AI 工作流和智能代理的图式框架。
通过节点和有向边的方式，你可以把 LLM 调用、工具调用、人类审核等步骤
组织成可视化、可调试、可恢复的流程，非常适合复杂业务场景下的 AI 应用开发。
"""

    # 调用图
    result_state = app.invoke({
        "text": input_text,
        "summary": "",
        "title": "",
        "bullets": "",
        "final_answer": "",
    })

    # 打印最终输出
    print("===== 最终结果 =====")
    print(result_state["final_answer"])
```

---

## 4. 并发是怎么体现的？

* LangGraph 会分析 **依赖关系** 来决定并行：

  * `summary` / `title` / `bullets` 都只依赖 `start` 的输出；
  * 它们之间互不依赖 → 可以同时跑。
* 当你调用 `app.invoke(...)` 时，内部调度会：

  1. 先跑 `start`
  2. 然后同时调度 `summary` / `title` / `bullets`
  3. 三个都完成后，再跑 `combine`

如果你把节点改成 `async def` + 用 `llm.ainvoke`，再在支持异步的环境里运行，**并发优势会更明显**（比如使用多路 HTTP 请求）。

---

## 5. 想要 async 并发版？

如果你下一步想看 “**异步 + 并发**（`async def` 节点 + `ainvoke`）” 版本，我也可以直接给你一份，把上面这个例子改成完全 async，让你在 FastAPI / asyncio 项目里能原生跑。你要的话就回我一句：

> 再给我一个 async 并发版本

我就按这个例子帮你改好 👌




人在回路（Human-in-the-loop）在 LangGraph v1.0 里，核心就是用 **`interrupt()` + 持久化（checkpointer）+ `Command(resume=...)`** 来“暂停 → 等人类 → 再继续”。([LangChain文档][1])

下面给你一个**完整可跑的审批工作流示例**：

> LLM 计划执行一个敏感操作（比如转账），先停下来问人类“同不同意？”，人点 ✅ 或 ❌ 后再继续。

---

## 1. 要点先说清楚

在 LangGraph v1.0 里做人在回路，一般要满足 3 个条件：([LangChain文档][1])

1. **有 checkpointer**：用于把图的当前状态存到某个地方（内存、SQLite、Postgres 等），这样暂停后可以随时恢复。
2. **调用 `interrupt()`**：在某个节点里调用，它会：

   * 立刻让图“停在这里”
   * 把你传给 `interrupt()` 的值存到结果的 `__interrupt__` 字段里
3. **用 `Command(resume=...)` 恢复**：

   * 之后再调用一次 `graph.invoke(Command(resume=你的决策), config=同一个 thread_id)`
   * 这个 `resume` 的值会作为 `interrupt()` 的返回值回到节点里，节点继续往下跑

---

## 2. 场景：转账前要人批准

* 状态里有：要做的动作描述 + 审批状态
* 图的结构：

```text
START → approval_node → (proceed_node 或 cancel_node) → END
```

---

## 3. 完整代码示例（LangGraph v1.0 + Human-in-the-loop）

```python
from typing import TypedDict, Optional, Literal

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from langgraph.checkpoint.memory import MemorySaver


# 1. 定义状态
class ApprovalState(TypedDict):
    action_details: str                  # 要执行的动作描述，比如 "Transfer $500"
    status: Optional[Literal[
        "pending", "approved", "rejected"
    ]]                                   # 当前状态


# 2. 定义节点：审批节点（这里触发人在回路）
def approval_node(state: ApprovalState) -> Command[Literal["proceed", "cancel"]]:
    """
    在这里暂停，等人类决定是否批准。
    返回值是一个 Command，用来告诉图“下一步跳到哪个节点”。
    """
    decision = interrupt({
        "question": "是否批准这个操作？",
        "details": state["action_details"],
    })
    # decision 是你在恢复时传给 Command(resume=...) 的值

    # 根据人类的决策跳转到不同节点
    if decision is True:
        # 去执行真正的操作
        return Command(goto="proceed")
    else:
        # 走取消分支
        return Command(goto="cancel")


def proceed_node(state: ApprovalState) -> ApprovalState:
    # 这里可以放真正的“执行动作”的代码，比如调支付 API
    return {
        **state,
        "status": "approved",
    }


def cancel_node(state: ApprovalState) -> ApprovalState:
    # 被拒绝的分支
    return {
        **state,
        "status": "rejected",
    }


# 3. 构建图
builder = StateGraph(ApprovalState)

builder.add_node("approval", approval_node)
builder.add_node("proceed", proceed_node)
builder.add_node("cancel", cancel_node)

builder.add_edge(START, "approval")
builder.add_edge("proceed", END)
builder.add_edge("cancel", END)

# 必须配置 checkpointer，interrupt 才能工作
checkpointer = MemorySaver()  # Demo 用内存，生产建议用 SQLite / Postgres 等

graph = builder.compile(checkpointer=checkpointer)


# 4. 演示：第一次运行 → 暂停等待人类；第二次运行 → 带上决策继续
if __name__ == "__main__":
    # thread_id 是这条“对话 / 流程”的 ID，暂停 & 恢复必须用同一个
    config = {"configurable": {"thread_id": "approval-001"}}

    # 第一次调用：会跑到 interrupt 那里停下
    first_result = graph.invoke(
        {
            "action_details": "Transfer $500 to Alice",
            "status": "pending",
        },
        config=config,
    )

    print("=== 第一次调用，图被中断 ===")
    print("状态里的 status:", first_result.get("status"))
    print("需要人类处理的内容 __interrupt__:")
    print(first_result["__interrupt__"])  # 这里就可以拿去喂到前端 UI，让人点“同意 / 拒绝”

    # 假设前端问了人：用户点了“同意”（True）
    human_decision = True  # True = 同意，False = 拒绝

    # 第二次调用：用 Command(resume=...) 恢复执行
    final_result = graph.invoke(
        Command(resume=human_decision),
        config=config,
    )

    print("\n=== 第二次调用，流程继续跑完 ===")
    print("最终状态 status:", final_result["status"])
```

---

## 4. 这个例子里，人在回路发生了什么？

1. **第一次 `graph.invoke(...)`：**

   * 跑到 `approval_node`
   * 调用 `interrupt({...})` → 图暂停，当前 state 被写入 checkpointer
   * 调用的返回值里会多一个 `__interrupt__` 字段，里面就是你传给 `interrupt()` 的那个 JSON（问题 + 详情 等）([LangChain文档][1])
   * 你把这个东西丢给前端/管理后台，展示给人看

2. **人类在 UI 上做决策：**

   * 比如点了“同意” → 你在后端变成 `True`（或别的结构）

3. **第二次 `graph.invoke(Command(resume=...))`：**

   * 用相同的 `thread_id` 调用
   * LangGraph 会从上次的中断点恢复
   * `interrupt(...)` 这行重新执行，但这次会直接返回你传给 `Command(resume=...)` 的值（这里是 `True`）([LangChain文档][1])
   * `approval_node` 根据这个决策返回 `Command(goto="proceed")` 或 `Command(goto="cancel")`，图继续往下跑到对应节点，最后到 `END`

---

## 5. 跟 LLM / OpenAI 结合做“草稿 + 审核”

如果你想做的是这种流程：

1. LLM 先写一段东西（比如邮件、合同、SQL）
2. 人类看一眼，想改就改，不想改就直接过
3. 然后再执行后续动作

可以在 **生成节点** 用 OpenAI，在 **审核节点** 用 `interrupt()` 把 LLM 的输出抛给前端，让人编辑后再 `Command(resume=编辑后的文本)`，节点里直接把这个值写回 state（官方文档里有“review and edit state”的模式）。([LangChain文档][1])

如果你愿意，我可以在这个基础上再给你一个：

* **OpenAI 起草邮件 → 人类修改/批准 → 再“发送”** 的完整例子（含 ChatOpenAI 调用）。只要你说一声：

> 来一个“邮件起草 + 人工审批”的例子

我就按这个业务帮你把 LLM 也接进去。

[1]: https://docs.langchain.com/oss/python/langgraph/interrupts "Interrupts - Docs by LangChain"




下面给你一个**可以直接跑**的「LangGraph v1.0 + OpenAI + RAG（Retriever Agent）」完整示例。
特点：

* 用 **OpenAI** 做 Embedding + Chat
* 用 **Chroma** 做向量库
* 用 **LangGraph** 把它们串成一个 **会自己决定要不要检索的 Agent**

---

## 1. 安装依赖

```bash
pip install -U \
  langgraph \
  langchain \
  langchain-openai \
  langchain-community \
  chromadb \
  tiktoken
```

---

## 2. 设置环境变量（推荐）

```bash
export OPENAI_API_KEY="你的 OpenAI Key"
```

如果你不想用环境变量，也可以在代码里直接传 `api_key="..."`。

---

## 3. 完整示例：Agentic RAG 检索 Agent

> 这个例子会：
>
> 1. 把几篇网页文章抓下来 → 切块 → 建 Chroma 向量库
> 2. 把 `retriever` 包装成一个 **tool**
> 3. 用 **LangGraph** 搭一个图：
>
>    * `agent` 节点：LLM 决定要不要调用检索工具
>    * `retrieve` 节点：真正去检索
>    * 检索后再回到 `agent`，让模型根据检索结果回答

```python
# rag_agent_langgraph.py

import os
from typing import Annotated, Sequence, TypedDict

# ==== 0. 环境变量（可选，如果你没在外面 export）====
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "你的API_KEY")

# ==== 1. 构建向量库 & retriever ====
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import WebBaseLoader
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

# 随便用几篇公开文章做 Demo，你可以换成你自己的文档
urls = [
    "https://lilianweng.github.io/posts/2023-06-23-agent/",
    "https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/",
    "https://lilianweng.github.io/posts/2023-10-25-adv-attack-llm/",
]

print("🔍 Loading web pages...")
docs = [WebBaseLoader(url).load() for url in urls]
docs = [d for sub in docs for d in sub]

# 切成 chunk
splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    chunk_size=500,
    chunk_overlap=100,
)
doc_splits = splitter.split_documents(docs)

print("📚 Building vector store...")
vectorstore = Chroma.from_documents(
    documents=doc_splits,
    collection_name="demo-rag",
    embedding=OpenAIEmbeddings(),  # 使用 OpenAI Embedding
)

retriever = vectorstore.as_retriever()

# ==== 2. 把 retriever 包成一个 Tool ====
from langchain.tools.retriever import create_retriever_tool

retriever_tool = create_retriever_tool(
    retriever=retriever,
    name="retrieve_blog_posts",
    description=(
        "检索与问题相关的技术博客内容，"
        "用于回答关于 LLM agents / prompt engineering / adversarial attacks 的问题。"
    ),
)

tools = [retriever_tool]

# ==== 3. 定义 Agent 的 state ====
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # LangGraph 状态里存一串 messages，每个节点 append
    messages: Annotated[Sequence[BaseMessage], add_messages]

# ==== 4. 定义各个节点 ====
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode, tools_condition

# 4.1 Agent 节点：负责思考 + 决定是否调用工具
def agent_node(state: AgentState) -> dict:
    """
    Agent 会根据 messages 决定：
    - 直接回答
    - 还是调用 retriever_tool
    """
    print("🤖 [agent] 被调用")
    messages = state["messages"]

    # 使用 OpenAI Chat 模型
    llm = ChatOpenAI(
        model="gpt-4o",   # 可换成 gpt-4.1 等
        temperature=0,
    ).bind_tools(tools)   # 绑定检索工具

    response = llm.invoke(messages)
    # 返回 list，会 append 到原 messages 中
    return {"messages": [response]}


# 4.2 Tool 节点：实际执行工具（检索）
tool_node = ToolNode(tools)


# ==== 5. 构建图（Graph） ====
from langgraph.graph import StateGraph, END

# 定义 StateGraph，使用我们上面定义的 AgentState
workflow = StateGraph(AgentState)

# 注册节点
workflow.add_node("agent", agent_node)
workflow.add_node("retrieve", tool_node)

# 入口从 agent 开始
workflow.set_entry_point("agent")

# 条件边：根据 agent 输出是否有 tool_call 决定下一步去哪
workflow.add_conditional_edges(
    "agent",
    tools_condition,   # 根据 messages 里是否有 tool calls 来判断
    {
        "action": "retrieve",  # 有工具调用 → 去执行工具
        END: END,              # 没有工具调用 → 直接结束对话
    },
)

# 工具执行完，再回到 agent 让模型根据检索结果继续回答
workflow.add_edge("retrieve", "agent")

# 编译成可以调用的 app
app = workflow.compile()

# ==== 6. 运行测试 ====
if __name__ == "__main__":
    from pprint import pprint

    # 这里 messages 可以直接用 ("user", "xxx") 简写
    user_input = "Lilian Weng 对 agent memory（代理记忆）是怎么分类的？用中文帮我总结一下。"

    inputs = {
        "messages": [
            ("user", user_input),
        ]
    }

    print("🚀 开始执行 Agentic RAG...")
    # 用 stream 可以看到每一步节点输出
    for event in app.stream(inputs, stream_mode="values"):
        # 每个 event 就是完整的 state（包含目前所有 messages）
        last_message = event["messages"][-1]
        print("---- 当前最后一条消息 ----")
        pprint(last_message)

    print("\n✅ 最终回答：")
    final_state = app.invoke(inputs)
    final_answer = final_state["messages"][-1].content
    print(final_answer)
```

---

## 4. 这段代码在图上做了什么？

简化理解成一个循环：

1. **agent 节点**

   * 看当前对话（state.messages）
   * 决定：

     * 直接回答
     * 或者调用 `retrieve_blog_posts` 工具

2. **tools_condition**

   * 如果刚才那一步有 tool_call → 走到 `retrieve` 节点
   * 如果没有 tool_call → 直接结束（END）

3. **retrieve 节点（ToolNode）**

   * 执行检索 tool
   * 把检索结果（作为 AI tool result / message）追加到 messages
   * 然后边 `retrieve -> agent` 再回到 agent，让模型根据检索结果做最后回答

整个流程就是典型的 **Agentic RAG**：

> LLM 先想一想要不要查资料 → 需要就查 → 用查到的内容回答。

---

## 5. 想怎么改？

你可以很容易地改成自己的场景：

* ✅ 把 `urls = [...]` 换成你自己的网页 / 文档
* ✅ 或者不用 `WebBaseLoader`，改成从本地文件夹加载
* ✅ 改模型：`gpt-4o` → `gpt-4.1` / `gpt-4o-mini` 等
* ✅ 想更复杂一点：可以增加

  * `grade_documents` 节点做检索相关性判断
  * `rewrite` 节点重写 Query
  * 单独的 `generate` 节点负责答案生成

---

如果你愿意，下一步我可以帮你把这个示例改成：

* **“读取本地 Markdown / PDF 文档” 的 RAG**
* 或者 **“公司知识库问答” 的多文件 RAG 模板项目结构（带 index graph + chat graph）**
