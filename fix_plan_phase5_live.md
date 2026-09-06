# Phase 5 Live 验收修复计划（给 Cursor / Codex 执行）

> 使命：让 Phase 5 在 **Streamlit + 真实 Gemini API（live）** 下三种模式（Baseline / Workflow / Multi-Agent）
> 均能端到端跑通并导出完整商业计划书 Markdown。
> 执行纪律：一次只做一个 Task；**禁止逐字段/逐 agent 打补丁**（这是过去 10+ 轮返工的根源，见第 1 节）；
> 所有修复必须落在第 3 节指定的文件范围内。

---

## 1. 历史失败根因审计（先读懂，避免重蹈覆辙）

过去所有报错归为 6 个根因：

- **信息不对称**：Gemini 收到的是去掉数量上限的 relaxed schema，严格校验在本地 Pydantic
  → 模型看不到上限，反复超限（tasks 9/8、input_requirements 11/8、key_claims 13/8、
  source_ids 10/8、needs_human_review 9/8 全是同一根因）。
- **逐字段打补丁**：每次只在单个 agent 的 prompt 补上限、单个 agent 加重试；约束不跨 agent 继承
  → 同类错误换个字段/agent 复发，形成打地鼠循环。
- **重试位置错误**：agent 层重试包住二次 `parse_*()`，真实异常在 `generate_json()` 内已抛出
  → 线上重试从未生效；fake-LLM 测试返回非法字符串而非抛异常，掩盖了该缺陷。
- **语义校验误判**：citation checker 纯关键词匹配，把"市场规模未知/数字仅为假设"等免责声明
  判为必须引用的事实 → 修正重试注定失败。
- **校正反馈贫瘠 + 整篇重写**：只反馈"章节+缺失数量"，且第二次重新生成整份 13 章
  → 修复成功率低、token 爆炸。
- **修复引入新复杂度**：为解决引用误判引入 StructuredClaim（多枚举嵌套对象）+ 大量 Field description
  → 生成 schema 体积暴涨，触发当前的 Gemini `400 too many states for serving`。

前 5 个根因已由既有重构解决（集中式 LLMClient 重试、schema_cardinality_contract 自动数量契约、
evidence_status 语义分类、CitationFailure 聚合反馈、失败章节 Patch）。
**当前唯一阻断验收的是第 6 个**，以及其暴露出的"离线测试无法发现请求期 400"这一测试盲区。

## 2. 当前阻断问题诊断（400 INVALID_ARGUMENT）

报错：`The specified schema produces a constraint that has too many states for serving`。
这发生在 **API 请求期**（Gemini 把 `response_schema` 编译成受限解码状态机时），与模型输出内容无关，
因此本地 mock 测试 215 项全绿也拦不住它。

`workflow/gemini_schema.py` 的 `relaxed_response_schema()` 目前只删约束键和大枚举，但仍保留：

1. **全部 `description` 字符串**（schemas/ 下共 155 处 Field description/Literal，错误信息明说
   "schemas with lots of text" 是主因之一）；
2. **全部 `title` 注解**（Pydantic 给每个模型/字段自动生成）；
3. **小枚举**（≤6 成员且 ≤100 字符的会保留，如 `EvidenceStatus` 4 值、`confidence` 3 值、
   `severity` 4 值）——它们嵌套在 `StructuredClaim` 中，随 13 个章节 × 每章节 8 条 key_claims
   重复展开，状态数相乘。

即：schema 复杂度 =（13 章节）×（每章节 5 字段 + key_claims 数组 ×（StructuredClaim 5 字段
+ 2 个枚举 + 5 段 description）），`SectionDrafts` / `ProposalDraft` / `RevisedProposal` 三个大 schema
全部超限。修复必须在 `gemini_schema.py` **一处集中解决**，让所有 schema 同时受益。

## 3. 修复任务

### T1 — 强化 `relaxed_response_schema()`（唯一的产品代码改动）

文件范围：仅 `workflow/gemini_schema.py`。

- [ ] 在 `_clean()` 中额外剥除注解键：`description`、`title`、`examples`、`default`、`$comment`。
- [ ] **关键陷阱（必须处理，否则直接破坏 schema）**：`title` / `description` 同时也是业务字段名
      （每个 section 都有名为 `title` 的 property）。剥除只能作用于 **schema 片段的注解键**，
      **绝不能作用于 `properties` 映射的键**。实现方式：`_clean()` 遍历到 key == `"properties"` 时，
      对其 value（映射）**保留全部键名**，仅对每个键的值递归清洗；注解剥除只发生在片段自身层级。
- [ ] 生成 schema 中**丢弃全部枚举**（把 `_is_expensive_enum` 判定改为无条件 drop，保留推断的
      plain type）。理由：枚举值已由 prompt 与 `schema_cardinality_contract` 传达，本地严格
      Pydantic 照常校验；13 章节重复展开时小枚举也是状态乘数。
- [ ] 保持现有行为不变：`$ref` 内联、单元素 `allOf` 扁平化、约束键剥除。
- [ ] 更新模块 docstring：写明"生成 schema 只保留 structure（type/properties/required/items），
      注解与枚举全部剥除；语义约束由 prompt 契约 + 本地 Pydantic 双重承担"。
- [ ] 跑 `pytest tests/test_gemini_schema.py -q`，按新行为更新既有断言（这是测试文件的预期更新，
      不算越界）。
- [ ] 提交 commit：`fix: strip annotations and enums from gemini generation schema`。

### T2 — 离线 schema 预算守卫（把"请求期 400"变成本地可拦截）

文件范围：仅新增 `tests/test_schema_budget.py`。

- [ ] 枚举生产环境实际发送给 Gemini 的全部 schema（逐一核对调用点后列全）：
      `BusinessProposal`、`ProposalOutline`、`SectionDrafts`、`CritiqueReport`、`RevisedProposal`、
      `RevisedProposalPatch`、`ProposalDraft`、`ResearchAnalysis`、`StrategyAnalysis`、
      `FinanceAssumptions`、`SupervisorPlan`（若 Supervisor 已确定性化则从清单移除）。
- [ ] 对每个 schema 断言 `relaxed_response_schema()` 输出：
  - 序列化后不含 `"description"`、`"enum"` 键（用递归键扫描，不是字符串包含——
    正文里可能合法出现这些词）；
  - `properties` 中的业务字段 `title`、`content` 等仍然存在（防 T1 陷阱回归）；
  - `json.dumps` 总长度低于预算常量 `MAX_GENERATION_SCHEMA_CHARS`（初值定 15_000，
    T3 实测通过后按"最大实测值 × 1.5"回填并注释来源）。
- [ ] 参数化测试，一个 schema 一个用例，失败信息包含实测长度。
- [ ] 提交 commit：`test: add generation schema budget guard`。

### T3 — 廉价 live schema 接受度测试（每个 schema 只花约 20 个 token）

文件范围：仅新增 `tests/test_live_schema_acceptance.py`（标记 `@pytest.mark.live`，默认排除）。

- [ ] 原理：`too many states` 的 400 在**请求被接受前**就返回，与生成长度无关。因此对 T2 清单中
      每个 schema 发一次真实请求：prompt 用一句话占位，`max_output_tokens=16`——
      schema 被拒会立刻 400，schema 被接受则廉价返回（输出会截断/校验失败，**不检查输出**，
      只断言未抛 400 INVALID_ARGUMENT）。
- [ ] 全套约 11 次请求、每次 ≤16 输出 token，额度成本可忽略；但仍标记 live，只手动运行：
      `pytest tests/test_live_schema_acceptance.py -m live -q`。
- [ ] 捕获断言：异常消息含 `INVALID_ARGUMENT` 或 `too many states` 即 fail 并打印 schema 名。
- [ ] 提交 commit：`test: add cheap live schema acceptance checks`。

### T4 — 运行预算核对（防止修完 400 后死于预算）

文件范围：仅 `.env`（本地，不提交）与 `.env.example` 的注释行。

- [ ] Multi-Agent 全链 LLM 节点：research / strategy / finance / writer / critic / revision = 6 次，
      加校正重试最坏 12 次。现 `LLM_RUN_MAX_REQUESTS=8` 会在多节点触发校正时中途熔断。
      改为 `LLM_RUN_MAX_REQUESTS=12`、`LLM_RUN_MAX_TOTAL_TOKENS=200000`（历史实测单次
      Revision 就消耗 ~31K tokens）。
- [ ] `.env.example` 对应两行加注释说明取值依据；不改任何代码默认值。
- [ ] 提交 commit：`chore: align run budget with multi-agent worst case`。

### T5 — Live 验收流程（人工执行，逐项打勾）

前置：T1-T4 完成、`pytest -q` 全绿、T3 live 接受度测试全绿。

- [ ] `streamlit run app.py`，用 `examples/sample_input.json` 的 AI education 样例。
- [ ] **Baseline 模式**：生成成功、13 章节齐全、Markdown 落盘 `outputs/`。
- [ ] **Workflow 模式**：全链跑通（planner → section_writer → assembler → critic → revision →
      export），run detail 页每节点 completed。
- [ ] **Multi-Agent 模式**：全链跑通；Tavily 已配置则 sources 表有 `web-*` 记录，未配置则确认
      降级警告出现且流程继续。
- [ ] 每种模式记录：run_id、总请求数、总 tokens、retry_count（run history 中均有）。
- [ ] 若三种模式各成功 1 次：Phase 5 live 验收通过，提交 commit：
      `test: phase 5 live acceptance passed`（commit message 中附三个 run_id）。

## 4. Live 再遇错误时的分诊表（按表处理，禁止即兴打补丁）

| 错误特征 | 根因 | 正确动作 |
|---|---|---|
| `400 ... too many states` | 某 schema 未被 T1 覆盖或预算回归 | 跑 T2 找出超标 schema，修 `gemini_schema.py`，**不改业务 schema** |
| `Invalid X output: ... too_long` | 模型超数量上限且校正也失败 | 确认该字段上限出现在 `schema_cardinality_contract` 输出里（跑一次打印确认）；仍失败则记录 run_id 交人工，**不逐字段改 prompt** |
| `source-sensitive claims without ... citations` | 引用校验失败且 Patch 重试耗尽 | 查 run history 中失败 claim 的 `evidence_status`：若为 assumption/unsupported 被误判 → 修 `citation_checker.py` 的判定逻辑；若确为漏引用 → 属模型质量问题，记录后用 Streamlit 的 Revision-only 重跑 |
| `Run budget exceeded` | 校正次数多于预算 | 按 T4 上调 `.env`，不改代码 |
| `RESOURCE_EXHAUSTED / 429` | 免费额度耗尽 | 等待配额恢复；**严禁**加自动重试（429 不重试是既有设计） |
| `TAVILY_API_KEY is not set` | 配置缺失 | 补 `.env` 或接受降级模式，不改代码 |
| `PromptBudgetExceededError` | 证据/critique 堆叠超 120K 字符 | 属预期保护；降低 RAG top_k 传参，不放宽预算 |

## 5. 禁止事项

- 禁止修改 `schemas/` 下任何业务 schema 来"绕过"400（结构与上限是产品契约）。
- 禁止在单个 agent 的 prompt 里新增数量上限文案（`schema_cardinality_contract` 已自动生成，
  人工补写会再次制造双源漂移）。
- 禁止为任何 4xx 增加自动重试；禁止静默截断列表。
- 禁止改动 `pytest.ini` 的 live 默认排除。
- 禁止在本计划范围外"顺手重构"。

## 6. 完成定义

- [ ] `pytest -q` 全绿（含新 T2 守卫）。
- [ ] `pytest -m live tests/test_live_schema_acceptance.py -q` 全绿。
- [ ] Streamlit 三模式 live 各成功 1 次，产出 13 章节完整 Markdown。
- [ ] 三个成功 run 的 run_id 记录在验收 commit message 中。
