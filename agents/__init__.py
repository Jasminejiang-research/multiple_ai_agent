"""Agent interfaces for the controlled multi-agent proposal workflow."""

from agents.base import AgentLogEvent, AgentLogHook, BaseAgent
from agents.finance import FinanceAgent, FinanceLLM
from agents.research import ResearchAgent, ResearchLLM
from agents.strategy import StrategyAgent, StrategyLLM
from agents.supervisor import SupervisorAgent, SupervisorLLM
from agents.writer import WriterAgent, WriterLLM

__all__ = [
    "AgentLogEvent",
    "AgentLogHook",
    "BaseAgent",
    "FinanceAgent",
    "FinanceLLM",
    "ResearchAgent",
    "ResearchLLM",
    "StrategyAgent",
    "StrategyLLM",
    "SupervisorAgent",
    "SupervisorLLM",
    "WriterAgent",
    "WriterLLM",
]
