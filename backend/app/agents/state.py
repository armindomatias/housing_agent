"""
Orchestrator agent state definitions.

OrchestratorState is the single shared state dict that flows through the
LangGraph pipeline. It carries the conversation messages, knowledge base,
task list, and execution metadata.
"""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


class KnowledgeEntry(TypedDict):
    """A single entry in the knowledge base virtual file system."""

    summary: str           # Always shown in the system message index
    content: str | None    # None = not loaded, str = full/partial content
    lines_loaded: int      # How many lines are currently loaded
    total_lines: int       # Total lines available (estimated from summary)
    source: str            # "supabase" | "tool" | "pipeline"


class TodoItem(TypedDict):
    """A single task in the agent's todo list."""

    id: str
    task: str
    status: str            # "pending" | "in_progress" | "completed"


class OrchestratorState(TypedDict):
    """
    Full state for the orchestrator LangGraph pipeline.

    Flows through: hydrate_context → agent ↔ [tools → reflect] → post_process
    """

    # Conversation messages (accumulated via add_messages reducer)
    messages: Annotated[list[BaseMessage], add_messages]

    # Identity
    user_id: str
    conversation_id: str

    # Knowledge base (unified virtual file system)
    # Keys use path-style naming: "user/profile", "portfolio/index",
    # "portfolio/{property_id}/resumo", "session/resumo_anterior"
    knowledge: dict[str, KnowledgeEntry]

    # Task list for multi-step requests
    todos: list[TodoItem]

    # Current user focus (property being discussed)
    # Format: {"property_id": str, "topic": str, "drill_down_level": int}
    current_focus: dict | None

    # Actions executed in this turn (persisted to action_log in post_process)
    executed_actions: list[dict]

    # SSE events to stream to the frontend
    stream_events: list[dict]
