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
Through static analysis, the Basic Facts extracted include: (1) the definition of \texttt{struct drm\_device} and its nested field \texttt{driver}; (2) the function \texttt{drm_open()} and its parameter type; and (3) the direct call to \texttt{allocate\_id()}. These facts serve as verifiable, code-grounded knowledge describing type relationships and call dependencies. Later, during semantic reasoning, the LLM can use these Basic Facts to deduce that \texttt{drm\_open()} transitions the device state by assigning a valid identifier, thus contributing to the ASDG’s state and data-flow inference.

\subsubsection{Call-Chain Refinement}
In C programs, a \textit{call graph} represents the set of calling relationships between functions, describing which functions invoke which others throughout the program. Generally, a call graph can be divided into two categories: (1) \textbf{direct function calls}, where a function explicitly invokes another through its name, and (2) \textbf{indirect function calls}, where the invocation occurs through function pointers, callbacks, or virtual operation tables. Direct calls can be easily extracted using the Basic Fact Extraction (BFE) process described in the previous section. However, in kernel driver development, indirect calls are heavily used, leading to incomplete or disconnected portions of the call graph that cannot be reconstructed through conventional static analysis. Restoring these missing connections has long been a significant challenge in program analysis research.

To address this challenge, we employ the state-of-the-art tool \textbf{DeepType}, an advanced deep learning-based type inference framework for C programs developed by the S3 team . DeepType implements the Strong Multi-Layer Type Analysis (SMLTA) algorithm to address the limitations of traditional type-based analyses. Considering the high false positive rate of conventional approaches, it uses a multi-layer type representation to describe function pointers, consisting of both the function signature and the composite types that encapsulate it. While this richer representation improves precision, it introduces challenges in type matching because address-taken functions may propagate through complex information flows between multi-layer types. To mitigate this, DeepType applies SMLTA, which enforces a strong matching constraint—only functions whose entire multi-layer types match an indirect call are considered valid targets. SMLTA resolves the relationships between multi-layer types based on the direction of information flow and employs an adapted breadth-first search (BFS) algorithm to discover all multi-layer types involved in the propagation of target functions. It further adopts conservative strategies to handle ambiguous type information. As a prototype implementation of SMLTA, DeepType effectively overcomes the challenges of multi-layer type matching and precisely identifies indirect call targets in C-based kernel drivers. By integrating DeepType’s inferred call edges into our analysis, we obtain an \textit{augmented call graph} that accurately reflects both direct and indirect invocation relationships—essential for later reasoning over inter-API dependencies.

\paragraph{Example.} Consider the following simplified snippet:
\begin{verbatim}
static int drv_open(struct inode *inode, struct file *filp) {
return drv_fops.open(inode, filp);   // indirect via function pointer table
}

static const struct file_operations drv_fops = {
.open = drv_open_impl,
};

static int drv\_open\_impl(struct inode *inode, struct file *filp) { return real_open(inode, filp);       // direct call } 
\end{verbatim} 

Basic Fact Extraction recovers the direct edge \texttt{drv\_open\_impl() -> real\_open()}, but without resolving the function pointer \texttt{drv\_fops.open}, the edge from \texttt{drv\_open()} to \texttt{drv\_open\_impl()} remains missing. DeepType identifies \texttt{drv\_open\_impl} as the dynamic target of \texttt{drv\_fops.open}, allowing us to add the missing indirect edge and obtain a precise, connected call graph that faithfully reflects the driver’s control flow.

\subsubsection{Dynamic Parameter-Type Inference} Given the refined call graph, we apply \textbf{LLM-guided semantic exploration} to infer the concrete runtime semantics of parameters whose types are ambiguous in static analysis. For example, a function parameter defined as \texttt{unsigned long addr} may actually hold the address of a specific kernel data structure. To resolve such latent semantics, we traverse the call chain upward and downward to collect the parameter’s usage contexts, and query an LLM to reason about its most plausible underlying type (e.g., a pointer to \texttt{struct drm\_device}). This step allows our fuzzing framework to construct valid objects and memory layouts for realistic test generation.

\subsubsection{Parameter Range Derivation} We next infer \textit{value-range constraints} for parameters. Condition-checking statements in the driver often imply bounds on valid inputs. For instance, the condition \texttt{if (nr >= DRM\_CORE\_IOCTL\_COUNT)} indicates that the ioctl number \texttt{nr} must lie within a bounded range. Combining syntactic conditions obtained from basic fact extraction with LLM-based reasoning about symbolic comparisons and enumeration semantics, we infer approximate value domains for each input field (e.g., \texttt{0 ≤ nr < DRM_CORE_IOCTL_COUNT}). Such range information helps the fuzzer prune infeasible inputs and concentrate on semantically valid cases.

\subsubsection{State and Parameter Dependency Inference} Finally, we construct both the \textit{state-machine transitions} and \textit{parameter-dependency edges} among ioctl APIs. State transitions describe the ordering constraints between APIs (e.g., \texttt{open()} must precede \texttt{ioctl(SETUP)}), while parameter dependencies capture data relationships such as ``\texttt{set\_format(image)} must precede \texttt{get\_format(image)}.''

To infer these dependencies, we design a \textbf{LangGraph-based reasoning framework}. Each API is treated as a node whose semantics are summarized by the LLM. For a target reasoning task (state inference or parameter influence), we first prompt the LLM to summarize the API’s behavioral intent based on its code. If the summary lacks sufficient context (e.g., missing definitions of called functions or relevant structures), the framework automatically identifies and retrieves the missing facts from the code fact database. Those facts are recursively summarized and fed back into the node’s reasoning context, forming an iterative summarization–refinement loop until the LLM deems the information sufficient. After all API nodes are individually summarized, the framework jointly reasons over the set of summaries to infer inter-API dependencies and produce the final \textbf{API State Dependency Graph (ASDG)}.

The resulting ASDG serves as the foundation for our state-aware fuzzing engine, enabling it to explore only valid state transitions and meaningful parameter interactions, thereby significantly improving both coverage and bug-discovery efficiency.



\subsection{State Dependency Graph Generation}

Our prototype builds an \textit{API State Dependency Graph (ASDG)} for kernel device drivers to support state-aware fuzzing over \texttt{ioctl} interfaces. The pipeline has three main stages: (1) basic fact extraction, (2) call-graph refinement, and (3) LLM-based semantic inference. Figure~\ref{fig:asdg-workflow} summarizes the overall workflow.

\textbf{Basic Fact Extraction.}
We first analyze driver source code with \textbf{Clang LibTooling} to obtain precise AST-level information. From each compilation unit, we extract function prototypes, macro and type declarations, structure nesting relations, direct call relations, and argument type hierarchies (including nested structure fields). These \emph{Basic Facts} form a code-grounded layer that is free of hallucination and later constrain all LLM reasoning.

\textbf{Call-Graph Refinement.}
Direct call edges are obtained directly from Basic Facts. To recover indirect calls that heavily appear in kernel drivers, we integrate \textbf{DeepType}, a Strong Multi-Layer Type Analysis (SMLTA)–based framework for C. DeepType models function pointers using multi-layer types (function signature plus surrounding composite types) and enforces strict whole-type matching to determine valid indirect call targets. By resolving information-flow–based relations between multi-layer types and conservatively handling ambiguous types, DeepType augments the call graph with accurate indirect edges, yielding a connected and precise call graph for later reasoning.

\textbf{LLM-Based Semantic Inference.}
Given the refined call graph and Basic Facts, we apply an LLM-based reasoning framework to infer higher-level semantics needed by fuzzing. First, we refine parameter types whose static types are overly generic (e.g., inferring that an \texttt{unsigned long} actually encodes a pointer to a specific kernel structure) by collecting their usage contexts along the call chain and querying the LLM under the constraints of Basic Facts. Second, we derive parameter value ranges from branch conditions and constants (e.g., bounds on ioctl numbers), combining syntactic checks with LLM reasoning about symbolic comparisons and enumeration semantics. Finally, we summarize each ioctl API’s behavior and let the LLM infer (1) state-transition relations (ordering constraints between APIs) and (2) parameter-dependency edges (data-flow relations such as ``set-before-get''). All reasoning is performed over Basic Facts and the augmented call graph, which both limits hallucinations and guides the LLM toward code-consistent conclusions. The resulting ASDG serves as the core input to our state-aware fuzzing engine, enabling it to focus on valid state transitions and meaningful parameter interactions.

