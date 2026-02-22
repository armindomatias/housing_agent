-- Stripe/Billing schema for Rehabify v1
-- Run in Supabase SQL editor (or via migration tooling).

create table if not exists public.billing_accounts (
    user_id uuid primary key references auth.users(id) on delete cascade,
    free_analyses_used integer not null default 0,
    cycle_analyses_used integer not null default 0,
    daily_usage_count integer not null default 0,
    daily_usage_date date,
    plan_code text not null default 'free',
    subscription_status text not null default '',
    cycle_start_at timestamptz,
    cycle_end_at timestamptz,
    stripe_customer_id text unique,
    stripe_subscription_id text,
    is_master_override boolean not null default false,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists idx_billing_accounts_stripe_customer
    on public.billing_accounts (stripe_customer_id);

create table if not exists public.billing_webhook_events (
    event_id text primary key,
    processed_at timestamptz not null default timezone('utc', now())
);

-- Optional trigger to keep updated_at fresh
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists trg_billing_accounts_updated_at on public.billing_accounts;
create trigger trg_billing_accounts_updated_at
before update on public.billing_accounts
for each row
execute procedure public.set_updated_at();

-- Recommended RLS setup:
-- 1) Enable RLS on billing_accounts.
-- 2) Allow users to read their own row (select where auth.uid() = user_id).
-- 3) Keep writes service-role only (backend uses SUPABASE_SECRET_KEY).
