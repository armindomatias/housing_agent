"""
Knowledge base management and context block builder.

Manages the agent's virtual knowledge file system:
- Building the context system message from current state
- Loading/offloading knowledge entries
- Demoting stale entries after turns

The context block is injected as a SystemMessage with name="context_refresh"
and is replaced (not accumulated) on every reflect pass.
"""

from app.agents.state import KnowledgeEntry, OrchestratorState, TodoItem

# Marker used to identify context messages so they can be replaced
CONTEXT_MESSAGE_NAME = "context_refresh"

# Status labels for knowledge entries
_STATUS_LOADED = "[carregado]"
_STATUS_AVAILABLE = "[disponível]"


def _render_knowledge_index(knowledge: dict[str, KnowledgeEntry]) -> str:
    """Render a compact knowledge index for the system prompt."""
    if not knowledge:
        return "  (vazio)"

    lines: list[str] = []
    for key, entry in sorted(knowledge.items()):
        status = _STATUS_LOADED if entry["content"] is not None else _STATUS_AVAILABLE
        lines.append(f"  {key} {status} — {entry['summary']}")
    return "\n".join(lines)


def _render_todos(todos: list[TodoItem]) -> str:
    """Render the current todo list."""
    if not todos:
        return "  (sem tarefas)"

    lines: list[str] = []
    icons = {"pending": "☐", "in_progress": "▶", "completed": "✓"}
    for todo in todos:
        icon = icons.get(todo["status"], "☐")
        lines.append(f"  {icon} [{todo['id']}] {todo['task']}")
    return "\n".join(lines)


def _render_focus(current_focus: dict | None) -> str:
    """Render the current focus context."""
    if not current_focus:
        return "  Nenhum imóvel em foco"
    prop_id = current_focus.get("property_id", "?")
    topic = current_focus.get("topic", "geral")
    level = current_focus.get("drill_down_level", 0)
    return f"  Imóvel: {prop_id} | Tópico: {topic} | Nível: {level}"


def build_context_block(state: OrchestratorState) -> str:
    """
    Build the full context system message content.

    This is injected into the message list as a SystemMessage before every
    agent call. It replaces the previous context block (identified by name).

    Sections:
    1. Base de Conhecimento — knowledge index
    2. Tarefas — current todos
    3. Foco Atual — property/topic being discussed
    """
    knowledge_index = _render_knowledge_index(state["knowledge"])
    todos_block = _render_todos(state.get("todos") or [])
    focus_block = _render_focus(state.get("current_focus"))

    return (
        "## Estado Atual\n\n"
        "### Base de Conhecimento\n"
        f"{knowledge_index}\n\n"
        "### Tarefas\n"
        f"{todos_block}\n\n"
        "### Foco Atual\n"
        f"{focus_block}"
    )


def load_knowledge_entry(
    knowledge: dict[str, KnowledgeEntry],
    key: str,
    content: str,
) -> dict[str, KnowledgeEntry]:
    """
    Mark a knowledge entry as loaded (content is now available).
    Returns updated knowledge dict.
    """
    updated = dict(knowledge)
    if key in updated:
        entry = dict(updated[key])
        entry["content"] = content
        lines = len(content.splitlines())
        entry["lines_loaded"] = lines
        entry["total_lines"] = max(entry["total_lines"], lines)
        updated[key] = KnowledgeEntry(**entry)  # type: ignore[misc]
    else:
        lines = len(content.splitlines())
        updated[key] = KnowledgeEntry(
            summary=key,
            content=content,
            lines_loaded=lines,
            total_lines=lines,
            source="tool",
        )
    return updated


def offload_knowledge_entry(
    knowledge: dict[str, KnowledgeEntry], key: str
) -> dict[str, KnowledgeEntry]:
    """
    Demote a knowledge entry back to available (content=None).
    Preserves summary and total_lines.
    """
    updated = dict(knowledge)
    if key in updated:
        entry = dict(updated[key])
        entry["content"] = None
        entry["lines_loaded"] = 0
        updated[key] = KnowledgeEntry(**entry)  # type: ignore[misc]
    return updated


def write_knowledge_entry(
    knowledge: dict[str, KnowledgeEntry],
    key: str,
    content: str,
    summary: str,
    source: str = "tool",
) -> dict[str, KnowledgeEntry]:
    """
    Create or replace a knowledge entry with new content and summary.
    """
    updated = dict(knowledge)
    lines = len(content.splitlines())
    updated[key] = KnowledgeEntry(
        summary=summary,
        content=content,
        lines_loaded=lines,
        total_lines=lines,
        source=source,
    )
    return updated


def remove_knowledge_entry(
    knowledge: dict[str, KnowledgeEntry], key: str
) -> dict[str, KnowledgeEntry]:
    """Remove a knowledge entry entirely."""
    return {k: v for k, v in knowledge.items() if k != key}


def demote_stale_entries(
    knowledge: dict[str, KnowledgeEntry],
    referenced_keys: set[str],
    always_loaded: set[str] | None = None,
) -> dict[str, KnowledgeEntry]:
    """
    Offload loaded entries that were NOT referenced in this turn.

    always_loaded entries (user/profile, portfolio/index, session/resumo_anterior)
    are never demoted.
    """
    protected = always_loaded or {
        "user/profile",
        "portfolio/index",
        "session/resumo_anterior",
    }
    updated = dict(knowledge)
    for key, entry in knowledge.items():
        if key in protected:
            continue
        if entry["content"] is not None and key not in referenced_keys:
            updated = offload_knowledge_entry(updated, key)
    return updated
