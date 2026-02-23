"""
Knowledge base hydration from Supabase.

Builds the initial knowledge dict for OrchestratorState by calling the
fast hydration query and populating:

  Always-present (loaded):
    user/profile         → profile_summary
    portfolio/index      → one-liner per portfolio item
    portfolio/{id}/resumo → active property analysis summary
    session/resumo_anterior → last session summary

  Available (summary only, content=None):
    user/fiscal, user/budget, user/renovation, user/preferences, user/goals
    portfolio/{id}/resumo for each non-active property
"""

import structlog
from supabase._async.client import AsyncClient as AsyncSupabaseClient

from app.agents.state import KnowledgeEntry
from app.services.supabase_client import (
    get_latest_analysis,
    hydrate_user_context,
)

logger = structlog.get_logger(__name__)


def _make_entry(
    summary: str,
    content: str | None,
    source: str = "supabase",
    total_lines: int | None = None,
) -> KnowledgeEntry:
    """Build a KnowledgeEntry. Estimates total_lines from content if provided."""
    if content is not None:
        lines = len(content.splitlines())
    else:
        # Estimate from summary length — rough heuristic
        lines = max(1, len(summary.splitlines()))
    return KnowledgeEntry(
        summary=summary,
        content=content,
        lines_loaded=lines if content is not None else 0,
        total_lines=total_lines if total_lines is not None else lines,
        source=source,
    )


def _profile_section_summary(section: str, data: dict | None) -> str:
    """Generate a short one-liner summary for a profile section JSONB."""
    if not data:
        return "Não preenchido"
    keys = list(data.keys())
    filled = [k for k in keys if data[k] not in (None, "", [], {})]
    return f"{len(filled)}/{len(keys)} campos preenchidos" if keys else "Não preenchido"


async def build_knowledge_base(
    client: AsyncSupabaseClient,
    user_id: str,
) -> dict[str, KnowledgeEntry]:
    """
    Hydrate the knowledge base from Supabase for a new conversation turn.

    Returns a dict keyed by knowledge path strings.
    """
    knowledge: dict[str, KnowledgeEntry] = {}

    context = await hydrate_user_context(client, user_id)
    if context is None:
        logger.warning("knowledge_base_hydration_no_profile", user_id=user_id)
        return knowledge

    # --- Always-present: user/profile ---
    profile_summary = context.get("profile_summary") or "Perfil não configurado"
    name = context.get("display_name") or "Utilizador"
    region = context.get("region") or "não especificada"
    sections = context.get("sections_completed") or []
    profile_content = (
        f"Nome: {name}\n"
        f"Região: {region}\n"
        f"Secções completas: {', '.join(sections) if sections else 'nenhuma'}\n"
        f"Resumo: {profile_summary}"
    )
    knowledge["user/profile"] = _make_entry(
        summary=profile_summary,
        content=profile_content,
    )

    # --- Available only: profile sections (not loaded by default) ---
    section_summaries = {
        "fiscal": context.get("fiscal_summary"),
        "budget": context.get("budget_summary"),
        "renovation": context.get("renovation_summary"),
        "preferences": context.get("preferences_summary"),
        "goals": context.get("goals_summary"),
    }
    for section, summary in section_summaries.items():
        knowledge[f"user/{section}"] = _make_entry(
            summary=summary or "Não preenchido",
            content=None,  # load on demand
        )

    # --- Always-present: portfolio/index ---
    portfolio: list[dict] = context.get("portfolio") or []
    if portfolio:
        index_lines = []
        for item in portfolio:
            active_marker = " [ativo]" if item.get("is_active") else ""
            nickname = item.get("nickname") or ""
            nickname_str = f' "{nickname}"' if nickname else ""
            summary_line = item.get("index_summary") or "sem resumo"
            index_lines.append(
                f"- {item['id']}{nickname_str}{active_marker}: {summary_line}"
            )
        index_content = "\n".join(index_lines)
        knowledge["portfolio/index"] = _make_entry(
            summary=f"{len(portfolio)} imóvel(is) no portfólio",
            content=index_content,
        )
    else:
        knowledge["portfolio/index"] = _make_entry(
            summary="Portfólio vazio",
            content="Nenhum imóvel adicionado ainda.",
        )

    # --- Per-property: available summaries + load active property ---
    for item in portfolio:
        prop_id = item.get("property_id") or item.get("id")
        item_summary = item.get("index_summary") or "sem resumo"

        if item.get("is_active"):
            # Load the active property's analysis summary (always-present)
            try:
                analysis = await get_latest_analysis(client, user_id, prop_id)
                if analysis and analysis.get("chat_summary"):
                    knowledge[f"portfolio/{prop_id}/resumo"] = _make_entry(
                        summary=item_summary,
                        content=analysis["chat_summary"],
                        source="supabase",
                    )
                    if analysis.get("detail_summary"):
                        knowledge[f"portfolio/{prop_id}/analise"] = _make_entry(
                            summary=f"Análise detalhada: {item_summary}",
                            content=None,  # load on demand
                        )
                else:
                    knowledge[f"portfolio/{prop_id}/resumo"] = _make_entry(
                        summary=item_summary,
                        content="Análise não disponível para este imóvel.",
                    )
            except Exception:
                logger.exception("knowledge_base_load_analysis_failed", property_id=prop_id)
                knowledge[f"portfolio/{prop_id}/resumo"] = _make_entry(
                    summary=item_summary,
                    content=None,
                )
        else:
            # Non-active: available but not loaded
            knowledge[f"portfolio/{prop_id}/resumo"] = _make_entry(
                summary=item_summary,
                content=None,
            )

    # --- Always-present: session/resumo_anterior ---
    last_session = context.get("last_session_summary")
    if last_session:
        knowledge["session/resumo_anterior"] = _make_entry(
            summary="Resumo da sessão anterior",
            content=last_session,
        )
    else:
        knowledge["session/resumo_anterior"] = _make_entry(
            summary="Primeira sessão",
            content=None,
        )

    logger.info(
        "knowledge_base_hydrated",
        user_id=user_id,
        total_keys=len(knowledge),
        loaded_keys=sum(1 for e in knowledge.values() if e["content"] is not None),
    )
    return knowledge
