# Evidence and Data Collection Matrix

_Operational register for a 48-hour, six-case exploratory evaluation of Single-Agent versus Multi-Agent, Gemini versus local Granite, final-only versus component-level critique, and fixed versus bounded conditional revision._

---

## 🎯 Purpose and priority

This file states **what must be collected, when it must be collected, how it is derived, and which claim becomes unavailable if it is missing**. Persistent field names, artifact names, chart labels, paper terminology, and presentation terminology are English.

- **P0 — mandatory:** without it, a core research question cannot be answered fairly, a central result cannot be audited, or a safety/reproducibility claim is invalid.
- **P1 — strengthening:** materially improves engineering depth or business interpretation but does not invalidate the primary comparison if transparently absent.

Multi-agent benchmarks increasingly separate task performance, collaboration, coordination failure, and resource cost rather than relying on one final-output score.[^1][^2] This register follows that multidimensional principle while keeping the primary study small enough for a two-day engineering sprint.

## ⏱️ Collection calendar

| Stage | Hours | Collect and freeze | Exit condition |
|---|---:|---|---|
| S0 Protocol Freeze | 0–2 | RQs, estimands, C1–C6, six cases, evidence snapshots, rubric, thresholds, seeds | Hashes exist before candidate optimization |
| S1 Baseline and Instrumentation | 2–5 | Legacy output, old confidence, route, Git/test/environment baseline, precise logging | Baseline retained and telemetry fixture passes |
| S2 Implementation Evaluation | 5–10 | Provenance, confidence, critics, gates, route traces, seeded defects, tests | G1–G3 evidence passes |
| S3 SLM Gates and Code Freeze | 5–12 in parallel | Hardware, model identity, memory/schema/time probes, condition diff, code/config hashes | GO/LIMITED-GO/NO-GO plus G4 approval |
| S4 Formal Runs | 12–24 | Run/node/claim/route/resource/error records for every planned row | All planned rows have a terminal status |
| S5 Blind Evaluation | 24–32 | Anonymous ratings, claim audits, edit time, critic adjudication, hidden repeats | Human scores and mapping locked |
| S6 Analysis | 32–36 | Paired effects, uncertainty, failures, calibration, Pareto and figure sidecars | Result tables regenerate from source files |
| S7 Paper, Slides, Audit | 36–48 | Claim-evidence map, reproducibility, limitations, PPT sources, rehearsal | Every reported claim maps to evidence |

Do not postpone run-level logging until S6. Information that was not recorded at execution time—especially latency, memory peaks, route decisions, retries, and human intervention—cannot be reconstructed reliably afterward.

## 🧪 Frozen condition contract

| Condition | Architecture and model | Review/control | Planned |
|---|---|---|---:|
| C1 | Single Agent · Gemini 2.5 Flash | Common final validation | 6 |
| C2 | Multi-Agent · Gemini 2.5 Flash | Legacy final-only critic, static route | 6 |
| C3 | Single Agent · Granite 4.0 H Micro Q4_K_M | Common final validation | 6 |
| C4 | Multi-Agent · Granite 4.0 H Micro Q4_K_M | Legacy final-only critic, static route | 6 |
| C5 | Multi-Agent · Gemini 2.5 Flash | Role critics, fixed review path, at most one revision | 6 |
| C6 | Multi-Agent · Gemini 2.5 Flash | Role critics, revision only on gate failure, at most once | 6 |

The experimental unit is `case_id`: **`n = 6 cases`**. Thirty-six planned runs are executions, not thirty-six independent observations.

Within one case, matched conditions must share:

- `brief_hash`
- `evidence_snapshot_hash`
- source allowlist and source IDs
- context and output ceilings
- temperature and seed policy where supported
- schema version
- applicable prompt content and formatting constraints
- one structured-output correction allowance

C2 → C5 may change only component review and the fixed targeted revision behavior. C5 → C6 may change only fixed versus conditional revision execution. Generate and archive a machine-readable condition diff before G4.

## 🔑 Keys and integrity rules

Use these stable keys:

```text
experiment_version
protocol_version
case_id
condition_id
run_id
node_event_id
claim_id
source_id
anonymous_output_id
```

Automated integrity assertions:

1. `run_id` and `node_event_id` are globally unique.
2. Every planned case-condition pair has one manifest row even when `failed`, `gate_failed`, or `intentionally_reduced`.
3. One case-condition pair has at most one canonical run per experiment version.
4. `brief_hash` and `evidence_snapshot_hash` are identical across matched conditions.
5. C2, C5, and C6 differ only in preregistered feature flags.
6. Every claim `source_id` belongs to the case allowlist.
7. Blind artifacts contain no model, condition, route, run ID, filename, or timing information.
8. A material post-freeze fix creates a new `experiment_version`.
9. Failures remain in completion, usable-draft, and unconditional-utility denominators.
10. Missingness uses one explicit value:

```text
observed
not_applicable
structurally_missing_due_failure
not_collected_protocol_deviation
```

Do not write zero for `not_applicable` and do not use an ordinary blank for a failure-caused missing value.

## 📋 Protocol, case, and input evidence

| ID / priority | Field or artifact | When and method | Source | Required for / missing consequence |
|---|---|---|---|---|
| I01 · P0 | `experiment_version`, `protocol_version`, owner, creation UTC, protocol hash | S0 · manual then hash | `01_evaluation_protocol.md` | Methods and version isolation; otherwise rules are ambiguous |
| I02 · P0 | RQ, hypothesis, estimand, direction, decision threshold | S0 · freeze before outputs | Protocol | RQ conclusions; otherwise post-result reframing is possible |
| I03 · P0 | `case_id`, domain, difficulty, risk, case rationale | S0 · manual | Frozen case manifest | External-validity boundary; otherwise case diversity is unknown |
| I04 · P0 | Brief JSON, SHA-256, word/token count, required sections | S0 · automatic hash | Frozen case folder | Fairness and task adherence; otherwise input variance confounds effects |
| I05 · P0 | Source ID, URL, publisher, date, retrieval UTC, type, authority, snapshot, content hash | S0 · retrieve and verify | Evidence manifest/snapshots | Evidence credibility and later claim audit |
| I06 · P0 | Packet and allowlist hashes, source count, snapshot tokens | S0 · automatic | Evidence manifest | Same-evidence comparison; otherwise model and retrieval effects mix |
| I07 · P0 | Planned row, within-case order, block, randomization seed | S0 · seeded script | Empty run manifest | Controls time, quota, and thermal order effects |
| I08 · P0 | Retry, inclusion, infrastructure-failure, and exclusion rules | S0 · manual | Protocol | Prevents selective removal of failures |
| I09 · P0 | Rubric dimensions, weights, 1/3/5 anchors, scored examples, rubric hash | S0 · manual | Evaluation rubric | Primary human outcome and rating consistency |
| I10 · P0 | Legacy run/output hash, section confidence, engine version | S1 before fixes · export | `data/app.db`, output files | Before/after confidence narrative; otherwise baseline is retrospective |
| I11 · P1 | Demo brief, expected flow, screenshots/recording plan | S1 · manual | Demo manifest | Presentation resilience; does not affect primary analysis |

## ⚙️ Configuration and fairness evidence

| ID / priority | Field or artifact | When and method | Source | Required for / missing consequence |
|---|---|---|---|---|
| C01 · P0 | Provider, exact `model_id`, revision/digest, quantization | S3 and every run · automatic | Config and model runtime | Exact LLM/SLM identity; generic names are not reproducible |
| C02 · P0 | Architecture, component review, dynamic revision, max revisions | S0 and every run · automatic | Condition registry | C1–C6 identity and clean ablation |
| C03 · P0 | Workflow, prompt, schema, confidence-engine versions | Every run · automatic | DB/log snapshot | Separates historical and candidate outputs |
| C04 · P0 | Prompt paths and SHA-256 per node | S3 · automatic | Freeze manifest | Excludes hidden prompt drift |
| C05 · P0 | Temperature, seed support, context, output cap, prompt cap | Every run · automatic | Run config | Model budget fairness |
| C06 · P0 | Request, token, node-time, and wall-time budgets | S3/run start · automatic | Budget config | Explains structured termination and cost |
| C07 · P0 | Structured mode, schema repair limit, retry/backoff | Every run · automatic | Client config | Valid@1 and reliability comparison |
| C08 · P0 | Formal Web disabled, frozen-packet RAG, allowed tools | Every run · assertion | Config audit | Prevents live retrieval from contaminating matched evidence |
| C09 · P0 | Chunking, overlap, batching, pruning, retained fields | Every run · automatic | Context config | Explains SLM/context quality effects |
| C10 · P0 | Locale, timezone, currency, and units | S0 · assertion | Protocol | Prevents inconsistent dates and finance values |
| C11 · P0 | Full condition-diff report | S3 · script | `condition_config_diff` | Audits that only declared factors changed |
| C12 · P1 | Safety/tool/export approval policies | S3 · snapshot | Reproducibility manifest | Supports HITL and safety discussion |

## 🚦 Run-level evidence

Persist run fields incrementally in `data/app.db`, `run_manifest.csv`, immutable outputs, and JSONL logs. The current database already stores run/version/input/token/cost/output/error fields, but verify whether precise monotonic elapsed time exists; add it before formal execution if only coarse timestamps are available.

| ID / priority | Field or artifact | When and method | Unit/status | Required for / missing consequence |
|---|---|---|---|---|
| R01 · P0 | IDs, version, case, condition, canonical/repeat | S4 · automatic | strings/boolean | Joins and paired analysis |
| R02 · P0 | Planned, observed, terminal, and value status | S4 · automatic | controlled enum | Honest completion denominator |
| R03 · P0 | Start/end UTC and monotonic elapsed | S4 · automatic | seconds | End-to-end latency and Pareto analysis |
| R04 · P0 | Prompt/completion/total tokens, requests, retries | S4 · client logs | counts | Coordination and dynamic overhead |
| R05 · P0 | Actual provider billing in original currency; missing reason | S4 · automatic/manual import | currency | Cost per usable draft; never infer a price |
| R06 · P1 | Time to first schema-valid draft | S4 · automatic | seconds | Product waiting time |
| R07 · P0 | Output path/hash, words/tokens, section count | S4 · automatic | counts/hash | Confirms the rated artifact is original |
| R08 · P0 | Brief/evidence/config/prompt/schema/code hashes | S4 · automatic | SHA-256 | Detects formal-run drift |
| R09 · P0 | Final schema, citation validation, external-use readiness | S4 · validators | booleans + reasons | Usable-draft rate and safety |
| R10 · P0 | Human interventions, categories, minutes | S4/S5 · timed manual log | count/minutes | Hidden labor and HITL |
| R11 · P0 for SLM | Peak RAM, VRAM, pagefile; P1 for API arms | S4 · telemetry | GiB | Local deployment feasibility |
| R12 · P0 if present | Protocol deviation ID and note | S4 · manual | reference | Honest anomaly interpretation |

## 🧩 Node, route, and coordination evidence

| ID / priority | Field or artifact | When and method | Unit/status | Required for / missing consequence |
|---|---|---|---|---|
| N01 · P0 | Node event, run, role, attempt, revision index | S4 · automatic | IDs/count | Distinguishes original, review, and revision calls |
| N02 · P0 | Node start/end and monotonic latency | S4 · automatic | seconds | Bottleneck and P50/P95 analysis |
| N03 · P0 | Node tokens, requests, retries, provider cost | S4 · client logs | counts/currency | Coordination overhead and C5/C6 savings |
| N04 · P0 | Input/output size and hashes | S4 · automatic | tokens/chars/hash | Handoff volume and pruning |
| N05 · P0 | Schema valid@1, final validity, repair count | S4 · validator | boolean/count | SLM structured-output reliability |
| N06 · P0 | Context limit, estimated prompt tokens, pruned/truncated, sources retained | S4 · automatic | count/boolean | Explains context-induced failure |
| N07 · P0 | Critic issue IDs, severity, scores, `must_fix` | S4 · structured output | controlled schema | Enables external critic adjudication |
| N08 · P0 | Gate `pass/revise/block`, trigger, budget before/after | S4 · automatic | enum/count | Proves runtime-conditional control |
| N09 · P0 | Route from/to/reason, skipped revision, termination | S4 · automatic | structured trace | Dynamic claim and boundedness |
| N10 · P0 | Pre/post hashes, changed fields, issue resolution, regression | S4/S5 · automatic + audit | flags | Attributes critic benefit and harm |
| N11 · P0 for SLM | Prefill/generation throughput and node resource peaks | S3/S4 · runtime telemetry | tokens/s, GiB | Locates local inference bottleneck |
| N12 · P0 | Error taxonomy, retry outcome, propagation | S4 · automatic + verify | enum/boolean | Coordination failure and recovery |

Derived collaboration metrics must store numerator, denominator, formula version, and `not_applicable` where Single Agent has no collaboration process:

- handoff completeness
- provenance retention
- contribution utilization
- verified contradictions per 1,000 output tokens
- coordination tokens / total tokens
- upstream defects reaching the final output
- recoverable failures fixed / recoverable failures
- loops or budget violations / runs
- unnecessary calls / calls

## 🔗 Claim, source, and confidence evidence

Create `claim_evidence_audit.csv`. Automatically extract all claims, but use the frozen sampling policy for manual verification.

| ID / priority | Field or artifact | When and method | Values | Required for / missing consequence |
|---|---|---|---|---|
| E01 · P0 | Claim ID, run, section, text, hash | S4/S5 · extraction | text/hash | Claim-level lineage and audit |
| E02 · P0 | Claim type | S5 · automatic then verify | fact/assumption/recommendation/projection/calculation | Prevents treating assumptions as facts |
| E03 · P0 | Impact and rationale | S5 · human verify | low/medium/high | Separates safety-critical errors |
| E04 · P0 | Evidence status | S4/S5 · system + audit | sourced/needs_validation/assumption/unsupported | Confidence semantics |
| E05 · P0 | Source IDs and allowlist result | S4 · automatic | list/boolean | Detects invented sources |
| E06 · P0 | Source support | S5 · blind audit | direct/partial/contextual/none | Citation correctness, not merely presence |
| E07 · P0 | Authority, recency, conflict | S5 · metadata + verify | 0–1/NA/flag | Evidence quality distinction |
| E08 · P0 | Confidence label, score, reason codes | S4 · automatic | enum/score/list | Diagnoses low confidence |
| E09 · P0 | Legacy and new confidence on the same claim | S5 · deterministic replay | labels/scores | Separates content change from aggregator change |
| E10 · P0 | Adjudicated calibration class | S5 · human audit | appropriate low/high, over-, underconfident | Tests whether calibration improved |
| E11 · P0 | Critic issue, remediation, new evidence, resolution | S5 · join + verify | IDs/flags | Shows whether a critic repaired evidence or relabeled it |
| E12 · P0 | Claim origin and downstream retention | S5 · lineage | role/node | Detects Writer-added unsupported novelty |
| E13 · P0 | Finance origin, formula, inputs, units | S5 · deterministic check | input/benchmark/assumption/calculated | Prevents finance provenance mixing |
| E14 · P1 | Prompt-injection flag and handling outcome | S4/S5 · safety log | enum | Empirical support for controlled Web Research |

Frozen calibration definitions:

```text
overconfidence = medium_or_high confidence
                 AND unsupported, contradicted, or incorrectly cited factual claim

underconfidence = low confidence
                  AND adequate direct evidence
                  AND no material conflict
                  AND no unresolved high/critical issue

appropriate_low = low confidence caused by missing, weak, or conflicting evidence;
                  context loss; or an unresolved material issue
```

Two-day audit policy:

1. Automatically extract all claims.
2. Manually verify every high-impact claim.
3. For the 24 C1–C4 core outputs, select at most five factual claims per output using a frozen stratified hash rule.
4. Verify all claims whose confidence changes across legacy and new aggregation or C2/C5/C6.
5. Report the denominator as **audited claims**, never as all claims unless every claim was actually verified.

## 🧭 Critic and dynamic-control evidence

Self-reported critic scores are not evidence of critic accuracy. Use seeded-defect fixtures and blind pre/post adjudication.

| ID / priority | Metric | Collection | Main use | Missing consequence |
|---|---|---|---|---|
| A01 · P0 | Critic TP/FP/FN, precision, recall, F1 | S2 fixtures + S5 verification | Critic validity | Cannot claim the critic detects real defects |
| A02 · P0 | True issues fixed / true issues found | S5 pre/post audit | Resolution rate | Cannot attribute improvement to review |
| A03 · P0 | New defects / revisions | S5 pre/post audit | Regression rate | Critic harm remains hidden |
| A04 · P0 | Upstream defects reaching final / upstream defects | S5 lineage | Propagation | Cannot show the value of local placement |
| A05 · P0 | Gate decision versus adjudicated revision need | S5 gate sample | Dynamic safety | Saved calls could hide missed repairs |
| A06 · P0 | Route pass/revise/block and revision count | S4 logs | Dynamic execution | Cannot prove route changed at runtime |
| A07 · P0 | Budget/loop/termination guard outcome | S4 logs | Boundedness | Dynamic route could be uncontrolled |
| A08 · P0 | C2→C5 and C5→C6 paired quality/overhead | S6 analysis | Ablation | Cannot isolate critic and routing effects |
| A09 · P1 | Per-role rubric dimensions | S5 rating | Agent heatmap | Fine-grained role comparison unavailable |

## 👤 Human evaluation and business evidence

Keep `blind_mapping_private.csv` separate from the rating file until every rating is locked. G-Eval may be used as a versioned auxiliary sensitivity measure, but the primary subjective outcome remains human and blind.[^3]

| ID / priority | Field or artifact | When and method | Unit/status | Required for / missing consequence |
|---|---|---|---|---|
| H01 · P0 | Anonymous ID, output hash, anonymization check | S5 · automatic | ID/hash/pass | Blinded connection to the exact artifact |
| H02 · P0 | Private condition mapping | S5 · sealed | ID mapping | Join after rating without pre-rating leakage |
| H03 · P0 | Rating order, seed, A/B orientation | S5 · automatic | seed/order | Controls order and side bias |
| H04 · P0 | Six rubric dimension ratings | S5 · Jasmine | integer 1–5 | Primary academic quality evidence |
| H05 · P0 | Calculated academic score | S5 · script | 0–100 | Aggregated primary outcome |
| H06 · P0 | Critical/major/minor issues and usable draft | S5 · Jasmine | counts/boolean | Safety and product outcome |
| H07 · P0 | C2/C5 and C5/C6 preference with ties/reason | S5 · blind | choice/reason | Sensitive architecture ablation |
| H08 · P0 | Edit start/end, minutes, categories, rewrite required | S5 · timed edit | minutes/flags | Human-effort and business value |
| H09 · P0 | Approximately 20% hidden duplicate ratings | S5 · pre-generated | IDs | Intra-rater consistency |
| H10 · P0 | Exact agreement and weighted kappa/ICC when appropriate | S6 · script | statistic | Evaluation reliability discussion |
| H11 · P1 | Optional second rater on 20–25% | S5 · blind | ratings | Inter-rater reliability; omit honestly if absent |
| H12 · P1 | Auxiliary Codex judge version, score, A/B swap stability | S5 · automatic | score/flag | Sensitivity only, never primary truth |
| H13 · P1 | Rating duration and fatigue marker | S5 · log | minutes/flag | Detects rating drift |
| H14 · P1 | Short English rationale linked to a rubric criterion | S5 · Jasmine | text | Qualitative failure examples |

Core human workload:

- Full rubric for 24 canonical C1–C4 outputs that actually completed.
- Six C2 versus C5 pairs.
- Six C5 versus C6 pairs.
- Approximately 20% hidden duplicates.
- Failed outputs receive `usable_draft = 0`; content fields use `structurally_missing_due_failure` rather than an invented quality score.

Business outcomes:

| ID / priority | Metric and formula | Source | Required interpretation |
|---|---|---|---|
| B01 · P0 | Usable draft: no critical unsupported claim and no core-logic rewrite | Validators + human rating | Primary product outcome |
| B02 · P0 | Human edit minutes | Timed edit log | Hidden labor |
| B03 · P1 | Normalized edit distance = changed characters / original characters | Diff script | Objective edit effort |
| B04 · P0 | Time to first valid draft | Run log | Waiting experience |
| B05 · P0 | Cost per usable draft = actual total cost / usable outputs | Run + rating | Cost with a meaningful denominator |
| B06 · P0 | Completion and usable-draft rates | Manifest + rating | Reliability |
| B07 · P1 | Throughput = usable drafts / wall-clock hour | Run log | Capacity |
| B08 · P0 | End-to-end and node P50/P95 | Run/node logs | Latency distribution |
| B09 · P0 | Unconditional utility = completion rate × mean quality among completed | Derived | Prevents successful-output selection bias |
| B10 · P0 | Quality, latency, and cost as separate Pareto coordinates | Results table | Deployment decision without opaque weighting |

Local API fee can be `not_applicable`, but local energy is `not_measured` unless a real meter or defensible telemetry source exists.

## 🖥️ Hardware and Granite feasibility evidence

| ID / priority | Field or artifact | When and method | Unit/status | Required for / missing consequence |
|---|---|---|---|---|
| SLM01 · P0 | OS, CPU, cores, total RAM, GPU, VRAM | S3 · inventory | exact/GiB | Deployment boundary and reproducibility |
| SLM02 · P0 | Free RAM and pagefile before load | Each probe · telemetry | GiB | Distinguishes model limit from background load |
| SLM03 · P0 | Ollama version, model tag/digest, GGUF, quantization, file size | S3 · runtime | exact/GiB | Exact local model identity |
| SLM04 · P0 | Actual context, temperature, parallelism, loaded-model cap | S3 · assertion | tokens/count | Prevents advertised/actual context confusion |
| SLM05 · P0 | Required prompt + output and context headroom | Each probe · calculation | tokens/% | Preflight before overflow |
| SLM06 · P0 | Peak RAM/VRAM/pagefile, CPU/GPU utilization | Probe/run · 1–5 s telemetry | GiB/% | Real machine feasibility |
| SLM07 · P0 | Prompt count/duration and prefill throughput | Probe/run · Ollama response | tokens/s | Separates prompt bottleneck |
| SLM08 · P0 | Generation count/duration and throughput | Probe/run · Ollama response | tokens/s | Runtime gate |
| SLM09 · P0 | Probe schema, valid@1, repair, raw error | S3 · Pydantic validation | status/count | Structured-output gate |
| SLM10 · P0 | Projected full runtime and observed smoke runtime | S3 · calculation + run | seconds | GO/NO-GO decision |
| SLM11 · P0 | Cold/warm flag | S3/S4 · automatic | boolean | Runtime fairness |
| SLM12 · P0 | Gate result, reason, time, fallback | S3 · record | enum/text | Prevents selective stopping |

Freeze these gates before testing:

```text
G1 Memory
Pass only if the selected model loads without OOM and a real-context probe does not
enter sustained paging. Record free and peak memory; do not rely on weight size alone.

G2 Structured output
Research packet, component review, Finance packet, and Writer batch must each pass
strict validation on first attempt or after at most one structured correction.

G3 Runtime
Recommended frozen threshold: generation >= 1.5 token/s, no component > 1,200 s,
and projected full Multi <= 5,400 s. If a different threshold is chosen, freeze it
before the first candidate result.
```

If H Micro fails, preserve that result. A smaller Granite variant may be studied only under a new condition name and must not inherit the C3/C4 label.

## 🧯 Failure and reproducibility evidence

| ID / priority | Field or artifact | When and method | Required for / missing consequence |
|---|---|---|---|
| F01 · P0 | Failure ID, run, node, timestamp | S4 · automatic | Connects error to condition |
| F02 · P0 | API quota, network, timeout, schema, context, provenance, safety, budget, loop, OOM, export, operator taxonomy | S4 · map + verify | Interpretable failure analysis |
| F03 · P0 | Exception type/message and redacted stack | S4 · automatic | Verifies classification without exposing secrets |
| F04 · P0 | Recoverable, retry count, outcome | S4 · automatic | Recovery rate |
| F05 · P0 | Propagated, downstream effect, final impact | S5 · trace + verify | Coordination failure |
| F06 · P0 | Guard triggered, termination reason, remaining budget | S4 · automatic | Bounded-control safety |
| F07 · P0 | Model / infrastructure / implementation / operator class | S5 · verify | Prevents conflating capability and infrastructure |
| F08 · P0 | Inclusion decision from frozen rule | S5 · automatic | Honest denominators |
| F09 · P0 if fixed | Fix, code version, affected and rerun IDs | S4 · decision log | Version separation |
| F10 · P1 | English screenshot or concise case narrative | S7 · manual | Presentation explanation |

| ID / priority | Reproducibility artifact | When | Required for / missing consequence |
|---|---|---|---|
| REP01 · P0 | Git commit or patch hash, branch, dirty state, freeze UTC | S3 | Exact code state |
| REP02 · P0 | Python and dependency lock/hash; Ollama version | S3 | Environment recreation |
| REP03 · P0 | Model/provider identity and digest | S3/S4 | Model version control |
| REP04 · P0 | Prompt/schema/workflow/config hashes | S3/S4 | Clean experimental comparison |
| REP05 · P0 | Brief/evidence/allowlist hashes | S0/S4 | Input provenance |
| REP06 · P0 | Randomization, anonymization, and bootstrap seeds | S0/S5/S6 | Analysis recreation |
| REP07 · P0 | Exact test, run, metric, and figure commands | Throughout | Operational reproduction |
| REP08 · P0 | Test command/result/duration/time | S2/S3 | Engineering verification |
| REP09 · P0 | Figure/table sidecar with sources, filters, script/hash | S6 | Prevents manual transcription |
| REP10 · P0 | Read-only raw snapshot and SHA-256 manifest | S5 | Protects formal evidence |
| REP11 · P0 | Known limitations and unmeasured variables | S7 | Prevents overclaiming |

## 📈 Analysis and figure production

Generate, where data permit:

| Figure/table | Required inputs | Main use |
|---|---|---|
| Condition/completion table | planned rows, terminal status, failures | Methods and execution reality |
| C2−C1 paired plot | blind quality, completion, usable draft by case | Single versus Multi |
| C4−C3 paired plot | same plus Granite feasibility | SLM architecture comparison |
| 2×2 interaction plot | complete C1–C4 case cells | Model × architecture interaction |
| C2→C5→C6 dumbbell/funnel | quality, issues, requests, routes | Critic and dynamic ablation |
| Confidence calibration plot | audited claims, legacy/new labels, adjudication | Under/overconfidence |
| Quality–latency–cost Pareto | quality, completion, latency, actual cost | Product decision |
| Agent × metric heatmap | role metrics, denominators | Collaboration analysis |
| Failure taxonomy and route plot | error/route/guard/final impact | Reliability and limitations |
| Human reliability table | duplicate ratings, optional overlap | Evaluation validity |

Every figure requires a sidecar:

```json
{
  "artifact": "figure_name.png",
  "source_files": ["run_manifest.csv", "blind_evaluation.csv"],
  "filters": "canonical == true; case_id in frozen_cases",
  "analysis_unit": "case_id",
  "script": "evaluation/figures/figure_name.py",
  "script_hash": "...",
  "generated_at_utc": "..."
}
```

## 📝 Research-question evidence map

| RQ / paper topic | Minimum evidence | Main collection stage |
|---|---|---|
| Research task and architecture | Frozen task, legacy/target graphs, implemented route traces | S0–S4 |
| Roles and communication | Typed inputs/outputs, handoff completeness, provenance retention | S2–S5 |
| Framework and prompts | Versioned architecture rationale, prompt hashes, schema tests | S0–S3 |
| SLM choice | Model identity, hardware, G1–G3, successful depth/failure | S3–S4 |
| Memory/context | Context budget, pruning, truncation, retained evidence | S3–S4 |
| RAG/Web credibility | Frozen snapshots, allowlist, support audit, injection controls | S0, S4–S5 |
| Single-Agent performance | C1/C3 quality, reliability, efficiency | S4–S6 |
| Multi-Agent performance | C2/C4 plus role/collaboration/failure metrics | S4–S6 |
| Fair comparison | Condition diff, shared hashes, paired analysis | S0, S3, S6 |
| Ablation | C2/C5/C6 quality, issues, routes, overhead | S4–S6 |
| Evaluation reliability | Blind procedure, anchors, hidden repeats, limitations | S0, S5–S6 |
| HITL | Intervention/edit logs, block route, approval policy | S4–S5 |
| Safety/reproducibility | Unsupported high-impact rate, failures, hashes, commands | S3–S7 |

The published Heidelberg qualification objectives explicitly include planning, implementation, evaluation, documentation, presentation, reliability, resource management, and comparison of alternatives under constraints.[^4] The matrix therefore preserves both scientific and engineering evidence rather than optimizing only a final plan score.

## 🚨 Minimum P0 package if time collapses

Do not delete the scientific backbone to preserve superficial scope. Retain:

1. Frozen six cases, evidence packets, rubric, C1/C2, and protocol hash.
2. One verified legacy output and one confidence diagnostic fixture.
3. Claim-to-source validation and unsupported-high-impact safety guardrail.
4. C1/C2 formal outputs with failures in the denominator.
5. One complete component-critic vertical slice with seeded-defect validation.
6. One bounded conditional route trace with termination evidence.
7. Granite memory/schema/time GO or NO-GO evidence, even if no end-to-end run completes.
8. Blind human scores, usable draft, edit time, latency, and completion.
9. Reproducible paired C2−C1 figure and critic vertical-slice evidence.
10. Honest limitations and exact code/prompt/schema/evidence hashes.

Do not sacrifice failure logging, matched evidence, primary blinding, or result traceability for additional models, agents, cases, animations, or live-demo polish.

## ✅ Stage gates

### Before implementation

- Six cases and evidence packets are frozen and hashed.
- C1–C6 and all decision thresholds are frozen.
- Rubric, anchors, failure, and exclusion rules are frozen.
- At least one legacy confidence artifact is preserved.

### Before formal runs

- Precise node/run latency, tokens, route, errors, resources, and hashes persist.
- Condition-diff audit passes.
- Each C1–C6 smoke path passes or has explicit gate evidence.
- Granite G1–G3 is recorded.
- Code, prompts, schemas, model configuration, and evidence are frozen.

### Before unblinding

- Every planned row has a terminal status.
- Failed rows remain in the manifest.
- Anonymous output hashes match source outputs.
- Rating order and rubric have not changed.
- The claim-audit sample was selected before revealing condition identity.

### Before paper or presentation claims

- Every number regenerates from a CSV and script.
- Comparisons use paired case-level effects.
- Confidence percentages name the audited-claim denominator.
- Granite failures are deployment results, not content-inferiority claims.
- `n = 6 cases` appears in Methods and Limitations.
- Completion, usable draft, and unconditional utility accompany successful-output quality.
- Every RQ maps to a table, figure, log, implementation artifact, or declared limitation.

## 🔗 References

[^1]: Zhu, X. et al. “MultiAgentBench: Evaluating the Collaboration and Competition of LLM Agents.” ACL 2025. https://aclanthology.org/2025.acl-long.421/

[^2]: Rasal, S. et al. “GEMMAS: A Benchmark Suite for Evaluating Multi-Agent Systems on Multi-Faceted Tasks.” EMNLP Industry 2025. https://aclanthology.org/2025.emnlp-industry.106/

[^3]: Liu, Y. et al. “G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment.” EMNLP 2023. https://aclanthology.org/2023.emnlp-main.153/

[^4]: Heidelberg University. “Module Handbook: Master Course of Studies Data and Computer Science.” https://www.informatik.uni-heidelberg.de/c/image/f/default/pdfs/mhb2024/MHB_Informatik_MSc_DaCS_aktuell.pdf
