\subsection{State Dependency Graph Generation}

To enable state-aware fuzzing of kernel device drivers, we construct an \textit{API State Dependency Graph (ASDG)} that captures state transitions, data flows, and parameter dependencies among the driver's \texttt{ioctl} interfaces. The construction of the ASDG consists of two major parts. First, we employ static analysis tools to extract code-level information from the driver source, which we refer to as \textit{Basic Fact Extraction}. Second, based on these Basic Facts, we leverage an LLM-based reasoning framework to infer higher-level semantic relationships that constitute the state transitions, data flows, and parameter dependencies represented in the ASDG. Figure~\ref{fig:asdg-workflow} illustrates the overall workflow, which consists of five major stages: basic fact extraction, call chain refinement, dynamic parameter type inference, parameter range derivation, and state and parameter dependency graph construction.

\subsubsection{Basic Fact Extraction}
We first perform structural analysis of the kernel driver source code using \textbf{Clang LibTooling}, which provides precise AST-level access to C code.
From each compilation unit, we extract \textit{code facts} including:
\begin{itemize}
\item macro definitions, structure and enumeration declarations, and function prototypes;
\item structure-to-structure nesting relationships;
\item direct function-call relations; and
\item argument type information, including nested type hierarchies if a parameter is a structure.
\end{itemize}

These code facts serve as the \textit{ground truth layer} for subsequent reasoning.
While they describe syntactic and type-level information available from the code, many semantic dependencies (e.g., implicit state transitions or hidden data correlations) are not directly visible.
Hence, we later employ LLM-assisted reasoning to infer such higher-level semantics on top of the extracted facts.

\paragraph{Example.} To illustrate, consider the following simplified kernel structure and function definition: 

\begin{verbatim} struct drm\\_device { int device\_id; struct drm\_driver *driver; };

int drm\_open(struct drm\_device *dev) { if (!dev->driver) return -EINVAL; dev->device\_id = allocate\_id(); return 0; } 

\end{verbatim} 

Through static analysis, the Basic Facts extracted include: (1) the definition of \texttt{struct drm\_device} and its nested field \texttt{driver}; (2) the function \texttt{drm\_open()} and its parameter type; and (3) the direct call to \texttt{allocate\_id()}. These facts serve as verifiable, code-grounded knowledge describing type relationships and call dependencies. Later, during semantic reasoning, the LLM can use these Basic Facts to deduce that \texttt{drm\_open()} transitions the device state by assigning a valid identifier, thus contributing to the ASDG’s state and data-flow inference.

\subsubsection{Call-Chain Refinement}
In C programs, a \textit{call graph} represents the set of calling relationships between functions, describing which functions invoke which others throughout the program. Generally, a call graph can be divided into two categories: (1) \textbf{direct function calls}, where a function explicitly invokes another through its name, and (2) \textbf{indirect function calls}, where the invocation occurs through function pointers, callbacks, or virtual operation tables. Direct calls can be easily extracted using the Basic Fact Extraction (BFE) process described in the previous section. However, in kernel driver development, indirect calls are heavily used, leading to incomplete or disconnected portions of the call graph that cannot be reconstructed through conventional static analysis. Restoring these missing connections has long been a significant challenge in program analysis research.

To address this challenge, we employ the state-of-the-art tool \textbf{DeepType}, which assists in recovering indirect call relationships and completing the call graph. DeepType models the correlation between pointer assignments and the data-flow of function objects. It collects pointer usage contexts, builds embedding representations of functions and call sites, and classifies potential targets through neural type inference. By integrating DeepType’s inferred call edges into our analysis, we obtain an \textit{augmented call graph} that accurately reflects both direct and indirect invocation relationships—essential for later reasoning over inter-API dependencies.

\paragraph{Example.} Consider the following simplified snippet:
\begin{verbatim}
static int drv\_open(struct inode *inode, struct file *filp) {
return drv\_fops.open(inode, filp);   // indirect via function pointer table
}

static const struct file\_operations drv\_fops = {
.open = drv\_open\_impl,
};

static int drv\_open\_impl(struct inode *inode, struct file *filp) {
return real\_open(inode, filp);       // direct call
}
\end{verbatim}

Basic Fact Extraction recovers the direct edge \texttt{drv\_open\_impl() -> real\_open()}, but without resolving the function pointer \texttt{drv\_fops.open}, the edge from \texttt{drv\_open()} to \texttt{drv\_open\_impl()} remains missing. DeepType identifies \texttt{drv\_open\_impl} as the dynamic target of \texttt{drv\_fops.open}, allowing us to add the missing indirect edge and obtain a precise, connected call graph that faithfully reflects the driver’s control flow.

\subsubsection{Dynamic Parameter-Type Inference}
Given the refined call graph, we apply \textbf{LLM-guided semantic exploration} to infer the concrete runtime semantics of parameters whose types are ambiguous in static analysis. For example, a function parameter defined as \texttt{unsigned long addr} may actually hold the address of a specific kernel data structure. To resolve such latent semantics, we traverse the call chain upward and downward to collect the parameter’s usage contexts, and query an LLM to reason about its most plausible underlying type (e.g., a pointer to \texttt{struct drm\_device}). This step allows our fuzzing framework to construct valid objects and memory layouts for realistic test generation.

\subsubsection{Parameter Range Derivation}
We next infer \textit{value-range constraints} for parameters. Condition-checking statements in the driver often imply bounds on valid inputs. For instance, the condition \texttt{if (nr >= DRM\_CORE\_IOCTL\_COUNT)} indicates that the ioctl number \texttt{nr} must lie within a bounded range. Combining syntactic conditions obtained from basic fact extraction with LLM-based reasoning about symbolic comparisons and enumeration semantics, we infer approximate value domains for each input field (e.g., \texttt{0 ≤ nr < DRM\_CORE\_IOCTL\_COUNT}). Such range information helps the fuzzer prune infeasible inputs and concentrate on semantically valid cases.

\subsubsection{State and Parameter Dependency Inference}
Finally, we construct both the \textit{state-machine transitions} and \textit{parameter-dependency edges} among ioctl APIs. State transitions describe the ordering constraints between APIs (e.g., \texttt{open()} must precede \texttt{ioctl(SETUP)}), while parameter dependencies capture data relationships such as ``\texttt{set\_format(image)} must precede \texttt{get\_format(image)}.''

To infer these dependencies, we design a \textbf{LangGraph-based reasoning framework}. Each API is treated as a node whose semantics are summarized by the LLM. For a target reasoning task (state inference or parameter influence), we first prompt the LLM to summarize the API’s behavioral intent based on its code. If the summary lacks sufficient context (e.g., missing definitions of called functions or relevant structures), the framework automatically identifies and retrieves the missing facts from the code fact database. Those facts are recursively summarized and fed back into the node’s reasoning context, forming an iterative summarization–refinement loop until the LLM deems the information sufficient. After all API nodes are individually summarized, the framework jointly reasons over the set of summaries to infer inter-API dependencies and produce the final \textbf{API State Dependency Graph (ASDG)}.

The resulting ASDG serves as the foundation for our state-aware fuzzing engine, enabling it to explore only valid state transitions and meaningful parameter interactions, thereby significantly improving both coverage and bug-discovery efficiency.
