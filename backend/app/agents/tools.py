"""
Orchestrator agent tools.

All tools use LangGraph's Command pattern with InjectedState to directly
update the graph state. Supabase client and services are accessed via
RunnableConfig configurable dict (injected at graph invocation time).

Tool categories:
  Context navigation:   read_context, write_context, remove_context
  Task management:      manage_todos
  User profile:         update_user_profile
  Portfolio:            save_to_portfolio, remove_from_portfolio,
                        switch_active_property, search_portfolio
  Analysis:             trigger_property_analysis, recalculate_costs
"""

import uuid
from typing import Annotated, Any

import structlog
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from app.agents.context import (
    load_knowledge_entry,
    remove_knowledge_entry,
    write_knowledge_entry,
)
from app.agents.state import OrchestratorState, TodoItem
from app.agents.summaries import (
    generate_master_profile_summary,
    generate_portfolio_index_line,
    generate_profile_section_summary,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_supabase(config: RunnableConfig):
    """Extract Supabase client from config. Returns None if not configured."""
    return config.get("configurable", {}).get("supabase")


def _get_renovation_graph(config: RunnableConfig):
    """Extract renovation graph from config."""
    return config.get("configurable", {}).get("renovation_graph")


def _ok(tool_call_id: str, msg: str, state_updates: dict) -> Command:
    """Build a Command with a ToolMessage and state updates."""
    return Command(
        update={
            **state_updates,
            "messages": [ToolMessage(content=msg, tool_call_id=tool_call_id)],
        }
    )


def _err(tool_call_id: str, msg: str) -> Command:
    """Build a Command with only an error ToolMessage (no state change)."""
    return Command(
        update={"messages": [ToolMessage(content=f"Erro: {msg}", tool_call_id=tool_call_id)]}
    )


# ---------------------------------------------------------------------------
# Context navigation tools
# ---------------------------------------------------------------------------


@tool
async def read_context(
    key: str,
    state: Annotated[OrchestratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    config: RunnableConfig,
    start_line: int = 0,
    num_lines: int | None = None,
) -> Command:
    """Read content from the knowledge base. For entries under 20 lines, loads full content.
    Use start_line and num_lines for partial reads on large entries.
    The entry status changes to [carregado] after reading."""
    knowledge = state["knowledge"]

    if key not in knowledge:
        return _err(tool_call_id, f"Chave '{key}' não encontrada na base de conhecimento.")

    entry = knowledge[key]
    content = entry["content"]

    if content is None:
        # Load on demand from Supabase
        supabase = _get_supabase(config)
        if supabase is None:
            return _err(tool_call_id, "Base de dados não disponível.")

        content = await _load_entry_from_db(key, state["user_id"], supabase)
        if content is None:
            return _err(tool_call_id, f"Não foi possível carregar '{key}' da base de dados.")

    # Apply line slice if requested
    lines = content.splitlines()
    if num_lines is not None:
        sliced_lines = lines[start_line : start_line + num_lines]
        result_content = "\n".join(sliced_lines)
        loaded_content = content  # store full content in knowledge base
    elif len(lines) <= 20:
        result_content = content
        loaded_content = content
    else:
        result_content = content
        loaded_content = content

    updated_knowledge = load_knowledge_entry(knowledge, key, loaded_content)

    lines_info = f"({len(lines)} linha(s))" if len(lines) > 1 else ""
    result = f"[{key}] {lines_info}\n{result_content}"

    return _ok(tool_call_id, result, {"knowledge": updated_knowledge})


@tool
async def write_context(
    key: str,
    content: str,
    summary: str,
    state: Annotated[OrchestratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Write or update content in the knowledge base with a one-line summary.
    Use for storing derived information, notes, or sub-agent results."""
    updated_knowledge = write_knowledge_entry(
        state["knowledge"], key, content, summary, source="tool"
    )
    return _ok(
        tool_call_id,
        f"'{key}' guardado na base de conhecimento.",
        {"knowledge": updated_knowledge},
    )


@tool
async def remove_context(
    key: str,
    state: Annotated[OrchestratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Remove an item from the knowledge base when it is no longer relevant."""
    if key not in state["knowledge"]:
        return _err(tool_call_id, f"Chave '{key}' não existe na base de conhecimento.")
    updated_knowledge = remove_knowledge_entry(state["knowledge"], key)
    return _ok(
        tool_call_id,
        f"'{key}' removido da base de conhecimento.",
        {"knowledge": updated_knowledge},
    )


async def _load_entry_from_db(
    key: str, user_id: str, supabase: Any
) -> str | None:
    """Load detailed content for a knowledge key from Supabase."""
    from app.services import supabase_client as db

    parts = key.split("/")

    # user/fiscal, user/budget, etc.
    if parts[0] == "user" and len(parts) == 2 and parts[1] in (
        "fiscal", "budget", "renovation", "preferences", "goals"
    ):
        profile = await db.get_user_profile(supabase, user_id)
        if not profile:
            return None
        section_data = profile.get(parts[1]) or {}
        if not section_data:
            return f"Secção '{parts[1]}' ainda não preenchida."
        lines = [f"{k}: {v}" for k, v in section_data.items() if v not in (None, "", [], {})]
        return "\n".join(lines) if lines else f"Secção '{parts[1]}' vazia."

    # portfolio/{property_id}/analise
    if parts[0] == "portfolio" and len(parts) == 3 and parts[2] == "analise":
        property_id = parts[1]
        analysis = await db.get_latest_analysis(supabase, user_id, property_id)
        if not analysis:
            return "Análise não disponível."
        detail = analysis.get("detail_summary") or analysis.get("chat_summary")
        return detail or "Análise sem resumo detalhado."

    # portfolio/{property_id}/resumo — load chat summary
    if parts[0] == "portfolio" and len(parts) == 3 and parts[2] == "resumo":
        property_id = parts[1]
        analysis = await db.get_latest_analysis(supabase, user_id, property_id)
        if not analysis:
            return "Análise não disponível para este imóvel."
        return analysis.get("chat_summary") or "Imóvel sem análise."

    return None


# ---------------------------------------------------------------------------
# Task management tools
# ---------------------------------------------------------------------------


@tool
async def manage_todos(
    action: str,
    state: Annotated[OrchestratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    task: str | None = None,
    task_id: str | None = None,
) -> Command:
    """Manage the task list for multi-step requests.
    Actions: 'add' (requires task parameter), 'complete' (requires task_id),
    'list'. Only create todos for complex multi-step work."""
    todos = list(state.get("todos") or [])

    if action == "add":
        if not task:
            return _err(tool_call_id, "Parâmetro 'task' é obrigatório para 'add'.")
        new_id = str(uuid.uuid4())[:8]
        todos.append(TodoItem(id=new_id, task=task, status="pending"))
        return _ok(tool_call_id, f"Tarefa adicionada: [{new_id}] {task}", {"todos": todos})

    if action == "complete":
        if not task_id:
            return _err(tool_call_id, "Parâmetro 'task_id' é obrigatório para 'complete'.")
        updated = False
        for i, t in enumerate(todos):
            if t["id"] == task_id:
                todos[i] = TodoItem(id=t["id"], task=t["task"], status="completed")
                updated = True
                break
        if not updated:
            return _err(tool_call_id, f"Tarefa '{task_id}' não encontrada.")
        return _ok(tool_call_id, f"Tarefa [{task_id}] marcada como concluída.", {"todos": todos})

    if action == "list":
        if not todos:
            return _ok(tool_call_id, "Sem tarefas pendentes.", {"todos": todos})
        lines = [f"[{t['id']}] {t['status']}: {t['task']}" for t in todos]
        return _ok(tool_call_id, "\n".join(lines), {"todos": todos})

    return _err(tool_call_id, f"Ação desconhecida: '{action}'. Use 'add', 'complete' ou 'list'.")


# ---------------------------------------------------------------------------
# User profile tools
# ---------------------------------------------------------------------------


@tool
async def update_user_profile(
    section: str,
    updates: dict,
    state: Annotated[OrchestratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    config: RunnableConfig,
) -> Command:
    """Update a user profile section (fiscal|budget|renovation|preferences|goals).
    Persists to Supabase and regenerates section and master summaries."""
    from app.constants import PROFILE_SECTIONS
    from app.services import supabase_client as db

    valid_sections = PROFILE_SECTIONS + ["display_name", "region"]
    if section not in valid_sections:
        return _err(
            tool_call_id,
            f"Secção inválida: '{section}'. Válidas: {', '.join(PROFILE_SECTIONS)}",
        )

    supabase = _get_supabase(config)
    user_id = state["user_id"]

    # Load current profile for old values
    profile = await db.get_user_profile(supabase, user_id) or {}

    # For top-level fields (display_name, region)
    if section in ("display_name", "region"):
        old_value = profile.get(section)
        await db.upsert_user_profile(supabase, user_id, {section: updates.get(section)})
        await db.log_action(
            supabase, user_id, "profile_update", "user_profile",
            conversation_id=state.get("conversation_id"),
            field_changed=section,
            old_value={"value": old_value},
            new_value={"value": updates.get(section)},
        )
        return _ok(tool_call_id, f"Perfil actualizado: {section}.", {})

    # For JSONB sections, merge with existing data
    existing_section = profile.get(section) or {}
    merged = {**existing_section, **updates}

    # Regenerate section summary
    section_summary = generate_profile_section_summary(section, merged)

    # Check if section is now complete (has at least some data)
    sections_completed = list(profile.get("sections_completed") or [])
    if section not in sections_completed and merged:
        sections_completed.append(section)

    # Regenerate master profile summary
    updated_profile = {
        **profile,
        section: merged,
        f"{section}_summary": section_summary,
        "sections_completed": sections_completed,
    }
    master_summary = generate_master_profile_summary(updated_profile)

    db_updates = {
        section: merged,
        f"{section}_summary": section_summary,
        "sections_completed": sections_completed,
        "profile_summary": master_summary,
    }
    await db.upsert_user_profile(supabase, user_id, db_updates)
    await db.log_action(
        supabase, user_id, "profile_update", "user_profile",
        conversation_id=state.get("conversation_id"),
        field_changed=section,
        old_value=existing_section,
        new_value=merged,
    )

    # Update knowledge base
    from app.agents.context import write_knowledge_entry as wke

    updated_knowledge = wke(
        state["knowledge"],
        f"user/{section}",
        "\n".join(f"{k}: {v}" for k, v in merged.items()),
        section_summary,
        source="supabase",
    )
    # Update master profile entry
    updated_knowledge = wke(
        updated_knowledge,
        "user/profile",
        (
            f"Nome: {updated_profile.get('display_name') or 'Utilizador'}\n"
            f"Região: {updated_profile.get('region') or 'não especificada'}\n"
            f"Secções completas: {', '.join(sections_completed)}\n"
            f"Resumo: {master_summary}"
        ),
        master_summary,
        source="supabase",
    )

    return _ok(
        tool_call_id,
        f"Perfil actualizado: secção '{section}'.",
        {"knowledge": updated_knowledge},
    )


# ---------------------------------------------------------------------------
# Portfolio management tools
# ---------------------------------------------------------------------------


@tool
async def save_to_portfolio(
    property_id: str,
    state: Annotated[OrchestratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    config: RunnableConfig,
    nickname: str | None = None,
) -> Command:
    """Save a property to the portfolio. Creates a portfolio_item and generates
    a one-line index summary."""
    from app.services import supabase_client as db

    supabase = _get_supabase(config)
    user_id = state["user_id"]

    # Check if already in portfolio
    existing = await db.get_portfolio_item(supabase, user_id, property_id)
    if existing:
        return _ok(
            tool_call_id,
            "Imóvel já está no portfólio.",
            {},
        )

    # Load property data for index summary

    prop = None
    try:
        response = await supabase.table("properties").select("*").eq("id", property_id).single().execute()
        prop = response.data
    except Exception:
        pass

    index_summary = generate_portfolio_index_line(prop or {})
    item = await db.create_portfolio_item(
        supabase, user_id, property_id, nickname=nickname, index_summary=index_summary
    )
    await db.log_action(
        supabase, user_id, "portfolio_add", "portfolio_item",
        entity_id=item["id"],
        conversation_id=state.get("conversation_id"),
        new_value={"property_id": property_id, "nickname": nickname},
    )

    # Update portfolio index in knowledge base
    nickname_str = f' "{nickname}"' if nickname else ""
    marker = " [ativo]" if item.get("is_active") else ""
    new_line = f"- {item['id']}{nickname_str}{marker}: {index_summary}"
    existing_content = (state["knowledge"].get("portfolio/index") or {}).get("content") or ""
    updated_content = (existing_content + "\n" + new_line).strip()

    portfolio_items = [e for e in state["knowledge"].get("portfolio/index", {}).get("content", "").splitlines() if e]
    new_count = len(portfolio_items) + 1
    from app.agents.context import write_knowledge_entry as wke
    updated_knowledge = wke(
        state["knowledge"],
        "portfolio/index",
        updated_content,
        f"{new_count} imóvel(is) no portfólio",
    )

    return _ok(
        tool_call_id,
        f"Imóvel guardado no portfólio{nickname_str}.",
        {"knowledge": updated_knowledge},
    )


@tool
async def remove_from_portfolio(
    property_id: str,
    state: Annotated[OrchestratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    config: RunnableConfig,
) -> Command:
    """Remove a property from the portfolio (sets status to 'archived').
    Always ask for confirmation before calling this tool."""
    from app.services import supabase_client as db

    supabase = _get_supabase(config)
    user_id = state["user_id"]

    item = await db.get_portfolio_item(supabase, user_id, property_id)
    if not item:
        return _err(tool_call_id, "Imóvel não encontrado no portfólio.")

    await db.update_portfolio_item(supabase, item["id"], {"status": "archived", "is_active": False})
    await db.log_action(
        supabase, user_id, "portfolio_remove", "portfolio_item",
        entity_id=item["id"],
        conversation_id=state.get("conversation_id"),
        old_value={"status": item["status"]},
        new_value={"status": "archived"},
    )

    # Remove from knowledge base
    from app.agents.context import remove_knowledge_entry as rke
    updated_knowledge = rke(state["knowledge"], f"portfolio/{property_id}/resumo")
    updated_knowledge = rke(updated_knowledge, f"portfolio/{property_id}/analise")

    return _ok(
        tool_call_id,
        "Imóvel removido do portfólio.",
        {"knowledge": updated_knowledge},
    )


@tool
async def switch_active_property(
    property_id: str,
    state: Annotated[OrchestratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    config: RunnableConfig,
) -> Command:
    """Switch the active (focused) property. Loads the new property summary
    and updates current_focus."""
    from app.services import supabase_client as db

    supabase = _get_supabase(config)
    user_id = state["user_id"]

    await db.set_active_portfolio_item(supabase, user_id, property_id)

    new_focus = {
        "property_id": property_id,
        "topic": "geral",
        "drill_down_level": 0,
    }

    # Load analysis for the newly active property
    analysis = await db.get_latest_analysis(supabase, user_id, property_id)
    from app.agents.context import write_knowledge_entry as wke
    updated_knowledge = state["knowledge"]
    if analysis and analysis.get("chat_summary"):
        item_summary = analysis.get("chat_summary", "sem resumo")
        updated_knowledge = wke(
            updated_knowledge,
            f"portfolio/{property_id}/resumo",
            analysis["chat_summary"],
            item_summary[:80],
            source="supabase",
        )

    return _ok(
        tool_call_id,
        f"Imóvel activo alterado para {property_id}.",
        {"current_focus": new_focus, "knowledge": updated_knowledge},
    )


@tool
async def search_portfolio(
    query: str,
    state: Annotated[OrchestratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    config: RunnableConfig,
) -> Command:
    """Resolve a natural language property reference to a portfolio item ID.
    Use for references like 'o de Alfama', 'o mais barato', 'o T2'."""
    supabase = _get_supabase(config)
    user_id = state["user_id"]

    response = (
        await supabase.table("portfolio_items")
        .select("id, property_id, nickname, index_summary, is_active, status, properties(location, price, num_rooms, title)")
        .eq("user_id", user_id)
        .neq("status", "archived")
        .execute()
    )
    items = response.data or []

    if not items:
        return _ok(tool_call_id, "Portfólio vazio.", {})

    # Build a searchable text for each item and do simple keyword matching
    query_lower = query.lower()
    matches = []
    for item in items:
        prop = item.get("properties") or {}
        searchable = " ".join([
            item.get("nickname") or "",
            item.get("index_summary") or "",
            prop.get("location") or "",
            prop.get("title") or "",
            str(prop.get("num_rooms") or ""),
            str(prop.get("price") or ""),
        ]).lower()
        # Score by keyword overlap
        score = sum(1 for word in query_lower.split() if word in searchable)
        if score > 0:
            matches.append((score, item))

    if not matches:
        # Return all items if no match
        all_lines = [
            f"ID: {it['id']} — {it.get('index_summary', 'sem resumo')}" for it in items
        ]
        return _ok(
            tool_call_id,
            f"Nenhuma correspondência para '{query}'. Imóveis disponíveis:\n" + "\n".join(all_lines),
            {},
        )

    matches.sort(key=lambda x: x[0], reverse=True)

    if len(matches) == 1 or matches[0][0] > matches[1][0]:
        best = matches[0][1]
        return _ok(
            tool_call_id,
            f"Imóvel encontrado: ID={best['property_id']} — {best.get('index_summary', '')}",
            {},
        )

    # Multiple matches — return options
    options = [f"ID: {m[1]['property_id']} — {m[1].get('index_summary', '')}" for _, m in matches[:3]]
    return _ok(
        tool_call_id,
        f"Múltiplas correspondências para '{query}':\n" + "\n".join(options),
        {},
    )


# ---------------------------------------------------------------------------
# Analysis tools
# ---------------------------------------------------------------------------


@tool
async def trigger_property_analysis(
    url: str,
    state: Annotated[OrchestratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    config: RunnableConfig,
) -> Command:
    """Scrape and analyze a property from an Idealista URL.
    Runs the full renovation pipeline and stores results in the knowledge base.
    Automatically adds the property to the portfolio when analysis is complete."""
    from app.agents.context import write_knowledge_entry as wke
    from app.agents.summaries import generate_analysis_chat_summary, generate_portfolio_index_line
    from app.graphs.state import create_initial_state

    graph = _get_renovation_graph(config)
    supabase = _get_supabase(config)
    user_id = state["user_id"]

    if graph is None:
        return _err(tool_call_id, "Pipeline de análise não disponível.")

    # Emit a thinking event
    updated_events = list(state.get("stream_events") or [])
    updated_events.append({"type": "thinking", "message": "A analisar imóvel..."})

    try:
        initial_state = create_initial_state(url, user_id)
        final_state = await graph.ainvoke(initial_state)

        if final_state.get("error"):
            return _err(tool_call_id, f"Falha na análise: {final_state['error']}")

        estimate = final_state.get("estimate")
        if estimate is None:
            return _err(tool_call_id, "Análise não produziu resultados.")

        estimate_dict = estimate.model_dump() if hasattr(estimate, "model_dump") else estimate
        prop_data = estimate_dict.get("property_data") or {}

        # Generate summaries
        result_for_summary = {
            "price": prop_data.get("price"),
            "area_m2": prop_data.get("area_m2"),
            "price_per_m2": prop_data.get("price_per_m2"),
            "overall_condition": estimate_dict.get("overall_condition"),
            "confidence_score": estimate_dict.get("overall_confidence"),
            "total_min": estimate_dict.get("total_cost_min"),
            "total_max": estimate_dict.get("total_cost_max"),
            "room_estimates": [
                {
                    "room_label": r.get("room_label"),
                    "room_type": r.get("room_type"),
                    "condition": r.get("condition"),
                    "cost_min": r.get("cost_min"),
                    "cost_max": r.get("cost_max"),
                }
                for r in estimate_dict.get("room_analyses") or []
            ],
        }
        chat_summary = generate_analysis_chat_summary(result_for_summary)
        index_line = generate_portfolio_index_line(prop_data, result_for_summary)

        # Persist property + analysis to Supabase
        property_id = None
        if supabase:
            from app.services.analysis_persistence import persist_analysis_to_db

            property_id = await persist_analysis_to_db(
                supabase, url, user_id, estimate_dict,
                conversation_id=state.get("conversation_id"),
            )
            if property_id is None:
                updated_events.append({
                    "type": "error",
                    "message": "Erro ao guardar dados na base de dados. A análise foi feita mas os resultados podem não ter sido guardados.",
                })

        # Update knowledge base
        knowledge_key = f"portfolio/{property_id or url}/resumo"
        updated_knowledge = wke(
            state["knowledge"],
            knowledge_key,
            chat_summary,
            index_line,
            source="pipeline",
        )

        return _ok(
            tool_call_id,
            f"Análise concluída.\n\n{chat_summary}",
            {
                "knowledge": updated_knowledge,
                "stream_events": updated_events,
                "current_focus": {
                    "property_id": property_id or url,
                    "topic": "renovação",
                    "drill_down_level": 0,
                },
            },
        )

    except Exception as e:
        logger.exception("trigger_property_analysis_failed", url=url)
        return _err(tool_call_id, f"Erro inesperado na análise: {str(e)}")


@tool
async def recalculate_costs(
    property_id: str,
    state: Annotated[OrchestratorState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    config: RunnableConfig,
    preferences: dict | None = None,
) -> Command:
    """Recalculate renovation costs using stored room features with updated preferences.
    No GPT re-run needed — uses cached room_features from the database.
    Pass preferences dict to override user profile (e.g., different finish level, diy_skills)."""
    from app.agents.context import write_knowledge_entry as wke
    from app.agents.summaries import generate_analysis_chat_summary
    from app.services import supabase_client as db

    supabase = _get_supabase(config)
    user_id = state["user_id"]

    if not supabase:
        return _err(tool_call_id, "Base de dados não disponível.")

    # Load room features
    room_features = await db.get_room_features(supabase, property_id)
    if not room_features:
        return _err(
            tool_call_id,
            "Funcionalidades de divisão não encontradas. É necessário analisar o imóvel primeiro.",
        )

    # Load current user preferences
    profile = await db.get_user_profile(supabase, user_id) or {}
    renovation_prefs = profile.get("renovation") or {}
    diy_skills = renovation_prefs.get("diy_skills") or []

    # Override with provided preferences
    if preferences:
        diy_skills = preferences.get("diy_skills", diy_skills)
        renovation_prefs = {**renovation_prefs, **preferences}

    # Recalculate using cost calculator
    try:
        from app.services.cost_calculator import recalculate_from_features

        updated_estimates = recalculate_from_features(room_features, diy_skills=diy_skills)
        total_min = sum(r.get("cost_min", 0) for r in updated_estimates)
        total_max = sum(r.get("cost_max", 0) for r in updated_estimates)

        result_for_summary = {
            "total_min": total_min,
            "total_max": total_max,
            "room_estimates": updated_estimates,
        }
        chat_summary = generate_analysis_chat_summary(result_for_summary)

        # Persist updated analysis
        latest = await db.get_latest_analysis(supabase, user_id, property_id)
        if latest:
            await db.update_analysis(supabase, latest["id"], {
                "result_data": {**(latest.get("result_data") or {}), "room_analyses": updated_estimates},
                "chat_summary": chat_summary,
                "user_preferences_snapshot": renovation_prefs,
            })
            await db.log_action(
                supabase, user_id, "cost_recalculate", "analysis",
                entity_id=latest["id"],
                conversation_id=state.get("conversation_id"),
                new_value={"diy_skills": diy_skills, "total_min": total_min, "total_max": total_max},
            )

        # Update knowledge base
        updated_knowledge = wke(
            state["knowledge"],
            f"portfolio/{property_id}/resumo",
            chat_summary,
            chat_summary.splitlines()[0] if chat_summary else "Custos recalculados",
            source="tool",
        )

        return _ok(
            tool_call_id,
            f"Custos recalculados.\n\n{chat_summary}",
            {"knowledge": updated_knowledge},
        )

    except ImportError:
        return _err(tool_call_id, "Calculadora de custos não disponível.")
    except Exception as e:
        logger.exception("recalculate_costs_failed", property_id=property_id)
        return _err(tool_call_id, f"Erro ao recalcular custos: {str(e)}")


# ---------------------------------------------------------------------------
# Tool list for graph binding
# ---------------------------------------------------------------------------

ORCHESTRATOR_TOOLS = [
    read_context,
    write_context,
    remove_context,
    manage_todos,
    update_user_profile,
    save_to_portfolio,
    remove_from_portfolio,
    switch_active_property,
    search_portfolio,
    trigger_property_analysis,
    recalculate_costs,
]
