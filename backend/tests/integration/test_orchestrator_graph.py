"""
Integration tests for the orchestrator LangGraph graph.

Tests graph compilation, routing logic, and node behaviour with mocked
external services. No real OpenAI or Supabase calls are made.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.context import CONTEXT_MESSAGE_NAME, build_context_block
from app.agents.orchestrator import (
    build_orchestrator_graph,
    reflect_node,
    should_continue,
)
from app.agents.state import KnowledgeEntry, OrchestratorState, TodoItem


def _make_state(**overrides) -> OrchestratorState:
    defaults = dict(
        messages=[HumanMessage(content="test")],
        user_id="user-123",
        conversation_id="conv-456",
        knowledge={},
        todos=[],
        current_focus=None,
        executed_actions=[],
        stream_events=[],
    )
    defaults.update(overrides)
    return OrchestratorState(**defaults)


def _make_entry(content: str | None, summary: str = "resumo") -> KnowledgeEntry:
    lines = len(content.splitlines()) if content else 0
    return KnowledgeEntry(
        summary=summary,
        content=content,
        lines_loaded=lines,
        total_lines=max(lines, 1),
        source="supabase",
    )


class TestGraphCompilation:
    def test_graph_compiles_without_error(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        from app.config import get_settings
        get_settings.cache_clear()
        settings = get_settings()
        graph = build_orchestrator_graph(settings)
        assert graph is not None

    def test_compiled_graph_has_invoke_method(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        from app.config import get_settings
        get_settings.cache_clear()
        settings = get_settings()
        graph = build_orchestrator_graph(settings)
        assert hasattr(graph, "ainvoke")
        assert hasattr(graph, "astream")


class TestShouldContinueRouting:
    def test_routes_to_post_process_when_no_tool_calls(self):
        state = _make_state(
            messages=[
                HumanMessage(content="olá"),
                AIMessage(content="Olá! Como posso ajudar?"),
            ]
        )
        result = should_continue(state)
        assert result == "post_process"

    def test_routes_to_tools_when_tool_calls_present(self):
        ai_msg = AIMessage(content="")
        ai_msg.tool_calls = [{"name": "read_context", "args": {"key": "user/profile"}, "id": "tc1"}]
        state = _make_state(messages=[HumanMessage(content="test"), ai_msg])
        result = should_continue(state)
        assert result == "tools"

    def test_routes_to_post_process_with_empty_tool_calls(self):
        ai_msg = AIMessage(content="resposta final")
        ai_msg.tool_calls = []
        state = _make_state(messages=[HumanMessage(content="test"), ai_msg])
        result = should_continue(state)
        assert result == "post_process"

    def test_routes_to_post_process_with_no_messages(self):
        state = _make_state(messages=[])
        result = should_continue(state)
        assert result == "post_process"


class TestReflectNode:
    def test_reflect_adds_context_message(self):
        state = _make_state(
            knowledge={"user/profile": _make_entry("Nome: João", "Perfil")},
            messages=[HumanMessage(content="olá")],
        )
        result = reflect_node(state)
        new_messages = result["messages"]
        context_msgs = [
            m for m in new_messages
            if isinstance(m, SystemMessage) and getattr(m, "name", None) == CONTEXT_MESSAGE_NAME
        ]
        assert len(context_msgs) == 1

    def test_reflect_replaces_previous_context_message(self):
        old_context = SystemMessage(content="old context", name=CONTEXT_MESSAGE_NAME)
        state = _make_state(
            messages=[HumanMessage(content="test"), old_context],
            knowledge={"user/profile": _make_entry("updated data")},
        )
        result = reflect_node(state)
        context_msgs = [
            m for m in result["messages"]
            if isinstance(m, SystemMessage) and getattr(m, "name", None) == CONTEXT_MESSAGE_NAME
        ]
        # Only one context message after reflect
        assert len(context_msgs) == 1
        assert "old context" not in context_msgs[0].content

    def test_reflect_preserves_non_context_messages(self):
        state = _make_state(
            messages=[
                HumanMessage(content="user message"),
                AIMessage(content="agent reply"),
            ]
        )
        result = reflect_node(state)
        non_context = [
            m for m in result["messages"]
            if not (isinstance(m, SystemMessage) and getattr(m, "name", None) == CONTEXT_MESSAGE_NAME)
        ]
        assert any(m.content == "user message" for m in non_context)
        assert any(m.content == "agent reply" for m in non_context)

    def test_reflect_context_contains_knowledge_index(self):
        state = _make_state(
            knowledge={
                "user/profile": _make_entry("Nome: Ana", "Perfil de Ana"),
                "user/fiscal": _make_entry(None, "IRS | 1ª habitação"),
            }
        )
        result = reflect_node(state)
        context_msg = next(
            m for m in result["messages"]
            if isinstance(m, SystemMessage) and getattr(m, "name", None) == CONTEXT_MESSAGE_NAME
        )
        assert "user/profile" in context_msg.content
        assert "user/fiscal" in context_msg.content

    def test_reflect_context_contains_todos(self):
        state = _make_state(
            todos=[TodoItem(id="t1", task="Analisar Alfama", status="pending")]
        )
        result = reflect_node(state)
        context_msg = next(
            m for m in result["messages"]
            if isinstance(m, SystemMessage) and getattr(m, "name", None) == CONTEXT_MESSAGE_NAME
        )
        assert "Analisar Alfama" in context_msg.content


class TestBuildContextBlock:
    def test_empty_state_produces_valid_block(self):
        state = _make_state()
        block = build_context_block(state)
        assert "Base de Conhecimento" in block
        assert "Tarefas" in block
        assert "Foco Atual" in block

    def test_block_shows_loaded_vs_available(self):
        state = _make_state(
            knowledge={
                "user/profile": _make_entry("data"),        # loaded
                "user/fiscal": _make_entry(None),           # available
            }
        )
        block = build_context_block(state)
        assert "[carregado]" in block
        assert "[disponível]" in block

    def test_block_shows_active_focus(self):
        state = _make_state(
            current_focus={"property_id": "abc-123", "topic": "cozinha", "drill_down_level": 1}
        )
        block = build_context_block(state)
        assert "abc-123" in block
        assert "cozinha" in block
