"""
Unit tests for OrchestratorState, KnowledgeEntry, and TodoItem TypedDicts.
"""
from app.agents.state import KnowledgeEntry, OrchestratorState, TodoItem


class TestKnowledgeEntry:
    def test_create_loaded_entry(self):
        entry = KnowledgeEntry(
            summary="Perfil do utilizador",
            content="Nome: João\nRegião: Lisboa",
            lines_loaded=2,
            total_lines=2,
            source="supabase",
        )
        assert entry["content"] is not None
        assert entry["lines_loaded"] == 2
        assert entry["source"] == "supabase"

    def test_create_available_entry(self):
        entry = KnowledgeEntry(
            summary="Análise detalhada",
            content=None,
            lines_loaded=0,
            total_lines=10,
            source="supabase",
        )
        assert entry["content"] is None
        assert entry["lines_loaded"] == 0

    def test_entry_sources(self):
        for source in ("supabase", "tool", "pipeline"):
            entry = KnowledgeEntry(
                summary="test", content="data", lines_loaded=1, total_lines=1, source=source
            )
            assert entry["source"] == source


class TestTodoItem:
    def test_create_pending_todo(self):
        todo = TodoItem(id="abc123", task="Analisar imóvel de Alfama", status="pending")
        assert todo["id"] == "abc123"
        assert todo["status"] == "pending"

    def test_todo_statuses(self):
        for status in ("pending", "in_progress", "completed"):
            todo = TodoItem(id="x", task="tarefa", status=status)
            assert todo["status"] == status


class TestOrchestratorState:
    def test_minimal_state_creation(self):
        from langchain_core.messages import HumanMessage
        state = OrchestratorState(
            messages=[HumanMessage(content="olá")],
            user_id="user-123",
            conversation_id="conv-456",
            knowledge={},
            todos=[],
            current_focus=None,
            executed_actions=[],
            stream_events=[],
        )
        assert state["user_id"] == "user-123"
        assert state["conversation_id"] == "conv-456"
        assert state["knowledge"] == {}
        assert state["todos"] == []
        assert state["current_focus"] is None

    def test_state_with_knowledge(self):
        entry = KnowledgeEntry(
            summary="Perfil", content="Nome: Ana", lines_loaded=1, total_lines=1, source="supabase"
        )
        from langchain_core.messages import HumanMessage
        state = OrchestratorState(
            messages=[HumanMessage(content="test")],
            user_id="u1",
            conversation_id="c1",
            knowledge={"user/profile": entry},
            todos=[],
            current_focus=None,
            executed_actions=[],
            stream_events=[],
        )
        assert "user/profile" in state["knowledge"]
        assert state["knowledge"]["user/profile"]["content"] == "Nome: Ana"

    def test_state_with_focus(self):
        from langchain_core.messages import HumanMessage
        state = OrchestratorState(
            messages=[HumanMessage(content="test")],
            user_id="u1",
            conversation_id="c1",
            knowledge={},
            todos=[],
            current_focus={"property_id": "prop-1", "topic": "cozinha", "drill_down_level": 1},
            executed_actions=[],
            stream_events=[],
        )
        assert state["current_focus"]["property_id"] == "prop-1"
        assert state["current_focus"]["drill_down_level"] == 1
