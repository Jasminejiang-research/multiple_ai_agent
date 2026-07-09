"""Agent interfaces for the controlled multi-agent proposal workflow."""

from agents.base import AgentLogEvent, AgentLogHook, BaseAgent
from agents.research import ResearchAgent, ResearchLLM
from agents.supervisor import SupervisorAgent, SupervisorLLM

__all__ = [
    "AgentLogEvent",
    "AgentLogHook",
    "BaseAgent",
    "ResearchAgent",
    "ResearchLLM",
    "SupervisorAgent",
    "SupervisorLLM",
]
