"""
Orchestrator LangGraph pipeline.

Graph topology:
    START → hydrate_context → agent ⟷ [tools → reflect] → post_process → END

Nodes:
    hydrate_context — load user context + knowledge base from Supabase once per turn
    agent           — LLM ReAct loop (reason → tool call or respond)
    tools           — ToolNode executing tool calls (tools return Command updates)
    reflect         — rebuild context system message after each tool call (no LLM)
    post_process    — persist messages, log actions, demote stale knowledge

Routing:
    agent → tools (if tool_calls present)
    agent → post_process (if final response)
    tools → reflect
    reflect → agent
"""

import structlog
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.agents.context import (
    CONTEXT_MESSAGE_NAME,
    build_context_block,
    demote_stale_entries,
)
from app.agents.prompts import build_system_prompt
from app.agents.state import OrchestratorState
from app.agents.tools import ORCHESTRATOR_TOOLS
from app.config import Settings
from app.services import supabase_client as db
from app.services.knowledge_store import build_knowledge_base

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Node: hydrate_context
# ---------------------------------------------------------------------------


async def hydrate_context_node(state: OrchestratorState, config: RunnableConfig) -> dict:
    """
    Runs once at turn start. Loads user context from Supabase and builds
    the initial knowledge base. Creates a new conversation row if needed.
    Injects the system prompt + initial context block into messages.
    """
    supabase = (config.get("configurable") or {}).get("supabase")
    user_id = state["user_id"]
    conversation_id = state.get("conversation_id") or ""

    knowledge = state.get("knowledge") or {}

    # Only hydrate on the first turn (empty knowledge) or explicit refresh
    if not knowledge and supabase:
        try:
            knowledge = await build_knowledge_base(supabase, user_id)
        except Exception:
            logger.exception("hydrate_context_knowledge_build_failed", user_id=user_id)

        # Auto-create a minimal profile for first-time users (no profile → empty knowledge)
        if not knowledge:
            try:
                await db.upsert_user_profile(supabase, user_id, {})
            except Exception:
                logger.exception("hydrate_context_auto_create_profile_failed", user_id=user_id)

    # Create conversation row if this is a new session
    if not conversation_id and supabase:
        try:
            conv = await db.create_conversation(supabase, user_id)
            conversation_id = conv["id"]
        except Exception:
            logger.exception("hydrate_context_create_conversation_failed", user_id=user_id)
            # Leave conversation_id empty — downstream saves will be skipped
            # (do NOT fall back to a fake UUID; that causes FK violations)

    # Build the initial context block
    working_state: OrchestratorState = {
        **state,  # type: ignore[misc]
        "knowledge": knowledge,
        "conversation_id": conversation_id,
    }
    context_content = build_context_block(working_state)

    # Inject system prompt once (only if messages are empty / first turn)
    messages = list(state.get("messages") or [])
    has_system = any(
        isinstance(m, SystemMessage) and getattr(m, "name", None) != CONTEXT_MESSAGE_NAME
        for m in messages
    )
    new_messages = []
    if not has_system:
        new_messages.append(SystemMessage(content=build_system_prompt()))

    # Always inject/replace the context block
    # Filter out previous context block (replace pattern)
    messages = [
        m for m in messages
        if not (isinstance(m, SystemMessage) and getattr(m, "name", None) == CONTEXT_MESSAGE_NAME)
    ]
    new_messages.append(SystemMessage(content=context_content, name=CONTEXT_MESSAGE_NAME))

    return {
        "knowledge": knowledge,
        "conversation_id": conversation_id,
        "todos": state.get("todos") or [],
        "current_focus": state.get("current_focus"),
        "executed_actions": state.get("executed_actions") or [],
        "stream_events": [{"type": "thinking", "message": "A processar..."}],
        "messages": messages + new_messages,
    }


# ---------------------------------------------------------------------------
# Node: agent
# ---------------------------------------------------------------------------


async def agent_node(state: OrchestratorState, config: RunnableConfig) -> dict:
    """
    LLM ReAct node. Bound with all orchestrator tools.
    The LLM decides to call tools or produce a final response.
    """
    cfg = config.get("configurable") or {}
    model_name = cfg.get("orchestrator_model", "gpt-4o")
    openai_api_key = cfg.get("openai_api_key", "")

    llm = ChatOpenAI(
        model=model_name,
        api_key=openai_api_key,
        streaming=True,
        temperature=0,
    )
    llm_with_tools = llm.bind_tools(ORCHESTRATOR_TOOLS)

    messages = state["messages"]
    response = await llm_with_tools.ainvoke(messages)

    # Collect stream events for the response
    events = list(state.get("stream_events") or [])
    if isinstance(response, AIMessage) and response.content:
        events.append({"type": "message", "content": response.content, "done": True})

    return {"messages": [response], "stream_events": events}


# ---------------------------------------------------------------------------
# Node: reflect
# ---------------------------------------------------------------------------


def reflect_node(state: OrchestratorState) -> dict:
    """
    Rebuilds the context system message after each tool execution.
    Pure state → message transformation — zero LLM calls.
    Replaces the previous context block (same name="context_refresh").
    """
    context_content = build_context_block(state)
    new_context = SystemMessage(content=context_content, name=CONTEXT_MESSAGE_NAME)

    # Replace previous context block in messages
    messages = [
        m for m in (state.get("messages") or [])
        if not (isinstance(m, SystemMessage) and getattr(m, "name", None) == CONTEXT_MESSAGE_NAME)
    ]
    messages.append(new_context)

    return {"messages": messages}


# ---------------------------------------------------------------------------
# Node: post_process
# ---------------------------------------------------------------------------


async def post_process_node(state: OrchestratorState, config: RunnableConfig) -> dict:
    """
    Runs after the agent produces its final response.
    - Persists new messages to Supabase
    - Logs executed actions to action_log
    - Demotes stale knowledge entries
    - Updates portfolio is_active if focus changed
    - Triggers async conversation summary if message threshold reached
    """
    supabase = (config.get("configurable") or {}).get("supabase")
    conversation_id = state.get("conversation_id") or ""

    if supabase and conversation_id:
        # Persist new user + assistant messages (skip system messages)
        messages = state.get("messages") or []
        for msg in messages[-3:]:  # save last few new messages
            role = None
            if hasattr(msg, "type"):
                role = {"human": "user", "ai": "assistant", "tool": "tool"}.get(msg.type)
            if role and hasattr(msg, "content") and msg.content:
                try:
                    await db.save_message(
                        supabase, conversation_id, role, str(msg.content)
                    )
                except Exception:
                    logger.exception("post_process_save_message_failed")

        # Increment message count (fire-and-forget)
        try:
            await db.increment_conversation_message_count(supabase, conversation_id)
        except Exception:
            logger.warning("post_process_increment_message_count_failed", conversation_id=conversation_id)

    # Demote knowledge entries not referenced recently
    # We approximate "referenced" by checking which keys appeared in tool call args
    referenced_keys: set[str] = set()
    for msg in (state.get("messages") or []):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                args = tc.get("args", {}) if isinstance(tc, dict) else {}
                key = args.get("key")
                if key:
                    referenced_keys.add(key)

    updated_knowledge = demote_stale_entries(state["knowledge"], referenced_keys)

    return {
        "knowledge": updated_knowledge,
        "executed_actions": [],  # reset for next turn
        "stream_events": state.get("stream_events") or [],
    }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def should_continue(state: OrchestratorState) -> str:
    """Route from agent: go to tools if tool_calls, else post_process."""
    last_message = state["messages"][-1] if state.get("messages") else None
    if last_message is None:
        return "post_process"
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "post_process"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_orchestrator_graph(settings: Settings) -> StateGraph:
    """
    Build and compile the orchestrator LangGraph.

    The graph is compiled once at startup and stored on app.state.
    Per-request context (user_id, conversation_id, supabase client) is
    passed via the `configurable` dict when invoking the graph.

    Args:
        settings: Application settings (used for default model name).

    Returns:
        Compiled LangGraph ready for async streaming invocation.
    """
    graph = StateGraph(OrchestratorState)

    graph.add_node("hydrate_context", hydrate_context_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(ORCHESTRATOR_TOOLS))
    graph.add_node("reflect", reflect_node)
    graph.add_node("post_process", post_process_node)

    graph.set_entry_point("hydrate_context")
    graph.add_edge("hydrate_context", "agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "post_process": "post_process"},
    )
    graph.add_edge("tools", "reflect")
    graph.add_edge("reflect", "agent")
    graph.add_edge("post_process", END)

    return graph.compile()
