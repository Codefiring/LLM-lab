\subsection{State Dependency Graph Generation}

To enable state-aware fuzzing of kernel device drivers, we construct an \textit{API State Dependency Graph (ASDG)} that captures state transitions, data flows, and parameter dependencies among the driver's \texttt{ioctl} interfaces. The construction of the ASDG consists of two major parts. First, we employ static analysis tools to extract code-level information from the driver source, which we refer to as \textit{Basic Fact Extraction}. Second, based on these Basic Facts, we leverage an LLM-based reasoning framework to infer higher-level semantic relationships that constitute the state transitions, data flows, and parameter dependencies represented in the ASDG. Figure~\ref{fig:asdg-workflow} illustrates the overall workflow, which consists of five major stages: basic fact extraction, call chain refinement, dynamic parameter type inference, parameter range derivation, and state and parameter dependency graph construction.

\subsubsection{Basic Fact Extraction}
The concept of \textit{Basic Facts} refers to the set of code definitions and relationships that can be extracted directly and deterministically from the source code through static analysis. These facts are inherently correct and preserve the original semantics of the code. The motivation for introducing this concept is threefold: (1) to extract and formalize factual information from device driver source code as a reliable foundation for further reasoning; (2) to mitigate potential hallucinations or misinterpretations that may arise during LLM-based inference by grounding reasoning in verifiable facts; and (3) to guide subsequent semantic analysis so that inferred relationships remain consistent with the code’s actual implementation logic, thereby producing more accurate and interpretable semantic insights.

We perform structural analysis of the kernel driver source code using \textbf{Clang LibTooling}, which provides precise AST-level access to C code. From each compilation unit, we extract \textit{code facts} including:
\begin{itemize}
\item macro definitions, structure and enumeration declarations, and function prototypes;
\item structure-to-structure nesting relationships;
\item direct function-call relations; and
\item argument type information, including nested type hierarchies if a parameter is a structure.
\end{itemize}

These code facts serve as the \textit{ground truth layer} for subsequent reasoning. While they describe syntactic and type-level information available from the code, many semantic dependencies (e.g., implicit state transitions or hidden data correlations) are not directly visible. Hence, we later employ LLM-assisted reasoning to infer such higher-level semantics on top of the extracted facts.

\paragraph{Example.} To illustrate, consider the following simplified kernel structure and function definition:
\begin{verbatim}
struct drm_device {
int device_id;
struct drm_driver *driver;
};

int drm_open(struct drm_device *dev) {
if (!dev->driver)
return -EINVAL;
dev->device_id = allocate_id();
return 0;
}
\end{verbatim}
Through static analysis, the Basic Facts extracted include: (1) the definition of 	exttt{struct drm_device} and its nested field 	exttt{driver}; (2) the function 	exttt{drm_open()} and its parameter type; and (3) the direct call to 	exttt{allocate_id()}. These facts serve as verifiable, code-grounded knowledge describing type relationships and call dependencies. Later, during semantic reasoning, the LLM can use these Basic Facts to deduce that 	exttt{drm_open()} transitions the device state by assigning a valid identifier, thus contributing to the ASDG’s state and data-flow inference.

\subsubsection{Call-Chain Refinement}
Indirect function calls (through function pointers, callbacks, or virtual operation tables) are prevalent in kernel code and obscure control-flow reconstruction. To recover a more complete call graph, we leverage \textbf{DeepType}, a machine-learning–aided static analysis framework that infers dynamic types of function pointers.

DeepType models the correlation between pointer assignments and the data-flow of function objects. It collects pointer usage contexts, builds embedding representations of functions and call sites, and classifies potential targets through neural type inference. By integrating DeepType’s inferred call edges into our analysis, we obtain an \textit{augmented call graph} that accurately reflects both direct and indirect invocation relationships—essential for later reasoning over inter-API dependencies.

\subsubsection{Dynamic Parameter-Type Inference}
Given the refined call graph, we apply \textbf{LLM-guided semantic exploration} to infer the concrete runtime semantics of parameters whose types are ambiguous in static analysis. For example, a function parameter defined as \texttt{unsigned long addr} may actually hold the address of a specific kernel data structure. To resolve such latent semantics, we traverse the call chain upward and downward to collect the parameter’s usage contexts, and query an LLM to reason about its most plausible underlying type (e.g., a pointer to \texttt{struct drm_device}). This step allows our fuzzing framework to construct valid objects and memory layouts for realistic test generation.

\subsubsection{Parameter Range Derivation}
We next infer \textit{value-range constraints} for parameters. Condition-checking statements in the driver often imply bounds on valid inputs. For instance, the condition \texttt{if (nr >= DRM_CORE_IOCTL_COUNT)} indicates that the ioctl number \texttt{nr} must lie within a bounded range. Combining syntactic conditions obtained from basic fact extraction with LLM-based reasoning about symbolic comparisons and enumeration semantics, we infer approximate value domains for each input field (e.g., \texttt{0 ≤ nr < DRM_CORE_IOCTL_COUNT}). Such range information helps the fuzzer prune infeasible inputs and concentrate on semantically valid cases.

\subsubsection{State and Parameter Dependency Inference}
Finally, we construct both the \textit{state-machine transitions} and \textit{parameter-dependency edges} among ioctl APIs. State transitions describe the ordering constraints between APIs (e.g., \texttt{open()} must precede \texttt{ioctl(SETUP)}), while parameter dependencies capture data relationships such as ``\texttt{set_format(image)} must precede \texttt{get_format(image)}.''

To infer these dependencies, we design a \textbf{LangGraph-based reasoning framework}. Each API is treated as a node whose semantics are summarized by the LLM. For a target reasoning task (state inference or parameter influence), we first prompt the LLM to summarize the API’s behavioral intent based on its code. If the summary lacks sufficient context (e.g., missing definitions of called functions or relevant structures), the framework automatically identifies and retrieves the missing facts from the code fact database. Those facts are recursively summarized and fed back into the node’s reasoning context, forming an iterative summarization–refinement loop until the LLM deems the information sufficient. After all API nodes are individually summarized, the framework jointly reasons over the set of summaries to infer inter-API dependencies and produce the final \textbf{API State Dependency Graph (ASDG)}.

The resulting ASDG serves as the foundation for our state-aware fuzzing engine, enabling it to explore only valid state transitions and meaningful parameter interactions, thereby significantly improving both coverage and bug-discovery efficiency.
