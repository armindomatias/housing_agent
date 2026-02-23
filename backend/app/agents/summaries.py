"""
Summary generation for analyses, portfolio items, user profiles and conversations.

Two approaches:
  1. Template-based (deterministic) — for analyses, portfolio index lines, profile sections.
     Fast, no LLM cost, always consistent format.
  2. LLM-based (GPT-4o-mini) — for conversation session summaries.
     Narrative 2-3 sentence summaries for context carry-over.

Summary formats:
  Analysis chat_summary (scannable):
    Preço: 180.000€ | Área: 65m² | €/m²: 2.769€
    Estado: Razoável | Confiança: 72%
    Renovação: 15.200€–24.800€
    Prioridades: Cozinha (mau, 5-8k€), WC (razoável, 3-5k€)

  Portfolio index line (one-liner):
    T2 Alfama, 180k€, reno 15-25k€

  Conversation summary (narrative):
    Discutimos o T2 de Alfama. Detalhámos cozinha (mau estado).
    Indeciso entre Alfama e Graça. Próximo: comparação formal.
"""

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Template-based summaries
# ---------------------------------------------------------------------------


def generate_analysis_chat_summary(result_data: dict) -> str:
    """
    Generate a compact scannable analysis summary from RenovationEstimate data.

    Expected result_data keys (from RenovationEstimate model):
      price, area_m2, price_per_m2, overall_condition, confidence_score,
      total_min, total_max, room_estimates (list of room estimate dicts)
    """
    lines: list[str] = []

    price = result_data.get("price")
    area = result_data.get("area_m2")
    price_per_m2 = result_data.get("price_per_m2")

    if price or area:
        parts = []
        if price:
            parts.append(f"Preço: {_fmt_euros(price)}")
        if area:
            parts.append(f"Área: {area}m²")
        if price_per_m2:
            parts.append(f"€/m²: {_fmt_euros(int(price_per_m2))}")
        lines.append(" | ".join(parts))

    condition = result_data.get("overall_condition")
    confidence = result_data.get("confidence_score")
    if condition or confidence is not None:
        parts = []
        if condition:
            parts.append(f"Estado: {_condition_label(condition)}")
        if confidence is not None:
            parts.append(f"Confiança: {int(confidence * 100)}%")
        lines.append(" | ".join(parts))

    total_min = result_data.get("total_min")
    total_max = result_data.get("total_max")
    if total_min is not None or total_max is not None:
        lines.append(f"Renovação: {_fmt_range(total_min, total_max)}")

    room_estimates = result_data.get("room_estimates") or []
    priority_rooms = _get_priority_rooms(room_estimates)
    if priority_rooms:
        lines.append(f"Prioridades: {priority_rooms}")

    return "\n".join(lines) if lines else "Análise concluída"


def generate_analysis_detail_summary(result_data: dict) -> str:
    """
    Generate a medium-length (~500 tokens) analysis summary.
    Includes all rooms with their condition and cost ranges.
    """
    chat_summary = generate_analysis_chat_summary(result_data)
    room_estimates = result_data.get("room_estimates") or []

    if not room_estimates:
        return chat_summary

    room_lines = ["", "Detalhes por divisão:"]
    for room in room_estimates:
        label = room.get("room_label") or room.get("room_type", "Divisão")
        condition = _condition_label(room.get("condition", ""))
        cost_min = room.get("cost_min")
        cost_max = room.get("cost_max")
        cost_str = _fmt_range(cost_min, cost_max)
        issues = room.get("main_issues") or []
        issue_str = f" — {', '.join(issues[:2])}" if issues else ""
        room_lines.append(f"  {label}: {condition}, {cost_str}{issue_str}")

    return chat_summary + "\n".join(room_lines)


def generate_portfolio_index_line(
    property_data: dict,
    analysis_data: dict | None = None,
) -> str:
    """
    Generate a one-liner for portfolio_items.index_summary.

    Format: "T2 Alfama, 180k€, reno 15-25k€"
    """
    parts: list[str] = []

    typology = property_data.get("num_rooms")
    location = property_data.get("location") or ""
    location_short = location.split(",")[0].strip() if location else ""

    if typology:
        prefix = f"T{typology}"
        if location_short:
            parts.append(f"{prefix} {location_short}")
        else:
            parts.append(prefix)
    elif location_short:
        parts.append(location_short)

    price = property_data.get("price")
    if price:
        parts.append(_fmt_euros_short(price))

    if analysis_data:
        total_min = analysis_data.get("total_min")
        total_max = analysis_data.get("total_max")
        if total_min is not None or total_max is not None:
            parts.append(f"reno {_fmt_range_short(total_min, total_max)}")

    return ", ".join(parts) if parts else "Imóvel sem dados"


def generate_profile_section_summary(section: str, data: dict) -> str:
    """
    Generate a short summary for a user_profiles section (fiscal, budget, etc.).
    """
    if not data:
        return "Não preenchido"

    if section == "fiscal":
        regime = data.get("tax_regime", "")
        first_time = data.get("first_time_buyer")
        parts = []
        if regime:
            parts.append(regime)
        if first_time is not None:
            parts.append("1ª habitação" if first_time else "não 1ª habitação")
        return " | ".join(parts) if parts else "Fiscal preenchido"

    if section == "budget":
        budget_min = data.get("budget_min")
        budget_max = data.get("budget_max")
        if budget_min or budget_max:
            return f"Orçamento: {_fmt_range(budget_min, budget_max)}"
        return "Orçamento definido"

    if section == "renovation":
        finish = data.get("finish_level", "")
        skills = data.get("diy_skills") or []
        parts = []
        if finish:
            parts.append(f"acabamento {finish}")
        if skills:
            parts.append(f"{len(skills)} skill(s) DIY")
        return " | ".join(parts) if parts else "Renovação preenchida"

    if section == "preferences":
        locations = data.get("preferred_locations") or []
        min_area = data.get("min_area")
        max_area = data.get("max_area")
        parts = []
        if locations:
            parts.append(f"zonas: {', '.join(locations[:2])}")
        if min_area or max_area:
            parts.append(f"área: {_fmt_range(min_area, max_area)}m²")
        return " | ".join(parts) if parts else "Preferências preenchidas"

    if section == "goals":
        reason = data.get("buying_reason", "")
        horizon = data.get("investment_horizon", "")
        parts = [p for p in [reason, horizon] if p]
        return " | ".join(parts) if parts else "Objetivos preenchidos"

    return "Preenchido"


def generate_master_profile_summary(profile: dict) -> str:
    """
    Generate the master profile_summary that goes in the always-present context.
    """
    name = profile.get("display_name") or "Utilizador"
    region = profile.get("region") or ""
    sections = profile.get("sections_completed") or []

    parts = [name]
    if region:
        parts.append(region)
    if sections:
        parts.append(f"{len(sections)}/5 secções completas")

    return " | ".join(parts)


# ---------------------------------------------------------------------------
# LLM-based conversation summary
# ---------------------------------------------------------------------------


async def generate_conversation_summary(
    messages: list[dict],
    openai_client: object,
    model: str = "gpt-4o-mini",
) -> str:
    """
    Generate a 2-3 sentence narrative summary of a conversation session.

    Used for session carry-over: the summary is stored in conversations.summary
    and loaded in the next session as session/resumo_anterior.

    Args:
        messages: List of {role, content} dicts from the conversation.
        openai_client: AsyncOpenAI client instance.
        model: OpenAI model to use (defaults to gpt-4o-mini for cost efficiency).
    """
    if not messages:
        return "Sessão sem mensagens relevantes."

    # Build a compact transcript for the summary prompt
    transcript_lines = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            label = "Utilizador" if role == "user" else "Assistente"
            # Truncate very long messages
            short_content = content[:300] + "..." if len(content) > 300 else content
            transcript_lines.append(f"{label}: {short_content}")

    transcript = "\n".join(transcript_lines)

    prompt = (
        "Resume esta conversa em 2-3 frases em Português de Portugal. "
        "Foca nos imóveis discutidos, decisões tomadas e próximos passos. "
        "Sê conciso e objetivo.\n\n"
        f"Conversa:\n{transcript}"
    )

    try:
        response = await openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        logger.exception("conversation_summary_generation_failed")
        return "Resumo indisponível."


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_euros(value: int | float) -> str:
    """Format a value as euros with thousands separator."""
    return f"{int(value):,}€".replace(",", ".")


def _fmt_euros_short(value: int | float) -> str:
    """Format a value as a short euro string (e.g. 180k€, 1.2M€)."""
    v = int(value)
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M€"
    if v >= 1_000:
        return f"{v // 1_000}k€"
    return f"{v}€"


def _fmt_range(min_val: int | float | None, max_val: int | float | None) -> str:
    """Format a cost range as '15.000€–25.000€'."""
    if min_val is not None and max_val is not None:
        return f"{_fmt_euros(min_val)}–{_fmt_euros(max_val)}"
    if min_val is not None:
        return f"a partir de {_fmt_euros(min_val)}"
    if max_val is not None:
        return f"até {_fmt_euros(max_val)}"
    return "valor não calculado"


def _fmt_range_short(min_val: int | float | None, max_val: int | float | None) -> str:
    """Format a cost range as '15-25k€'."""
    if min_val is not None and max_val is not None:
        min_k = min_val // 1000
        max_k = max_val // 1000
        if min_k == max_k:
            return f"{min_k}k€"
        return f"{min_k}-{max_k}k€"
    return _fmt_range(min_val, max_val)


def _condition_label(condition: str) -> str:
    """Convert a RoomCondition enum value to a Portuguese label."""
    mapping = {
        "excellent": "Excelente",
        "good": "Bom",
        "fair": "Razoável",
        "poor": "Mau",
        "needs_full_renovation": "Remodelação total",
    }
    return mapping.get(condition.lower(), condition.capitalize())


def _get_priority_rooms(room_estimates: list[dict], max_rooms: int = 3) -> str:
    """Extract top priority rooms (worst condition / highest cost) as a string."""
    if not room_estimates:
        return ""

    # Sort by condition severity (worst first) then by cost_max
    condition_order = {
        "needs_full_renovation": 0,
        "poor": 1,
        "fair": 2,
        "good": 3,
        "excellent": 4,
    }

    def sort_key(r: dict) -> tuple:
        cond = condition_order.get(r.get("condition", "").lower(), 5)
        cost = r.get("cost_max") or 0
        return (cond, -cost)

    sorted_rooms = sorted(room_estimates, key=sort_key)
    top_rooms = sorted_rooms[:max_rooms]

    parts = []
    for room in top_rooms:
        label = room.get("room_label") or room.get("room_type", "Divisão")
        condition = _condition_label(room.get("condition", ""))
        cost_min = room.get("cost_min")
        cost_max = room.get("cost_max")
        cost_str = _fmt_range_short(cost_min, cost_max)
        parts.append(f"{label} ({condition.lower()}, {cost_str})")

    return ", ".join(parts)
