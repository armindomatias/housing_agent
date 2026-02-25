-- Migration 002: Add increment_conversation_message_count RPC function
--
-- The orchestrator calls this function after each turn to track message volume
-- per conversation. Was missing from migration 001.

CREATE OR REPLACE FUNCTION public.increment_conversation_message_count(conversation_id uuid)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
AS $$
  UPDATE public.conversations
  SET message_count = COALESCE(message_count, 0) + 1
  WHERE id = conversation_id;
$$;
