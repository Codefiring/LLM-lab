\subsection{State Dependency Graph Generation}

To enable state-aware fuzzing of kernel device drivers, we construct an \textit{API State Dependency Graph (ASDG)} that captures both control-state transitions and parameter dependencies among the driver's \texttt{ioctl} interfaces. 
The construction process combines static program analysis with LLM-based semantic inference to recover high-level behavioral relations that are not explicitly encoded in the source code. 
Figure~\ref{fig:asdg-workflow} illustrates the overall workflow, which consists of five major stages.

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

\subsubsection{Call-Chain Refinement via DeepType}
Indirect function calls (through function pointers, callbacks, or virtual operation tables) are prevalent in kernel code and obscure control-flow reconstruction. 
To recover a more complete call graph, we leverage \textbf{DeepType}, a machine-learning–aided static analysis framework that infers dynamic types of function pointers. 

DeepType models the correlation between pointer assignments and the data-flow of function objects. 
It collects pointer usage contexts, builds embedding representations of functions and call sites, and classifies potential targets through neural type inference. 
By integrating DeepType’s inferred call edges into our analysis, we obtain an \textit{augmented call graph} that accurately reflects both direct and indirect invocation relationships—essential for later reasoning over inter-API dependencies.

\subsubsection{Dynamic Parameter-Type Inference}
Given the refined call graph, we apply \textbf{LLM-guided semantic exploration} to infer the concrete runtime semantics of parameters whose types are ambiguous in static analysis. 
For example, a function parameter defined as \texttt{unsigned long addr} may actually hold the address of a specific kernel data structure. 
To resolve such latent semantics, we traverse the call chain upward and downward to collect the parameter’s usage contexts, and query an LLM to reason about its most plausible underlying type (e.g., a pointer to \texttt{struct drm\_device}). 
This step allows our fuzzing framework to construct valid objects and memory layouts for realistic test generation.

\subsubsection{Parameter Range Derivation}
We next infer \textit{value-range constraints} for parameters. 
Condition-checking statements in the driver often imply bounds on valid inputs. 
For instance, the condition \texttt{if (nr >= DRM\_CORE\_IOCTL\_COUNT)} indicates that the ioctl number \texttt{nr} must lie within a bounded range. 
Combining syntactic conditions obtained from basic fact extraction with LLM-based reasoning about symbolic comparisons and enumeration semantics, we infer approximate value domains for each input field (e.g., \texttt{0 ≤ nr < DRM\_CORE\_IOCTL\_COUNT}). 
Such range information helps the fuzzer prune infeasible inputs and concentrate on semantically valid cases.

\subsubsection{State and Parameter Dependency Inference}
Finally, we construct both the \textit{state-machine transitions} and \textit{parameter-dependency edges} among ioctl APIs. 
State transitions describe the ordering constraints between APIs (e.g., \texttt{open()} must precede \texttt{ioctl(SETUP)}), while parameter dependencies capture data relationships such as ``\texttt{set\_format(image)} must precede \texttt{get\_format(image)}.'' 

To infer these dependencies, we design a \textbf{LangGraph-based reasoning framework}. 
Each API is treated as a node whose semantics are summarized by the LLM. 
For a target reasoning task (state inference or parameter influence), we first prompt the LLM to summarize the API’s behavioral intent based on its code. 
If the summary lacks sufficient context (e.g., missing definitions of called functions or relevant structures), the framework automatically identifies and retrieves the missing facts from the code fact database. 
Those facts are recursively summarized and fed back into the node’s reasoning context, forming an iterative summarization–refinement loop until the LLM deems the information sufficient. 
After all API nodes are individually summarized, the framework jointly reasons over the set of summaries to infer inter-API dependencies and produce the final \textbf{API State Dependency Graph (ASDG)}.

The resulting ASDG serves as the foundation for our state-aware fuzzing engine, enabling it to explore only valid state transitions and meaningful parameter interactions, thereby significantly improving both coverage and bug-discovery efficiency.
