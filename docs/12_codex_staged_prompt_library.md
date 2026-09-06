# Codex Staged Prompt Library for the 48-Hour Multiple-Agent Project

_Copy one prompt at a time. Every paste-ready prompt begins with a Chinese task summary for auditability; its operative requirements are in English. All code, experiment artifacts, paper text, and presentation content produced by these prompts must be English._

---

## 📋 How to use this library

Use one persistent **Controller** task and no more than two concurrent implementation workers. Give each worker exclusive file ownership. Do not start a later prompt until the prerequisite gate has passed.

| Order | Prompt | Owner | Gate produced |
|---:|---|---|---|
| 0 | Controller and dashboard | Control Room | Execution control established |
| 1 | Protocol and baseline freeze | Evaluation | G0: protocol frozen |
| 2 | Metrics, provenance, and confidence | Core Product | G1: evidence contract passes |
| 3 | Granite feasibility | SLM | G2: GO / LIMITED-GO / NO-GO |
| 4 | Role-specific critics | Core Product | Reviewed-static C5 passes |
| 5 | Bounded dynamic routing | Core Product | G3: bounded C6 passes |
| 6 | Experiment runner | Evaluation | Runner and blind pack pass |
| 7 | Integration and code freeze | Controller + owners | G4: formal configuration frozen |
| 8 | Formal experiment execution | Evaluation | G5: manifest complete |
| 9 | Blind scoring and analysis | Evaluation + Jasmine | G6/G7: scores and results locked |
| 10 | Engineering paper | Paper | Evidence-bound English draft |
| 11 | Presentation | Slides | English deck and speaker notes |
| 12 | Final audit | Controller | G8: submission-readiness decision |

OpenAI's current prompting guidance recommends specifying the expected outcome, success criteria, evidence, test expectations, allowed side effects, and stopping rules for long-running work.[^1] Every prompt below therefore uses the same contract.

## 🎛️ Prompt 0 — Controller and execution dashboard

```text
中文任务摘要：你是未来48小时的项目总控 Codex。建立单一事实源、阶段门控、文件所有权和停止条件；你负责审计、集成和一致性，不要在本阶段大规模修改产品代码。

Outcome first
Establish an auditable control system for the 48-hour implementation, experiment, paper, and presentation workflow. Jasmine must be able to determine within one minute what is complete, blocked, evidenced, and awaiting a decision.

Project
C:\Users\JasmineJiang\Projects\multiple_ai_agent

Required reading
- docs/multiple_ai_agent_optimization_2day_plan.md
- the files 10–15 in the final-presentation planning package
- the current Git status, test structure, experiment assets, and SLM assets

Final artifact directory
C:\Users\JasmineJiang\Desktop\s4\hu-3.Intelligent System\@final presentation

Scope
1. Inspect the repository and record all pre-existing modified and untracked files.
2. Create G0–G8, an ownership map, dependency map, decision log, critical path, and scope-reduction order.
3. Assign exactly one writer to each file; only the Controller may accept a cross-workstream handoff.
4. Keep this setup stage read-only for product code.
5. Never infer that a stage passed because code exists; require the declared evidence.

Required artifacts
- 00A_48_hour_execution_dashboard.md
- 00B_decision_log.md
- an initial repository-state record

Dashboard fields
- stage, gate, owner, status, deadline, dependency
- expected artifact and verification evidence
- decision owner, residual risk, and next action
- protocol, evidence, code, prompt, schema, and model hashes when available

Acceptance criteria
- Every work package has one accountable owner and non-overlapping file ownership.
- Every gate has explicit pass, fail, and intentionally-reduced criteria.
- No formal run can start before G4.
- No empirical Results sentence can be treated as factual before G7.
- Existing user changes are preserved.

Verification
- Record `git status --short --branch` and the baseline test command.
- Verify that every referenced existing path opens; label future paths as pending.
- Cross-check the dashboard against the two-day optimization plan.

Stopping rules
- Stop before destructive Git operations, commits, resets, merges, or discarding user work unless Jasmine explicitly authorizes them.
- Stop if two workstreams require ownership of the same file and isolation is not possible.
- Never fabricate results, scores, runs, citations, or completion states.

Language contract
All code, comments, identifiers, documentation artifacts, experiment fields, figures, paper text, and presentation content must be English. Every Codex status or final response must begin with one concise Chinese outcome summary; all subsequent technical detail must be English.

Required handoff
中文状态摘要：
Stage / gate:
Outcome:
Completed:
Evidence:
Files changed:
Tests or runs:
Protocol deviations:
Residual risks:
Next action:
Decision needed from Jasmine:
```

## 🧪 Prompt 1 — Baseline and protocol freeze

```text
中文任务摘要：冻结当前系统基线、研究问题、六个测试案例、证据包、C1–C6条件、指标和盲评规则。在本阶段不要优化产品；目标是使之后的任何改动都能被公平比较。

Outcome first
Produce an immutable and auditable baseline plus evaluation protocol before any candidate optimization is accepted.

Project
C:\Users\JasmineJiang\Projects\multiple_ai_agent

Read first
- docs/multiple_ai_agent_optimization_2day_plan.md
- current workflow, schemas, prompts, validators, database models, tests, and SLM documentation
- 00A_48_hour_execution_dashboard.md and 00B_decision_log.md

Scope
1. Document the implemented legacy graph, final-only critic, confidence aggregation, Web/RAG behavior, model settings, Git state, environment, and baseline tests.
2. Freeze six stratified business-planning cases with materially different difficulty profiles.
3. Freeze one evidence packet and source allowlist per case; store stable source IDs and SHA-256 hashes.
4. Freeze C1 Gemini Single, C2 Gemini Multi legacy, C3 Granite Single, C4 Granite Multi legacy, C5 Gemini Multi reviewed-static, and C6 Gemini Multi bounded-dynamic.
5. Freeze academic, business, collaboration, confidence, safety, reliability, and resource metrics.
6. Freeze rubric weights and 1/3/5 anchors, failure handling, retry and exclusion rules, randomization, anonymization, stopping rules, and human blind scoring.
7. Capture one representative legacy output if available. If unavailable, preserve the failure instead of changing the protocol.

Required artifacts
- 01_evaluation_protocol.md
- 02_frozen_cases_and_evidence_manifest.csv
- baseline_manifest.json
- example_outputs/legacy_baseline.md or baseline_failure.json
- protocol and evidence-manifest hashes in the dashboard

Acceptance criteria
- All six cases have `case_id`, task brief, difficulty rationale, required sections, evidence packet, allowlist, and packet hash.
- Conditions differ only in declared factors and share the same case evidence.
- The primary quality outcome, business outcome, and safety guardrail are operationally defined.
- Failures remain in completion and usable-output denominators.
- Rating files hide architecture and model.
- The protocol calls the study an exploratory engineering pilot with `n = 6 cases`.
- No candidate output influenced the rubric.

Verification
- Run the current full test suite and save command, result, timestamp, and environment.
- Validate key uniqueness, hashes, condition differences, and absence of secrets.
- Verify that each metric has a formula, unit, source, direction, and automatic/manual classification.

Stopping rules
- If an API call hits the predeclared retry limit, record the infrastructure failure and stop retrying.
- If evidence cannot be frozen consistently, do not begin product changes.
- Do not edit product code, prompts, schemas, or metric definitions in this stage.
- Do not invent a baseline output.

Language contract
All protocol artifacts, cases, rubrics, labels, and technical content must be English. Every Codex response must begin with one concise Chinese outcome summary; all subsequent detail must be English.

Return the standard handoff from Prompt 0.
```

## 🔎 Prompt 2 — Metrics, provenance, and calibrated confidence

```text
中文任务摘要：先实现专业的 agent-level 指标、claim-to-source provenance 和可校准 confidence，再改变 Critic 架构。目标不是机械减少 low，而是减少欠置信且不增加过度自信。

Outcome first
Implement a backward-compatible evidence and confidence contract that makes every material claim auditable and produces defensible reason-coded confidence.

Project
C:\Users\JasmineJiang\Projects\multiple_ai_agent

Prerequisites
- G0 passed and hashes are recorded.
- Read the protocol, evidence manifest, current schemas, agents, writer, workflow nodes, and confidence validators.

Scope
1. Add or normalize `claim_id`, `claim_text`, `claim_type`, `evidence_status`, `source_ids`, `source_support`, `source_quality`, `source_recency`, `critic_status`, and `confidence_reason_codes`.
2. Preserve historical outputs using explicit defaults or an adapter.
3. Reject source IDs outside the frozen allowlist.
4. Treat credible frozen Web and RAG evidence as external evidence while validating direct support and authority.
5. Replace section-wide low triggered by any assumption with documented claim-level evaluation and deterministic aggregation.
6. Keep assumptions, recommendations, calculations, projections, user inputs, and external facts semantically distinct.
7. Implement the protocol's agent and collaboration metrics that can be calculated at this layer.
8. Do not add role critics or dynamic routing yet.

Required artifacts
- English code and focused tests
- docs/CONFIDENCE_PROVENANCE_SPEC.md
- 02B_confidence_provenance_change_log.md
- frozen fixtures for supported fact, assumption, unsupported claim, Web-only, RAG-only, mixed evidence, and conflicting evidence

Acceptance criteria
- Adequately supported Web-only claims are not mechanically forced to low.
- Ordinary explicit business assumptions do not force the whole section to low.
- High-impact unsupported facts remain low and block external-use readiness.
- Confidence rises only when evidence or a verified issue state changes.
- Every label exposes deterministic reason codes.
- Underconfidence falls on the frozen fixture without an increase in overconfidence.
- Historical output fixtures still load.

Verification
- Test every confidence boundary, invented source IDs, allowlist enforcement, backward compatibility, and mixed-claim sections.
- Report before/after values on the frozen fixture.
- Run targeted tests and then the complete suite; return exact commands and counts.

Stopping rules
- If the frozen metric definition must change, stop and request a protocol amendment.
- Never raise confidence by string replacement or arbitrary relabeling.
- Do not change unrelated prompts, architecture, or SLM files.

Language contract
All source, tests, schemas, fixtures, documentation, and logs must be English. Every response must begin with one concise Chinese outcome summary; all subsequent detail must be English.

Return the standard handoff from Prompt 0.
```

## 🖥️ Prompt 3 — Granite SLM feasibility and integration

```text
中文任务摘要：在本机资源限制下验证 IBM Granite 4.0 H Micro，并且只有通过 memory、schema 和 time gates 后才接入正式实验。不要重试 Qwen2.5，也不要迁移到新的托管平台。

Outcome first
Produce a documented GO, LIMITED-GO, or NO-GO decision for local Granite and, only after a pass, a reproducible integration for the SLM experiment arms.

Project
C:\Users\JasmineJiang\Projects\multiple_ai_agent

Known boundary
- approximately 15.8 GiB RAM
- Intel i7-1165G7, 4 physical / 8 logical cores
- NVIDIA MX450 with 2 GiB VRAM
- CPU-first, one process, one loaded model, limited disk

Scope
1. Inspect and preserve all existing `slm/` work and the recorded Qwen2.5 failure history.
2. Do not retry Qwen2.5 and do not test another hosted provider.
3. Configure Ollama through the project's existing client contract.
4. Freeze the exact tag, digest, quantization, context, output cap, and generation settings.
5. Run staged probes: model load; short schema; Research packet; critic schema; Finance packet; Writer batch; Single smoke; Multi smoke only if earlier gates pass.
6. Measure file size, load time, prompt/output tokens, valid@1, repair count, wall time, peak RAM/VRAM/pagefile, throughput, pruning, and failure reason.
7. Validate actual usable context; never infer it from an advertised maximum.
8. Enforce single concurrency and preserve all invalid raw outputs.

Required artifacts
- 10_hardware_and_slm_feasibility.csv or equivalent populated register
- slm_preflight_manifest.json
- exact English run instructions
- structured probe outputs
- Single/Multi smoke output only when feasible
- dashboard GO / LIMITED-GO / NO-GO decision

GO gates
- Model loads without OOM or sustained pagefile thrashing.
- Required schema probes pass on first attempt or after at most one structured correction.
- Validated context fits the compact frozen input with documented headroom.
- A component finishes within 20 minutes.
- Projected full Multi run does not exceed 90 minutes per case.

Fallback order
1. H Micro at a smaller validated context with compact packets.
2. H 1B for explicitly separate node-level feasibility.
3. SLM Single or component-level comparison only.
4. NO-GO with complete engineering failure evidence.

Verification
- Record exact commands, environment, model digest, configuration, schema results, and telemetry.
- Run focused integration tests without modifying files owned by Core Product.

Stopping rules
- Stop a component above 20 minutes or projected Multi above 90 minutes.
- Stop after two consecutive schema failures after the allowed correction.
- Stop on sustained paging, unsafe instability, or unavailable disk.
- Do not silently substitute a smaller model under C3/C4; create a new condition if the protocol is amended.
- Request narrow approval before installation or model download when required.

Language contract
All code, configuration, commands, reports, outputs, and logs must be English. Every response must begin with one concise Chinese outcome summary; all subsequent detail must be English.

Return the standard handoff from Prompt 0.
```

## 🧭 Prompt 4 — Role-specific critics and reviewed-static C5

```text
中文任务摘要：在 Research、Strategy 和 Finance 后加入专业的 role-specific critics，并保留 Writer 后的 final critic。先实现固定 review 路径；本阶段不要声称完成动态路由。

Outcome first
Deliver a reviewed-static multi-agent workflow that detects specialist defects before downstream propagation and preserves the legacy workflow behind a feature flag.

Project
C:\Users\JasmineJiang\Projects\multiple_ai_agent

Prerequisites
- G0 and G1 passed.
- Provenance schemas and reason-coded confidence are stable.

Scope
1. Define a reusable `AgentReview` contract containing role, dimension scores, issue IDs, severity, evidence gaps, `must_fix`, forbidden changes, decision, and rationale.
2. Implement role-specific policies for Research, Strategy, and Finance.
3. Research review may request one bounded evidence action. Strategy and Finance reviews may not browse or invent facts.
4. Implement at most one targeted revision per role.
5. C5 remains a fixed topology: the review stage always executes; a pass records a deterministic no-op revision result.
6. Preserve the final Writer critic.
7. Persist original output, review, revision, issue resolution, regression, and route evidence.
8. Preserve legacy final-only behavior as C2 through a feature flag.

Required artifacts
- English implementation and tests
- seeded-defect fixtures for every reviewed role
- 02C_role_critic_implementation_report.md
- one mock reviewed-static route trace

Acceptance criteria
- Each specialist receives a role-appropriate review.
- A critic cannot invent a source ID or create new evidence.
- Every role receives zero or one revision, never two.
- Revisions are issue-targeted rather than unrestricted rewrites.
- C2 and C5 are independently reproducible.
- The protocol can calculate critic precision, recall, resolution, and regression from persisted fields.

Verification
- Test pass, true defect, false positive, invented source, exact revision cap, regression, legacy flag, persistence, and mock end-to-end behavior.
- Run targeted and complete tests with exact results.

Stopping rules
- Fail immediately if any role revises twice.
- Do not accept a critic that rewrites valid content without a verified issue.
- Resolve schema conflicts with G1 before continuing.
- Do not implement conditional routing or an autonomous supervisor in this stage.

Language contract
All code, prompts, schemas, tests, logs, route names, and reports must be English. Every response must begin with one concise Chinese outcome summary; all subsequent detail must be English.

Return the standard handoff from Prompt 0.
```

## 🔀 Prompt 5 — Bounded dynamic routing and termination

```text
中文任务摘要：把 reviewed-static 工作流扩展为受限动态质量门：Critic 通过则跳过返工，未通过才定向返工一次，然后继续或安全终止。不要实现自由自治 Supervisor，也不要允许无限循环。

Outcome first
Deliver a reproducible bounded-dynamic C6 whose executed route changes from validated review state while preserving all static baselines and guaranteeing termination.

Project
C:\Users\JasmineJiang\Projects\multiple_ai_agent

Prerequisites
- Reviewed-static C5 tests pass.
- Legacy behavior and G1 contracts remain green.

Scope
1. Implement `pass -> next role`, `revise -> one targeted revision -> next role`, and `block -> human review or failed terminal state`.
2. Use one routing mechanism per decision node; never combine an unconditional outgoing edge with a dynamic command that causes both paths to execute.
3. Restrict routes to an allowlist.
4. Enforce one revision per role plus global request, token, and wall-clock budgets.
5. Persist route trace, decision reason, skipped revision, budget state, and termination reason.
6. Make the guard deterministic from the structured review even when an LLM produces that review.
7. Preserve C1–C5 exactly.
8. Describe the implementation as bounded conditional revision, not a fully autonomous supervisor.

Required artifacts
- English implementation and tests
- docs/BOUNDED_DYNAMIC_ROUTING.md
- 02D_dynamic_routing_implementation_report.md
- pass, revise, block, budget-exhausted, and timeout traces

Acceptance criteria
- Passing roles execute no revision call.
- Failing roles execute exactly one targeted revision.
- Every path terminates.
- Budget exhaustion preserves partial artifacts and a structured terminal status.
- C5 executes a fixed path while C6 executes a condition-dependent path.
- Route logs support path-efficiency, recovery, and guard-success metrics.

Verification
- Test pass, revise, block, max revision, token/request/time budget, invalid route, persistence, and absence of duplicate outgoing execution.
- Run full regression tests.

Stopping rules
- Stop integration if any role revises twice or two outgoing routes execute.
- If full C6 cannot pass inside the time box, implement one complete Research vertical slice and label the reduction before formal runs.
- Do not train or fine-tune a router, add arbitrary agents, or modify the protocol.

Language contract
All code, comments, route labels, tests, logs, and documents must be English. Every response must begin with one concise Chinese outcome summary; all subsequent detail must be English.

Return the standard handoff from Prompt 0.
```

## ⚙️ Prompt 6 — Auditable experiment runner

```text
中文任务摘要：实现可恢复、可匿名、可审计的 C1–C6 实验 runner 和指标导出，但本阶段不要执行正式实验。每个计划 run 即使失败也必须写入 manifest。

Outcome first
Deliver a tested runner that can execute the frozen matrix without manual transcription, resume safely, retain failures, and generate condition-blind scoring packs.

Project
C:\Users\JasmineJiang\Projects\multiple_ai_agent

Required inputs
- frozen protocol, case/evidence manifest, condition flags, logging contract, and dashboard hashes

Scope
1. Implement a machine-readable C1–C6 registry.
2. Load identical frozen briefs and evidence packets across matched conditions.
3. Randomize condition order within each case with a recorded seed.
4. Persist after every node and run; support idempotent resume.
5. Enforce the frozen retry policy and retain failures.
6. Produce anonymous IDs and blind files with no model, condition, route, run ID, timing, or filename leakage.
7. Export structural, citation, confidence, finance, collaboration, reliability, resource, and failure fields.
8. Keep human ratings empty and separate.
9. Add precise monotonic end-to-end and node latency if current logs only provide coarse timestamps.
10. Do not make formal provider calls.

Minimum manifest fields
experiment_version, run_id, anonymous_output_id, case_id, condition_id, model_id, model_digest, architecture_mode, critic_mode, routing_mode, protocol_hash, brief_hash, evidence_hash, prompt_hash, schema_hash, code_freeze_hash, seed, start_utc, end_utc, elapsed_seconds, status, value_status, failure_category, retries, requests, prompt_tokens, completion_tokens, actual_api_cost, peak_ram_gib, peak_vram_gib, context_limit, pruning_occurred, route_trace_path, output_path, output_hash, and log_path.

Required artifacts
- runner code and tests
- docs/EXPERIMENT_RUNNER.md
- initialized manifest and metric schemas
- blind-scoring fixture
- resume, failure, and leakage fixtures

Acceptance criteria
- A complete fixture matrix runs with no external API.
- Resume never duplicates or overwrites a canonical completed run.
- Failures remain in the matrix.
- Blind files contain no condition leakage.
- Matched evidence hashes are identical.
- Every automatic metric traces to raw evidence.
- Formal mode refuses to start without all freeze hashes.

Verification
- Test success, schema failure, timeout, quota, context overflow, interruption, resume, retry exhaustion, blind stability, leakage, hash mismatch, and deterministic metrics.
- Run the full suite and report exact results.

Stopping rules
- Do not enable formal mode if matched evidence equality, safe resume, or blinding fails.
- Do not fabricate unavailable telemetry; use a reason-coded missing status.
- Do not change cases, rubric, or frozen scores.

Language contract
All code, comments, field names, manifests, test fixtures, and documentation must be English. Every response must begin with one concise Chinese outcome summary; all subsequent detail must be English.

Return the standard handoff from Prompt 0.
```

## 🔒 Prompt 7 — Integration, smoke tests, and code freeze

```text
中文任务摘要：集成各工作包、执行完整测试和每个可行条件的单案例冒烟，并生成正式实验冻结清单。不要在冒烟失败时绕过测试或偷偷缩减条件。

Outcome first
Produce a defensible G4 code freeze in which the protocol, product, prompts, schemas, evidence, model settings, runner, and failure handling are mutually consistent.

Project
C:\Users\JasmineJiang\Projects\multiple_ai_agent

Scope
1. Review each worker handoff and owned-file diff.
2. Resolve only integration defects; do not add new features.
3. Run targeted tests, full tests, and one mock end-to-end route for legacy, reviewed-static, and bounded-dynamic modes.
4. Run one real smoke per feasible C1–C6 condition under predeclared limits.
5. Verify evidence equality, source allowlists, route caps, failure persistence, resume, and blind-file leakage.
6. Record Git state or a patch hash, dependency lock, prompts, schemas, evidence, configuration, models, and hardware.
7. Mark unavailable conditions `gate_failed` or `intentionally_reduced` with an explicit reason.

Required artifacts
- 03A_code_and_config_freeze_manifest.json
- 03B_smoke_and_test_report.md
- updated dashboard and decision log

Acceptance criteria
- Full tests pass or every failure is scoped and accepted before formal work.
- Every feasible condition has a successful smoke; every infeasible condition has gate evidence.
- No two conditions differ outside their declared factors.
- The runner writes failures and cannot overwrite canonical output.
- All freeze hashes are recorded.
- Jasmine explicitly approves `G4 CODE FREEZE`.

Stopping rules
- Do not start formal runs without Jasmine's approval.
- Stop on source violations, second revisions, uncontrolled loops, hash mismatch, blind leakage, or data overwrite.
- Do not commit or discard pre-existing changes without explicit authorization.
- After freeze, only a P0 defect may change code; such a change requires a new experiment version and reruns of all affected comparisons.

Language contract
All reports, logs, labels, tests, and implementation content must be English. Every response must begin with one concise Chinese outcome summary; all subsequent detail must be English.

Return the standard handoff from Prompt 0 and a single GO / NO-GO recommendation.
```

## 🚦 Prompt 8 — Formal experiment execution

```text
中文任务摘要：在 Jasmine 明确批准 code freeze 后执行冻结的最多36次正式实验。不得边跑边调参、根据输出好坏选择重跑，也不得删除失败结果。

Outcome first
Complete the frozen pilot matrix, or its predeclared reduced version, with a terminal and auditable record for every planned run.

Project
C:\Users\JasmineJiang\Projects\multiple_ai_agent

Prerequisites
- G0–G4 passed.
- Jasmine has explicitly written `APPROVE G4 CODE FREEZE`.

Matrix
- C1: Gemini Single, 6 cases
- C2: Gemini Multi legacy, 6 cases
- C3: Granite Single, 6 cases if feasible
- C4: Granite Multi legacy, 6 cases if feasible
- C5: Gemini Multi reviewed-static, 6 cases
- C6: Gemini Multi bounded-dynamic, 6 cases

Scope
1. Recheck all hashes before each block.
2. Execute randomized conditions within case blocks.
3. Run Granite sequentially with single concurrency.
4. Persist output, logs, telemetry, route, claims, errors, and manifest rows immediately.
5. Apply only the frozen retry and stop rules.
6. Generate blind artifacts without inspecting quality to decide reruns.
7. Report block-level progress and remaining time.

Required artifacts
- populated run, node, claim, failure, and telemetry records
- immutable raw outputs and hashes
- blind packs
- 03B_formal_run_completion_report.md

Acceptance criteria
- Every planned case-condition row ends as success, failed, gate_failed, or intentionally_reduced.
- No row disappears and no failure is excluded from completion or usable-output denominators.
- Matched runs share protocol, case, evidence, and schema hashes.
- Every deviation has time, reason, affected comparisons, and decision owner.
- Outputs are anonymized before rating.

Reduction order
1. Remove sentinel repeats.
2. Remove optional SLM transfer checks.
3. Reduce Granite Multi to Single plus node-level feasibility.
4. Reduce full bounded dynamics to the previously declared Research vertical slice.
Never remove C1/C2, evidence control, failure logging, or the confidence safety guardrail unless infrastructure makes them impossible.

Stopping rules
- Apply the frozen Granite time/memory/schema limits.
- Stop on Gemini quota exhaustion after the frozen retry, source allowlist violation, hash mismatch, a second role revision, or blind leakage.
- If a P0 implementation defect appears, pause every run, record a protocol amendment, change experiment version, and rerun every affected condition from one version.
- Never mix pre-fix and post-fix outputs as one condition.

Language contract
All run artifacts, generated plans, logs, fields, reports, and labels must be English. Every response must begin with one concise Chinese outcome summary; all subsequent detail must be English.

Return the standard handoff from Prompt 0 after each condition block and at completion.
```

## 📊 Prompt 9 — Blind scoring, analysis, and figures

```text
中文任务摘要：从冻结运行中生成匿名评分包、自动指标、配对统计、图表和 failure analysis。Jasmine 负责主要人工评分；Codex 不得自行填主观质量分或补造缺失数据。

Outcome first
Produce a traceable results package in which every number maps to a frozen artifact, every main comparison is paired by case, and uncertainty plus failure are visible.

Project
C:\Users\JasmineJiang\Projects\multiple_ai_agent

Phase A before human scoring
1. Validate the planned matrix, terminal statuses, hashes, and failure classification.
2. Generate randomized blind output IDs and a blank English scoring form.
3. Scan every blind artifact for condition/model/route leakage.
4. Provide Jasmine with a concise scoring guide, frozen anchors, and expected time.
5. Stop before subjective outcome analysis until Jasmine returns the locked ratings.

Phase B after Jasmine writes `BLIND SCORING COMPLETE`
1. Validate rating ranges, missingness, hidden duplicates, and mapping integrity; then lock scores.
2. Calculate automatic agent, collaboration, confidence, business, reliability, and resource metrics.
3. Use case as the experimental unit; calculate paired differences, positive-case counts, medians/IQR, standardized effects where defensible, and case-cluster bootstrap intervals.
4. Label exact Wilcoxon or permutation p-values exploratory.
5. Estimate C2−C1, C4−C3, Gemini−Granite within architecture, architecture-by-model interaction, C5−C2, and C6−C5 where data exist.
6. Analyze completion-adjusted utility, latency, cost, edit time, critic effectiveness, confidence calibration, and failure modes.
7. Never claim population-level superiority from six cases.

Required artifacts
- locked blind evaluation file
- final result tables
- paired, interaction, ablation, Pareto, calibration, route, completion, and failure figures
- failure analysis and statistical log
- scripts, tests, and per-figure data sidecars

Acceptance criteria
- Every table cell and figure point is regenerated from source files.
- Failures stay visible.
- Human, deterministic, and LLM-judge metrics are separate.
- Missingness uses explicit reason categories.
- Repeats are not counted as independent cases.
- Each RQ maps to evidence or an explicit limitation.

Verification
- Test joins, duplicate/missing detection, known-answer fixtures, bootstrap seed, figure data exports, and run counts.
- Cross-check all headline values with the run manifest.

Stopping rules
- If ratings are incomplete, return the scoring handoff and stop; never fill them.
- Regenerate blind IDs before scoring if leakage exists.
- Omit or qualify statistics unsupported by the sample.
- Do not modify formal outputs, ratings, protocol, or frozen conditions.

Language contract
All analysis, tables, figures, captions, forms, and reports must be English. Every response must begin with one concise Chinese outcome summary; all subsequent detail must be English.

Return the standard handoff from Prompt 0.
```

## 📝 Prompt 10 — Evidence-bound engineering paper

```text
中文任务摘要：根据锁定的代码、实验数据和图表撰写英文 Master Practical 工程论文，并系统回答问题1–14。先完成证据约束的技术初稿，再逐节使用 academic-humanizer；不能改变数字、引用或结论边界。

Outcome first
Produce a defensible English engineering paper at Heidelberg University DSBA Master Practical “Intelligent Systems” level, with every central claim linked to code, experiment evidence, a table, a figure, or an explicit limitation.

Context
- 8 ECTS Master Practical
- target quality range approximately German grade 1.5–2.0, without claiming or guaranteeing a grade
- exploratory engineering pilot
- AI-use disclosure is outside scope and must not be introduced

Required coverage
1. Research task.
2. Agentic architecture.
3. Roles and communication contracts.
4. Framework choice.
5. Prompt design and research.
6. SLM choice.
7. Memory and context management.
8. RAG, controlled Web Research, and evidence credibility.
9. Single-Agent evaluation.
10. Multi-Agent final-task, collaboration, failure, and fair-comparison evaluation.
11. Ablation study.
12. Evaluation reliability.
13. Human-in-the-loop.
14. Safety, reproducibility, and engineering reliability.

Scope
1. Write Methods only from implemented facts and freeze manifests.
2. Write Results only from locked result tables.
3. Distinguish legacy static, reviewed-static, and bounded conditional revision.
4. Do not describe the deterministic Supervisor as an autonomous LLM router.
5. Explain that local inference removes some API-budget pressure but does not itself create dynamic control.
6. Treat SLM gate failures as engineering feasibility evidence, not hidden missing results.
7. State `n = 6 cases`, primary-rater limitations, and external-validity limits.
8. Use primary literature and official documentation for technical claims.
9. Create a claim-evidence matrix before language polishing.
10. After the complete technical draft, use the academic-humanizer skill one section at a time while preserving terminology, values, references, equations, uncertainty, and causal boundaries.

Required artifacts
- English paper draft
- claim-evidence matrix
- reference audit
- language-revision log

Acceptance criteria
- Questions 1–14 are explicitly answered.
- Every Results number equals the locked table.
- Central empirical claims point to artifacts.
- Contributions, trade-offs, failures, and limitations are all present.
- No AI-disclosure section is added.
- No fabricated citation or final placeholder remains.

Stopping rules
- If G7 is not locked, write Methods and an explicitly labeled Results skeleton only.
- Remove or qualify unverified sources.
- Revert any humanization change that alters a value, result, term, or conclusion.
- Do not broaden findings beyond the frozen cases.

Language contract
The paper, tables, captions, appendices, citations, and revision logs must be English. Every response must begin with one concise Chinese outcome summary; all subsequent detail must be English.

Return the standard handoff from Prompt 0.
```

## 🎤 Prompt 11 — Thirty-minute presentation

```text
中文任务摘要：基于锁定结果和论文制作海德堡大学 DSBA Master Practical “Intelligent Systems”的30分钟英文汇报；按约23–24分钟主讲加6–7分钟问答设计，并准备技术附录和失败备选叙事。

Outcome first
Create a polished evidence-led English deck through which an examiner can understand the problem, architecture, fair evaluation, measured results, limitations, and engineering maturity within the time limit.

Context
- Heidelberg University DSBA Master Practical “Intelligent Systems”
- 8 ECTS
- target quality range approximately German grade 1.5–2.0, without a grade guarantee
- use the approved 30-minute blueprint and locked paper/results

Scope
1. Use the blueprint's 23-slide, approximately 23-minute main narrative plus appendix.
2. Keep one assertion and one primary visual per slide.
3. Use exact values, denominators, units, direction, and uncertainty on result slides.
4. Distinguish observations, interpretations, and limitations.
5. Include legacy-versus-target architecture, fair 2×2 design, C2/C5/C6 ablation, confidence calibration, Pareto trade-off, failures, and bounded conclusion.
6. Use only locked figures or create traceable figures with data sidecars.
7. Add English speaker notes containing time, transition, evidence source, and likely examiner question.
8. Include a backup slide for every fragile or incomplete arm.
9. Prefer a recorded 45–60 second product demonstration over a risky live provider call.
10. Use the available presentation skill, render the deck, and inspect every slide visually.

Required artifacts
- master_practical_presentation.pptx
- PDF backup when export is available
- speaker notes
- slide-to-evidence map
- expected questions and answers
- timed rehearsal log

Acceptance criteria
- Prepared speech is 22:45–23:15, leaving at least six minutes for questions and recovery.
- Every quantitative slide maps to one source artifact.
- Slides, charts, notes, appendix, and demo language are English.
- Static behavior is never presented as autonomous dynamics.
- Failed SLM cases and missing metrics are stated honestly.
- No universal Multi-Agent superiority is claimed.
- Render inspection finds no overlap, clipping, unreadable text, or placeholders.
- At least three rehearsals are logged; the conclusion directly answers the RQs.

Stopping rules
- If G7 is not locked, create the design skeleton only and leave explicit placeholders.
- Omit untraceable figures.
- Move secondary detail to backup instead of speaking faster.
- Do not invent results, quotes, or references.

Language contract
All slide text, charts, notes, appendix, demo content, and Q&A must be English. Every response must begin with one concise Chinese outcome summary; all subsequent detail must be English.

Return the standard handoff from Prompt 0.
```

## 🛡️ Prompt 12 — Final cross-audit

```text
中文任务摘要：对代码、实验、论文和PPT做最终交叉审计，优先发现影响可信度或成绩的阻断问题；不要为了看起来完成而隐藏缺陷、修改评分或强化不受支持的结论。

Outcome first
Issue an evidence-based READY, READY WITH DECLARED LIMITATIONS, or NOT READY decision covering code correctness, experimental integrity, paper/deck consistency, reproducibility, and presentation timing.

Project
C:\Users\JasmineJiang\Projects\multiple_ai_agent

Final artifact directory
C:\Users\JasmineJiang\Desktop\s4\hu-3.Intelligent System\@final presentation

Scope
1. Run the complete automated suite and record exact results.
2. Identify the exact formal code state and preserved user changes.
3. Verify protocol, evidence, code, prompt, schema, model, and results hashes.
4. Recalculate headline values from source artifacts.
5. Cross-check every number across CSV, tables, paper, figures, slides, and notes.
6. Cross-check terminology: legacy static, reviewed-static, bounded conditional revision, Single-Agent, Multi-Agent, Gemini, and Granite.
7. Confirm that all failures, reductions, and skipped runs remain visible.
8. Verify paper coverage of questions 1–14, citation traceability, and claim limits.
9. Render and inspect the presentation; verify rehearsal duration and backup slides.
10. Make only safe evidence-preserving corrections and escalate material contradictions.

Required artifacts
- reproducibility manifest
- final audit report
- submission checklist
- final test log
- final rehearsal log

Severity
- P0: invalid result, fabricated/inconsistent value, broken code, missing central evidence, uncontrolled loop, source violation, or unreadable deck.
- P1: unsupported central claim, incomplete reproducibility, missing required question, or talk over 30 minutes.
- P2: non-central wording, formatting, citation, or appendix polish.

Acceptance criteria
- All central values regenerate from source data.
- No paper/deck contradiction or unimplemented completed claim remains.
- Failures remain in denominators.
- Reproducibility contains hardware, software, model, context, hashes, commands, seeds, and paths.
- Prepared talk fits 23–24 minutes.
- The checklist names every deliverable and readiness state.

Stopping rules
- Do not silently repair a material result mismatch.
- Do not alter locked human ratings or formal outputs.
- Do not use destructive Git operations.
- If a P0 defect cannot be fixed without invalidating an experiment, mark that claim NOT READY and propose the safest narrower claim.
- Do not guarantee a grade.

Language contract
All audit artifacts and corrections must be English. Every response must begin with one concise Chinese outcome summary; all subsequent detail must be English.

Return the standard handoff from Prompt 0 and the final readiness classification.
```

## 🧯 Rescue prompts

### Scope reset

```text
中文任务摘要：停止范围扩张，回到当前阶段的验收目标；先报告已经发生的修改，不要擅自撤销任何文件。

Stop implementation. Report the files already changed, why each change is required for the current acceptance criteria, and which changes are optional. Revert nothing. Continue only with the smallest set that satisfies the active gate. Do not touch files owned by another workstream.
```

### Root-cause reset

```text
中文任务摘要：停止重复同一修复路线，把当前阻塞转化为可验证的根因、诊断步骤和最低风险降级方案。

Stop retrying the same approach. Return: (1) the exact failing command and error; (2) the smallest reproducible case; (3) three plausible root causes ranked by evidence; (4) one targeted diagnostic for each cause; and (5) the lowest-risk fallback that preserves interpretability. Do not increase timeouts as the primary fix.
```

### Evidence-bound status request

```text
中文任务摘要：只报告当前可验证状态，不要继续实现，也不要用计划中的动作冒充已经完成的结果。

Return the standard handoff now. Separate implemented, tested, observed, inferred, planned, and blocked items. For every completed claim, cite a file, test result, run ID, log, hash, or screenshot. Do not make changes in this response.
```

## ✅ Short user approvals

Use the shortest possible control messages:

```text
APPROVE G0 PROTOCOL
APPROVE GRANITE GO
APPROVE G4 CODE FREEZE
BLIND SCORING COMPLETE
LOCK G7 RESULTS
APPROVE PAPER CLAIMS
APPROVE FINAL DECK
```

Reject a gate with:

```text
REJECT Gx
Reason:
Required correction:
Must not change:
Deadline:
```

## 🔗 Reference

[^1]: OpenAI. “Model guidance: Prompting best practices.” https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.5
