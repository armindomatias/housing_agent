"""
Unit tests for the knowledge base context management functions.
Tests context.py helpers: load, offload, write, remove, demote, and context block building.
"""

import pytest
from app.agents.context import (
    _render_focus,
    _render_knowledge_index,
    _render_todos,
    build_context_block,
    demote_stale_entries,
    load_knowledge_entry,
    offload_knowledge_entry,
    remove_knowledge_entry,
    write_knowledge_entry,
)
from app.agents.state import KnowledgeEntry, OrchestratorState, TodoItem
from langchain_core.messages import HumanMessage


def _make_entry(content: str | None, summary: str = "resumo") -> KnowledgeEntry:
    lines = len(content.splitlines()) if content else 0
    return KnowledgeEntry(
        summary=summary,
        content=content,
        lines_loaded=lines,
        total_lines=max(lines, 5),
        source="supabase",
    )


def _make_state(**overrides) -> OrchestratorState:
    defaults = dict(
        messages=[HumanMessage(content="test")],
        user_id="u1",
        conversation_id="c1",
        knowledge={},
        todos=[],
        current_focus=None,
        executed_actions=[],
        stream_events=[],
    )
    defaults.update(overrides)
    return OrchestratorState(**defaults)


class TestLoadKnowledgeEntry:
    def test_load_new_key(self):
        knowledge: dict[str, KnowledgeEntry] = {}
        updated = load_knowledge_entry(knowledge, "user/profile", "Nome: João\nRegião: Lisboa")
        assert updated["user/profile"]["content"] == "Nome: João\nRegião: Lisboa"
        assert updated["user/profile"]["lines_loaded"] == 2

    def test_load_existing_available_entry(self):
        knowledge = {"user/fiscal": _make_entry(None, "Não preenchido")}
        updated = load_knowledge_entry(knowledge, "user/fiscal", "regime: IRS\nprimeira: True")
        assert updated["user/fiscal"]["content"] == "regime: IRS\nprimeira: True"
        assert updated["user/fiscal"]["lines_loaded"] == 2

    def test_load_preserves_other_entries(self):
        knowledge = {
            "user/profile": _make_entry("Nome: Ana"),
            "user/fiscal": _make_entry(None),
        }
        updated = load_knowledge_entry(knowledge, "user/fiscal", "regime: IRS")
        assert updated["user/profile"]["content"] == "Nome: Ana"
        assert updated["user/fiscal"]["content"] == "regime: IRS"

    def test_load_updates_total_lines(self):
        entry = _make_entry(None)
        knowledge = {"key": entry}
        updated = load_knowledge_entry(knowledge, "key", "a\nb\nc\nd\ne\nf")
        assert updated["key"]["total_lines"] >= 6


class TestOffloadKnowledgeEntry:
    def test_offload_loaded_entry(self):
        knowledge = {"user/fiscal": _make_entry("regime: IRS")}
        updated = offload_knowledge_entry(knowledge, "user/fiscal")
        assert updated["user/fiscal"]["content"] is None
        assert updated["user/fiscal"]["lines_loaded"] == 0

    def test_offload_preserves_summary(self):
        knowledge = {"user/fiscal": _make_entry("regime: IRS", summary="IRS | 1ª habitação")}
        updated = offload_knowledge_entry(knowledge, "user/fiscal")
        assert updated["user/fiscal"]["summary"] == "IRS | 1ª habitação"

    def test_offload_missing_key_is_noop(self):
        knowledge: dict[str, KnowledgeEntry] = {}
        updated = offload_knowledge_entry(knowledge, "nonexistent")
        assert updated == {}


class TestWriteKnowledgeEntry:
    def test_write_new_entry(self):
        knowledge: dict[str, KnowledgeEntry] = {}
        updated = write_knowledge_entry(knowledge, "notes/custom", "linha 1\nlinha 2", "nota personalizada")
        assert updated["notes/custom"]["content"] == "linha 1\nlinha 2"
        assert updated["notes/custom"]["summary"] == "nota personalizada"
        assert updated["notes/custom"]["source"] == "tool"

    def test_write_overwrites_existing(self):
        knowledge = {"notes/custom": _make_entry("conteúdo antigo", "resumo antigo")}
        updated = write_knowledge_entry(knowledge, "notes/custom", "conteúdo novo", "resumo novo")
        assert updated["notes/custom"]["content"] == "conteúdo novo"
        assert updated["notes/custom"]["summary"] == "resumo novo"

    def test_write_custom_source(self):
        knowledge: dict[str, KnowledgeEntry] = {}
        updated = write_knowledge_entry(knowledge, "k", "v", "s", source="pipeline")
        assert updated["k"]["source"] == "pipeline"


class TestRemoveKnowledgeEntry:
    def test_remove_existing(self):
        knowledge = {
            "user/profile": _make_entry("data"),
            "user/fiscal": _make_entry(None),
        }
        updated = remove_knowledge_entry(knowledge, "user/fiscal")
        assert "user/fiscal" not in updated
        assert "user/profile" in updated

    def test_remove_missing_is_noop(self):
        knowledge = {"user/profile": _make_entry("data")}
        updated = remove_knowledge_entry(knowledge, "nonexistent")
        assert "user/profile" in updated
        assert len(updated) == 1


class TestDemoteStaleEntries:
    def test_demotes_unreferenced_loaded_entries(self):
        knowledge = {
            "user/profile": _make_entry("profile data"),          # protected
            "portfolio/index": _make_entry("index data"),         # protected
            "session/resumo_anterior": _make_entry("session"),    # protected
            "user/fiscal": _make_entry("fiscal data"),            # should demote
        }
        updated = demote_stale_entries(knowledge, referenced_keys=set())
        # Protected entries stay loaded
        assert updated["user/profile"]["content"] is not None
        assert updated["portfolio/index"]["content"] is not None
        assert updated["session/resumo_anterior"]["content"] is not None
        # Unreferenced non-protected entry is demoted
        assert updated["user/fiscal"]["content"] is None

    def test_keeps_referenced_entries_loaded(self):
        knowledge = {
            "user/fiscal": _make_entry("fiscal data"),
        }
        updated = demote_stale_entries(knowledge, referenced_keys={"user/fiscal"})
        assert updated["user/fiscal"]["content"] == "fiscal data"

    def test_custom_always_loaded_set(self):
        knowledge = {
            "special/key": _make_entry("data"),
            "other/key": _make_entry("data"),
        }
        updated = demote_stale_entries(
            knowledge,
            referenced_keys=set(),
            always_loaded={"special/key"},
        )
        assert updated["special/key"]["content"] is not None
        assert updated["other/key"]["content"] is None


class TestRenderHelpers:
    def test_render_knowledge_index_empty(self):
        result = _render_knowledge_index({})
        assert "(vazio)" in result

    def test_render_knowledge_index_loaded_vs_available(self):
        knowledge = {
            "user/profile": _make_entry("loaded content"),
            "user/fiscal": _make_entry(None),
        }
        result = _render_knowledge_index(knowledge)
        assert "[carregado]" in result
        assert "[disponível]" in result

    def test_render_todos_empty(self):
        result = _render_todos([])
        assert "(sem tarefas)" in result

    def test_render_todos_with_items(self):
        todos = [
            TodoItem(id="a1", task="Analisar imóvel", status="pending"),
            TodoItem(id="a2", task="Comparar preços", status="completed"),
        ]
        result = _render_todos(todos)
        assert "Analisar imóvel" in result
        assert "Comparar preços" in result
        assert "☐" in result   # pending
        assert "✓" in result   # completed

    def test_render_focus_none(self):
        result = _render_focus(None)
        assert "Nenhum" in result

    def test_render_focus_with_data(self):
        focus = {"property_id": "prop-abc", "topic": "cozinha", "drill_down_level": 2}
        result = _render_focus(focus)
        assert "prop-abc" in result
        assert "cozinha" in result
        assert "2" in result


class TestBuildContextBlock:
    def test_contains_all_sections(self):
        state = _make_state(
            knowledge={"user/profile": _make_entry("Nome: João")},
            todos=[TodoItem(id="t1", task="tarefa", status="pending")],
            current_focus={"property_id": "p1", "topic": "geral", "drill_down_level": 0},
        )
        block = build_context_block(state)
        assert "Base de Conhecimento" in block
        assert "Tarefas" in block
        assert "Foco Atual" in block

    def test_knowledge_index_shown(self):
        state = _make_state(
            knowledge={"user/profile": _make_entry("data", "Perfil do utilizador")}
        )
        block = build_context_block(state)
        assert "user/profile" in block
        assert "Perfil do utilizador" in block
