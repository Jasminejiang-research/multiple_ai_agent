# Open Proposal Agent - Phase 7 重写版：四臂对比评估系统 (Sprints 11-12)

> 用途：给 Cursor / Codex 逐步执行的极细粒度开发清单。**本文件完全替代** `sprint_plan.md` 中的
> `## Phase 7 - 加入评估系统 (Sprints 11-12)`。
> 前置条件：`sprint_plan_SLM.md` 的 **S1-S4 已完成**——即 `slm/` 隔离模块已实现，
> `python -m slm.cli --mode {baseline,workflow,multi}` 三条 pipeline 均可跑通。
> **继承 SLM 方案的隔离原则**：本 Phase 的所有代码只写在 `evals/` 内，
> **对 `evals/` 与 `slm/` 之外的任何现有文件零修改**。校正埋点通过继承与运行时 patch 实现，
> 绝不改动 `workflow/llm_client.py` 的重试计数、token 记账与校验闭环。
> 与原版 Phase 7 的四点不同：
> 1. 评估对象从"架构演进对比"改为 **4 个实验臂**（single/multi × Gemini/Qwen）。
> 2. 全程考虑 **Gemini 免费 API 额度限制**：runner 必须限速、记账、可断点续跑。
> 3. 每个指标明确划分 **Agent/脚本自动产出 vs 开发者人工判断**，尤其"引用权威性"——
>    agent 负责产出引用来源清单，权威性判断由开发者完成。
> 4. 新增 **实验记录表格自动生成器**（任务 11.7），一条命令产出可一目了然对比四臂的 Markdown 表。

---

## 0. 实验设计总览

### 0.1 实验矩阵（4 臂 × 5 案例 × 3 重复 = 60 runs）

| Experiment ID | Agent 架构 | 模型 | 入口（runner 调用的函数） |
|---|---|---|---|
| `single_gemini` | Single Agent | Gemini 2.5 Flash | `app.generate_proposal(client, idea)`，client 由 runner 构造 |
| `multi_gemini` | Multiple Agents | Gemini 2.5 Flash | `app.run_multi_agent_pipeline(user_brief)` |
| `single_qwen` | Single Agent | Qwen2.5-3B-Instruct | `slm.pipeline.run_slm_baseline(idea)` |
| `multi_qwen` | Multiple Agents | Qwen2.5-3B-Instruct | `slm.pipeline.run_slm_multi_agent(user_brief)` |

**没有 provider 开关**。`slm/` 是独立模块，两种模型走各自的入口函数；runner 用一张
"实验臂 → 入口函数"的映射表分发。qwen 两臂的 import 必须是 guarded 的，
**删除 `slm/` 后 gemini 两臂仍能正常评估**（这是 SLM 隔离原则的延续）。

固定条件（写死并记录，保证公平对比）：

- 5 个 case（SaaS / 教育 / 医疗 / 电商 / 餐饮），4 臂共用同一组 user brief。
- 每个 case × 臂重复 k=3 次（一致性指标需要）。
- 各节点 temperature 使用代码现值（planner 0.2 / section_writer 0.3 / 其余 0.2），4 臂一致。
  `slm/factories.py` 已要求逐一对齐，本 Phase 开跑前用 11.2 的核对项再确认一次。
- multi 臂的 Tavily、knowledge_base 配置在两个 multi 臂之间保持一致；
  single 臂本身不接 RAG/Web，这是架构差异的一部分，不是配置不公平。
- SLM 臂使用 `slm/config.py` 的预算默认值（60K prompt chars / 8192 输出 tokens），
  与 Gemini 臂不同，**必须在报告中如实注明这一预算差异**。

### 0.2 指标体系与"人工 vs Agent"分工总表（本文件的核心）

| # | 指标组 | 具体指标 | 计算方式 | Agent/脚本自动产出 | Developer 人工动作 |
|---|---|---|---|---|---|
| 1 | 结构合规 | valid@1、valid@2、章节完整率、字段缺失率 | 确定性：Pydantic 校验 + 埋点计数 | `metrics_structural.json` 每 run 一行；异常 run 清单 | 仅抽查异常 run（≤10 分钟/臂），不打分 |
| 2 | 系统效率 | prompt/output/total tokens、LLM 请求次数、校正率、传输重试率、端到端与分节点延迟、成本 | 埋点日志（run history DB + 校正 sidecar） | `metrics_efficiency.json` + 每臂汇总 | 审阅离群点并写一句归因（如 Ollama 冷启动） |
| 3 | 可观测性与可复现性 | 埋点字段齐全率（自动）；重放可复现性（人工） | 脚本扫描 DB + 人工重放 | `observability_checklist.json`：逐 run 检查 model_name/prompt_version/节点快照/usage/sources 是否齐全 | 每臂抽 1 个 run 按归档配置重放一次，对照检查单判定"可复现 / 部分 / 不可复现"并记录差异 |
| 4 | 一致性 | 同 case 3 次重复的：valid@1 波动、输出长度 CV、章节存在一致率、critic 总分标准差；财务数字量级一致（可选） | 脚本对比 3 重复 | `metrics_consistency.json` + 分歧 diff 报告（列出差异最大章节的三版原文） | 对每臂差异最大的 2 组 diff 做语义判定：`consistent_paraphrase` vs `substantive_contradiction` |
| 5 | 引用权威性 | 来源权威分（1-5）、关键 claim 引用覆盖率、claim-source 支持性抽检合格率、过时来源占比 | **Agent 产出证据，开发者判断** | 每 run 一份 **Citation Manifest**：claim → source_id → url/publisher/source_quality/published_date/stale/summary（见 11.5） | 按 12.2-D 的权威性 rubric 对每个去重来源打 1-5 分；抽 20% claim 核验来源是否真支持该 claim；single 臂无来源时如实记 coverage=0（这是实验发现，不是错误） |
| 6 | 端到端质量 | `docs/EVALUATION_RUBRIC.md` 10 维度 1-5 分 | 人工盲评 | 匿名化盲评包（隐藏臂标签的 60 份 proposal）+ 空白评分表 | 盲评打分（唯一的大工作量人工项） |

分工原则：**凡是确定性可计算的一律脚本算，开发者只看异常**；**凡是需要领域判断的
（权威性、语义一致性、可复现性结论、质量分）一律开发者做，但脚本必须先把证据整理成
可直接评审的材料包**——开发者不应该自己去翻数据库。

### 0.3 免费 API 额度约束与预算账本

Gemini 免费档有 RPM（每分钟请求）/ RPD（每日请求）/ TPM（每分钟 tokens）三重限制，
且额度会调整。**执行前必须查询当日官方 rate limits 页面**，把实际数值填入 `evals/.env.eval`，
不要在代码里硬编码：

```text
EVAL_GEMINI_MAX_REQUESTS_PER_DAY=      # 官方 RPD 的 80%，留缓冲
EVAL_GEMINI_MAX_REQUESTS_PER_MINUTE=   # 官方 RPM 的 80%
EVAL_MIN_SECONDS_BETWEEN_RUNS=30       # run 间冷却
```

预算量级估算（用于排期，非硬编码）：

| 臂 | runs | 每 run 请求数（含校正，取上界） | 请求合计 |
|---|---|---|---|
| `single_gemini` | 15 | ~2 | ~30 |
| `multi_gemini` | 15 | ~12（8 节点 + 校正余量） | ~180 |
| `single_qwen` / `multi_qwen` | 30 | 本地推理，无额度限制 | 0（只耗时间） |

⇒ Gemini 侧约 **210+ 请求**。若免费档 RPD 低于此数，`multi_gemini` 必须跨天执行——因此
runner 的**断点续跑与当日记账是硬需求，不是优化项**。Qwen 侧瓶颈是本地推理速度
（`slm/README.md` 已记录实测 tokens/s），按实测延迟 × 30 run 估算，可通宵挂机。

---

## Sprint 11 - 埋点、基础设施与报表生成器

#### Goal

用**零修改现有代码**的方式补齐 valid@1 所需埋点；给 run 打实验臂标签；实现限速可续跑的
四臂 runner；实现全部自动指标计算器、人工评审材料包与实验记录表格生成器。
**本 Sprint 结束时不需要跑完任何真实实验。**

#### Deliverables

- `evals/instrumentation.py`（非侵入式校正埋点）
- `evals/cases/*.json`（5 个）
- `evals/runner.py`、`evals/manifest.json`、`evals/quota_ledger.json`
- `evals/metrics_structural.py`、`metrics_efficiency.py`、`metrics_consistency.py`、`observability_check.py`
- `evals/citation_manifest.py`、`evals/blind_bundle.py`
- **`evals/report_tables.py`（实验记录表格生成器）**
- `evals/tests/`（本 Phase 的测试，同样不进 `tests/`，用 `pytest evals/tests -q` 显式运行）

#### Tasks

##### 11.1 非侵入式校正埋点（零修改现有代码）

> 原方案要改 `workflow/llm_client.py` 的 `LLMUsageTracker` 与 `generate_structured` 重试计数。
> 那正是 SLM 隔离原则要保护的基线代码，**已废弃**。改用继承 + 运行时 patch。

- [ ] 创建 `evals/instrumentation.py`，定义 `CORRECTION_MARKER = "# Structured Output Correction"`，
      注释写明该串必须与 `workflow/llm_client.py` 校正 prompt 中的标记行逐字一致。
- [ ] 定义 `_CorrectionCountingMixin`：override `_generate_once(self, prompt, schema, **kwargs)`，
      按 **schema 名** 累计 `{attempts, corrections}`（`CORRECTION_MARKER in prompt` 即判定为校正尝试），
      然后 `return super()._generate_once(...)`。
      *按 schema 名归属而非节点名*：每个节点/Agent 绑定唯一 schema（ProposalOutline=planner、
      SectionDrafts=section_writer、CritiqueReport=critic、RevisedProposal=revision、
      ResearchAnalysis/StrategyAnalysis/FinanceAssumptions/ProposalDraft=各 Agent），
      同一 run 内一一对应，因此无需知道节点上下文。
- [ ] 定义 `capture_corrections()` 上下文管理器（ContextVar，仿 `capture_llm_usage()` 的写法）。
- [ ] 定义 `InstrumentedLLMClient(_CorrectionCountingMixin, LLMClient)`；
      定义 `InstrumentedSLMClient(_CorrectionCountingMixin, SLMClient)`，**其 import 必须 guarded**
      （`slm/` 不存在时该类不可用，但 gemini 两臂不受影响）。
- [ ] 定义注入方式，全部为运行时 patch，不改任何源文件：
  - `multi_gemini`：`patch("workflow.llm_client.create_default_llm_client", …)` 返回 `InstrumentedLLMClient`，patch 包住整个 `app.run_multi_agent_pipeline(...)` 调用。
  - `single_gemini`：直接 `app.generate_proposal(InstrumentedLLMClient(...), idea)`，无需 patch。
  - `multi_qwen` / `single_qwen`：`patch("slm.factories.SLMClient", InstrumentedSLMClient)` 包住 `slm.pipeline.*` 调用。
- [ ] **关键推导关系**写进模块 docstring：
  - `节点 valid@1` = 该 schema 的 `corrections == 0` 且节点状态 completed；
  - `valid@2` = 节点状态 completed（本系统每次 `generate_structured` 至多 2 次语义尝试，故 k=2）；
  - `传输重试数` = DB 中 `retry_count` − 本埋点的 `corrections`
    （503 短重试发生在 `_generate_once` 内部，不额外触发 `_generate_once` 调用，故两者可相减）。
- [ ] **契约测试**（防止上游改文案导致静默失效）：断言 `CORRECTION_MARKER` 确实出现在
      `LLMClient.generate_structured` 触发校正时构造的 prompt 中（用 fake client 触发一次校正并捕获 prompt）。
- [ ] 校正数据落 sidecar：`evals/results/raw/{run_id}_corrections.json`，**不写 DB**，
      指标计算器在读取时与 DB join。
- [ ] 单测：mixin 计数正确（首试不计校正、校正计 1）、guarded import 在 `slm/` 缺失时不报错。
- [ ] 提交 commit：`feat(evals): add non-invasive correction instrumentation`。

##### 11.2 评估案例与公平性核对（4 臂共用）

- [ ] 创建 `evals/cases/`，5 个 JSON：`saas_crm.json`、`ai_education.json`、`healthcare_booking.json`、`ecommerce_seller_tool.json`、`restaurant_inventory.json`。
- [ ] 每个 case 字段：`case_id`、完整 `user_brief`（满足 InputValidator 的必填与长度校验）、`expected_strengths`（盲评参考）、`known_risks`、`evaluation_notes`。
- [ ] 每个 case 先用最便宜的方式（`single_qwen`）干跑一次，确认能通过输入校验，不浪费 Gemini 额度。
- [ ] **公平性核对**：逐一比对 `slm/factories.py` 的 9 个 adapter temperature 与
      `workflow/llm.py` + `agents/*.py` 的默认值是否完全一致，不一致立即修 `slm/`（不改现有代码）。
- [ ] 提交 commit：`test(evals): add four-arm evaluation cases`。

##### 11.3 评估 Runner（臂映射、额度感知、可断点续跑）

- [ ] 创建 `evals/runner.py`，CLI：`python -m evals.runner --arm multi_gemini --cases all --repeats 3`。
- [ ] **臂 → 入口映射表**（替代原 `LLM_PROVIDER` 开关）：

  ```python
  # gemini 两臂：直接调用 app.py 的现成函数（single 臂传 instrumented client）
  # qwen 两臂：调用 slm.pipeline 的函数，import 必须 guarded
  try:
      from slm import pipeline as slm_pipeline
  except ImportError:
      slm_pipeline = None   # slm/ 被删除时，仅 qwen 两臂不可用
  ```

  - [ ] 请求 qwen 臂而 `slm_pipeline is None` 时：给出清晰错误"slm/ 模块不存在，qwen 臂不可用；gemini 臂不受影响"，退出码非 0，**不影响已排队的 gemini job**。
- [ ] 实验矩阵展开为 job 列表 (arm, case_id, repeat)，按 arm 分组执行。
- [ ] **实验臂标签**（不做 DB 迁移）：约定 `session_id = "eval:{arm}:{case_id}:r{repeat}"`
      （如 `eval:multi_qwen:case03:r2`）。gemini 臂经 `app.py` 走默认 `session_id="streamlit"`，
      无法直接传参 ⇒ **以 `evals/manifest.json` 为准**：runner 在每个 run 前后记录
      run_id ↔ (arm, case, repeat, env 快照, 状态, 起止时间)。manifest 是臂归属的唯一权威来源，
      `session_id` 仅作为 qwen 臂的辅助冗余。
- [ ] **断点续跑**：启动时读 manifest，状态 completed 的 job 跳过；每完成一个 run 立即落盘。
      中断后重跑同一命令必须无重复消耗。
- [ ] **额度记账**：`evals/quota_ledger.json` 按日期累计 gemini 请求数与 tokens（从 run 的 token_usage 读实际值）。
      当 `已用 + 单 run 上界(12)` 超过 `EVAL_GEMINI_MAX_REQUESTS_PER_DAY` 时**拒绝启动新 gemini run**，
      打印"今日额度耗尽，明天继续"。
- [ ] **限速**：gemini run 之间 sleep `EVAL_MIN_SECONDS_BETWEEN_RUNS`；收到 429 时当前 run 记为
      `failed_quota`（可重跑），不计入 valid@k 分母，并停止当日 gemini 队列。
- [ ] qwen 臂启动前先探测 `SLM_BASE_URL/models`（复用 `slm.preflight_slm.check_slm_preflight`），失败快速报错。
- [ ] 每个 run 用 `capture_corrections()` 包住，结束后写 `{run_id}_corrections.json`。
- [ ] `--dry-run`：只打印将执行的 job、预计请求数、今日剩余额度，不调任何 LLM。
- [ ] 单测（mock 入口函数）：断点续跑跳过、额度拒绝、manifest 落盘、`slm/` 缺失时 gemini 臂仍可跑。
- [ ] 提交 commit：`feat(evals): add quota-aware resumable four-arm runner`。

##### 11.4 自动指标计算器（离线，只读 DB 与产物，不调 LLM，可反复重算）

- [ ] `evals/metrics_structural.py`：逐 run 输出——各 schema 的 valid@1/valid@2（DB 状态 + 校正 sidecar）、
      run 级 valid@1（全节点首试通过）、13 章节存在且非空的完整率、必填字段缺失率
      （扫描 agent_outputs payload 空值）。输出 `evals/results/metrics_structural.json` + 每臂汇总。
- [ ] `evals/metrics_efficiency.py`：逐 run 输出——tokens 三项、请求数、校正率、
      传输重试率（`retry_count − corrections`）、端到端延迟（`runs.updated_at − created_at`）、
      分节点延迟（node_outputs 同名节点 started/completed 两行 `created_at` 差值）、
      成本（gemini 按 env 单价；qwen 记 0 并标注"本地推理，以延迟为代价指标"）。
- [ ] `evals/metrics_consistency.py`：按 (arm, case) 聚合 3 重复——valid@1 一致性、
      最终 Markdown 长度 CV、章节存在一致率、critic overall_score 标准差；
      生成"分歧 diff 报告"：每组重复中差异最大章节的三版原文并排，供 12.2-B 人工判定。
      （可选）财务章节数字提取与量级比对。
- [ ] `evals/observability_check.py`：逐 run 扫描——model_name / prompt_version / workflow_version /
      全节点输入输出快照 / token_usage / sources（multi 臂）是否齐全，输出齐全率与缺失明细。
- [ ] 所有计算器对 failed run 输出记录而非崩溃（失败也是数据）。
- [ ] `evals/tests/test_eval_metrics.py`：用手工构造的 mini run history（内存 SQLite）+ 假 sidecar
      验证每个指标，含校正/传输重试区分、缺章节、失败 run 等边界。
- [ ] 提交 commit：`feat(evals): add deterministic four-arm metric calculators`。

##### 11.5 Citation Manifest 生成器（Agent 产出 → 开发者评审的桥梁）

- [ ] 创建 `evals/citation_manifest.py`：逐 run 汇集——proposal 各 section 的 `key_claims` 与
      `source_ids`（来自最终 draft JSON）、sources 表全部字段
      （url/publisher/published_date/source_quality/stale/summary/query）、citation_checker 的覆盖率结果。
- [ ] 输出人类可评审的 `evals/results/citations/{run_id}.md`：按 claim 分组，
      每条 claim 下列出其引用来源的完整元数据与摘要；无来源的关键 claim 单独列为 **UNSUPPORTED** 区块。
- [ ] 同时输出机器可读 CSV，供开发者直接加两列：`authority_score`、`supports_claim`。
- [ ] single 臂：如实生成"无来源能力，关键 claim N 条全部 UNSUPPORTED"，不视为错误。
- [ ] 提交 commit：`feat(evals): add citation manifest generator`。

##### 11.6 盲评材料包生成器

- [ ] 创建 `evals/blind_bundle.py`：把 60 份最终 proposal 复制为随机编号 `P01..P60` 的 Markdown，
      **剥离**所有能泄露臂身份的信息（model_name、run_id、耗时、provider 字样；来源 URL 保留但隐藏检索元信息）。
- [ ] 生成 sealed mapping `evals/results/blind_mapping.json`（编号 → run_id）与空白评分表
      `evals/results/blind_scores.csv`（P01..P60 × 10 维度）。
- [ ] 规程写入 docstring：**开发者填完全部分数并 commit 之后**，才允许打开 mapping 反匿名。
- [ ] 提交 commit：`feat(evals): add blind review bundle generator`。

##### 11.7 实验记录表格生成器（一条命令看懂四臂对比）

> 目标：把散落在 DB、sidecar、CSV 里的数据，一次性渲染成"行=指标、列=四臂"的 Markdown 表，
> 让开发者不必翻任何原始数据就能对比关键结果。实验途中也能随时出表看进度。

- [ ] 创建 `evals/report_tables.py`，CLI：
      `python -m evals.report_tables --out evals/results/EXPERIMENT_RECORD.md [--partial] [--csv]`。
- [ ] 数据来源：`metrics_*.json` + `observability_checklist.json` + `manifest.json` +
      `quota_ledger.json` + 人工填写的 `citations/*.csv` 与 `blind_scores.csv`。
      **只读，不重算**；任一来源缺失时该表整体标 `TBD`，绝不留空、绝不编造。
- [ ] 统一渲染规则：
  - 所有表一律 **行 = 指标，列 = `single_gemini` / `multi_gemini` / `single_qwen` / `multi_qwen`**，四臂并排便于横向比较。
  - 数值单元格格式 `均值 ± 标准差 (n=样本数)`；比率保留 1 位小数百分比；缺数据写 `TBD`。
  - `--partial` 模式下，未跑完的臂正常显示 `TBD` 而不报错（供 12.1 逐臂检查用）。
- [ ] 实现以下表格（每张一个 `render_*` 函数，便于单测）：
  - **T0 实验进度总览**：每臂 completed / failed / failed_quota / 待跑 run 数，已消耗 gemini 请求与今日剩余额度。
  - **T1 结构合规**：valid@1、valid@2、13 章节完整率、必填字段缺失率。
  - **T2 系统效率**：prompt/output/total tokens、LLM 请求数、校正率、传输重试率、端到端延迟、单 run 成本。
  - **T3 可观测性与可复现性**：埋点齐全率（自动）+ 人工重放结论（`reproducible`/`partially`/`not_reproducible`）。
  - **T4 一致性**：valid@1 波动、长度 CV、章节存在一致率、critic 总分标准差、人工语义判定计数。
  - **T5 引用权威性**：平均权威分、关键 claim 引用覆盖率、`supports_claim` 合格率、幻觉引用率、过时来源占比。
  - **T6 端到端质量**：10 个 rubric 维度 × 四臂 + 总分。
  - **T7 效应速览**：三行——架构效应（multi − single，两模型各一列）、模型效应（gemini − qwen，两架构各一列）、交互效应（差之差）。每格给出关键指标的差值与方向。
- [ ] `--csv` 额外导出各表为 CSV（便于导入论文/表格软件）。
- [ ] 单测：给定伪造的 metrics JSON 与人工 CSV，断言表格行列齐全、缺数据渲染为 `TBD`、
      `--partial` 不抛异常、效应表的差值计算正确（含符号方向）。
- [ ] 提交 commit：`feat(evals): add experiment record table generator`。

#### Definition of Done

- [ ] 校正与传输重试可区分，valid@1 可推导，且**未修改任何现有源文件**。
- [ ] runner 通过 dry-run 演示完整矩阵、额度预估、断点续跑；删除 `slm/` 后 gemini 两臂仍可运行。
- [ ] 全部计算器 + manifest + 盲评包 + 表格生成器有单测且 `pytest evals/tests -q` 全绿。
- [ ] `pytest -q` 现有测试零回归；`git status` 显示改动仅限 `evals/`（与本文档）。

---

## Sprint 12 - 执行、人工评审与报告

#### Goal

按额度日程跑完 60 runs，完成全部人工评审，产出四臂对比报告。

#### Tasks

##### 12.1 执行矩阵（额度感知的日程）

- [ ] 查询当日 Gemini 官方 rate limits，填入 `evals/.env.eval` 三个 `EVAL_` 变量。
- [ ] Day 0（不耗 Gemini 额度）：跑 `single_qwen` 15 runs、`multi_qwen` 15 runs（可通宵）。
      顺带验证 runner 全链路——问题在免费臂上暴露和修复。
- [ ] Day 1：跑 `single_gemini` 15 runs（~30 请求）；额度富余则开始 `multi_gemini`。
- [ ] Day 1-N：`multi_gemini` 15 runs，由 runner 记账自动跨天，直至完成。
- [ ] **每个 arm 完成后**：立即跑 4 个指标计算器，再跑
      `python -m evals.report_tables --partial`，用 T0/T1/T2 检查数据完整性
      （趁热发现埋点问题可低成本补跑）。
- [ ] 全部 60 runs 完成后：生成全部 citation manifest 与盲评包。
- [ ] 备份 `data/app.db`、`evals/manifest.json`、`evals/results/` 至独立目录（论文级原始数据）。
- [ ] 提交 commit：`eval: complete four-arm experiment runs`。

##### 12.2 人工评审（developer 工作清单，按耗时从小到大）

**A. 结构/效率异常抽查（~30 分钟）**

- [ ] 看 T1/T2 两张表，对每个离群点（如某 run 延迟 3 倍于同臂均值）写一句归因备注，
      存 `evals/results/human/anomaly_notes.md`。

**B. 一致性语义判定（~1 小时）**

- [ ] 对每臂"分歧最大"的 2 组 diff（共 8 组），逐组判定并记录：
      `consistent_paraphrase`（表述不同、结论一致）或 `substantive_contradiction`（实质矛盾，
      如市场规模差一个量级），存 `evals/results/human/consistency_verdicts.csv`。

**C. 可复现性重放（~2 小时）**

- [ ] 每臂抽 1 个 run，按 manifest 中归档的 env 快照重放同一 case 一次。
- [ ] 对照检查：能否恢复完整配置（模型、prompt version、预算）？重放是否成功？结构指标是否同档？
- [ ] 每臂给出结论 `reproducible` / `partially` / `not_reproducible` 并附一句说明，
      存 `evals/results/human/reproducibility.csv`（T3 表会读它）。
      已知限制如实记录（Gemini 无 seed 参数、temperature>0 输出必然漂移）。

**D. 引用权威性评审（~3 小时，仅 multi 两臂有实质工作量）**

- [ ] 打开 `citations/*.csv`，对每个**去重后的来源**按以下锚点打 `authority_score`（1-5）。
      锚点仅是起点，**开发者的领域判断优先于自动 `source_quality` 标签**：
  - 5 = 官方一手（政府统计、公司财报、SEC/监管文件）
  - 4 = 研究机构 / 学术 / 权威行业数据库
  - 3 = 主流可信媒体
  - 2 = 垂直行业博客 / 厂商软文
  - 1 = SEO 内容农场 / 无法溯源 / 与主题无关
- [ ] 抽 20% 的 claim（每臂至少 10 条，优先 market size / 竞品 / 趋势类）打开原始 URL 核验，
      填 `supports_claim`：`yes` / `partial` / `no`。
      **来源存在但不支持该 claim = 幻觉引用**，T5 表单独统计该比率。
- [ ] 对 `stale=true` 的来源确认过时标记是否合理。
- [ ] single 两臂：确认 manifest 显示 coverage=0，写入报告作为架构差异发现。

**E. 端到端质量盲评（~10 小时，可分多天）**

- [ ] 按 `docs/EVALUATION_RUBRIC.md` 对 P01..P60 逐份打 10 维度分，填 `blind_scores.csv`。
- [ ] 全部填完并 commit 后，才运行反匿名脚本合并臂标签。
- [ ] 提交 commit：`eval: complete human review scores`。

##### 12.3 汇总报告

- [ ] 运行 `python -m evals.report_tables --out evals/results/EXPERIMENT_RECORD.md --csv`
      生成全量表格（此时人工数据已齐，T3/T5/T6 不再是 TBD）。
- [ ] 创建 `docs/four_arm_comparison.md`，**直接嵌入 T0-T7 表格**，并补充叙述：
  - 实验设置（矩阵、case、**预算差异声明**、免费额度对执行的实际影响）。
  - 逐指标组解读（T1-T6），重点解释异常与人工判定结果。
  - 结论：**架构效应（single→multi）与模型效应（Gemini→Qwen）分开讨论**，
    交互效应（multi 是否放大/缩小 SLM 劣势）单独一节，引用 T7。
  - 局限性：k=3 样本量、单人评审无 inter-rater 信度、免费额度导致跨天执行、
    两臂预算不同等，如实写。
- [ ] 所有数字来自 `evals/results/` 真实产物；缺数据写 TBD，**绝不编造**。
- [ ] README 的 Benchmark 小节引用该报告。
- [ ] 提交 commit：`eval: add four-arm comparison report`。

#### Definition of Done

- [ ] 60 runs（或明确记录的失败 run）全部有 run history + manifest 记录。
- [ ] 6 组指标全部有真实数据；人工评审 A-E 全部完成且有落盘产物。
- [ ] `EXPERIMENT_RECORD.md` 一页看完四臂对比；`docs/four_arm_comparison.md` 完成。
- [ ] 原始数据已备份，第三方可凭之复算全部自动指标。

---

## 附录 1：产出物清单（按指标索引）

| 指标组 | Agent/脚本产物（自动） | Developer 产物（人工） | 汇入表格 |
|---|---|---|---|
| 结构合规 | `metrics_structural.json` | `human/anomaly_notes.md` | T1 |
| 系统效率 | `metrics_efficiency.json` + 校正 sidecar | 同上 | T2 |
| 可观测/可复现 | `observability_checklist.json` | `human/reproducibility.csv` | T3 |
| 一致性 | `metrics_consistency.json` + 分歧 diff 报告 | `human/consistency_verdicts.csv` | T4 |
| 引用权威性 | `citations/{run_id}.md` + 打分 CSV 模板 | CSV 中 `authority_score`、`supports_claim` 两列 | T5 |
| 端到端质量 | 盲评包 P01..P60 + 空白评分表 | `blind_scores.csv` 全量分数 | T6 |
| 全部 | — | — | **T0/T7 由 `report_tables.py` 汇总** |

## 附录 2：明确不做什么

- **不修改 `evals/` 与 `slm/` 之外的任何文件**（延续 SLM 隔离原则）；校正埋点一律走继承 + 运行时 patch。
- 不改 `pytest.ini`；本 Phase 测试用 `pytest evals/tests -q` 显式运行。
- 不引入 LLM-as-judge（确定性指标 + 单人盲评已满足对比需求；避免引入第三个模型的偏差与额度消耗）。
- 不做 promptfoo / Ragas 集成（原版 Phase 7 遗留项，与四臂对比无关）。
- 不为评估修改任何 prompt、agent、schema——评估期间代码冻结。
- 不在 CI 中调用真实 LLM；CI 只跑指标计算器与表格生成器的单测。
- 不做超过 4 臂的扩展矩阵。

## 附录 3：Stop Conditions（暂停并人工检查）

- [ ] 同一臂连续 3 个 run 因结构校验失败终止（先查埋点/预算配置，再怀疑模型能力）。
- [ ] Gemini 返回 429 后 runner 未停止当日队列（额度保护失效，立即修）。
- [ ] manifest 与 DB 的 run 记录对不上（可复现性根基被破坏）。
- [ ] 契约测试失败（`CORRECTION_MARKER` 不再匹配）⇒ 所有校正率数据作废，修复后重算。
- [ ] 盲评期间从任何渠道泄露臂身份（该份评分作废重评）。
- [ ] 任何表格中的数字无法从 `evals/results/` 原始产物复算出来。

## 附录 4：Cursor / Codex 执行模板

```text
You are working on Open Proposal Agent. Read sprint_plan_phase7_eval.md first.
Prerequisite: sprint_plan_SLM.md S1-S4 are complete (isolated slm/ module exists).
Implement only this task:

TASK: <paste one checkbox>

Hard constraints (violating any of these fails the task):
- Create/modify files ONLY inside evals/. ZERO changes to existing code —
  app.py, workflow/, agents/, schemas/, rag/, storage/, tools/, prompts/,
  tests/, pytest.ini, requirements.txt. Do not touch slm/ either.
- Correction instrumentation is achieved by subclassing + runtime patching,
  never by editing workflow/llm_client.py.
- Import slm/ only through a guarded try/except so that deleting slm/
  disables the qwen arms without breaking the gemini arms.
- Metric calculators and report_tables are offline: they read the run-history
  DB and evals/results/ artifacts, never call an LLM, and are re-runnable.
- The runner must respect EVAL_GEMINI_MAX_REQUESTS_PER_DAY and resume from
  evals/manifest.json without re-consuming quota.
- Never fabricate metric numbers; missing data renders as TBD; failed runs
  are recorded as data.
- After coding: run `pytest -q` AND `pytest evals/tests -q`; both must pass.
  Then run `git status` and confirm changes are confined to evals/.
```

## 附录 5：Commit 规范

```text
feat(evals): add non-invasive correction instrumentation
test(evals): add four-arm evaluation cases
feat(evals): add quota-aware resumable four-arm runner
feat(evals): add deterministic four-arm metric calculators
feat(evals): add citation manifest generator
feat(evals): add blind review bundle generator
feat(evals): add experiment record table generator
eval: complete four-arm experiment runs
eval: complete human review scores
eval: add four-arm comparison report
```
