-- Rehabify Orchestrator Schema
-- Migration 001: Core tables for conversational agent, user profiles, portfolio, and analysis
--
-- Fast context hydration query (for reference - use in knowledge_store.py):
--
-- SELECT
--   up.profile_summary, up.display_name, up.region,
--   up.sections_completed,
--   up.fiscal_summary, up.budget_summary, up.renovation_summary,
--   up.preferences_summary, up.goals_summary,
--   json_agg(DISTINCT jsonb_build_object(
--     'id', pi.id, 'property_id', pi.property_id,
--     'nickname', pi.nickname, 'index_summary', pi.index_summary,
--     'is_active', pi.is_active, 'status', pi.status
--   )) FILTER (WHERE pi.id IS NOT NULL) AS portfolio,
--   (SELECT c.summary FROM conversations c
--    WHERE c.user_id = $1 AND c.ended_at IS NOT NULL
--    ORDER BY c.ended_at DESC LIMIT 1) AS last_session_summary
-- FROM user_profiles up
-- LEFT JOIN portfolio_items pi ON pi.user_id = up.id AND pi.status != 'archived'
-- WHERE up.id = $1
-- GROUP BY up.id;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- ============================================================
-- user_profiles
-- User context collected conversationally over time.
-- ============================================================
CREATE TABLE IF NOT EXISTS user_profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,

  -- Identity (always loaded, flat for indexing)
  display_name TEXT,
  region TEXT,

  -- Sectioned data (JSONB for flexibility)
  fiscal JSONB DEFAULT '{}',
  -- fiscal keys: tax_regime, marital_status, dependents, first_time_buyer, income_bracket, current_property
  fiscal_summary TEXT,

  budget JSONB DEFAULT '{}',
  -- budget keys: budget_min, budget_max, financing_type, mortgage_preapproval, property_purpose, investment_horizon, rental_yield_target
  budget_summary TEXT,

  renovation JSONB DEFAULT '{}',
  -- renovation keys: diy_skills[], finish_level, renovation_budget_ceiling, has_contractor, time_availability
  renovation_summary TEXT,

  preferences JSONB DEFAULT '{}',
  -- preferences keys: preferred_locations[], min_area, max_area, min_rooms, must_haves[], deal_breakers[]
  preferences_summary TEXT,

  goals JSONB DEFAULT '{}',
  -- goals keys: buying_reason, timeline, risk_tolerance, experience_level, open_notes
  goals_summary TEXT,

  -- Master compact summary (for always-present tier)
  profile_summary TEXT,

  -- Completeness tracking
  sections_completed TEXT[] DEFAULT '{}',

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_id ON user_profiles(id);


-- ============================================================
-- properties
-- Scraped Idealista data. Shared across users (deduplicated by idealista_id).
-- ============================================================
CREATE TABLE IF NOT EXISTS properties (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  idealista_id TEXT UNIQUE,
  url TEXT NOT NULL,
  title TEXT,
  price INTEGER,
  area_m2 NUMERIC,
  usable_area_m2 NUMERIC,
  num_rooms INTEGER,
  num_bathrooms INTEGER,
  floor TEXT,
  location TEXT,
  description TEXT,
  image_urls TEXT[],
  image_tags JSONB,
  orientation TEXT,
  price_per_m2 NUMERIC,
  raw_scraped_data JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_properties_idealista_id ON properties(idealista_id);


-- ============================================================
-- portfolio_items
-- User <-> Property relationship.
-- ============================================================
CREATE TABLE IF NOT EXISTS portfolio_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  property_id UUID REFERENCES properties(id) ON DELETE CASCADE,
  nickname TEXT,                    -- user-assigned name ("o de Alfama")
  notes TEXT,
  is_active BOOLEAN DEFAULT FALSE,  -- currently focused property
  index_summary TEXT,               -- one-liner: "T2 Alfama, 180k€, reno 15-25k€"
  status TEXT DEFAULT 'saved',      -- saved | analyzing | analyzed | archived
  added_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, property_id)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_user ON portfolio_items(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_active ON portfolio_items(user_id, is_active) WHERE is_active = TRUE;


-- ============================================================
-- room_features
-- GPT-extracted features per room. Belongs to the property (not per-user).
-- Enables recalculation without GPT re-run.
-- ============================================================
CREATE TABLE IF NOT EXISTS room_features (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id UUID REFERENCES properties(id) ON DELETE CASCADE,
  room_type TEXT NOT NULL,
  room_number INTEGER NOT NULL,
  room_label TEXT,
  features JSONB NOT NULL,          -- KitchenFeatures | BathroomFeatures | GenericRoomFeatures
  images TEXT[],
  extraction_model TEXT,            -- "gpt-4o"
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_room_features_property ON room_features(property_id);


-- ============================================================
-- analyses
-- Analysis results per user per property. Costs depend on user preferences.
-- ============================================================
CREATE TABLE IF NOT EXISTS analyses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  property_id UUID REFERENCES properties(id) ON DELETE CASCADE,
  portfolio_item_id UUID REFERENCES portfolio_items(id) ON DELETE CASCADE,
  analysis_type TEXT NOT NULL,        -- renovation | fiscal | comparison
  result_data JSONB NOT NULL,         -- full RenovationEstimate
  chat_summary TEXT,                  -- compact (~200 tokens)
  detail_summary TEXT,                -- medium (~500 tokens)
  user_preferences_snapshot JSONB,    -- preferences at calculation time
  status TEXT DEFAULT 'completed',    -- pending | running | completed | failed
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analyses_user_property ON analyses(user_id, property_id);
CREATE INDEX IF NOT EXISTS idx_analyses_portfolio ON analyses(portfolio_item_id);


-- ============================================================
-- conversations
-- Session tracking with carry-over summaries.
-- ============================================================
CREATE TABLE IF NOT EXISTS conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  ended_at TIMESTAMPTZ,
  summary TEXT,               -- generated at session end
  message_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_latest ON conversations(user_id, ended_at DESC);


-- ============================================================
-- messages
-- Individual messages within a conversation.
-- ============================================================
CREATE TABLE IF NOT EXISTS messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL,           -- user | assistant | system | tool
  content TEXT NOT NULL,
  tool_calls JSONB,
  tool_call_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);


-- ============================================================
-- action_log
-- Every mutation triggered by conversation. ML-ready.
-- ============================================================
CREATE TABLE IF NOT EXISTS action_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  conversation_id UUID REFERENCES conversations(id),
  message_id UUID REFERENCES messages(id),
  action_type TEXT NOT NULL,      -- profile_update | portfolio_add | portfolio_remove | analysis_trigger | cost_recalculate
  entity_type TEXT NOT NULL,      -- user_profile | portfolio_item | analysis | property
  entity_id UUID,
  field_changed TEXT,
  old_value JSONB,
  new_value JSONB,
  trigger_message TEXT,
  confidence NUMERIC,
  confirmed_by_user BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_action_log_user ON action_log(user_id);
CREATE INDEX IF NOT EXISTS idx_action_log_conversation ON action_log(conversation_id);


-- ============================================================
-- Row Level Security (RLS)
-- Users can only access their own data.
-- ============================================================

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE action_log ENABLE ROW LEVEL SECURITY;

-- user_profiles: users manage their own profile
CREATE POLICY "users_own_profile" ON user_profiles
  FOR ALL USING (auth.uid() = id);

-- portfolio_items: users manage their own portfolio
CREATE POLICY "users_own_portfolio" ON portfolio_items
  FOR ALL USING (auth.uid() = user_id);

-- analyses: users manage their own analyses
CREATE POLICY "users_own_analyses" ON analyses
  FOR ALL USING (auth.uid() = user_id);

-- conversations: users manage their own conversations
CREATE POLICY "users_own_conversations" ON conversations
  FOR ALL USING (auth.uid() = user_id);

-- messages: users access messages through their conversations
CREATE POLICY "users_own_messages" ON messages
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM conversations c
      WHERE c.id = messages.conversation_id AND c.user_id = auth.uid()
    )
  );

-- action_log: users view their own action log
CREATE POLICY "users_own_action_log" ON action_log
  FOR ALL USING (auth.uid() = user_id);

-- properties: readable by all authenticated users (shared, deduplicated)
ALTER TABLE properties ENABLE ROW LEVEL SECURITY;
CREATE POLICY "properties_readable_by_all" ON properties
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "properties_insertable_by_service" ON properties
  FOR INSERT WITH CHECK (auth.role() = 'service_role');

-- room_features: readable by all authenticated users (belongs to property)
ALTER TABLE room_features ENABLE ROW LEVEL SECURITY;
CREATE POLICY "room_features_readable_by_all" ON room_features
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "room_features_insertable_by_service" ON room_features
  FOR INSERT WITH CHECK (auth.role() = 'service_role');
