# Open Proposal Agent - Sprint Plan

> 用途：给 Cursor 逐步执行的极细粒度开发清单。  
> 项目策略：从零基础开始，不直接做复杂 multi-agent；先建立 baseline，再演进为 workflow、multi-agent、RAG、web research、human approval、evaluation、MCP 和开源发布。  
> 执行规则：每完成一个 checkbox，就提交一次小 commit 或至少保存清晰的工作状态。

---

## Global Development Rules for Cursor

- [ ] 一次只处理一个 checkbox，不要同时改多个大模块。
- [ ] 每次写代码前先确认目标文件路径。
- [ ] 每次新增函数都写 docstring 或注释说明输入输出。
- [ ] 每次新增 Pydantic schema 后，写最小测试。
- [ ] 每次新增 prompt 后，用至少 1 个 sample input 手动测试。
- [ ] 每次新增 workflow 节点后，保存该节点输入输出日志。
- [ ] 每次引入新依赖后，更新 `pyproject.toml` 和 README。
- [ ] 每次完成 Sprint 后，更新 `docs/roadmap.md` 或 README progress。
- [ ] 不提前实现 MCP、复杂 Web 前端、多用户权限、自动发邮件。
- [ ] 所有 API key 只放 `.env`，不要提交到 Git。



### Cursor Completion Report Protocol

每完成一个 Task checkbox 后，Cursor 必须回答：

1. 这个 Task 新增/修改了哪些文件？
2. 每个文件在系统架构中负责什么？
3. 这个 Task 对最终 business proposal generation pipeline 的作用是什么？
4. 现在有哪些测试证明它工作了？
5. 这个 Task 还不能证明什么？

---



## Phase 0 - 定义项目边界，不写代码 (Sprint 0)



### Sprint 0 - Project Boundary and Documentation



#### Goal

先不写业务代码。明确产品范围、输出格式、成功标准、评估标准。

#### Deliverables

- `README.md`
- `docs/PRD.md`
- `docs/USER_STORIES.md`
- `docs/PROPOSAL_OUTPUT_SCHEMA.md`
- `docs/EVALUATION_RUBRIC.md`
- `docs/architecture_design.md`



#### Tasks



##### 0.1 Repository Setup

- [ ] 在 GitHub 创建仓库 `open-proposal-agent`。
- [ ] 在 GitLab 创建镜像仓库或备份仓库。
- [ ] 在本地 clone GitHub 仓库。
- [ ] 用 Cursor 打开项目根目录。
- [ ] 创建 `README.md`。
- [ ] 创建 `.gitignore`。
- [ ] 创建 `.env.example`。
- [ ] 创建 `docs/` 文件夹。
- [ ] 创建 `outputs/` 文件夹。
- [ ] 创建 `knowledge_base/` 文件夹。
- [ ] 创建 `examples/` 文件夹。
- [ ] 创建 `tests/` 文件夹。
- [ ] 提交 commit：`chore: initialize repository structure`。



##### 0.2 README v0

- [ ] 在 README 写项目名称：`Open Proposal Agent`。
- [ ] 写一句话介绍。
- [ ] 写目标用户：早期创业者、商学院学生、产品经理。
- [ ] 写 MVP 输入字段。
- [ ] 写 MVP 输出章节。
- [ ] 写第一版不做什么。
- [ ] 写 10 行以内 Quickstart 占位。
- [ ] 写 Roadmap 占位。
- [ ] 提交 commit：`docs: add initial README`。



##### 0.3 PRD

- [ ] 创建 `docs/PRD.md`。
- [ ] 写 Product Overview。
- [ ] 写 User Personas。
- [ ] 写 Core User Journey。
- [ ] 写 MVP Scope。
- [ ] 写 Non-goals。
- [ ] 写 Success Metrics。
- [ ] 写 Risks。
- [ ] 写 Open Questions。
- [ ] 提交 commit：`docs: add PRD`。



##### 0.4 User Stories

- [ ] 创建 `docs/USER_STORIES.md`。
- [ ] 写用户故事：作为早期创业者，我想输入商业想法并生成 proposal。
- [ ] 写用户故事：作为学生，我想生成固定结构 proposal。
- [ ] 写用户故事：作为产品经理，我想看到风险和假设。
- [ ] 写用户故事：作为研究者，我想对比 baseline 和 multi-agent 质量。
- [ ] 每条用户故事加 acceptance criteria。
- [ ] 提交 commit：`docs: add user stories`。



##### 0.5 Output Schema Documentation

- [ ] 创建 `docs/PROPOSAL_OUTPUT_SCHEMA.md`。
- [ ] 列出 13 个 proposal 章节。
- [ ] 为每个章节写目的。
- [ ] 为每个章节写必须包含的内容。
- [ ] 为每个章节写禁止内容。
- [ ] 定义 key claims 和 citations 的要求。
- [ ] 提交 commit：`docs: define proposal output schema`。



##### 0.6 Evaluation Rubric Documentation

- [ ] 创建 `docs/EVALUATION_RUBRIC.md`。
- [ ] 写 10 个评分维度。
- [ ] 每个维度定义 1-5 分标准。
- [ ] 写 hallucination 风险评估标准。
- [ ] 写 financial consistency 评估标准。
- [ ] 写 evidence quality 评估标准。
- [ ] 写总分计算方式。
- [ ] 提交 commit：`docs: add evaluation rubric`。



#### Definition of Done

- [ ] 项目边界清楚。
- [ ] 输出结构清楚。
- [ ] 成功标准清楚。
- [ ] 第一版不做什么清楚。
- [ ] 可以开始写 Single-Agent Baseline。

---



## Phase 1 - 做一个 Single-Agent Baseline (Sprints 1-4)



### Sprint 1 - Python Project Foundation



#### Goal

搭建可运行的 Python 项目骨架，为 Streamlit 和 Pydantic 做准备。

#### Deliverables

- `pyproject.toml`
- `src/open_proposal_agent/`
- `tests/test_imports.py`
- `.env.example`



#### Tasks



##### 1.1 Python Environment

- [ ] 确认本机 Python 版本为 3.11 或以上。
- [ ] 创建虚拟环境 `.venv`。
- [ ] 激活虚拟环境。
- [ ] 创建 `pyproject.toml`。
- [ ] 添加基础依赖：`pydantic`、`python-dotenv`、`pytest`、`rich`。
- [ ] 添加 Streamlit 依赖：`streamlit`。
- [ ] 添加 LLM client 依赖：先选一个 provider，例如 `openai`。
- [ ] 安装项目依赖。
- [ ] 运行 `python --version` 确认环境。
- [ ] 提交 commit：`chore: add python project configuration`。



##### 1.2 Package Structure

- [ ] 创建 `src/open_proposal_agent/__init__.py`。
- [ ] 创建 `src/open_proposal_agent/schemas/`。
- [ ] 创建 `src/open_proposal_agent/prompts/`。
- [ ] 创建 `src/open_proposal_agent/llm/`。
- [ ] 创建 `src/open_proposal_agent/export/`。
- [ ] 创建 `src/open_proposal_agent/utils/`。
- [ ] 创建 `tests/test_imports.py`。
- [ ] 在测试中 import `open_proposal_agent`。
- [ ] 运行 `pytest`。
- [ ] 提交 commit：`chore: add package skeleton`。



##### 1.3 Environment Variables

- [ ] 在 `.env.example` 添加 `OPENAI_API_KEY=`。
- [ ] 在 `.env.example` 添加 `DEFAULT_MODEL=`。
- [ ] 在 `.env.example` 添加 `OUTPUT_DIR=outputs`。
- [ ] 创建本地 `.env`，不要提交。
- [ ] 写 `src/open_proposal_agent/utils/config.py`。
- [ ] 在 `config.py` 中读取环境变量。
- [ ] 写测试确认 config 可加载。
- [ ] 提交 commit：`chore: add environment configuration`。



#### Definition of Done

- [ ] `pytest` 可运行。
- [ ] 项目可以被 import。
- [ ] `.env.example` 完整。
- [ ] 没有 API key 被提交。

---



### Sprint 2 - Core Schemas



#### Goal

先定义结构化输入输出，再写 LLM 逻辑。

#### Deliverables

- `src/open_proposal_agent/schemas/proposal.py`
- `src/open_proposal_agent/schemas/workflow.py`
- `tests/test_schemas.py`



#### Tasks



##### 2.1 User Input Schema

- [ ] 创建 `schemas/proposal.py`。
- [ ] 定义 `ProposalGoal` enum。
- [ ] 定义 `UserBrief` schema。
- [ ] 字段包含 company/product name。
- [ ] 字段包含 industry。
- [ ] 字段包含 target_customer。
- [ ] 字段包含 problem。
- [ ] 字段包含 solution。
- [ ] 字段包含 business_model。
- [ ] 字段包含 geography。
- [ ] 字段包含 proposal_goal。
- [ ] 字段包含 optional stage。
- [ ] 字段包含 optional known_competitors。
- [ ] 添加字段最小长度校验。
- [ ] 写 valid input 测试。
- [ ] 写 missing required field 测试。
- [ ] 提交 commit：`feat: add user brief schema`。



##### 2.2 Proposal Output Schema

- [ ] 定义 `ProposalSection` schema。
- [ ] 定义 `ProposalDraft` schema。
- [ ] 添加 13 个固定章节字段。
- [ ] 每个 section 支持 `title`。
- [ ] 每个 section 支持 `content`。
- [ ] 每个 section 支持 `key_claims`。
- [ ] 每个 section 支持 `source_ids`。
- [ ] 每个 section 支持 `confidence`。
- [ ] 写测试确认 13 个章节都存在。
- [ ] 写测试确认空 content 不通过。
- [ ] 提交 commit：`feat: add proposal output schema`。



##### 2.3 Critique Schema

- [ ] 定义 `CritiqueSeverity` enum。
- [ ] 定义 `CritiqueIssueType` enum。
- [ ] 定义 `CritiqueIssue` schema。
- [ ] 定义 `CritiqueReport` schema。
- [ ] 添加 `overall_score` 范围 0-10。
- [ ] 添加 `must_fix_before_export`。
- [ ] 写测试确认 severity 枚举有效。
- [ ] 写测试确认 score 超出范围会失败。
- [ ] 提交 commit：`feat: add critique schema`。



##### 2.4 Markdown Rendering Schema Support

- [ ] 给 `ProposalDraft` 添加 `to_markdown()` 方法或单独 renderer。
- [ ] 确保 Markdown 包含标题。
- [ ] 确保 Markdown 包含 13 个章节。
- [ ] 确保 Markdown 包含 confidence。
- [ ] 确保 Markdown 包含 key claims。
- [ ] 写测试确认 Markdown 字符串包含 `Executive Summary`。
- [ ] 提交 commit：`feat: add proposal markdown renderer`。



#### Definition of Done

- [ ] 所有核心 schema 可用。
- [ ] schema 测试通过。
- [ ] 任何 proposal 输出都能转成 Markdown。

---



### Sprint 3 - Single-Agent Baseline



#### Goal

实现最简单可运行版本：用户输入 idea，一个 LLM 生成完整 proposal，并导出 Markdown。

#### Deliverables

- `prompts/single_agent_proposal.md`
- `src/open_proposal_agent/llm/client.py`
- `src/open_proposal_agent/baseline.py`
- `outputs/*.md`



#### Tasks



##### 3.1 Prompt File

- [ ] 创建 `prompts/single_agent_proposal.md`。
- [ ] 写 Role：business proposal generation assistant。
- [ ] 写 Objective：生成 investor-style structured business proposal。
- [ ] 写 Inputs：UserBrief 字段。
- [ ] 写 Required Sections：13 个章节。
- [ ] 写 Output Rules：不得编造具体市场数据。
- [ ] 写 Output Rules：信息不足时写 assumption。
- [ ] 写 Output Rules：以 Markdown 输出。
- [ ] 写 Quality Criteria。
- [ ] 提交 commit：`feat: add single agent prompt`。



##### 3.2 LLM Client

- [ ] 创建 `llm/client.py`。
- [ ] 写 `LLMClient` 类。
- [ ] 从 config 读取 API key。
- [ ] 从 config 读取 model name。
- [ ] 写 `generate_text(prompt: str) -> str`。
- [ ] 加错误处理：无 API key 时给清晰错误。
- [ ] 加错误处理：API 调用失败时返回可读异常。
- [ ] 写一个不调用真实 API 的 mock test。
- [ ] 提交 commit：`feat: add llm client wrapper`。



##### 3.3 Baseline Generator

- [ ] 创建 `baseline.py`。
- [ ] 写 `build_single_agent_prompt(user_brief)`。
- [ ] 写 `generate_baseline_proposal(user_brief)`。
- [ ] 调用 prompt file。
- [ ] 注入用户输入。
- [ ] 调用 LLM。
- [ ] 保存 raw response。
- [ ] 暂时允许 Markdown response，不强制 JSON。
- [ ] 提交 commit：`feat: implement single agent baseline generator`。



##### 3.4 Export Markdown

- [ ] 创建 `export/markdown.py`。
- [ ] 写 `save_markdown(content, output_dir, project_name)`。
- [ ] 文件名包含日期。
- [ ] 文件名做 safe slug。
- [ ] 保存到 `outputs/`。
- [ ] 返回文件路径。
- [ ] 写测试确认文件被创建。
- [ ] 提交 commit：`feat: add markdown exporter`。



##### 3.5 Manual Test Case

- [ ] 创建 `examples/sample_input.json`。
- [ ] 填一个 AI education app 示例。
- [ ] 写一个脚本读取 sample input。
- [ ] 调用 baseline generator。
- [ ] 保存 Markdown。
- [ ] 手动检查是否有 13 个章节。
- [ ] 提交 commit：`test: add baseline sample input`。



#### Definition of Done

- [ ] 一个 sample input 可以生成 proposal。
- [ ] proposal 保存为 Markdown。
- [ ] 输出大致 5-10 页。
- [ ] 章节结构稳定。
- [ ] README 写明如何运行 baseline。

---



### Sprint 4 - Streamlit MVP UI



#### Goal

让非技术用户可以通过浏览器表单使用 baseline。

#### Deliverables

- `app.py` 或 `src/open_proposal_agent/app/streamlit_app.py`
- Streamlit 表单
- Markdown 下载按钮



#### Tasks



##### 4.1 Basic App

- [ ] 创建 `app.py`。
- [ ] 添加页面标题 `Open Proposal Agent`。
- [ ] 添加项目说明。
- [ ] 添加 sidebar 显示当前阶段：Single-Agent Baseline。
- [ ] 添加 warning：输出是草案，不是法律/投资建议。
- [ ] 运行 `streamlit run app.py`。
- [ ] 提交 commit：`feat: add streamlit app shell`。



##### 4.2 User Form

- [ ] 添加 text input：Company / Product Name。
- [ ] 添加 text input：Industry。
- [ ] 添加 text area：Target Customer。
- [ ] 添加 text area：Problem。
- [ ] 添加 text area：Solution。
- [ ] 添加 text input：Business Model。
- [ ] 添加 text input：Geography。
- [ ] 添加 selectbox：Proposal Goal。
- [ ] 添加 optional text area：Known Competitors。
- [ ] 添加 optional text area：Additional Context。
- [ ] 表单提交后创建 `UserBrief`。
- [ ] 表单缺失时显示 validation error。
- [ ] 提交 commit：`feat: add proposal input form`。



##### 4.3 Generate Button

- [ ] 添加 `Generate Proposal` 按钮。
- [ ] 点击按钮后显示 spinner。
- [ ] 调用 baseline generator。
- [ ] 显示生成结果 Markdown。
- [ ] 保存 Markdown 到 outputs。
- [ ] 显示保存路径。
- [ ] 添加下载按钮。
- [ ] 提交 commit：`feat: connect streamlit app to baseline generator`。



##### 4.4 UI Robustness

- [ ] API key 缺失时在 UI 中显示明确错误。
- [ ] LLM 调用失败时显示错误但不崩溃。
- [ ] 用户输入过短时提示补充。
- [ ] 生成过程中禁用重复点击。
- [ ] README 添加 Streamlit 运行命令。
- [ ] 提交 commit：`fix: improve streamlit error handling`。



#### Definition of Done

- [ ] 用户不用命令行即可输入 idea。
- [ ] 用户可以看到 proposal。
- [ ] 用户可以下载 Markdown。
- [ ] Streamlit 不因常见错误崩溃。

---



## Phase 2 - 把 Single-Agent 改成 Deterministic Workflow (Sprints 5-6)



### Sprint 5 - Deterministic Workflow with LangGraph



#### Goal

把 single prompt 改成分步骤 workflow：validate → plan → write sections → assemble → critique → revise → export。

#### Deliverables

- `src/open_proposal_agent/workflows/proposal_graph.py`
- `src/open_proposal_agent/schemas/workflow.py`
- `prompts/planner.md`
- `prompts/section_writer.md`
- `prompts/basic_critic.md`
- `prompts/revision.md`



#### Tasks



##### 5.1 Install and Prepare LangGraph

- [x] 添加 `langgraph` 依赖。
- [x] 创建 `workflows/` 目录。
- [x] 创建 `workflows/proposal_graph.py`。
- [x] 创建 `schemas/workflow.py`。
- [x] 定义 `WorkflowState`。
- [x] 写最小 import test。
- [x] 提交 commit：`chore: add langgraph workflow foundation`。



##### 5.2 InputValidator Node

- [x] 写 `input_validator_node(state)`。
- [x] 检查 required fields。
- [x] 检查文本长度。
- [x] 返回 missing info list。
- [x] 不调用 LLM。
- [x] 写单元测试：完整输入通过。
- [x] 写单元测试：缺字段返回 missing info。
- [x] 提交 commit：`feat: add input validator node`。



##### 5.3 ProposalPlanner Node

- [x] 创建 `prompts/planner.md`。
- [x] prompt 要求输出 proposal outline。
- [x] 定义 `ProposalOutline` schema。
- [x] 写 `proposal_planner_node(state)`。
- [x] 调用 LLM。
- [x] 解析输出。
- [x] 保存到 state。
- [x] 写 mock test。
- [x] 提交 commit：`feat: add proposal planner node`。



##### 5.4 SectionWriter Node

- [x] 创建 `prompts/section_writer.md`。
- [x] 定义 `SectionDrafts` schema。
- [x] 写 `section_writer_node(state)`。
- [x] 为 13 个章节生成草稿。
- [x] 不做 critique。
- [x] 不新增工具调用。
- [x] 写 mock test。
- [x] 提交 commit：`feat: add section writer node`。



##### 5.5 ProposalAssembler Node

- [x] 写 `proposal_assembler_node(state)`。
- [x] 将 SectionDrafts 组合成 ProposalDraft。
- [x] 检查 13 个章节都存在。
- [x] 生成 Markdown preview。
- [x] 不调用 LLM。
- [x] 写单元测试。
- [x] 提交 commit：`feat: add proposal assembler node`。



##### 5.6 BasicCritic Node

- [x] 创建 `prompts/basic_critic.md`。
- [x] prompt 要求输出 issue list。
- [x] 使用 CritiqueReport schema。
- [x] 写 `basic_critic_node(state)`。
- [x] 检查逻辑漏洞。
- [x] 检查证据缺口。
- [x] 检查财务假设不清楚处。
- [x] 写 mock test。
- [x] 提交 commit：`feat: add basic critic node`。



##### 5.7 Revision Node

- [x] 创建 `prompts/revision.md`。
- [x] prompt 要求只根据 critique 修订。
- [x] 写 `revision_node(state)`。
- [x] 输入 draft + critique。
- [x] 输出 revised proposal。
- [x] 写 mock test。
- [x] 提交 commit：`feat: add revision node`。



##### 5.8 Graph Assembly

- [x] 在 `proposal_graph.py` 中定义 graph。
- [x] 添加节点：validator。
- [x] 添加节点：planner。
- [x] 添加节点：section_writer。
- [x] 添加节点：assembler。
- [x] 添加节点：critic。
- [x] 添加节点：revision。
- [x] 添加节点：exporter。
- [x] 设置正常边。
- [x] 设置 missing info 分支。
- [x] 写端到端 mock test。
- [x] 提交 commit：`feat: assemble proposal workflow graph`。



#### Definition of Done

- [x] workflow 可以跑完整流程。
- [x] 每一步有明确输入输出。
- [x] 中间节点可以单独测试。
- [x] Streamlit 可以选择运行 baseline 或 workflow。

---



### Sprint 6 - Persistence and Observability



#### Goal

让每次运行可追踪、可调试、可复现。

#### Deliverables

- SQLite database
- `runs` table
- `node_outputs` table
- basic logging
- run detail UI



#### Tasks



##### 6.1 SQLite Setup

- [x] 添加 `sqlalchemy` 依赖。
- [x] 创建 `storage/db.py`。
- [x] 创建 SQLite 连接。
- [x] 默认数据库路径为 `data/app.db`。
- [x] 创建 `data/` 文件夹。
- [x] `.gitignore` 排除 `data/*.db`。
- [ ] *提交 commit：*`chore: add sqlite storage setup`。



##### 6.2 DB Models

- [x] 创建 `storage/models.py`。
- [x] 定义 `RunRecord` table。
- [x] 定义 `NodeOutput` table。
- [x] 定义 `AgentOutput` table。
- [x] 定义 `ProposalOutput` table。
- [x] 定义 `ErrorRecord` table。
- [x] 写测试创建表。
- [ ] 提交 commit：`feat: add database models`。



##### 6.3 Run Repository

- [x] 创建 `storage/repositories.py`。
- [x] 写 `create_run()`。
- [x] 写 `update_run_status()`。
- [x] 写 `save_node_output()`。
- [x] 写 `save_error()`。
- [x] 写 `get_run()`。
- [x] 写 `list_runs()`。
- [x] 写单元测试。
- [ ] 提交 commit：`feat: add run repository`。



##### 6.4 Workflow Logging

- [x] 每个 workflow node 开始时记录 step name。
- [x] 每个 workflow node 结束时保存 output。
- [x] 每个 LLM 调用保存 prompt version。
- [x] 每个异常保存 error record。
- [x] 在 Streamlit 显示 run_id。
- [x] 在 Streamlit 显示每步状态。
- [ ] 提交 commit：`feat: add workflow run logging`。



##### 6.5 Run Detail UI

- [x] 在 Streamlit sidebar 添加 recent runs。
- [x] 点击 run 显示输入 brief。
- [x] 显示每个节点状态。
- [x] 显示每个节点输出 preview。
- [x] 显示 error message。
- [x] 显示 final output path。
- [x] 提交 commit：`feat: add run detail view`。



#### Definition of Done

- [x] 每次生成都有 run_id。
- [x] 每一步输出可查看。
- [x] 出错时知道哪个节点失败。
- [x] 同一输入可以保存 run record。

---



## Phase 3 - 引入真正的 Multiple Agents (Sprint 7)



### Sprint 7 - First Multi-Agent Version



#### Goal

引入真正的 multiple agents，但保持可控。第一版只做 Supervisor + Research + Strategy + Finance + Writer + Critic。

#### Deliverables

- `agents/supervisor.py`
- `agents/research.py`
- `agents/strategy.py`
- `agents/finance.py`
- `agents/writer.py`
- `agents/critic.py`
- corresponding prompts and schemas



#### Tasks



##### 7.1 Agent Base Interface

- [x] 创建 `agents/base.py`。
- [x] 定义 `BaseAgent`。
- [x] 字段包含 `name`。
- [x] 字段包含 `description`。
- [x] 字段包含 `prompt_path`。
- [x] 定义 `run(input) -> output` 接口。
- [x] 添加日志记录 hook。
- [x] 写 mock agent test。
- [ ] 提交 commit：`feat: add base agent interface`。



##### 7.2 Supervisor Agent

- [x] 创建 `agents/supervisor.py`。
- [x] 创建 `prompts/supervisor.md`。
- [x] 定义 `SupervisorPlan` schema。
- [x] Supervisor 负责拆任务。
- [x] Supervisor 负责决定调用哪些 Agent。
- [x] Supervisor 不直接生成研究结论。
- [x] 写 mock test。
- [ ] 提交 commit：`feat: add supervisor agent`。



##### 7.3 Research Agent

- [x] 创建 `agents/research.py`。
- [x] 创建 `prompts/research_agent.md`。
- [x] 定义 `ResearchAnalysis` schema。
- [x] 输出 market trends。
- [x] 输出 customer notes。
- [x] 输出 competitor assumptions。
- [x] 明确标注 unsupported claims。
- [x] 不做完整 proposal 写作。
- [x] 写 mock test。
- [ ] 提交 commit：`feat: add research agent`。



##### 7.4 Strategy Agent

- [x] 创建 `agents/strategy.py`。
- [x] 创建 `prompts/strategy_agent.md`。
- [x] 定义 `StrategyAnalysis` schema。
- [x] 输出 value proposition。
- [x] 输出 business model logic。
- [x] 输出 GTM strategy。
- [x] 输出 moat hypotheses。
- [x] 不编造 market data。
- [x] 写 mock test。
- [ ] 提交 commit：`feat: add strategy agent`。



##### 7.5 Finance Agent

- [x] 创建 `agents/finance.py`。
- [x] 创建 `prompts/finance_agent.md`。
- [x] 定义 `FinanceAssumptions` schema。
- [x] 输出 revenue assumptions。
- [x] 输出 cost assumptions。
- [x] 输出 unit economics assumptions。
- [x] 输出 break-even discussion。
- [x] 明确所有数字是 assumptions，不是预测。
- [x] 写 mock test。
- [x] 提交 commit：`feat: add finance agent`。



##### 7.6 Writer Agent

- [x] 创建 `agents/writer.py`。
- [x] 创建 `prompts/writer_agent.md`。
- [x] Writer 输入 research + strategy + finance。
- [x] Writer 输出 ProposalDraft。
- [x] Writer 不新增未经验证事实。
- [x] Writer 标注低置信度内容。
- [x] 写 mock test。
- [x] 提交 commit：`feat: add writer agent`。



##### 7.7 Critic Agent

- [x] 创建 `agents/critic.py`。
- [x] 创建 `prompts/critic_agent.md`。
- [x] Critic 输入 ProposalDraft。
- [x] Critic 输出 CritiqueReport。
- [x] Critic 检查 unsupported claims。
- [x] Critic 检查 financial inconsistency。
- [x] Critic 检查 weak GTM。
- [x] Critic 不直接重写 proposal。
- [x] 写 mock test。
- [x] 提交 commit：`feat: add critic agent`。



##### 7.8 Multi-Agent Workflow

- [x] 创建 `workflow/multi_agent_graph.py`（沿用现有目录命名）。
- [x] Graph 开始调用 Supervisor。
- [x] Graph 调用 Research Agent。
- [x] Graph 调用 Strategy Agent。
- [x] Graph 调用 Finance Agent。
- [x] Graph 调用 Writer Agent。
- [x] Graph 调用 Critic Agent。
- [x] Graph 调用 Revision Node。
- [x] 保存每个 Agent 输出。
- [x] Streamlit 增加运行模式选择：Baseline / Workflow / Multi-Agent。
- [ ] 提交 commit：`feat: add controlled multi-agent workflow`。



#### Definition of Done

- [ ] 系统不是只有 Agent 名字，而是有职责隔离。
- [ ] 每个 Agent 有输入输出 schema。
- [ ] 每个 Agent 输出可单独查看。
- [ ] Supervisor 控制流程。
- [ ] Agent 不自由无限对话。

---



## Phase 4 - 加入 RAG 和 Proposal Knowledge Base (Sprint 8)



### Sprint 8 - RAG and Knowledge Base



#### Goal

让 proposal 生成基于模板、案例、框架、用户上传资料，而不是只靠模型记忆。

#### Deliverables

- `knowledge_base/proposal_templates/`
- `knowledge_base/business_frameworks/`
- `knowledge_base/example_proposals/`
- `knowledge_base/industry_research/`
- `rag/loaders.py`
- `rag/index.py`
- `rag/retriever.py`
- `rag/citation_checker.py`



#### Tasks



##### 8.1 Knowledge Base Folders

- [x] 创建 `knowledge_base/proposal_templates/`。
- [x] 创建 `knowledge_base/business_frameworks/`。
- [x] 创建 `knowledge_base/example_proposals/`。
- [x] 创建 `knowledge_base/industry_research/`。
- [x] 每个文件夹添加 `.gitkeep`。
- [x] README 说明每个文件夹用途。
- [ ] 提交 commit：`chore: add knowledge base folders`。



##### 8.2 Seed Documents

- [x] 添加 1 个 investor proposal template Markdown。
- [x] 添加 1 个 consulting memo template Markdown。
- [x] 添加 1 个 grant proposal template Markdown。
- [x] 添加 SWOT framework Markdown。
- [x] 添加 Porter Five Forces framework Markdown。
- [x] 添加 TAM/SAM/SOM framework Markdown。
- [x] 添加 AARRR framework Markdown。
- [x] 添加 unit economics framework Markdown。
- [ ] 提交 commit：`docs: add seed knowledge base documents`。



##### 8.3 Document Loaders

- [x] 创建 `rag/loaders.py`。
- [x] 实现 Markdown loader。
- [x] 实现 TXT loader。
- [x] 预留 PDF loader。
- [x] 每个 loaded document 保存 source metadata。
- [x] 写测试加载 Markdown。
- [ ] 提交 commit：`feat: add document loaders`。



##### 8.4 Vector Index

- [x] 添加 Chroma 依赖。
- [x] 创建 `rag/index.py`。
- [x] 实现 `build_index()`。
- [x] 实现 `add_documents()`。
- [x] 实现 `persist_index()`。
- [x] 实现 `load_index()`。
- [x] 写测试：index 可创建。
- [ ] 提交 commit：`feat: add vector index`。



##### 8.5 Retriever

- [x] 创建 `rag/retriever.py`。
- [x] 实现 `rewrite_query(user_brief, section)`。
- [x] 实现 `retrieve(query, top_k)`。
- [x] 返回 EvidenceChunk。
- [x] EvidenceChunk 包含 source_id。
- [x] EvidenceChunk 包含 text。
- [x] EvidenceChunk 包含 score。
- [x] EvidenceChunk 包含 metadata。
- [x] 写测试：query 返回 chunk。
- [ ] 提交 commit：`feat: add RAG retriever`。



##### 8.6 Evidence Filter

- [x] 实现 `filter_evidence(chunks, min_score)`。
- [x] 过滤空内容。
- [x] 过滤低分结果。
- [x] 过滤重复 chunk。
- [x] 保留 source metadata。
- [x] 写测试。
- [ ] 提交 commit：`feat: add evidence filter`。



##### 8.7 Citation Checker

- [x] 创建 `rag/citation_checker.py`。
- [x] 实现 `extract_key_claims(proposal_section)`。
- [x] 实现 `check_claim_has_source(claim, source_ids)`。
- [x] 对 market size claim 强制要求 source。
- [x] 对 competitor claim 强制要求 source。
- [x] 对 trend claim 强制要求 source。
- [x] 输出 citation coverage score。
- [x] 写测试。
- [ ] 提交 commit：`feat: add citation checker`。



##### 8.8 RAG-enabled Writer

- [x] 修改 Writer Agent 输入，加入 evidence chunks。
- [x] 修改 Writer prompt，要求使用 evidence。
- [x] 修改 Writer prompt，要求标注 source_id。
- [x] 修改 workflow，在写章节前检索相关资料。
- [x] 在 Streamlit 显示 sources。
- [ ] 提交 commit：`feat: integrate RAG into proposal writing`。



#### Definition of Done

- [ ] 系统能从 knowledge_base 检索资料。
- [ ] Writer 可以基于 evidence 写章节。
- [ ] 关键事实带 source_id。
- [ ] Citation Checker 可以报告覆盖率。

---



## Phase 5 - 加入 Web Research，但必须受控 (Sprint 9)



### Sprint 9 - Controlled Web Research and Citation



#### Goal

Market Research Agent 和 Competitor Agent 可以查互联网，但必须受控、可追踪、可引用。

#### Deliverables

- `tools/web_search.py`
- `schemas/source.py`
- `sources` database table
- citation UI



#### Tasks



##### 9.1 Source Schema

- [x] 创建 `schemas/source.py`。
- [x] 定义 `SourceQuality` enum。
- [x] 定义 `WebSearchResult` schema。
- [x] 字段包含 title。
- [x] 字段包含 url。
- [x] 字段包含 publisher。
- [x] 字段包含 published_date。
- [x] 字段包含 summary。
- [x] 字段包含 relevance_score。
- [x] 字段包含 source_quality。
- [x] 写测试。
- [x] 提交 commit：`feat: add source schemas`。



##### 9.2 Web Search Tool Interface

- [x] 创建 `tools/web_search.py`。
- [x] 定义 `search_web(query, allowed_domains=None, recency=None, max_results=5)`。
- [x] 初期可实现 mock search，避免马上接真实 API。
- [x] 返回 list of WebSearchResult。
- [x] 记录 query。
- [x] 记录 timestamp。
- [x] 写 mock test。
- [x] 提交 commit：`feat: add controlled web search interface`。



##### 9.3 Real Search Provider

- [x] 选择 Tavily / SerpAPI / Bing Search API 中一个。
- [x] 在 `.env.example` 添加对应 API key。
- [x] 实现 provider client。
- [x] 处理 API error。
- [x] 处理 no results。
- [x] 处理 rate limit。
- [x] 写 integration note，不在 CI 中调用真实 API。
- [x] 提交 commit：`feat: add web search provider integration`。



##### 9.4 Source Quality Ranking

- [x] 实现 `classify_source_quality(url, publisher)`。
- [x] 官方域名标记 official。
- [x] 财报或 SEC 文件标记 financial_report。
- [x] 大学或研究机构标记 research_org / academic。
- [x] 主流媒体标记 news。
- [x] 其他标记 blog 或 unknown。
- [x] 写测试覆盖 5 类来源。
- [x] 提交 commit：`feat: add source quality classifier`。



##### 9.5 Recency Filter

- [x] 实现 published_date 解析。
- [x] 允许设置 recency，例如 last_12_months。
- [x] 过时来源不删除，但标记 stale。
- [x] 在 proposal 中要求注明过时资料。
- [x] 写测试。
- [x] 提交 commit：`feat: add source recency filter`。



##### 9.6 Integrate with Agents

- [ ] Market Research Agent 可以调用 search_web。
- [ ] Competitor Agent 可以调用 search_web。
- [ ] Strategy Agent 暂时不直接调用 web。
- [ ] Finance Agent 暂时不直接调用 web。
- [ ] 保存所有 web sources 到 DB。
- [ ] 在 Streamlit 显示 sources table。
- [ ] 提交 commit：`feat: integrate web research into research agents`。



##### 9.7 Citation Enforcement

- [ ] 对 market size 相关 claim 要求 citation。
- [ ] 对 competitor list 要求 citation。
- [ ] 对 trend claim 要求 citation。
- [ ] 如果无 citation，则 Critic 标记 high severity。
- [ ] 如果 source low quality，则 Critic 标记 medium severity。
- [ ] 提交 commit：`feat: enforce citations for key claims`。



#### Definition of Done

- [ ] web research 有受控入口。
- [ ] 每个来源有 metadata。
- [ ] 关键事实可以追溯到 source。
- [ ] 低质量或过时来源会被标记。

---



## Phase 6 - 加入 Human-in-the-loop (Sprint 10)



### Sprint 10 - Human-in-the-loop



#### Goal

在关键节点暂停，让用户批准、编辑或拒绝。

#### Deliverables

- approval workflow
- approval database table
- Streamlit approval UI
- audit logs



#### Tasks



##### 10.1 Approval Schema

- [ ] 定义 `ApprovalDecision` enum。
- [ ] 定义 `ApprovalRecord` schema。
- [ ] 字段包含 approval_id。
- [ ] 字段包含 run_id。
- [ ] 字段包含 step。
- [ ] 字段包含 decision。
- [ ] 字段包含 user_comment。
- [ ] 字段包含 before_value。
- [ ] 字段包含 after_value。
- [ ] 字段包含 approved_at。
- [ ] 写测试。
- [ ] 提交 commit：`feat: add approval schema`。



##### 10.2 Approval Storage

- [ ] 在 DB 添加 approvals table。
- [ ] 写 `save_approval()`。
- [ ] 写 `get_approvals_for_run()`。
- [ ] 写测试。
- [ ] 提交 commit：`feat: add approval storage`。



##### 10.3 Approval Points

- [ ] 在 proposal brief 后添加 approval point。
- [ ] 在 research plan 后添加 approval point。
- [ ] 在 core sources 后添加 approval point。
- [ ] 在 finance assumptions 后添加 approval point。
- [ ] 在 final proposal 前添加 approval point。
- [ ] 提交 commit：`feat: add workflow approval points`。



##### 10.4 Streamlit Approval UI

- [ ] 显示当前等待审批的 step。
- [ ] 显示待审批内容。
- [ ] 添加 Approve 按钮。
- [ ] 添加 Reject 按钮。
- [ ] 添加 Edit text area。
- [ ] 添加 Submit Edit 按钮。
- [ ] 保存审批记录。
- [ ] 审批后继续 workflow。
- [ ] 提交 commit：`feat: add human approval UI`。



##### 10.5 Audit Log UI

- [ ] 在 run detail 页面显示 approvals。
- [ ] 显示审批时间。
- [ ] 显示审批决定。
- [ ] 显示用户评论。
- [ ] 显示编辑前后差异的简化 preview。
- [ ] 提交 commit：`feat: add approval audit log view`。



#### Definition of Done

- [ ] workflow 可以暂停。
- [ ] 用户可以 approve / reject / edit。
- [ ] 审批后 workflow 可以恢复。
- [ ] 每次审批都有审计记录。

---



## Phase 7 - 加入评估系统，这是“博士生水平”的关键 (Sprints 11-12)



### Sprint 11 - Evaluation Benchmark



#### Goal

建立博士生水平的核心差异：可评估、可复现的 proposal generation benchmark。

#### Deliverables

- `evals/cases/*.yaml`
- `evals/rubric.yaml`
- `src/open_proposal_agent/evals/runner.py`
- eval report



#### Tasks



##### 11.1 Eval Case Format

- [ ] 定义 eval case YAML 格式。
- [ ] 字段包含 case_id。
- [ ] 字段包含 user_brief。
- [ ] 字段包含 expected_strengths。
- [ ] 字段包含 known_risks。
- [ ] 字段包含 evaluation_notes。
- [ ] 写 sample YAML。
- [ ] 提交 commit：`feat: define evaluation case format`。



##### 11.2 Create 10 Test Cases

- [ ] 创建 `saas_crm_case.yaml`。
- [ ] 创建 `amazon_seller_tool_case.yaml`。
- [ ] 创建 `ai_education_app_case.yaml`。
- [ ] 创建 `healthcare_booking_case.yaml`。
- [ ] 创建 `food_delivery_case.yaml`。
- [ ] 创建 `fintech_budgeting_case.yaml`。
- [ ] 创建 `climate_reporting_case.yaml`。
- [ ] 创建 `creator_tool_case.yaml`。
- [ ] 创建 `legal_ops_case.yaml`。
- [ ] 创建 `restaurant_inventory_case.yaml`。
- [ ] 提交 commit：`test: add initial evaluation cases`。



##### 11.3 Rubric YAML

- [ ] 创建 `evals/rubric.yaml`。
- [ ] 添加 Problem clarity 维度。
- [ ] 添加 Customer specificity 维度。
- [ ] 添加 Market reasoning 维度。
- [ ] 添加 Competitive insight 维度。
- [ ] 添加 Business model quality 维度。
- [ ] 添加 Financial assumption quality 维度。
- [ ] 添加 Risk analysis 维度。
- [ ] 添加 Evidence quality 维度。
- [ ] 添加 Writing quality 维度。
- [ ] 添加 Actionability 维度。
- [ ] 每个维度写 1-5 分标准。
- [ ] 提交 commit：`feat: add evaluation rubric yaml`。



##### 11.4 Evaluation Runner

- [ ] 创建 `evals/runner.py`。
- [ ] 加载 cases。
- [ ] 对每个 case 调用 selected workflow。
- [ ] 保存 generated proposal。
- [ ] 调用 rubric scorer。
- [ ] 输出 score JSON。
- [ ] 输出 Markdown report。
- [ ] 写 dry-run 模式。
- [ ] 提交 commit：`feat: add evaluation runner`。



##### 11.5 Baseline vs Multi-Agent Comparison

- [ ] 跑 single-agent baseline。
- [ ] 保存 baseline scores。
- [ ] 跑 workflow-only。
- [ ] 保存 workflow-only scores。
- [ ] 跑 multi-agent。
- [ ] 保存 multi-agent scores。
- [ ] 生成对比表。
- [ ] 不编造结果；没有数据就写 TBD。
- [ ] 提交 commit：`eval: add baseline comparison report`。



##### 11.6 CI Evaluation Skeleton

- [ ] 创建 `.github/workflows/test.yml`。
- [ ] 配置安装依赖。
- [ ] 配置运行 pytest。
- [ ] 创建 `.github/workflows/eval.yml`。
- [ ] eval workflow 默认手动触发。
- [ ] 不在 CI 中强制调用付费 LLM。
- [ ] 提交 commit：`ci: add test and eval workflows`。



#### Definition of Done

- [ ] 至少 10 个 eval cases。
- [ ] 有评分 rubric。
- [ ] 可以对比 baseline 和 multi-agent。
- [ ] README 可以展示真实或 TBD benchmark 表。

---



### Sprint 12 - Testing and Prompt Regression



#### Goal

建立基础自动测试和 prompt 回归测试，避免后续改动破坏质量。

#### Deliverables

- pytest tests
- promptfoo config optional
- regression report



#### Tasks



##### 12.1 Unit Test Coverage

- [ ] 测试 UserBrief validation。
- [ ] 测试 ProposalDraft validation。
- [ ] 测试 CritiqueReport validation。
- [ ] 测试 Markdown exporter。
- [ ] 测试 SQLite repositories。
- [ ] 测试 RAG loaders。
- [ ] 测试 citation checker。
- [ ] 测试 source classifier。
- [ ] 提交 commit：`test: expand unit test coverage`。



##### 12.2 Workflow Tests

- [ ] 用 mock LLM 测试 baseline。
- [ ] 用 mock LLM 测试 deterministic workflow。
- [ ] 用 mock agents 测试 multi-agent workflow。
- [ ] 测试 missing info branch。
- [ ] 测试 critique revision branch。
- [ ] 测试 approval pause branch。
- [ ] 提交 commit：`test: add workflow tests`。



##### 12.3 Prompt Versioning

- [ ] 为每个 prompt 顶部添加 version。
- [ ] 为每个 prompt 添加 changelog。
- [ ] 在 run record 中保存 prompt version。
- [ ] 在 README 说明 prompt 更新规则。
- [ ] 提交 commit：`chore: add prompt versioning`。



##### 12.4 Promptfoo Optional Setup

- [ ] 添加 promptfoo 配置文件。
- [ ] 选择 3 个关键 prompt 做 smoke eval。
- [ ] 添加 planner prompt eval。
- [ ] 添加 critic prompt eval。
- [ ] 添加 writer prompt eval。
- [ ] 记录如何本地运行 promptfoo。
- [ ] 提交 commit：`eval: add prompt regression skeleton`。



#### Definition of Done

- [ ] 关键 schema 和 workflow 有测试。
- [ ] prompt 有版本记录。
- [ ] 可以发现明显回归。

---



## Phase 8 - 加入 MCP，但不要太早 (Sprint 13)



### Sprint 13 - MCP Adapter and Security Model



#### Goal

不要太早做 MCP。完成核心系统后，再加入标准化工具连接和安全边界。

#### Deliverables

- `tools/mcp_adapter.py`
- `docs/security.md`
- File MCP server prototype
- Search MCP adapter prototype



#### Tasks



##### 13.1 Security Documentation

- [ ] 创建 `docs/security.md`。
- [ ] 写 tool allowlist 原则。
- [ ] 写 file access boundary。
- [ ] 写 prompt injection 风险。
- [ ] 写 SSRF 风险。
- [ ] 写 token management。
- [ ] 写 human approval policy。
- [ ] 写 audit log policy。
- [ ] 提交 commit：`docs: add security model`。



##### 13.2 Tool Permission Model

- [ ] 定义 `ToolPermission` schema。
- [ ] 定义 tool name。
- [ ] 定义 allowed agents。
- [ ] 定义 requires_approval。
- [ ] 定义 allowed_paths。
- [ ] 定义 allowed_domains。
- [ ] 写测试。
- [ ] 提交 commit：`feat: add tool permission model`。



##### 13.3 MCP Adapter Skeleton

- [ ] 创建 `tools/mcp_adapter.py`。
- [ ] 定义 `MCPToolAdapter` 类。
- [ ] 实现 `list_tools()` 占位。
- [ ] 实现 `call_tool()` 占位。
- [ ] 在 call 前检查 permission。
- [ ] 记录 tool call log。
- [ ] 写 mock test。
- [ ] 提交 commit：`feat: add MCP adapter skeleton`。



##### 13.4 File MCP Prototype

- [ ] 设计 File MCP server 只读项目目录。
- [ ] 禁止读取 `.env`。
- [ ] 禁止读取 home directory。
- [ ] 只允许 `knowledge_base/` 和 `uploads/`。
- [ ] 添加 path normalization。
- [ ] 写安全测试：拒绝 `../.env`。
- [ ] 提交 commit：`feat: prototype secure file MCP access`。



##### 13.5 Search MCP Prototype

- [ ] 将现有 `search_web` 包装为 MCP-style tool。
- [ ] 保留 allowed domains。
- [ ] 保留 recency filter。
- [ ] 保留 source quality ranking。
- [ ] 保留 audit log。
- [ ] 提交 commit：`feat: prototype search MCP adapter`。



#### Definition of Done

- [ ] MCP client/server 概念分离。
- [ ] 工具权限最小化。
- [ ] README 或 docs 有 security model。
- [ ] 高风险工具调用需要 approval。

---



## Phase 9 - 做成真正开源产品 (Sprints 14-15)



### Sprint 14 - Docker and Deployment



#### Goal

让别人 clone 后能一键运行。

#### Deliverables

- `Dockerfile`
- `docker-compose.yml`
- deployment docs



#### Tasks



##### 14.1 Dockerfile

- [ ] 创建 `Dockerfile`。
- [ ] 使用 Python 3.11 base image。
- [ ] 设置 workdir。
- [ ] 复制 pyproject。
- [ ] 安装依赖。
- [ ] 复制项目文件。
- [ ] 暴露 Streamlit 端口。
- [ ] 设置默认启动命令。
- [ ] 本地 build image。
- [ ] 提交 commit：`build: add Dockerfile`。



##### 14.2 Docker Compose

- [ ] 创建 `docker-compose.yml`。
- [ ] 添加 app service。
- [ ] 挂载 outputs volume。
- [ ] 挂载 knowledge_base volume。
- [ ] 读取 `.env`。
- [ ] 本地运行 `docker compose up`。
- [ ] README 添加 Docker 运行方式。
- [ ] 提交 commit：`build: add docker compose setup`。



##### 14.3 Deployment Notes

- [ ] 创建 `docs/deployment.md`。
- [ ] 写本地运行。
- [ ] 写 Docker 运行。
- [ ] 写 Render 部署注意事项。
- [ ] 写 Railway 部署注意事项。
- [ ] 写 Cloud Run 部署注意事项。
- [ ] 写环境变量配置。
- [ ] 提交 commit：`docs: add deployment guide`。



#### Definition of Done

- [ ] `docker compose up` 可以启动 app。
- [ ] README 有清晰运行说明。
- [ ] 环境变量不进入镜像。

---



### Sprint 15 - Open Source Release v0.1.0



#### Goal

把项目从 demo 打磨成别人能理解、能运行、能贡献的开源项目。

#### Deliverables

- professional README
- Apache 2.0 license
- docs complete
- examples complete
- GitHub release v0.1.0



#### Tasks



##### 15.1 License

- [ ] 选择 Apache 2.0 license。
- [ ] 添加 `LICENSE` 文件。
- [ ] README 标注 license。
- [ ] 提交 commit：`docs: add Apache 2.0 license`。



##### 15.2 README Finalization

- [ ] README 添加 Demo GIF 或 screenshot 占位。
- [ ] README 添加 Quickstart。
- [ ] README 添加 Architecture diagram。
- [ ] README 添加 Agent roles。
- [ ] README 添加 Workflow graph。
- [ ] README 添加 Evaluation benchmark。
- [ ] README 添加 Security model。
- [ ] README 添加 Roadmap。
- [ ] README 添加 Contribution guide。
- [ ] README 添加 Citation / Acknowledgements。
- [ ] 提交 commit：`docs: finalize README for v0.1.0`。



##### 15.3 Examples

- [ ] 添加 `examples/sample_input.json`。
- [ ] 添加 `examples/sample_output_baseline.md`。
- [ ] 添加 `examples/sample_output_workflow.md`。
- [ ] 添加 `examples/sample_output_multi_agent.md`，如果已完成。
- [ ] 添加 sample sources，避免包含版权敏感内容。
- [ ] 提交 commit：`docs: add runnable examples`。



##### 15.4 Documentation Review

- [ ] 检查 `docs/PRD.md`。
- [ ] 检查 `docs/USER_STORIES.md`。
- [ ] 检查 `docs/PROPOSAL_OUTPUT_SCHEMA.md`。
- [ ] 检查 `docs/EVALUATION_RUBRIC.md`。
- [ ] 检查 `docs/architecture_design.md`。
- [ ] 检查 `docs/security.md`。
- [ ] 检查 `docs/deployment.md`。
- [ ] 修复过时内容。
- [ ] 提交 commit：`docs: polish documentation`。



##### 15.5 Release Preparation

- [ ] 确认 pytest 通过。
- [ ] 确认 Streamlit 本地可运行。
- [ ] 确认 Docker 可运行。
- [ ] 确认 sample input 可生成 output。
- [ ] 确认没有 API key 泄露。
- [ ] 确认 `.env` 未提交。
- [ ] 创建 Git tag `v0.1.0`。
- [ ] 创建 GitHub Release。
- [ ] 写 release notes。
- [ ] 提交 commit：`release: v0.1.0`。



#### Definition of Done

- [ ] 新用户可以 clone 并运行。
- [ ] README 足够专业。
- [ ] 文档解释架构和安全边界。
- [ ] 有 benchmark 或 benchmark placeholder。
- [ ] GitHub Release 发布。

---



## 16-week Suggested Timeline


| 周数         | Sprint       | 主要产出                                      |
| ---------- | ------------ | ----------------------------------------- |
| Week 1     | Sprint 0-1   | 文档、仓库、Python 项目骨架                         |
| Week 2     | Sprint 2-4   | Schema、Single-Agent、Streamlit MVP         |
| Week 3-4   | Sprint 5-6   | LangGraph workflow、日志、SQLite              |
| Week 5-6   | Sprint 7     | Multi-Agent：Supervisor + Workers + Critic |
| Week 7-8   | Sprint 8     | RAG、knowledge base、citation checker       |
| Week 9-10  | Sprint 9     | Web research、source quality、citations     |
| Week 11-12 | Sprint 10-12 | Human approval、eval benchmark、tests       |
| Week 13-14 | Sprint 13    | MCP adapter、安全模型                          |
| Week 15-16 | Sprint 14-15 | Docker、CI、README、开源发布                     |


---



## Minimum MVP Checklist

只要下面这些完成，就可以认为 MVP 成立：

- [ ] 用户可以打开 Streamlit。
- [ ] 用户可以输入产品名称、行业、目标客户、痛点、解决方案、商业模式、地区、proposal 目标。
- [ ] 系统可以调用 LLM。
- [ ] 系统生成固定结构 proposal。
- [ ] proposal 包含 13 个章节。
- [ ] proposal 保存为 Markdown。
- [ ] 用户可以下载 Markdown。
- [ ] README 说明如何运行。
- [ ] `.env.example` 说明需要哪些 API key。
- [ ] 项目没有提交密钥。

---



## Research-grade Checklist

项目要达到博士生研究/工程作品水平，至少完成：

- [ ] 有 single-agent baseline。
- [ ] 有 deterministic workflow。
- [ ] 有真正职责隔离的 multi-agent。
- [ ] 有 Generate → Critique → Revise。
- [ ] 有 RAG knowledge base。
- [ ] 有 controlled web research。
- [ ] 有 citation checker。
- [ ] 有 human-in-the-loop。
- [ ] 有 10-30 个 benchmark cases。
- [ ] 有 component-level evaluation。
- [ ] 有 end-to-end evaluation。
- [ ] 有 regression evaluation。
- [ ] 有 ablation study。
- [ ] 有 logs/traces。
- [ ] 有 security model。
- [ ] 有 Docker。
- [ ] 有 GitHub Actions。
- [ ] 有 professional README。
- [ ] 有可复现 demo。

---



## Cursor Prompt Templates



### Prompt 1 - Implement One Task Only

```text
You are helping me build Open Proposal Agent. Please implement only the following task:

TASK: <paste one checkbox here>

Constraints:
- Do not implement future sprint features.
- Keep the code beginner-friendly.
- Add comments where helpful.
- Add or update tests if the task changes code.
- Update README only if needed for this task.
- After coding, summarize changed files and how to test.
```



### Prompt 2 - Debug a Failing Test

```text
The following test is failing in Open Proposal Agent:

<error output>

Please:
1. Explain the root cause in simple language.
2. Fix the smallest possible code area.
3. Do not rewrite unrelated modules.
4. Show how to rerun the test.
```



### Prompt 3 - Add a New Agent

```text
Add a new Agent to Open Proposal Agent.

Agent name: <name>
Responsibility: <responsibility>
Forbidden actions: <what it must not do>
Input schema: <schema name>
Output schema: <schema name>

Requirements:
- Create the agent file.
- Create the prompt file.
- Add schema if missing.
- Add a mock unit test.
- Do not connect it to the main workflow until I ask.
```



### Prompt 4 - Review Architecture Before Coding

```text
Before implementing the next task, review architecture_design.md and sprint_plan.md.
Tell me:
1. Which files will change.
2. Which existing schemas or functions will be reused.
3. What tests should be added.
4. What risks or simplifications you recommend.
Do not write code yet.
```

---



## Commit Message Convention

Use short, clear commits:

```text
chore: initialize repository structure
docs: add PRD
feat: add user brief schema
feat: implement single agent baseline
feat: add streamlit input form
feat: add proposal workflow graph
feat: add research agent
test: add workflow tests
eval: add benchmark cases
build: add docker compose setup
release: v0.1.0
```

---



## Stop Conditions

暂停开发并人工检查的情况：

- [ ] LLM 输出开始编造具体市场规模但无来源。
- [ ] Agent 输出不符合 Pydantic schema。
- [ ] Writer Agent 新增了 Research Agent 没有提供的事实。
- [ ] Critic Agent 只泛泛而谈，没有具体 issue。
- [ ] RAG 检索结果和章节无关。
- [ ] Web search 来源低质量或过时。
- [ ] 财务假设出现单位错误或计算矛盾。
- [ ] 代码开始一次性改动太多文件。
- [ ] Cursor 试图提前实现 MCP 或复杂前端。
- [ ] `.env` 或 API key 有泄露风险。
