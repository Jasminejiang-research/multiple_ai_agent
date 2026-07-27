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
