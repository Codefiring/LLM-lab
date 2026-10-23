Here's the week in brief, with the agent work itemized.

## Shipped

`57be829` — the gateway now goes to the address the engine assigned instead of reading a configured host copy. The two paths could disagree about where a container actually was; fixed with one shared decision point used by both.

## The main design work: `workbench-driven-from-outside`

108 tasks, 14 added / 1 modified requirement, validated. Plus its prerequisite `egress-chosen-per-build` (29 tasks). Three earlier designs — `plan-revised-from-its-failure`, `agents-repair-then-ask`, `plan-found-by-running-it` — were deleted, because all three were accountability machinery wrapped around a guess rather than ways to stop guessing.

The core inversion: **run the commands first, then write the plan from what worked.**

## What the new agent system fixes, item by item

1. **A BuildPlan was guessed before anything ran.** Read five manifests, predict a plan, pay 242 seconds of build-and-probe to learn the guess was wrong. Now the agent runs commands in a workbench container and the plan is a transcript of what exited zero.

2. **Nothing carried a failure back.** A failed build was terminal; the taxonomy the probe and builder already knew was flattened into one string at the boundary. Now most failures are observed directly in raw workbench output, and the one distinction code must still carry (the stage boundary) is named.

3. **A repository no analyzer recognized was never shown to a model.** `resolve-plan.ts:73` returned `needs-input` for `not-applicable` *above* the check for whether a model was configured. That path now reaches the agent.

4. **`needs_input` was a question nobody could answer.** Designed as a question channel, but no endpoint accepted an answer — the only recourse was editing configuration and rebuilding, which discarded everything the attempt learned. Now the agent authors its own structured question, and an answer or a bare rerun starts a build that carries the transcript forward.

5. **Four agent roles, a veto, a nine-shape classification, and a deny-listed read channel — all of it cost of guessing.** A command that exits zero is checked by the kernel in under a second. The structure collapsed to one agent whose loop is observe, run, observe.

6. **"Did it work" was going to be the model's judgment.** Now the plane's own probe answers it, in the workbench as well as on the built image — the same code that gates `current_image`. An agent exploring by a different standard would submit plans that fail at the gate for reasons it cannot see.

7. **The toolchain allowlist was the only real check on a model-authored plan, and it is weak.** Replaced for this provenance by something stronger and only possible because the plane executes the commands: **a step the plane did not run and observe exit zero is refused, whatever it names.**

8. **Framework adoption would have put a dependency tree in the token-holding process.** Making the workbench an API resource means the SDK runs in its own process with its own dependencies — the plane's `dependencies` stays `{}` — and Claude Agent SDK or DeepAgents become clients rather than integrations.

9. **An agent given a wider toolchain but no runtime stage would have been stuck.** Only `/app` crosses the stage boundary, so a system package installed in the builder is absent from the served image. `runtimeSteps`/`runtimeEnv` before `USER 10001:10001`, plus a probe failure that names the boundary rather than reporting a timeout.

10. **The workbench had no access to the server's configured env and secrets.** Without it the agent could never reproduce a start that depends on a variable, would attribute the failure to the plan — and worse, still could not verify after a person supplied one.

11. **Nobody would be told a question was waiting.** A flow promising nobody is in the path left the one moment a person is needed unwatched. Three tiers now: a bounded wait on the operation that returns the moment state changes and carries the question in the same response; the open question on the server listing so one call finds every waiting server; a zero-dependency helper in `scripts/`.

12. **Answering a credential question required arranging an environment variable first** — a second task to answer the first. A third `SecretSource` (`store:`, alongside `env:` and `file:`) takes a name and a value once. What the old refusal actually protected is kept: write-only from outside, no getter on the interface, never returned by any read.

13. **An agent an operator had to launch isn't automation.** The plane starts the agent as a container, with the token, server id, plane URL and model endpoint in its environment — subject to the same `ContainerSpec` as everything else.

Neither proposal is committed yet.