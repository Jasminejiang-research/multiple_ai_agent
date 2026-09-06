删除本文件夹即可完整回滚 SLM 实验，无需任何其他操作。

# SLM 实验

## 必读：服务端上下文窗口

`SLM_MODEL_NAME` **必须**指向一个显式设置了 `num_ctx` 的模型。Ollama 对超窗
prompt 的处理是**静默左截断**——不报错、不警告、`finish_reason=stop`——被丢弃
的正是 prompt 头部的指令段。参见下方「S4.5 根因」。

```bash
curl -X POST http://localhost:11434/api/create -d '{"model":"qwen2.5-3b-32k","from":"qwen2.5:3b","parameters":{"num_ctx":32768},"stream":false}'
```

`check_slm_preflight()` 会在启动时实测端点的有效窗口并与
`required_context_tokens()` 比对，不足则以 `slm_context_window_too_small`
中止。实测结果按 `base_url|model_name|required_tokens` 缓存在
`slm/context_window_cache.json`（已 gitignore），只有首次运行付出探测成本；
删除该文件可强制重测，`SLM_CONTEXT_PROBE=0` 可跳过检查。

> **当前实验对象是 Qwen2.5-7B-Instruct（SiliconFlow 托管），不是 3B。**
> 下方"验证记录"里 S1.2 / S4.1 / S4.8 的全部数据都是本机 Ollama 上的
> Qwen2.5-**3B** 测得的，**对 7B 不成立，仅作历史留档**。
> `sprint_plan_SLM.md` 仍写 3B，尚未更新——待 7B 跑通后再决定是否修订。

## 部署形态：从 Ollama 到 SiliconFlow

两次切换，原因不同：

**第一次，本机 Ollama → 云端。** 本机（MX450 2GB 显存 / 16GB 内存）无法承载
3B × 32K 上下文，详见 S4.8：吞吐塌到 0.06 t/s，一次 writer 请求跑 10h21m 只
产出 2,234 token。

**第二次，DashScope → SiliconFlow。** 阿里云百炼已不再提供
Qwen2.5-3B-Instruct（231 个模型的目录里没有它，控制台搜 "Qwen2.5" 只剩
Omni-7B 与 VL-Embedding）。SiliconFlow 提供 `Qwen/Qwen2.5-7B-Instruct`，
因此实验对象由 3B 改为 **7B**。

本机 Ollama 的 3B 模型已删除。若日后需要重新测本地延迟，重新
`ollama pull qwen2.5:3b` 并按 S4.8 的结论设置 `num_ctx` 即可。

## 旧部署形态：为什么离开 DashScope

本机（MX450 2GB 显存 / 16GB 内存）无法承载 Qwen2.5-3B × 32K 上下文：模型加
KV 缓存共 3.56 GB，仅 0.55 GB 能进显存，上下文涨到 15K token 后开始换页，
生成吞吐从约 3 t/s 塌到 **0.06 t/s**——一次 writer 请求跑了 10h21m 只产出
2,234 token，最终 500。详见下方 S4.8。

因此 SLM 臂改用 `sprint_plan_SLM.md` 1.2 表列出的第三种部署方式：DashScope 的
OpenAI 兼容端点。`SLMClient` 一套代码通吃，切换成本只是三个环境变量。**本机
Ollama 部署保留用于延迟指标测量**——那是本地部署唯一不可替代的用途。

切换需要在 `slm/.env.slm` 填入你自己的 DashScope API key，以及从定价页填入
`SLM_INPUT_USD_PER_MILLION_TOKENS` / `SLM_OUTPUT_USD_PER_MILLION_TOKENS`，
否则 SLM 臂在每条 run record 里的成本恒为 0。

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

### S4.5 S4.1 全数失败的根因与修复（2026-07-27）

S4.2 的应急措施把 S4.1 的九次失败当成九个独立的模型能力问题处理。实际上它们
共享同一个环境根因：**Ollama 的有效上下文窗口是 2048 token**。

`/api/show` 显示 `qwen2.5:3b` 的 `parameters` 为空——Modelfile 没有
`PARAMETER num_ctx`，于是走服务端默认值，而模型自身
`qwen2.context_length` 是 32768。实测证据：

| 探针（42,872 字符） | `prompt_eval_count` | 能否复述 prompt 开头的口令 |
|---|---:|---|
| 默认 | **2050** | 否 |
| `num_ctx=16384` | 7067 | 是 |

按实测的 4.36 chars/token 换算，**最小**的 finance 请求（仅 brief，无前置
packet）就是 9,700 字符 / 2,227 token，已经超窗；multi 模式带上
`research_analysis` 与 `strategy_analysis` 后约 3,520 token，超过 40% 被丢弃。
被丢的正是 `prompts/finance_agent.md` 的指令头部——那里逐字写着
`"All financial figures are assumptions for planning discussion, not forecasts."`
校正请求同样失败，因为校正段追加在尾部，指令头部依然缺失。

同一根因解释全部九次失败：

| S4.1 记录 | 截断解释 |
|---|---|
| finance「assumption-not-forecast」×2 | 指令头部不在窗口内 |
| baseline「校正后仍把 schema 描述当作结果」 | 保留的是尾部，即追加的 JSON schema；`relaxed_response_schema` 保留 `description`，模型照抄成字段值 |
| research 多出 `source_quality` 字段 | `extra="forbid"` 的约束在被丢弃的段落里 |
| `APITimeoutError` 与 1000s+ 的 run | `max_tokens=8192` > `num_ctx=2048`，生成超窗触发 context shift 循环，反复重新 prefill |

同时发现两个 `slm/` 内的缺陷：

1. `openai.OpenAI(...)` 未设 `max_retries`，SDK 默认 2。一次
   `APITimeoutError` 实耗 3 × `SLM_REQUEST_TIMEOUT`，且这些重试绕过
   `reserve_run_request()` 与 usage tracker，run budget 和 `retry_count` 记账
   偏低。已改为 `max_retries=0`，瞬时重试仍由本模块自己完成并计数。
2. preflight 只探活 `/models`，从不验证端点能否提供 `SLM_MAX_PROMPT_CHARS` +
   `SLM_MAX_OUTPUT_TOKENS` 所需的窗口。配置写 22K、实际 2K，差十倍而全程无声。
   已补 `slm_context_window_too_small` 断言。

修复验证：同一份代码、同一 prompt、同一 schema，仅把 `SLM_MODEL_NAME` 指向
`qwen2.5-3b-32k`，finance 节点在 281.4s 后通过严格校验，
`assumption_notice` 为 `'All financial figures are assumptions for planning
discussion, not forecasts.'`——与 prompt 中的示例逐字一致，反证此前模型确实
从未读到该段。preflight 对原 `qwen2.5:3b` 实测得 2050 < 23192，31s 内以
`slm_context_window_too_small` 中止。

其他实测数据：`SLM_REQUEST_TIMEOUT` 默认值由 300 上调至 900（单次 finance
调用即 281s）；32K 窗口下 `/api/ps` 报告占用 3.56 GB（0.55 GB 在 2GB 显存的
MX450，其余在内存）。

**S4.1 与 S4.2 的结论作废**：那批失败率是在 6% 上下文窗口下测得的，不能作为
Qwen2.5-3B 的能力证据，S4.2 依据它启用的应急措施也需要在修复后重新评估。

#### 修复后首次 multi 实跑（run `20260727_152916_369283`）

supervisor / research / strategy / **finance** 全部完成，`retry_count: 0`——
finance 首次请求即通过严格校验，S4.1 中两次失败的 assumption-not-forecast
契约不再触发。该跑最终失败于 writer 的
`PromptBudgetExceededError: 71926 > 60000`。

这是同一根因的延伸：`SLM_MAX_PROMPT_CHARS=60000` 是按一个从不存在的窗口标定
的。71,926 字符 ≈ 16,500 token，加 8,192 输出 = 24,700，本就放得进 32,768。
预算必须满足不变式

```
SLM_MAX_PROMPT_CHARS / CHARS_PER_TOKEN + SLM_MAX_OUTPUT_TOKENS <= num_ctx
```

据此把本机 `.env.slm` 的 `SLM_MAX_PROMPT_CHARS` 调至 90000
（30,692 <= 32,768，余量 2,076 token）。`slm/config.py` 的默认值
`DEFAULT_MAX_PROMPT_CHARS=60000` 未改动——它由 sprint plan 1.2 表固定，是否
一并调整属实验参数决策。注意该不变式的上限来自 `num_ctx`，不是模型标称的
32K；换模型或改 `num_ctx` 后必须重新核对，preflight 的窗口断言会捕获不一致。

#### 第二次 multi 实跑（run `20260727_155603_572432`）

supervisor / research / strategy / finance / rag_retrieval 全部完成，
`retry_count: 0`（finance 零校正通过第二次复现）。writer 请求**成功发出**
（`request_count: 4`），在 900s 超时。整跑 2675s。

这次超时是**一次干净的 900s 失败**而非修复前的 3×900s——`max_retries=0` 生效。

剩余瓶颈与结构化输出无关，是纯吞吐：multi 的 `writer` 拿的是
`StructuredJsonLLM(ProposalDraft)`，要在单次请求内生成全部 13 个章节；约
16,500 token 的 prefill 在本机就要 200s 量级，之后还要生成数千 token。S4.2 的
`ChunkedSectionAdapter` 只接在 workflow 的 `section_writer` 上。

#### S4.6 writer 分批适配器（2026-07-27）

新增 `ChunkedProposalAdapter`，与 `ChunkedSectionAdapter` 同构但面向
`ProposalDraft`——后者的 13 个章节是**具名对象字段**而非列表，因此按
`PROPOSAL_SECTION_FIELD_NAMES` 的 5/4/4 切分，每批用 `create_model` 动态构造
只含该批字段的子模型（`extra="forbid"`，防止批次间串写），再合并成完整
`ProposalDraft` 做严格校验。`global_source_ids` 不进子模型：它由
`ProposalDraft` 自己的 validator 从各章节的 `source_ids` 推导。

由 `SLM_CHUNKED_WRITER` 控制，**默认关闭**——分批会让 SLM 臂的写作方式与
Gemini 臂（单次成文）不同，属 Phase 7 可比性决策，不应是默认值。

启用它的依据是 run `20260727_171547_339176`：`SLM_REQUEST_TIMEOUT=2700` 下
writer 单次请求仍然超时，整跑 3402.9s，其中 writer 独占 2700s 且无输出
（`request_count: 4`，前置四节点合计约 700s）。**在本机硬件上，13 章节单次
成文不可行**——这是模型加硬件的能力边界，不是待调的参数。

已知限制（与 `ChunkedSectionAdapter` 相同）：调用方的整体校验器（writer 的
引用校验）在合并后的 draft 上运行，且**没有校正机会**——一次校正意味着重新
生成全部三批。批次内的标题契约仍享有正常的一次校正。

#### S4.7 分批首跑暴露的两个缺陷（run `20260727_181428_132075`）

分批让 writer 从"永不返回"变成"能返回但校验失败"：batch 1 通过，batch 2 在
一次校正后仍有 12 项错误，整跑 2614.9s、`request_count: 6`。这 12 项指向两个
本模块的缺陷，都已修复：

1. **子模型比真实 schema 更严**。`_proposal_batch_model` 原本设
   `extra="forbid"`，而 `ProposalDraft` 自己**没有**设——模型自作主张多写一个
   `required_sections` 键，`ProposalDraft` 本会忽略，子模型却整批判失败。这是
   分批路径凭空多出来的失败模式。改为与 `ProposalDraft` 配置完全一致；跨批次
   串写依然无害，因为合并只读本批次的字段名。
2. **json_object 模式发的是 relaxed schema**。`relaxed_response_schema` 会丢弃
   成员数 >6 的枚举，这是为 **Gemini 把 schema 编译成受限解码状态机**准备的
   缓解措施——而 json_object 模式下没有任何东西编译它，schema 只是 prompt 文本。
   后果是模型从未见过 `claim_type` 的 9 个合法值，于是自创
   `revenue_stream` / `product_launch` / `marketing_strategy`；`content_anchor`
   的必填性也一并丢失。改为在 json_object 模式下发送严格
   `model_json_schema()`，json_schema 模式保持 relaxed。附带好处：严格版**更小**
   （writer 最大批次 3,228 vs 8,460 字符），因为 `$ref` 不展开重复定义。

同时把 `SLM_RUN_MAX_REQUESTS` 从 12 提到 18、`SLM_RUN_MAX_TOTAL_TOKENS` 从
160000 提到 300000。理由与预算重算同类：12 是按单次成文的 writer 定的，分批后
最少 8 次请求（research/strategy/finance 3 + writer 3 + critic + revision）、
每节点各一次校正则 16 次，12 会中途熔断。

### S4.8 本机硬件天花板与 SLM_REQUEST_TIMEOUT 失效（2026-07-28）

第六次 multi 实跑（run `20260727_222846_718971`，加了枚举契约）在 writer 挂死。
Ollama 服务端日志：

```
[GIN] 2026/07/28 - 11:44:55 | 500 | 10h21m32s | POST "/v1/chat/completions"
slot print_timing: task 10690 | n_decoded = 2234, tg = 0.06 t/s
slot   operator(): n_ctx_slot = 32768, task.n_tokens = 13210
slot      release: n_tokens = 15448, truncated = 0
```

**一次请求 10 小时 21 分只生成 2,234 token。** `truncated = 0` 说明 num_ctx
修复始终有效，问题不在截断。3 秒窗口显示吞吐在 0–3.2 t/s 剧烈波动，累计均值
0.06 t/s——典型的换页特征：`/api/ps` 报告模型加 KV 占 3.56 GB，其中只有
0.55 GB 在 2GB 显存，其余压在内存上，上下文涨到 15K token 时可用物理内存
不足。同一跑里更早的请求是 3–23 分钟不等，说明是随上下文增长逐步塌陷，
不是一开始就卡死。

**这是硬件天花板，不是代码缺陷。**

附带发现一个缺陷并已修复：`SLM_REQUEST_TIMEOUT=2700` **没有终止**这个 10 小时
的请求。SDK 的 timeout 是 httpx 的 read timeout，衡量的是相邻 socket 读之间的
间隔而非总耗时，因此不是墙钟上界（它在第四次跑里确实生效过，说明只是不可靠，
不是完全无效）。`slm/client.py` 现在用守护线程加了一层墙钟看门狗，
`WALL_CLOCK_GRACE_MULTIPLIER = 1.2` 让 SDK 超时先有机会抛出正常的
`APITimeoutError`，看门狗只兜住它完全不触发的情况。线程设为 daemon，确保
被放弃的请求永远不会阻塞解释器退出——正是这一点把一次卡死变成了通宵挂起。
