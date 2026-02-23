"""
Async Supabase client for orchestrator DB operations.

Provides typed wrappers around the Supabase async client for all tables
used by the orchestrator agent: user_profiles, properties, portfolio_items,
room_features, analyses, conversations, messages, action_log.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from supabase._async.client import AsyncClient as AsyncSupabaseClient

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# user_profiles
# ---------------------------------------------------------------------------


async def get_user_profile(
    client: AsyncSupabaseClient, user_id: str
) -> dict | None:
    """Fetch full user profile row. Returns None if not found."""
    response = await client.table("user_profiles").select("*").eq("id", user_id).single().execute()
    return response.data


async def upsert_user_profile(
    client: AsyncSupabaseClient, user_id: str, updates: dict
) -> dict:
    """Insert or update user_profiles row. Always sets updated_at."""
    updates["id"] = user_id
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    response = (
        await client.table("user_profiles")
        .upsert(updates, on_conflict="id")
        .execute()
    )
    return response.data[0]


async def hydrate_user_context(
    client: AsyncSupabaseClient, user_id: str
) -> dict | None:
    """
    Fast context hydration query — loads the always-present tier in one round trip.

    Returns a dict with:
      profile_summary, display_name, region, sections_completed,
      fiscal_summary, budget_summary, renovation_summary,
      preferences_summary, goals_summary,
      portfolio (list of portfolio_item summaries),
      last_session_summary
    """
    # Load user profile
    profile = await get_user_profile(client, user_id)
    if profile is None:
        return None

    # Load active portfolio items (not archived)
    portfolio_response = (
        await client.table("portfolio_items")
        .select("id, property_id, nickname, index_summary, is_active, status")
        .eq("user_id", user_id)
        .neq("status", "archived")
        .execute()
    )
    portfolio = portfolio_response.data or []

    # Load last session summary
    last_session_response = (
        await client.table("conversations")
        .select("summary")
        .eq("user_id", user_id)
        .not_.is_("ended_at", "null")
        .order("ended_at", desc=True)
        .limit(1)
        .execute()
    )
    last_session = last_session_response.data
    last_session_summary = last_session[0]["summary"] if last_session else None

    return {
        "profile_summary": profile.get("profile_summary"),
        "display_name": profile.get("display_name"),
        "region": profile.get("region"),
        "sections_completed": profile.get("sections_completed", []),
        "fiscal_summary": profile.get("fiscal_summary"),
        "budget_summary": profile.get("budget_summary"),
        "renovation_summary": profile.get("renovation_summary"),
        "preferences_summary": profile.get("preferences_summary"),
        "goals_summary": profile.get("goals_summary"),
        "portfolio": portfolio,
        "last_session_summary": last_session_summary,
    }


# ---------------------------------------------------------------------------
# properties
# ---------------------------------------------------------------------------


async def get_property_by_idealista_id(
    client: AsyncSupabaseClient, idealista_id: str
) -> dict | None:
    """Look up a property by its Idealista listing ID."""
    response = (
        await client.table("properties")
        .select("*")
        .eq("idealista_id", idealista_id)
        .single()
        .execute()
    )
    return response.data


async def upsert_property(
    client: AsyncSupabaseClient, property_data: dict
) -> dict:
    """Insert or update a property row. Deduplicates on idealista_id."""
    property_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    response = (
        await client.table("properties")
        .upsert(property_data, on_conflict="idealista_id")
        .execute()
    )
    return response.data[0]


# ---------------------------------------------------------------------------
# portfolio_items
# ---------------------------------------------------------------------------


async def get_portfolio_item(
    client: AsyncSupabaseClient, user_id: str, property_id: str
) -> dict | None:
    """Get a specific portfolio item by user + property."""
    response = (
        await client.table("portfolio_items")
        .select("*")
        .eq("user_id", user_id)
        .eq("property_id", property_id)
        .single()
        .execute()
    )
    return response.data


async def create_portfolio_item(
    client: AsyncSupabaseClient,
    user_id: str,
    property_id: str,
    nickname: str | None = None,
    index_summary: str | None = None,
) -> dict:
    """Add a property to a user's portfolio."""
    data = {
        "user_id": user_id,
        "property_id": property_id,
        "nickname": nickname,
        "index_summary": index_summary,
        "status": "saved",
    }
    response = await client.table("portfolio_items").insert(data).execute()
    return response.data[0]


async def update_portfolio_item(
    client: AsyncSupabaseClient, item_id: str, updates: dict
) -> dict:
    """Update a portfolio item by its ID."""
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    response = (
        await client.table("portfolio_items")
        .update(updates)
        .eq("id", item_id)
        .execute()
    )
    return response.data[0]


async def set_active_portfolio_item(
    client: AsyncSupabaseClient, user_id: str, property_id: str
) -> None:
    """Set one portfolio item as active, deactivating all others for the user."""
    await (
        client.table("portfolio_items")
        .update({"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("user_id", user_id)
        .execute()
    )
    await (
        client.table("portfolio_items")
        .update({"is_active": True, "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("user_id", user_id)
        .eq("property_id", property_id)
        .execute()
    )


# ---------------------------------------------------------------------------
# analyses
# ---------------------------------------------------------------------------


async def get_latest_analysis(
    client: AsyncSupabaseClient,
    user_id: str,
    property_id: str,
    analysis_type: str = "renovation",
) -> dict | None:
    """Get the most recent analysis for a user+property combination."""
    response = (
        await client.table("analyses")
        .select("*")
        .eq("user_id", user_id)
        .eq("property_id", property_id)
        .eq("analysis_type", analysis_type)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    data = response.data
    return data[0] if data else None


async def create_analysis(
    client: AsyncSupabaseClient, analysis_data: dict
) -> dict:
    """Insert a new analysis record."""
    response = await client.table("analyses").insert(analysis_data).execute()
    return response.data[0]


async def update_analysis(
    client: AsyncSupabaseClient, analysis_id: str, updates: dict
) -> dict:
    """Update an existing analysis record."""
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    response = (
        await client.table("analyses")
        .update(updates)
        .eq("id", analysis_id)
        .execute()
    )
    return response.data[0]


# ---------------------------------------------------------------------------
# conversations
# ---------------------------------------------------------------------------


async def create_conversation(
    client: AsyncSupabaseClient, user_id: str
) -> dict:
    """Start a new conversation session."""
    data = {"user_id": user_id, "started_at": datetime.now(timezone.utc).isoformat()}
    response = await client.table("conversations").insert(data).execute()
    return response.data[0]


async def end_conversation(
    client: AsyncSupabaseClient,
    conversation_id: str,
    summary: str | None = None,
    message_count: int = 0,
) -> dict:
    """Mark a conversation as ended and store its summary."""
    updates: dict[str, Any] = {
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "message_count": message_count,
    }
    if summary:
        updates["summary"] = summary
    response = (
        await client.table("conversations")
        .update(updates)
        .eq("id", conversation_id)
        .execute()
    )
    return response.data[0]


async def increment_conversation_message_count(
    client: AsyncSupabaseClient, conversation_id: str
) -> None:
    """Increment the message counter for a conversation."""
    await client.rpc(
        "increment_conversation_message_count",
        {"conversation_id": conversation_id},
    ).execute()


# ---------------------------------------------------------------------------
# messages
# ---------------------------------------------------------------------------


async def save_message(
    client: AsyncSupabaseClient,
    conversation_id: str,
    role: str,
    content: str,
    tool_calls: list | None = None,
    tool_call_id: str | None = None,
) -> dict:
    """Persist a single message to the messages table."""
    data: dict[str, Any] = {
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
    }
    if tool_calls:
        data["tool_calls"] = tool_calls
    if tool_call_id:
        data["tool_call_id"] = tool_call_id
    response = await client.table("messages").insert(data).execute()
    return response.data[0]


async def get_conversation_messages(
    client: AsyncSupabaseClient, conversation_id: str
) -> list[dict]:
    """Load all messages for a conversation in chronological order."""
    response = (
        await client.table("messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .execute()
    )
    return response.data or []


# ---------------------------------------------------------------------------
# action_log
# ---------------------------------------------------------------------------


async def log_action(
    client: AsyncSupabaseClient,
    user_id: str,
    action_type: str,
    entity_type: str,
    entity_id: str | None = None,
    conversation_id: str | None = None,
    message_id: str | None = None,
    field_changed: str | None = None,
    old_value: Any = None,
    new_value: Any = None,
    trigger_message: str | None = None,
    confidence: float | None = None,
) -> dict:
    """Write an action to the audit log."""
    data: dict[str, Any] = {
        "user_id": user_id,
        "action_type": action_type,
        "entity_type": entity_type,
    }
    if entity_id:
        data["entity_id"] = entity_id
    if conversation_id:
        data["conversation_id"] = conversation_id
    if message_id:
        data["message_id"] = message_id
    if field_changed:
        data["field_changed"] = field_changed
    if old_value is not None:
        data["old_value"] = old_value
    if new_value is not None:
        data["new_value"] = new_value
    if trigger_message:
        data["trigger_message"] = trigger_message
    if confidence is not None:
        data["confidence"] = confidence
    response = await client.table("action_log").insert(data).execute()
    return response.data[0]


# ---------------------------------------------------------------------------
# room_features
# ---------------------------------------------------------------------------


async def get_room_features(
    client: AsyncSupabaseClient, property_id: str
) -> list[dict]:
    """Load all room features for a property."""
    response = (
        await client.table("room_features")
        .select("*")
        .eq("property_id", property_id)
        .execute()
    )
    return response.data or []


async def save_room_features(
    client: AsyncSupabaseClient, property_id: str, rooms: list[dict]
) -> list[dict]:
    """Bulk-insert room features for a property."""
    for room in rooms:
        room["property_id"] = property_id
    response = await client.table("room_features").insert(rooms).execute()
    return response.data or []


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())
