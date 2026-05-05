# Design proposal — eliminate the parent×subflow slot deadlock in pycmor's parallel orchestration

**Status**: proposal, awaiting review.
**Author**: optimisation working group, 2026-05-05.
**Audience**: pycmor maintainers, AWI HPC team, external reviewers.
**Companion**: `OPTIMIZATION_PLAN.md` (Round 4 sweep data, supports the
problem statement); `bench_hr_ua_6hr_results.md` (single-rule profiling
data).

---

## 1. Problem statement

When pycmor runs in parallel mode (`pycmor.parallel: true,
pipeline_orchestrator: dask`), individual cmorize jobs **deadlock
probabilistically** at moderate-to-high worker × thread-per-worker
configurations on production yamls (cap7_atm and similar). The
deadlock manifests as:

* a worker process at 0 % CPU,
* no Prefect task events emitted for tens of minutes to hours,
* SLURM keeps the job allocated until the wallclock limit kills it,
* completed-rule count stops increasing.

We have direct evidence of the failure mode from a controlled
24-job sweep on `mini-cap7` (7 heaviest cap7_atm rules, 3 ensemble
copies × 8 (W, mem-per-worker) configurations, see
`OPTIMIZATION_PLAN.md` § Round 4):

| W × TPW × mem | total slots | deadlocks (out of 3) |
|---|---|---|
| 2 × 4 × 64 GB | 8  | 0  (current production default — clean) |
| 3 × 4 × 32 GB | 12 | 1 |
| 3 × 4 × 48 GB | 12 | 0 |
| 4 × 4 × 16 GB | 16 | 0 |
| 4 × 4 × 24 GB | 16 | 2 |
| 4 × 4 × 32 GB | 16 | 1 |
| 4 × 4 × 40 GB | 16 | 1 |

Deadlock probability is non-monotonic in memory and concentrated at
mid-memory + high-slot configurations. Once `collapse_steps=true`
(commit `3169ce5` — collapses 13 pipeline steps into one Prefect
task) is applied to the same sweep, deadlocks drop substantially but
not to zero (`4×4×40` still produced 1/3). The first observation —
that 2×4×64 has been the only consistently safe production
configuration — is itself evidence of the same deadlock pattern: the
configuration ran below the threshold where the pattern triggers.

This is **not a memory bug** (nothing is OOMing — RSS and cgroup
peaks are well under their limits), and it is **not the
HLGExprSequence pickle bug** (that bug surfaces as a thread-lock
serialisation failure across task boundaries; we already addressed it
behind `PYCMOR_PREFECT_COLLAPSE=1`/`collapse_steps`, see Round 4b in
`OPTIMIZATION_PLAN.md`). The deadlocks remain, with different
fingerprint: workers genuinely idle, not crashing, just unable to
proceed.

The structural cause is **nested submission of bounded thread-pool
work**: pycmor's per-rule "Process rule" Prefect task itself spawns a
Prefect subflow whose tasks share the *same* DaskTaskRunner thread
pool. When enough rules become concurrent, parents fill the pool and
children block waiting for a parent to release a thread it cannot
release until its children finish — a classic resource-allocation
deadlock.

Goal: eliminate this deadlock pattern from pycmor without sacrificing
the Prefect features the codebase relies on (per-rule cache_policy,
on_completion / on_failure hooks, run-name labelling, retry
semantics). Make it safe to run at higher concurrency than the
current 2×4×64 default.

---

## 2. Current architecture (verbatim, with file references)

The relevant control flow for one rule, when `parallel: true`:

```
cmorizer.process()
  └─ for each rule:
       └─ Cmorizer._process_rule(rule)              # @task("Process rule")
            └─ for pipeline in rule.pipelines:
                 └─ pipeline.run(data, rule)         # Pipeline.run
                      └─ Pipeline._run_prefect(...)
                           └─ dynamic_flow = @flow(task_runner=DaskTaskRunner(...))
                                def dynamic_flow(data, rule):
                                    return self._run_native(data, rule)
                           └─ dynamic_flow(...)      # SUBFLOW invocation
                                └─ for step in self.steps:
                                     └─ step(data, rule)   # each step is a @task
```

Source-level references:

* **Outer task wrapper**:
  `src/pycmor/core/cmorizer.py:1087-1107`,
  `Cmorizer._process_rule`. Decorated with
  `@task(name="Process rule")`.
* **Subflow factory**:
  `src/pycmor/core/pipeline.py:177-203`,
  `Pipeline._run_prefect`. Constructs a fresh `@flow` per call with a
  `DaskTaskRunner`. The factory captures the cluster's scheduler
  address; if no cluster has been assigned via `assign_cluster(...)`,
  it falls back to a local cluster.
* **Step prefectisation**:
  `src/pycmor/core/pipeline.py:108-150`, `Pipeline._prefectize_steps`.
  Each step in the pipeline is wrapped as a `Task` (or one collapsed
  task if `collapse_steps=true`).
* **The cluster shared across rules**: a single `LocalCluster` (or
  `SLURMCluster`) is created once by `Cmorizer.__init__` /
  `Cmorizer._setup_cluster()` (see `core/cmorizer.py`,
  `_setup_cluster` and adjacent methods). All rules' `_run_prefect`
  attach to the same scheduler.

So the Dask scheduler sees N `_process_rule` tasks (N = total rules
≈ 52 for cap7_atm) and, **inside each one**, M further tasks
(M = number of pipeline steps per rule, currently 1 with collapse or
13 without). All competing for `W × TPW` thread slots.

---

## 3. Mechanism of the deadlock

Define:

* `S = W × TPW`: total worker thread slots.
* `P_active`: number of Process-rule parent tasks currently running
  (each occupies one thread).
* `C_active`: number of pipeline child tasks currently running
  (each occupies one thread).
* `P_active + C_active ≤ S` always.

Each parent that is *running its body* is blocked at the synchronous
call `result = dynamic_flow(data, rule_spec, return_state=True)`
(`pipeline.py:197`). The parent thread cannot make progress until
the subflow returns. The subflow returns only when its child task(s)
have completed. The child tasks need a free thread.

The deadlock condition: `P_active = S` and `C_active = 0`. No child
can start. No parent will release until a child starts. No exit
path.

Why probabilistic: Prefect/Dask schedules submission greedily and
asynchronously. The Dask scheduler may either (a) schedule a
parent's body to start before another parent's child gets a chance,
or (b) prioritise children if they were submitted first. Empirically
(b) is sometimes the case at low slot counts but degrades at higher
slot counts. The exact Dask scheduling policy depends on
`distributed.scheduler.allowed-failures`, the
`order` heuristic, and timing of submissions.

Why mid-memory configurations show *more* deadlocks than tight ones:
in `4×4×16`, dask-nanny aggressively kills workers that exceed
budget; the kill+restart cycle effectively breaks the resource hold
because Prefect retries the killed task on a different worker. The
deadlock can't lock in. In `4×4×24` and `4×4×32`, workers stay alive
just long enough that the deadlock pattern stabilises; in `4×4×64`
the slot count is low enough that the over-subscription doesn't
form. So the tight-memory configurations are accidentally robust for
the wrong reason (workers churning), and the generous-memory ones
are robust for the right reason (lower N parents per pool).

---

## 4. Proposed change: eliminate the inner subflow

### 4.1 Design

Replace the subflow with a direct synchronous call. The pipeline
runs *natively* inside the Process rule task — no second Prefect flow
boundary. Pseudocode delta in `Pipeline._run_prefect`:

**Before** (current, `pipeline.py:177-203`):

```python
def _run_prefect(self, data, rule_spec):
    cmor_name  = rule_spec.get("cmor_name")
    rule_name  = rule_spec.get("name", cmor_name)
    addr = self._cluster.scheduler.address if self._cluster else None

    @flow(
        flow_run_name=f"{self.name} - {rule_name}",
        description =rule_spec.get("description", ""),
        task_runner=DaskTaskRunner(address=addr),
        on_completion=[self.on_completion],
        on_failure  =[self.on_failure],
    )
    def dynamic_flow(data, rule_spec):
        return self._run_native(data, rule_spec)

    result = dynamic_flow(data, rule_spec, return_state=True)
    if result.is_failed():
        exc = result.result(raise_on_failure=False)
        if isinstance(exc, BaseException):
            raise exc
        raise RuntimeError(f"Pipeline '{self.name}' failed for rule '{rule_name}': {exc}")
    return result.result()
```

**After** (proposed):

```python
def _run_prefect(self, data, rule_spec):
    """Run the pipeline synchronously in the calling task's thread.

    No inner subflow. The wrapping `@task(name="Process rule")` in
    cmorizer already provides the run-name + cache + retry boundary
    that the old subflow contributed; nesting a second flow inside
    the task adds nothing but a slot deadlock window.
    """
    cmor_name = rule_spec.get("cmor_name")
    rule_name = rule_spec.get("name", cmor_name)
    logger.info(f"Pipeline '{self.name}' running for rule '{rule_name}'")
    try:
        result = self._run_native(data, rule_spec)
    except BaseException as exc:
        # Preserve the on_failure callback semantics:
        try:
            self.on_failure(flow=None, flowrun=None,
                            state={"name": rule_name, "exception": exc})
        except Exception as cb_exc:
            logger.warning(f"on_failure callback raised: {cb_exc}")
        raise
    try:
        self.on_completion(flow=None, flowrun=None,
                           state={"name": rule_name})
    except Exception as cb_exc:
        logger.warning(f"on_completion callback raised: {cb_exc}")
    return result
```

`_run_native(self, data, rule_spec)` already exists at
`pipeline.py:122-125` and runs the pipeline steps synchronously
in-thread:

```python
def _run_native(self, data, rule_spec):
    for step in self.steps:
        data = step(data, rule_spec)
    return data
```

This already does what we need. The change is removing the subflow
wrapper from `_run_prefect` and routing through `_run_native`
directly; the `@flow` and `DaskTaskRunner` lines are deleted.

### 4.2 What is lost

* **The inner subflow's run name and Prefect UI page**. The Prefect
  UI currently shows `bench_ua_6hr_pipeline - ua_6hr_pl7h` as a
  separate flow run nested under the `Process rule` task. After the
  change, the user sees only the outer `Process rule` task with the
  rule name. Mitigation: rename the outer task to embed the rule and
  pipeline name (e.g. `Process rule[ua_6hr_pl7h via FrozenPipeline]`).
  Prefect supports parameterised task names.
* **Per-step Prefect task tracking and caching for the steps inside
  the pipeline**, but only when `collapse_steps=False`. With
  `collapse_steps=True` (the recommended config after
  `OPTIMIZATION_PLAN.md` Round 2 + 4) there is already only one
  Prefect task per pipeline, so there is nothing further to lose
  here. We propose making `collapse_steps=True` the **default** as
  part of this PR — see § 7.
* **The on_completion / on_failure hooks attached to the inner flow**.
  These are currently `Pipeline.on_completion` / `Pipeline.on_failure`,
  see `pipeline.py:155-171`. Both are static methods that log
  pipeline completion / failure to the report log. The proposed
  patch invokes them directly with synthetic arguments rather than
  via Prefect's flow lifecycle. Trade-off: they no longer receive a
  real `flow` and `flowrun` object, just a stub dict. For pycmor's
  current callbacks (which only `logger.info` / `logger.error` the
  arguments) the dict is sufficient; if downstream code grows to
  inspect Prefect's `flowrun` attributes we'd need to revisit.

### 4.3 What is gained

* **The deadlock window is eliminated**. The `Process rule` task is
  the *only* level submitting work to the dask pool. There is no
  second-level submission that could over-subscribe.
* **Memory / slot budgeting becomes predictable**: with one task per
  rule, `S = W × TPW` is the literal cap on rule concurrency. To
  schedule 16 concurrent rules safely we need 16 slots, full stop —
  no longer N×2 = 32.
* **Higher-concurrency configs become viable in production**:
  `4×4×16`, `4×4×32` and `3×4×48` all looked promising in mini-cap7
  but had probabilistic deadlock failures in `OPTIMIZATION_PLAN.md`
  Round 4. With the deadlock removed these become first-class
  candidates and one of them likely yields the 15-23 % wall
  reduction observed in the mini-cap7 sweep, but reliably.
* **Heartbeat logging** (separate small change shipping alongside
  this) gives operators an unambiguous "still working" signal during
  the long save_dataset runs that previously looked indistinguishable
  from a hang.

---

## 5. Risk assessment

| risk | likelihood | impact | mitigation |
|---|---|---|---|
| on_completion/on_failure callbacks break because they expect Prefect-shaped arguments | low (current implementations only `logger.info(state)`) | low (logging) | provide the dict shape and document it; add a one-line test |
| existing test suite mocks the subflow shape | low | low | run `tests/unit/test_pipeline.py` post-patch; expand only if a test breaks |
| External agents call `Pipeline._run_prefect` directly and expect a `Completed` State | low (it is a private method) | low | keep behaviour: when the pipeline succeeds, return the result data; when it fails, raise — same as the current code |
| Loss of per-step Prefect cache reuse (cache_key_fn etc.) | medium *if* anyone re-enables non-collapsed pipelines | low (cache wasn't reliably hitting anyway — see HashError noise in earlier logs) | document that `collapse_steps=True` is the production-tested path |
| Lower-priority: Prefect UI shows fewer entities per rule | n/a | low | rename outer task to embed pipeline name |
| Hidden code paths assume a flow-context exists when the steps run (e.g. `prefect.context.get_run_context()`) | medium | medium | pre-flight grep across `pycmor/std_lib/` for `get_run_context` and any decorator-with-side-effects patterns; mock test |
| Killed parent task does not propagate cancellation to in-flight pipeline body | medium | medium | the **current** subflow design has the same property — Prefect's dask runner cancels from outside; the inner flow's tasks are already in the same boat. The new design is no worse. |

The single largest unknown is the **prefect.context** pre-flight
audit. We have not yet grep'd the pipeline-step library for context
look-ups. This is item 1 in the validation plan below.

---

## 6. Validation plan

### Phase 6.1 — static audit (1 hour)

* `git grep -nE "from prefect\.context|get_run_context|TaskRunContext"` in `src/pycmor/`.
* If any pipeline step calls one of these, mark it as needing rework
  before the patch lands.
* Diff the existing `tests/unit/test_pipeline.py` and
  `tests/unit/test_files.py` against the proposed change. Identify
  any test that asserts a `Completed` state shape. Adjust as needed.

### Phase 6.2 — single-rule smoke test (30 min)

* `examples/cmip7_bench_hr_ua_6hr.yaml` at `parallel: false` (default)
  and `parallel: true`. Confirm `pycmor process` succeeds end-to-end
  in both modes. The single-rule case is small enough that any
  surface-level break shows immediately.

### Phase 6.3 — mini-cap7 re-sweep (3 hours)

* Re-run the 24-job mini-cap7 sweep
  (`examples/launch_mini_cap7_sweep.sh`) with the new pipeline
  implementation. Goal: zero deadlocks across all 8 configurations.
  Compare wall to Round 4b (`PYCMOR_PREFECT_COLLAPSE=1`) — should
  match or improve, never regress.
* Spot-check: run the existing `pycmor_bench_hr_ua_6hr.yaml` ensemble
  (5 ensemble × source data) — wall should match the warm-cache
  baseline (~2:45) within ensemble variance.

### Phase 6.4 — full cap7_atm validation (3 hours)

* `submit_hr_year.sh` against year 1587 cap7_atm at the new default
  config (likely `3×4×48` or `4×4×16` based on Round 4b). Acceptance
  criteria:
  * ≥ 48/52 rules complete (matches current production baseline);
  * wall ≤ 2:30 (15-23 % improvement over the 2:57 baseline);
  * zero `KilledWorker` events;
  * zero deadlock symptoms (no log silence > 5 min after the heavy
    rules have started, with the heartbeat patch from issue #1
    confirming progress within each save).

### Phase 6.5 — cross-tier regression (overnight)

* Run all 17 HR tier yamls with `submit_hr_year.sh` under the new
  defaults. None should regress vs current baseline (52-rule core
  rules, 17-rule ocean tiers, etc.).

---

## 7. Bundled changes

This proposal is for a single patch with the following pieces:

1. **`src/pycmor/core/pipeline.py`**:
   - Refactor `_run_prefect` to call `_run_native` directly, no inner `@flow`.
   - Wire on_completion / on_failure callbacks via direct calls.
   - Default `collapse_steps=True` going forward (env var
     `PYCMOR_PREFECT_COLLAPSE` becomes `=0` to opt out).

2. **`src/pycmor/core/cmorizer.py`**:
   - Optionally rename the outer `@task` to embed the rule name
     (e.g. via `task_run_name="Process rule[{rule.name}]"`).

3. **`src/pycmor/std_lib/files.py`**:
   - Add the `_Heartbeat` context manager around `save_dataset`
     (issue #1; small, independent, ships in this same PR for one
     atomic UX improvement).

4. **`tests/unit/`**:
   - Adjust tests if any assert flow-state shapes; otherwise
     expand to cover the new direct-callback path.

5. **`OPTIMIZATION_PLAN.md`**:
   - Append a Round 5 entry pointing at this design and the
     Phase 6.3-6.4 validation results.

6. **`HANDOFF_memory_pressure.md`** (the project's running
   investigation log):
   - Cross-reference the Round 4 deadlock evidence to the design
     proposal so future agents understand the context.

Estimated effort: 3-5 days of careful work, including the static
audit and validation. The actual code change is ~50 lines.

---

## 8. Alternatives considered

### 8.1 Run "Process rule" off the dask pool entirely

Use a separate `concurrent.futures.ThreadPoolExecutor` (or
`ProcessPoolExecutor`) at the top level for `_process_rule`, so dask
workers only see pipeline child tasks. This is the cleanest
separation and has been used in similar tools (e.g. some Dagster
configurations). However:

* requires changing `Cmorizer.process()` to manage a second
  executor, including how progress, retries, and exceptions
  propagate;
* loses the natural "everything is a Prefect task" narrative;
* the resulting code path is harder to reason about (two parallel
  executors, two queues, two failure semantics).

The proposed change in § 4 is strictly simpler: collapse two layers
into one. It achieves the same deadlock-elimination property with
fewer moving parts.

### 8.2 Increase `TPW` so child tasks always have headroom

E.g. set `TPW = 8` so each parent has spare threads in its own
worker. Empirically: as `TPW` grows, the deadlock window narrows but
contention on shared memory / blosc CPUs grows. The Round 4 sweep
held `TPW=4` constant precisely because lower values
(`TPW = 1, 2`) deadlock catastrophically — pycmor's earlier
investigations confirmed this.

This is a tuning band-aid; it doesn't change the structural fact
that a parent×child same-pool nesting can deadlock. Rejected.

### 8.3 Rewrite to native Dask delayed graphs (no Prefect)

Express the entire cmorize flow as a dask `delayed`/`futures`
DAG. This is the orthodox Dask approach and would let the scheduler
see the full graph upfront, avoiding nested submission. However it
is a multi-week rewrite of pycmor's orchestration layer and the
project's per-rule observability (run names, retries,
`on_completion`/`on_failure` hooks, per-task caching) would all need
re-implementation. Out of scope for the present problem.

### 8.4 Switch task runner to Prefect's `ConcurrentTaskRunner`

Prefect's default task runner uses `asyncio` rather than dask.
Avoids the dask thread pool entirely. But: pycmor's pipeline steps
are *intentionally* dask-backed (the dataset loads as a dask array,
xarray operations build a dask graph that's evaluated during
`save_dataset`). Switching the *task* runner away from dask doesn't
remove dask usage — dask still exists for the data plane. The slot
question collapses to "how many Prefect concurrent tasks" vs "how
many dask threads", and the same M-parents-blocking-N-children
shape can re-emerge depending on configuration. This adds complexity
without solving the structural issue.

---

## 9. Open questions for review

1. Are the on_completion / on_failure callbacks guaranteed to never
   inspect Prefect-flow-specific fields anywhere in the codebase?
   We will answer this in the static audit (Phase 6.1) but flag it
   here for reviewers.
2. Is anyone running pycmor with `parallel: true,
   pipeline_orchestrator: prefect_native` (i.e. without dask)? If so,
   does the proposed change affect that path? (`_run_prefect` is
   only called when the orchestrator is dask in `parallel:true` mode;
   we believe the answer is "no impact", but want a maintainer to
   confirm.)
3. The cmorizer caches Prefect *task* results (`cache_policy`).
   Does anyone actually rely on cache hits between runs of the same
   yaml? With `collapse_steps=True` becoming the default, the cache
   key changes (1 task per rule instead of 13), so any stored cache
   from before the change is invalidated. This is acceptable for
   production runs (one cmorize per simulation year) but worth
   flagging for development workflows.
4. The proposal default-flips `collapse_steps`. Is there any user
   actively relying on the 13-task-per-rule behaviour for
   per-step inspection? If so, opting back in via
   `collapse_steps: false` per-pipeline yaml is preserved.

---

## 10. Decision required

We propose **landing this patch on a feature branch and running
Phase 6.3-6.5 before merging to main**. The risk surface is small
(50 lines of code, no behavioural change for serial/single-rule mode),
the upside is large (eliminates a real production failure mode and
opens 15-23 % wall reduction on heavy yamls), and the validation
plan is well-scoped (≤ 1 working day of compute-time across the
proposed phases).

Reviewers requested for sign-off:

* pycmor maintainer for the architectural change (`pipeline.py`,
  `cmorizer.py`).
* AWI HPC team for the Lustre / SLURM behaviour the validation runs
  exercise (none expected to change but worth a sanity check).
* Any user actively relying on the per-step Prefect UI granularity.
