删除本文件夹即可完整回滚 SLM 实验，无需任何其他操作。

# SLM 实验

## 上游私有依赖

`slm.client` 直接依赖 `workflow.llm_client._ACTIVE_USAGE_TRACKER`，以便 SLM
请求继续写入现有 `capture_llm_usage()` 上下文。若上游重命名该私有名称，此处
必须同步更新；`slm/tests/test_slm_client.py` 的契约测试会立即报告这种漂移。

## 验证记录

### S1.2 结构化输出能力验证（2026-07-26）

环境：Ollama OpenAI-compatible endpoint `http://localhost:11434/v1`，
模型 `qwen2.5:3b`，OpenAI Python SDK `2.48.0`，temperature `0`。
验证脚本与原始 JSON 结果位于 Git 忽略的 `slm/tmp/`。

1. `json_object` + prompt 内嵌三字段 schema：通过。返回合法 JSON 并通过
   严格 Pydantic 校验；耗时 4.375 秒，输出 20 tokens，`finish_reason=stop`。
2. 三字段 `json_schema`：通过。字段结构、类型及禁止额外字段的约束生效，
   严格 Pydantic 校验通过；耗时 2.364 秒，输出 24 tokens，
   `finish_reason=stop`。
3. `relaxed_response_schema(CritiqueReport)`：通过。请求无 provider 错误，
   返回值通过原始 `CritiqueReport` 严格 Pydantic 校验；耗时 1.993 秒，
   输出 26 tokens，`finish_reason=stop`。
4. `relaxed_response_schema(ProposalDraft)`：请求成功但严格校验失败。模型在
   40.013 秒内输出 476 tokens，`finish_reason=stop`；13 个章节结构和标题均
   生成，但所有 `content` 都是空字符串，触发原始 schema 的 13 个
   `min_length=40` 校验错误。

结论：端点存活，小 schema 与真实 `CritiqueReport` 的 `json_schema` 可用；
13 章节大 schema 的请求可完成，但不能可靠满足被 relaxed schema 移除的严格
字段约束。因此 S2.4 的默认模式应使用 `json_object`，并保留严格 Pydantic
校验与一次校正请求。

### S4.1 逐管道验证（2026-07-27）

环境：Ollama OpenAI-compatible endpoint `http://localhost:11434/v1`，
模型 `qwen2.5:3b`，`SLM_STRUCTURED_MODE=json_object`，其余参数使用
`slm/.env.slm.example` 的默认值。三种模式均使用同一份
[`slm/examples/ai_education.json`](examples/ai_education.json) 输入。命令形式为：

```powershell
python -m slm.cli --mode <baseline|workflow|multi> --input slm/examples/ai_education.json
```

本机没有全局 `python` 命令，实际执行时使用 Codex 的 Python 3.12 解释器，
并从项目 `.venv` 与 Git 忽略的 `slm/tmp/s4-deps` 加载依赖；管道代码、配置和
输入均未因此改变。以下结果是冒烟可用性记录，不是 Phase 7 四臂对比实验数据。

| 模式 | 次数 | run_id | 结果 | 耗时（秒） | 结构校正次数 | 终止原因 |
|---|---:|---|---|---:|---:|---|
| baseline | 1 | `20260727_095201_368798` | 失败 | 1479.242 | 0 | `APITimeoutError`；没有返回可校验响应 |
| baseline | 2 | `20260727_101750_047609` | 失败 | 450.128 | 1 | 校正后仍把 schema 描述当作结果，`BusinessProposal` 缺少 16 个必填字段 |
| baseline | 3 | `20260727_120342_234467` | 失败 | 1196.144 | 0 | `APITimeoutError`；没有返回可校验响应 |
| workflow | 1 | `20260727_122503_415593` | 失败 | 1020.259 | 0 | planner 成功，`section_writer` 请求超时 |
| workflow | 2 | `20260727_124335_181660` | 失败 | 1035.766 | 0 | planner 成功，`section_writer` 请求超时 |
| workflow | 3 | `20260727_130335_678059` | 失败 | 1044.432 | 0 | planner 成功，`section_writer` 请求超时 |
| multi | 1 | `20260727_132153_557721` | 失败 | 554.784 | 1 | finance 校正后成功；writer prompt `91832 > 60000`，发请求前被预算守卫拦截 |
| multi | 2 | `20260727_133220_690299` | 失败 | 112.359 | 1 | research 校正后仍有额外字段 `source_quality` |
| multi | 3 | `20260727_133450_124867` | 失败 | 563.176 | 1 | finance 校正后仍未满足 assumption-not-forecast 契约 |

汇总：

| 模式 | 成功次数 | 最终失败率 | 平均耗时（秒） | 总结构校正次数 |
|---|---:|---:|---:|---:|
| baseline | 0/3 | 100% | 1041.838 | 1 |
| workflow | 0/3 | 100% | 1033.486 | 0 |
| multi | 0/3 | 100% | 410.106 | 3 |

各结构化 LLM 节点的 `StructuredOutputValidationError` 触发率，以节点实际执行
次数为分母；`retry_count` 与最终持久化错误共同用于确认触发：

| 模式 | 节点 | 实际执行次数 | 触发次数 | 触发率 |
|---|---|---:|---:|---:|
| baseline | `BusinessProposal` | 3 | 1 | 33.3% |
| workflow | `proposal_planner` | 3 | 0 | 0% |
| workflow | `section_writer` | 3 | 0 | 0% |
| workflow | `basic_critic` | 0 | 0 | N/A（未到达） |
| workflow | `revision` | 0 | 0 | N/A（未到达） |
| multi | `research` | 3 | 1 | 33.3% |
| multi | `strategy` | 2 | 0 | 0% |
| multi | `finance` | 2 | 2 | 100% |
| multi | `writer` | 1 | 0 | 0%（预算守卫在请求前拦截） |
| multi | `critic` | 0 | 0 | N/A（未到达） |
| multi | `revision` | 0 | 0 | N/A（未到达） |

`supervisor` 是确定性计划节点，`rag_retrieval` 不调用结构化 LLM，故不计入上表。
multi 第 1、3 次均完成 research 与 strategy，第 1 次还完成 finance 和本地 RAG，
因此 RAG 路径本身可运行。当前环境已配置 Tavily，三次 multi 实跑均走真实 Web
证据路径，没有触发未配置降级；无 Tavily 时注入 `no_web_search` 且继续本地 RAG
的行为由 `slm/tests/test_slm_pipeline.py` 的隔离测试覆盖。

结论：默认配置下三条 pipeline 的最终失败率均为 100%，主要可用性瓶颈分别是
baseline 大输出超时/结构漂移、workflow 的 13 章节 `section_writer` 超时，以及
multi 的 finance 结构契约和 writer prompt 超出独立 60K 字符预算。

### S4.2 数据驱动应急（2026-07-27）

根据上述 S4.1 数据，只启用已触发的两类应急：

- `SectionDrafts`、`ProposalDraft`、`RevisedProposal` 强制使用
  `json_object`，不受全局 `SLM_STRUCTURED_MODE=json_schema` 覆盖影响。
- workflow 的 `section_writer` 改由 `ChunkedSectionAdapter` 注入，将固定
  13 章节按 5/4/4 分成三次严格校验请求，再合并为完整 `SectionDrafts`。
- multi-agent graph 通过既有 `rag_top_k` 注入参数从 3 下调到 1，减少进入
  writer prompt 的 RAG 证据体积，不修改 graph builder 或 prompt。

九次 S4.1 实跑均未出现 `finish_reason=length`，所以没有修改 prompt，也没有增加
截断续写逻辑。`SLM_MAX_OUTPUT_TOKENS` 仍由 `slm/config.py` 独立读取，并作为
OpenAI-compatible 请求的 `max_tokens` 参数传入；对应契约由
`slm/tests/test_slm_client.py` 覆盖。
