# Orchestrator Chat Agent

## Goal

Build a conversational AI agent that serves as the primary interface for Rehabify users. Instead of navigating UI forms and buttons, users interact through a chat interface where the agent **detects intent**, **executes actions silently**, **manages persistent context across sessions**, and **delegates to existing pipelines** (renovation analysis, cost calculation).

The agent replaces a traditional dashboard with a single conversational entry point — the user says what they need, and the system figures out the rest.

---

## Scope

- [x] Orchestrator state schema (`agents/state.py`) — TypedDict-based shared state for LangGraph
- [x] Knowledge base virtual file system (`agents/context.py`) — load/offload/demote pattern
- [x] System prompt in Portuguese with English section headers (`agents/prompts.py`)
- [x] Template-based and LLM-based summary generation (`agents/summaries.py`)
- [x] 11 agent tools with LangGraph Command pattern (`agents/tools.py`)
- [x] LangGraph orchestrator pipeline with 5 nodes (`agents/orchestrator.py`)
- [x] Knowledge store hydration from Supabase (`services/knowledge_store.py`)
- [x] Async Supabase client with typed wrappers (`services/supabase_client.py`)
- [x] SSE-streaming chat API endpoint (`api/v1/chat.py`)
- [x] Database migration for orchestrator schema (8 tables with RLS)
- [x] Orchestrator config section in `config.py`
- [x] Constants for DIY skills, profile sections, portfolio statuses, analysis types
- [x] Startup wiring in `main.py` (graph compilation + Supabase client)
- [x] Unit tests: state, context, summaries, tools (6 test files)
- [x] Integration tests: graph compilation, routing, reflect node, chat API endpoint

---

## Architecture

### Graph Topology

```
START
  │
  ▼
hydrate_context ──► agent ◄──► tools ──► reflect
                      │                     │
                      │                     └──► agent (loop back)
                      ▼
                 post_process
                      │
                      ▼
                     END
```

**Nodes:**

| Node | Type | Purpose |
|------|------|---------|
| `hydrate_context` | Async, DB | Loads user context + knowledge base from Supabase. Creates conversation row. Injects system prompt + initial context block. |
| `agent` | Async, LLM | GPT-4o ReAct node. Bound with 11 tools. Decides to call tools or produce a final response. |
| `tools` | LangGraph ToolNode | Executes tool calls. Tools return `Command` objects that update state directly. |
| `reflect` | Sync, pure | Rebuilds the context system message after each tool execution. Zero LLM calls. Replaces previous context block. |
| `post_process` | Async, DB | Persists messages to Supabase. Demotes stale knowledge entries. Resets execution metadata. |

**Routing:**

- `agent → tools` if the last message contains `tool_calls`
- `agent → post_process` if the last message is a final text response
- `tools → reflect → agent` (always loops back for the next ReAct step)
- `post_process → END`

### State Schema

The `OrchestratorState` is a single TypedDict that flows through all nodes:

```python
class OrchestratorState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # LangGraph message reducer
    user_id: str
    conversation_id: str
    knowledge: dict[str, KnowledgeEntry]   # Virtual file system
    todos: list[TodoItem]                  # Multi-step task tracker
    current_focus: dict | None             # Active property + topic
    executed_actions: list[dict]           # Actions in current turn
    stream_events: list[dict]             # SSE events for frontend
```

Key design choice: `messages` uses LangGraph's `add_messages` reducer, which **accumulates** messages across turns rather than replacing them. All other fields use the default **replace** strategy.

### Knowledge Base (Virtual File System)

The knowledge base is the agent's working memory. It uses path-style keys and a two-tier loading strategy:

**Always-present (loaded into context on every turn):**
- `user/profile` — master profile summary
- `portfolio/index` — one-liner per portfolio item
- `portfolio/{id}/resumo` — active property's analysis summary
- `session/resumo_anterior` — last conversation session summary

**Available (summary only, content loaded on demand):**
- `user/fiscal`, `user/budget`, `user/renovation`, `user/preferences`, `user/goals`
- `portfolio/{id}/resumo` for non-active properties
- `portfolio/{id}/analise` — detailed analysis (loaded when user drills down)

**Entry structure:**

```python
class KnowledgeEntry(TypedDict):
    summary: str           # Always shown in the system message index
    content: str | None    # None = not loaded, str = full/partial content
    lines_loaded: int      # How many lines are currently loaded
    total_lines: int       # Total lines available
    source: str            # "supabase" | "tool" | "pipeline"
```

**Why this design:**
- The LLM sees an index of all available data without paying the token cost of loading everything
- The agent can `read_context` to load entries on demand when summaries are insufficient
- The `reflect` node rebuilds the context block after each tool call, so the agent always sees the latest state
- `demote_stale_entries` automatically offloads entries that weren't referenced in the current turn, preventing context bloat

**Context block injected as a SystemMessage:**

```
## Estado Atual

### Base de Conhecimento
  user/profile [carregado] — João Silva | Lisboa | 3/5 secções completas
  user/fiscal [disponível] — IRS | 1ª habitação
  user/budget [disponível] — Orçamento: 150.000€–250.000€
  portfolio/index [carregado] — 2 imóvel(is) no portfólio
  portfolio/abc-123/resumo [carregado] — T2 Alfama, 180k€, reno 15-25k€

### Tarefas
  ☐ [a1b2c3d4] Analisar imóvel de Graça

### Foco Atual
  Imóvel: abc-123 | Tópico: renovação | Nível: 0
```

The context block is identified by `name="context_refresh"` and **replaced** (not accumulated) on every reflect pass.

---

## Tools

11 tools organized into 5 categories, all using LangGraph's `Command` pattern with `InjectedState`:

### Context Navigation

| Tool | Purpose | State Updates |
|------|---------|--------------|
| `read_context` | Load content from knowledge base. Supports partial reads via `start_line`/`num_lines`. | `knowledge` (entry → loaded) |
| `write_context` | Store derived information, notes, or sub-agent results. | `knowledge` (new/updated entry) |
| `remove_context` | Remove irrelevant entries from knowledge base. | `knowledge` (entry removed) |

### Task Management

| Tool | Purpose | State Updates |
|------|---------|--------------|
| `manage_todos` | Add, complete, or list tasks for multi-step requests. Actions: `add`, `complete`, `list`. | `todos` |

### User Profile

| Tool | Purpose | State Updates |
|------|---------|--------------|
| `update_user_profile` | Update a profile section (fiscal, budget, renovation, preferences, goals). Persists to Supabase. Regenerates section + master summaries. | `knowledge` (profile entries updated) |

### Portfolio Management

| Tool | Purpose | State Updates |
|------|---------|--------------|
| `save_to_portfolio` | Add a property to the user's portfolio. Generates index summary. | `knowledge` (portfolio/index updated) |
| `remove_from_portfolio` | Archive a portfolio item (soft delete). Requires confirmation. | `knowledge` (property entries removed) |
| `switch_active_property` | Change the focused property. Loads new property's analysis. | `current_focus`, `knowledge` |
| `search_portfolio` | Resolve natural language references ("o de Alfama", "o mais barato") to property IDs via keyword matching. | None (read-only) |

### Analysis

| Tool | Purpose | State Updates |
|------|---------|--------------|
| `trigger_property_analysis` | Run the full renovation pipeline (scrape → classify → estimate) for an Idealista URL. Persists property + analysis + portfolio item to Supabase. | `knowledge`, `current_focus`, `stream_events` |
| `recalculate_costs` | Recalculate costs using cached room features + updated preferences. No GPT re-run. | `knowledge` |

### Command Pattern

All tools return `Command` objects rather than plain strings. This allows tools to **directly update graph state** alongside their response:

```python
def _ok(tool_call_id: str, msg: str, state_updates: dict) -> Command:
    return Command(
        update={
            **state_updates,
            "messages": [ToolMessage(content=msg, tool_call_id=tool_call_id)],
        }
    )
```

External services (Supabase client, renovation graph) are injected via `RunnableConfig.configurable` at invocation time, not imported globally. This enables clean testing and decoupled architecture.

---

## System Prompt Design

The prompt (`agents/prompts.py`) is in Portuguese (Portugal) and encodes 6 core behaviors:

1. **Progressive disclosure** — Summarize first, offer detail on request. "Posso detalhar a cozinha se quiseres."
2. **Action detection** — Implicit actions (budget updates) execute silently; ambiguous actions prompt confirmation; destructive actions always require explicit consent.
3. **Natural acknowledgment** — Weave actions into conversational response, never "Atualizei o teu perfil."
4. **Knowledge base discipline** — Use summaries when sufficient; only `read_context` when details are needed. Never mention "base de conhecimento" to the user.
5. **Info collection** — One question per turn, only when contextually relevant. Conversational, not form-like.
6. **Property resolution** — Use `search_portfolio` for natural references ("o de Alfama").

### Formatting Rules
- Monetary values: `180.000€` (thousands separator), not `180000€`
- Cost ranges: `15.000€–25.000€`
- Compact analysis format: `Preço: 180.000€ | Área: 65m² | €/m²: 2.769€`

---

## Summary Generation

Two approaches:

### Template-Based (Deterministic)

No LLM cost. Used for:

| Summary Type | Format | Example |
|-------------|--------|---------|
| Analysis chat summary | Multi-line scannable | `Preço: 180.000€ | Área: 65m² | €/m²: 2.769€` |
| Analysis detail summary | Chat summary + per-room breakdown | Includes all rooms with condition, cost range, top issues |
| Portfolio index line | One-liner | `T2 Alfama, 180k€, reno 15-25k€` |
| Profile section summary | Short descriptive | `IRS | 1ª habitação` |
| Master profile summary | Compact identity | `João Silva | Lisboa | 3/5 secções completas` |

### LLM-Based (GPT-4o-mini)

Used only for **conversation session summaries** — a 2-3 sentence narrative for context carry-over between sessions. Called at conversation end, stored in `conversations.summary`.

```
Discutimos o T2 de Alfama. Detalhámos cozinha (mau estado).
Indeciso entre Alfama e Graça. Próximo: comparação formal.
```

---

## Chat API Endpoint

**`POST /api/v1/chat`** — Streams via Server-Sent Events (SSE).

### Request

```json
{
  "message": "Analisa este imóvel: https://www.idealista.pt/imovel/12345/",
  "conversation_id": "conv-uuid-optional"
}
```

### SSE Event Types

| Type | When | Payload |
|------|------|---------|
| `thinking` | Agent is processing | `{"type": "thinking", "message": "A processar..."}` |
| `tool_call` | A tool is being executed | `{"type": "tool_call", "tool": "trigger_property_analysis", "args": {...}}` |
| `action` | A mutation was performed | `{"type": "action", "action_type": "...", "summary": "..."}` |
| `message` | Streamed response text | `{"type": "message", "content": "...", "done": false/true}` |
| `todo_update` | Task list changed | `{"type": "todo_update", "todos": [...]}` |
| `error` | An error occurred | `{"type": "error", "message": "..."}` |

### Auth

Protected by `CurrentUser` dependency (Supabase JWT). Returns 401 without valid token.

### SSE Streaming Implementation

The endpoint uses `graph.astream()` to stream LangGraph chunks. Each chunk is a `{node_name: state_update}` dict. The generator:

1. Yields an immediate `thinking` event for UI responsiveness
2. Iterates over graph stream chunks
3. Extracts `stream_events`, `todos`, and `tool_calls` from each chunk
4. Deduplicates events using a `sent_events` set (indexed by position)

---

## Supabase Client (`services/supabase_client.py`)

Typed async wrappers around the Supabase client for all orchestrator tables:

| Table | Operations |
|-------|-----------|
| `user_profiles` | `get_user_profile`, `upsert_user_profile`, `hydrate_user_context` |
| `properties` | `get_property_by_idealista_id`, `upsert_property` |
| `portfolio_items` | `get_portfolio_item`, `create_portfolio_item`, `update_portfolio_item`, `set_active_portfolio_item` |
| `analyses` | `get_latest_analysis`, `create_analysis`, `update_analysis` |
| `conversations` | `create_conversation`, `end_conversation`, `increment_conversation_message_count` |
| `messages` | `save_message`, `get_conversation_messages` |
| `action_log` | `log_action` (full audit trail with old/new values) |
| `room_features` | `get_room_features`, `save_room_features` |

### Context Hydration

`hydrate_user_context()` performs a fast multi-query hydration in ~3 round trips:
1. Load user profile (full row)
2. Load active portfolio items (not archived)
3. Load last session summary (most recent ended conversation)

Returns a flat dict with all always-present tier data.

---

## Knowledge Store (`services/knowledge_store.py`)

`build_knowledge_base()` transforms the hydrated Supabase data into the `dict[str, KnowledgeEntry]` format:

- **Always-present entries** get `content` populated (loaded immediately)
- **Available entries** get `content=None` (loaded on demand via `read_context`)
- Active property's analysis is loaded eagerly; non-active properties are available-only
- Empty states produce sensible defaults ("Portfólio vazio", "Perfil não configurado")

---

## Database Schema

The migration creates 8 tables with Row-Level Security (RLS):

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `user_profiles` | User identity + profile sections (JSONB) | `id` (= auth.uid), `fiscal`, `budget`, `renovation`, `preferences`, `goals`, `*_summary` |
| `properties` | Scraped property data | `idealista_id`, `url`, `price`, `area_m2`, `location`, `image_urls`, `raw_scraped_data` |
| `portfolio_items` | User ↔ Property junction | `user_id`, `property_id`, `nickname`, `status`, `is_active`, `index_summary` |
| `room_features` | Cached feature extraction results per room | `property_id`, `room_type`, `room_index`, `features` (JSONB) |
| `analyses` | Analysis results + summaries | `user_id`, `property_id`, `analysis_type`, `result_data` (JSONB), `chat_summary`, `status` |
| `conversations` | Session tracking | `user_id`, `started_at`, `ended_at`, `summary`, `message_count` |
| `messages` | Full message log | `conversation_id`, `role`, `content`, `tool_calls` (JSONB) |
| `action_log` | Audit trail for all mutations | `user_id`, `action_type`, `entity_type`, `field_changed`, `old_value`, `new_value`, `trigger_message`, `confidence` |

### RLS Policy

All tables enforce `auth.uid() = user_id` for SELECT, INSERT, UPDATE, and DELETE. Properties table uses a portfolio-based policy: users can only see properties linked to their portfolio items.

### Key Indexes

- `portfolio_items(user_id, status)` — portfolio listing
- `analyses(user_id, property_id, analysis_type)` — latest analysis lookup
- `messages(conversation_id, created_at)` — chronological message retrieval
- `action_log(user_id, created_at)` — audit trail queries
- `properties(idealista_id)` — deduplication on scrape

---

## Configuration

New `OrchestratorConfig` section in `config.py`:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `model` | `gpt-4o` | LLM for the agent node |
| `session_timeout_minutes` | `30` | Inactivity threshold for session end |
| `context_budget_tokens` | `4000` | Max tokens before auto-demoting knowledge entries |
| `min_lines_for_partial_read` | `20` | Below this, always load full content |
| `summary_model` | `gpt-4o-mini` | Model for conversation summaries (cheaper) |
| `summary_trigger_message_count` | `20` | Messages before generating async session summary |

All env-overridable via `ORCHESTRATOR__KEY` format (e.g., `ORCHESTRATOR__MODEL=gpt-4o-mini`).

---

## Decisions Log

### 1. LangGraph over plain async chains

**Choice:** LangGraph StateGraph with compiled graph, not raw async function chains.

**Why:** The agent loop (reason → tool → reflect → reason) maps naturally to a state graph. LangGraph gives us: automatic message accumulation, conditional routing, tool execution via ToolNode, and future checkpointing for persistence. The reflect node (pure state transformation, no LLM) would be awkward as middleware in a chain.

### 2. Knowledge base as virtual file system (not RAG)

**Choice:** Path-keyed dict with load/offload semantics instead of vector search.

**Why:** The data is structured and finite (user profile, portfolio items, analyses). Vector search adds latency and complexity for data the agent can navigate deterministically. The virtual file system pattern gives the agent IDE-like browsing: see all available files in the index, load what it needs, auto-offload what it doesn't reference. This keeps context tight and predictable.

### 3. Command pattern for tools (not string returns)

**Choice:** Tools return `Command` objects with state updates, not plain strings.

**Why:** Every tool that mutates data needs to update both the database AND the graph state. With plain string returns, the agent would need to reason about state updates after each tool call. With Commands, tools directly specify their state effects — the graph applies them atomically. This is cleaner and prevents state drift.

### 4. Reflect node (not inline context rebuild)

**Choice:** Dedicated `reflect` node that runs after every tool execution.

**Why:** After each tool call, the knowledge base may have changed (new entries loaded, entries removed, summaries regenerated). The agent needs to see the updated context before making its next decision. A dedicated reflect node keeps this concern isolated and makes the update cycle explicit: `agent → tools → reflect → agent`.

### 5. Template-based summaries over LLM for structured data

**Choice:** Deterministic Python templates for analysis/portfolio/profile summaries; LLM only for conversation summaries.

**Why:** Analysis summaries follow a fixed format (`Preço: X | Área: Y | €/m²: Z`). Using GPT for this adds cost, latency, and unpredictability. Template-based summaries are instant, free, and always consistent. LLM summaries are reserved for the one truly unstructured task: summarizing a conversation into 2-3 narrative sentences.

### 6. SSE over WebSockets for streaming

**Choice:** Server-Sent Events via `sse-starlette`, not WebSockets.

**Why:** The chat pattern is request-response with streamed replies — the client sends a message, the server streams back events. SSE is simpler than WebSockets for this pattern: no connection management, no heartbeats, automatic reconnection, works through proxies and CDNs. WebSockets would be needed if we wanted bidirectional streaming or server-initiated messages, which we don't currently need.

### 7. RunnableConfig for dependency injection

**Choice:** Pass Supabase client and renovation graph via `config["configurable"]` at invocation time.

**Why:** Tools need access to external services but shouldn't import them globally. LangGraph's `RunnableConfig` provides a clean injection mechanism: the API endpoint assembles the config with the authenticated Supabase client and compiled renovation graph, then passes it to `graph.astream()`. Tools extract what they need via helper functions (`_get_supabase`, `_get_renovation_graph`). This makes tools testable in isolation.

### 8. Soft delete for portfolio items

**Choice:** Portfolio removal sets `status = "archived"` instead of deleting the row.

**Why:** Users might want to restore removed properties. The action log records the removal, but having the row preserved makes restoration trivial. Queries filter with `.neq("status", "archived")` so archived items are invisible in normal use.

### 9. Action log as audit trail

**Choice:** Every mutation (profile update, portfolio add/remove, analysis trigger, cost recalculation) is logged to `action_log` with old/new values.

**Why:** When the agent silently updates a user's profile based on conversational intent, the user should be able to see what changed and when. The action log enables: undo functionality, audit display in the UI, and debugging implicit action detection. Each entry captures `field_changed`, `old_value`, `new_value`, `trigger_message`, and `confidence`.

### 10. Deduplication on `sent_events` set

**Choice:** The SSE generator tracks sent events by index to avoid duplicate delivery.

**Why:** LangGraph's `astream()` yields full node outputs, which may include previously accumulated `stream_events`. Without deduplication, the same event would be sent multiple times. The `sent_events: set[int]` tracks which indices have been yielded.

---

## Files Changed

### New Files (15)

| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/agents/__init__.py` | 7 | Package docstring |
| `backend/app/agents/state.py` | 63 | OrchestratorState, KnowledgeEntry, TodoItem TypedDicts |
| `backend/app/agents/context.py` | 182 | Knowledge base CRUD + context block builder |
| `backend/app/agents/prompts.py` | 95 | System prompt (Portuguese) |
| `backend/app/agents/summaries.py` | 358 | Template-based + LLM-based summary generation |
| `backend/app/agents/tools.py` | 846 | 11 orchestrator tools with Command pattern |
| `backend/app/agents/orchestrator.py` | 283 | LangGraph pipeline (5 nodes, routing, compilation) |
| `backend/app/api/v1/chat.py` | 185 | SSE-streaming chat endpoint |
| `backend/app/services/knowledge_store.py` | 187 | Knowledge base hydration from Supabase |
| `backend/app/services/supabase_client.py` | 417 | Async Supabase client wrappers |
| `backend/tests/unit/test_orchestrator_state.py` | 102 | State TypedDict tests |
| `backend/tests/unit/test_knowledge_store.py` | 229 | Context CRUD + demote tests |
| `backend/tests/unit/test_summaries.py` | 166 | Summary generation tests |
| `backend/tests/unit/test_orchestrator_tools.py` | 156 | Tool registry + helper tests |
| `backend/tests/integration/test_orchestrator_graph.py` | 195 | Graph compilation, routing, reflect tests |
| `backend/tests/integration/test_chat_api.py` | 89 | Chat endpoint HTTP tests |

### Modified Files (4)

| File | Changes |
|------|---------|
| `backend/app/config.py` | Added `OrchestratorConfig` nested model + `orchestrator` field on Settings |
| `backend/app/constants.py` | Added `DIY_SKILL_CATEGORIES`, `PROFILE_SECTIONS`, `PORTFOLIO_STATUS_VALUES`, `ANALYSIS_TYPES` |
| `backend/app/main.py` | Added orchestrator graph compilation in lifespan + chat router registration + Supabase client init |
| `.gitignore` | Added `.worktrees` |

---

## Test Coverage

| Test File | Tests | Covers |
|-----------|-------|--------|
| `test_orchestrator_state.py` | 8 | KnowledgeEntry creation (loaded/available), TodoItem statuses, OrchestratorState with knowledge/focus |
| `test_knowledge_store.py` | 17 | load/offload/write/remove entries, demote stale entries (protected vs unprotected), render helpers (index/todos/focus), build_context_block |
| `test_summaries.py` | 15 | Euro formatting (thousands, short, range), condition labels, analysis chat summary (full/minimal/priority rooms), portfolio index line, profile section summaries, master profile |
| `test_orchestrator_tools.py` | 12 | Tool registry (11 tools), Command helpers (_ok/_err), manage_todos logic (add/complete/preserve), tool schema verification, description quality |
| `test_orchestrator_graph.py` | 10 | Graph compilation, should_continue routing (tools/post_process/empty), reflect node (add/replace/preserve context), build_context_block sections |
| `test_chat_api.py` | 7 | Health endpoint, auth protection (no token/invalid token), request validation (missing message, optional conversation_id), OpenAPI schema registration |

**Total: 69 tests**

---

## Data Flow Example

User sends: _"Analisa este imóvel: https://www.idealista.pt/imovel/12345/"_

```
1. POST /api/v1/chat
   ├── Auth: JWT → user_id
   ├── Build initial state with HumanMessage
   └── graph.astream(state, config)

2. hydrate_context
   ├── Load user profile, portfolio, last session from Supabase
   ├── Build knowledge dict (always-present + available entries)
   ├── Create conversation row
   └── Inject system prompt + context block

3. agent (turn 1)
   ├── GPT-4o sees: system prompt + context + user message
   └── Decides: call trigger_property_analysis(url="https://...")

4. tools
   ├── trigger_property_analysis executes:
   │   ├── Runs renovation pipeline (scrape → classify → estimate)
   │   ├── Generates chat_summary + index_line
   │   ├── Persists property + portfolio_item + analysis to Supabase
   │   ├── Logs action to action_log
   │   └── Returns Command with updated knowledge + current_focus
   └── ToolNode applies Command to state

5. reflect
   ├── Rebuilds context block with new knowledge entries
   └── Replaces previous context_refresh SystemMessage

6. agent (turn 2)
   ├── GPT-4o sees: updated context (new property in knowledge base)
   └── Produces final response with analysis summary

7. post_process
   ├── Persists user + assistant messages to Supabase
   ├── Demotes stale knowledge entries
   └── Resets executed_actions

8. SSE stream delivers: thinking → tool_call → message (done=true)
```

---

## Future Improvements

### Short-term

- **LangGraph checkpointing** — Persist graph state between API calls so multi-turn conversations share accumulated state (messages, knowledge). Currently each request starts with a fresh knowledge hydration.
- **Token budget enforcement** — The `context_budget_tokens` config exists but isn't actively enforced. Implement automatic demoting/summarizing when the context block exceeds the budget.
- **Conversation session end detection** — Use `session_timeout_minutes` to detect when a session has ended and trigger the LLM-based conversation summary automatically.
- **`summary_trigger_message_count`** — Wire up the async conversation summary generation when the message count threshold is reached.
- **SSE token-level streaming** — Currently streams at the node level. Implement token-by-token streaming from the LLM for a more responsive chat experience (LangGraph `astream_events`).

### Medium-term

- **Comparison tool** — `compare_properties` tool that generates side-by-side analysis of 2-3 portfolio items. Template-based comparison tables.
- **Fiscal analysis tool** — `calculate_taxes` tool integrating IMT + Stamp Duty calculator with the user's fiscal profile. Already planned as an analysis type.
- **Proactive suggestions** — After a property analysis, the agent could proactively suggest: "This property is within your budget. Want me to calculate the total cost including taxes?"
- **Memory across sessions** — Currently only carries a 2-3 sentence summary. Could carry structured memory (decisions made, properties rejected with reasons, open questions).
- **WebSocket upgrade** — If we need server-initiated messages (price alerts, analysis completion notifications), upgrade from SSE to WebSocket.
- **Search portfolio with embeddings** — Replace keyword matching in `search_portfolio` with semantic vector search for better natural language resolution.

### Long-term

- **Multi-agent delegation** — The orchestrator could delegate to specialized sub-agents (fiscal advisor, renovation expert, market analyst) instead of handling everything in one ReAct loop.
- **Human-in-the-loop for high-stakes actions** — Before submitting a property offer or committing to a renovation plan, require explicit user approval through a structured UI flow (not just chat confirmation).
- **Offline property monitoring** — Background agents that monitor portfolio properties for price changes, new comparable listings, or market shifts. Notify users via the chat on their next session.
- **PDF report generation** — Generate a comprehensive property analysis PDF from the knowledge base data, suitable for sharing with banks, contractors, or family.
