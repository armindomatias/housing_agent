"""
Shared helper for persisting a completed renovation analysis to Supabase.

Used by both the analyze endpoint (POST /api/v1/analyze) and the
trigger_property_analysis orchestrator tool so the DB logic lives in one place.
"""

import re

import structlog

from app.agents.summaries import generate_analysis_chat_summary, generate_portfolio_index_line
from app.services import supabase_client as db

logger = structlog.get_logger(__name__)


async def persist_analysis_to_db(
    supabase: object,
    url: str,
    user_id: str,
    estimate_dict: dict,
    conversation_id: str | None = None,
) -> str | None:
    """
    Persist a completed renovation analysis to Supabase.

    Args:
        supabase: Async Supabase client instance.
        url: Idealista property URL.
        user_id: Authenticated user ID.
        estimate_dict: Serialized RenovationEstimate dict (result of model_dump()).
        conversation_id: Optional chat conversation ID for audit log.

    Returns:
        The property_id (UUID string) on success, None on failure.
    """
    try:
        prop_data = estimate_dict.get("property_data") or {}

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

        _id_match = re.search(r"/imovel/(\d+)", url)
        prop_db_data = {
            "url": url,
            "idealista_id": _id_match.group(1) if _id_match else None,
            "title": prop_data.get("title"),
            "price": int(prop_data.get("price") or 0) or None,
            "area_m2": prop_data.get("area_m2"),
            "num_rooms": prop_data.get("num_rooms"),
            "num_bathrooms": prop_data.get("num_bathrooms"),
            "location": prop_data.get("location"),
            "description": prop_data.get("description"),
            "image_urls": prop_data.get("image_urls"),
            "raw_scraped_data": prop_data,
            "price_per_m2": prop_data.get("price_per_m2"),
        }

        saved_prop = await db.upsert_property(supabase, prop_db_data)
        property_id = saved_prop["id"]

        portfolio_item = await db.create_portfolio_item(
            supabase, user_id, property_id, index_summary=index_line
        )
        await db.update_portfolio_item(
            supabase, portfolio_item["id"], {"status": "analyzed"}
        )

        await db.create_analysis(supabase, {
            "user_id": user_id,
            "property_id": property_id,
            "portfolio_item_id": portfolio_item["id"],
            "analysis_type": "renovation",
            "result_data": estimate_dict,
            "chat_summary": chat_summary,
            "status": "completed",
        })

        room_analyses = estimate_dict.get("room_analyses") or []
        room_features_data = [
            {
                "room_type": r.get("room_type"),
                "room_number": r.get("room_number", i + 1),
                "room_label": r.get("room_label"),
                "features": r.get("features"),
                "images": r.get("images"),
                "extraction_model": r.get("extraction_model"),
            }
            for i, r in enumerate(room_analyses)
            if r.get("features") is not None
        ]
        if room_features_data:
            await db.save_room_features(supabase, property_id, room_features_data)

        await db.log_action(
            supabase, user_id, "analysis_trigger", "analysis",
            entity_id=property_id,
            conversation_id=conversation_id,
            new_value={"url": url, "chat_summary": chat_summary},
        )

        logger.info("analyze_endpoint_db_persist_success", url=url, property_id=property_id)
        return property_id

    except Exception:
        logger.exception("analysis_db_persist_failed", url=url)
        return None
