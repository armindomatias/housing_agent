"""
Chat API endpoint.

Provides a conversational interface to the orchestrator agent.
Streams responses via Server-Sent Events (SSE).

Endpoint:
    POST /api/v1/chat

Request body:
    { "message": string, "conversation_id": string | null }

SSE event types:
    {"type": "thinking", "message": "..."}
    {"type": "tool_call", "tool": "...", "args": {...}}
    {"type": "action", "action_type": "...", "summary": "..."}
    {"type": "message", "content": "...", "done": false}
    {"type": "message", "content": "", "done": true}
    {"type": "todo_update", "todos": [...]}
    {"type": "error", "message": "..."}
"""

import json
from typing import AsyncGenerator

import structlog
from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.auth import CurrentUser
from app.config import get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""

    message: str
    conversation_id: str | None = None


async def stream_chat(
    message: str,
    user_id: str,
    conversation_id: str | None,
    request: Request,
) -> AsyncGenerator[str, None]:
    """
    Generator that streams orchestrator agent events as SSE.

    Invokes the orchestrator graph with the user message and
    yields each stream event as a JSON string.
    """
    settings = get_settings()
    graph = getattr(request.app.state, "orchestrator_graph", None)
    supabase = getattr(request.app.state, "supabase", None)

    if graph is None:
        yield json.dumps({"type": "error", "message": "Agente não disponível."})
        return

    # Build initial state for this turn
    initial_state = {
        "messages": [HumanMessage(content=message)],
        "user_id": user_id,
        "conversation_id": conversation_id or "",
        "knowledge": {},
        "todos": [],
        "current_focus": None,
        "executed_actions": [],
        "stream_events": [],
    }

    # Config injected into every node via config["configurable"]
    run_config = {
        "configurable": {
            "supabase": supabase,
            "openai_api_key": settings.openai_api_key,
            "orchestrator_model": settings.orchestrator.model,
            "renovation_graph": getattr(request.app.state, "graph", None),
        }
    }

    sent_events: set[int] = set()
    sent_event_count = 0

    try:
        # Yield an immediate "thinking" event so the UI shows activity
        yield json.dumps({"type": "thinking", "message": "A processar..."})

        async for chunk in graph.astream(initial_state, config=run_config):
            # chunk is {node_name: state_update}
            if not isinstance(chunk, dict):
                continue

            node_state = next(iter(chunk.values()), {})
            if not isinstance(node_state, dict):
                continue

            # Stream SSE events from state
            events = node_state.get("stream_events") or []
            for i, event in enumerate(events):
                if i not in sent_events:
                    sent_events.add(i)
                    sent_event_count += 1
                    if isinstance(event, dict):
                        yield json.dumps(event, ensure_ascii=False)

            # Stream todo updates when todos change
            todos = node_state.get("todos")
            if todos is not None:
                yield json.dumps({"type": "todo_update", "todos": todos})

            # Stream tool call notifications
            messages = node_state.get("messages") or []
            for msg in messages:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                        tool_args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                        yield json.dumps({
                            "type": "tool_call",
                            "tool": tool_name,
                            "args": tool_args,
                        }, ensure_ascii=False)

    except Exception as e:
        logger.exception("stream_chat_error", user_id=user_id)
        yield json.dumps({"type": "error", "message": f"Erro inesperado: {str(e)}"})


@router.post("", response_class=EventSourceResponse)
async def chat_stream(
    body: ChatRequest,
    request: Request,
    user: CurrentUser,
) -> EventSourceResponse:
    """
    Conversational interface to the Rehabify orchestrator agent.

    Streams the agent's response via Server-Sent Events. Each event is a
    JSON object with a `type` field.

    Event types:
    - **thinking**: Agent is processing (show loading indicator)
    - **tool_call**: A tool is being executed (optional display)
    - **action**: A mutation was performed (profile update, portfolio change)
    - **message**: Streamed response text token or final response
    - **todo_update**: Task list changed
    - **error**: An error occurred

    Example usage with curl:
    ```
    curl -N -X POST http://localhost:8000/api/v1/chat \\
      -H "Content-Type: application/json" \\
      -H "Authorization: Bearer <token>" \\
      -d '{"message": "Analisa este imóvel: https://www.idealista.pt/imovel/12345/"}'
    ```
    """
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=422, detail="Mensagem não pode estar vazia.")

    structlog.contextvars.bind_contextvars(user_id=user.id, message_preview=body.message[:50])

    return EventSourceResponse(
        stream_chat(
            message=body.message.strip(),
            user_id=user.id,
            conversation_id=body.conversation_id,
            request=request,
        ),
        media_type="text/event-stream",
    )


@router.get("/health")
async def health_check() -> dict:
    """Health check for the chat service."""
    return {"status": "healthy", "service": "rehabify-chat"}
