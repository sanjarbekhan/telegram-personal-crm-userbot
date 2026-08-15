create extension if not exists pgcrypto;

create table if not exists telegram_customers (
  id uuid primary key default gen_random_uuid(),
  telegram_user_id bigint unique not null,
  full_name text,
  username text,
  phone text,
  first_seen_at timestamptz default now(),
  last_seen_at timestamptz default now(),
  status text default 'new' check (status in ('new', 'contacted', 'interested', 'follow_up', 'paid', 'rejected', 'do_not_contact')),
  is_lead boolean not null default false,
  lead_source text not null default 'telegram',
  pipeline_status text not null default 'new' check (pipeline_status in ('new', 'contacted', 'interested', 'questionnaire', 'awaiting_documents', 'awaiting_payment', 'paid', 'drafting', 'review', 'published', 'lost')),
  lead_temperature text not null default 'warm' check (lead_temperature in ('cold', 'warm', 'hot')),
  notes text,
  last_inbound_at timestamptz,
  last_outbound_at timestamptz,
  next_action_at timestamptz,
  payment_status text not null default 'not_requested' check (payment_status in ('not_requested', 'awaiting', 'paid', 'refunded')),
  payment_amount int,
  application_complete boolean not null default false,
  photo_received boolean not null default false,
  instagram_username text,
  documents_received boolean not null default false,
  consent_received boolean not null default false,
  published_url text,
  published_at timestamptz,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists telegram_chat_messages (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid references telegram_customers(id) on delete cascade,
  telegram_user_id bigint not null,
  message_id bigint not null,
  direction text not null check (direction in ('incoming', 'outgoing')),
  message_text text,
  message_date date not null,
  created_at timestamptz default now(),
  unique (telegram_user_id, message_id)
);

create table if not exists telegram_broadcasts (
  id uuid primary key default gen_random_uuid(),
  target_date date not null,
  message_text text not null,
  total_count int default 0,
  sent_count int default 0,
  failed_count int default 0,
  skipped_count int default 0,
  status text default 'draft' check (status in ('draft', 'queued', 'running', 'finished', 'cancelled')),
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz default now()
);

create table if not exists telegram_broadcast_logs (
  id uuid primary key default gen_random_uuid(),
  broadcast_id uuid references telegram_broadcasts(id) on delete cascade,
  customer_id uuid references telegram_customers(id) on delete cascade,
  telegram_user_id bigint not null,
  status text default 'pending' check (status in ('pending', 'processing', 'sent', 'failed', 'skipped')),
  error_text text,
  sent_at timestamptz,
  created_at timestamptz default now(),
  unique (broadcast_id, telegram_user_id)
);

create table if not exists telegram_scheduled_messages (
  id uuid primary key default gen_random_uuid(),
  scheduled_at timestamptz not null,
  timezone text not null default 'Asia/Tashkent',
  message_text text not null check (char_length(message_text) between 1 and 4096),
  total_count int not null default 0 check (total_count between 1 and 50),
  sent_count int not null default 0,
  failed_count int not null default 0,
  skipped_count int not null default 0,
  status text not null default 'queued' check (status in ('queued', 'running', 'finished', 'cancelled')),
  kind text not null default 'manual' check (kind in ('manual', 'follow_up')),
  customer_id uuid references telegram_customers(id) on delete cascade,
  cancel_on_reply boolean not null default false,
  sequence_step int,
  template_key text,
  cancelled_reason text,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists telegram_scheduled_recipients (
  id uuid primary key default gen_random_uuid(),
  scheduled_message_id uuid not null references telegram_scheduled_messages(id) on delete cascade,
  username text not null check (username ~ '^[a-z][a-z0-9_]{4,31}$'),
  telegram_user_id bigint,
  status text not null default 'pending' check (status in ('pending', 'processing', 'sent', 'failed', 'skipped')),
  error_text text,
  sent_at timestamptz,
  created_at timestamptz not null default now(),
  unique (scheduled_message_id, username)
);

-- Idempotent upgrades for databases created with an earlier schema version.
alter table telegram_customers add column if not exists is_lead boolean not null default false;
alter table telegram_customers add column if not exists lead_source text not null default 'telegram';
alter table telegram_customers add column if not exists pipeline_status text not null default 'new';
alter table telegram_customers add column if not exists lead_temperature text not null default 'warm';
alter table telegram_customers add column if not exists notes text;
alter table telegram_customers add column if not exists last_inbound_at timestamptz;
alter table telegram_customers add column if not exists last_outbound_at timestamptz;
alter table telegram_customers add column if not exists next_action_at timestamptz;
alter table telegram_customers add column if not exists payment_status text not null default 'not_requested';
alter table telegram_customers add column if not exists payment_amount int;
alter table telegram_customers add column if not exists application_complete boolean not null default false;
alter table telegram_customers add column if not exists photo_received boolean not null default false;
alter table telegram_customers add column if not exists instagram_username text;
alter table telegram_customers add column if not exists documents_received boolean not null default false;
alter table telegram_customers add column if not exists consent_received boolean not null default false;
alter table telegram_customers add column if not exists published_url text;
alter table telegram_customers add column if not exists published_at timestamptz;

alter table telegram_scheduled_messages add column if not exists kind text not null default 'manual';
alter table telegram_scheduled_messages add column if not exists customer_id uuid references telegram_customers(id) on delete cascade;
alter table telegram_scheduled_messages add column if not exists cancel_on_reply boolean not null default false;
alter table telegram_scheduled_messages add column if not exists sequence_step int;
alter table telegram_scheduled_messages add column if not exists template_key text;
alter table telegram_scheduled_messages add column if not exists cancelled_reason text;

create table if not exists crm_settings (
  key text primary key,
  value text,
  updated_at timestamptz default now()
);

insert into crm_settings (key, value)
values
  ('daily_send_limit', '100'),
  ('min_delay_seconds', '20'),
  ('max_delay_seconds', '40')
on conflict (key) do nothing;

create index if not exists idx_chat_messages_date
  on telegram_chat_messages(message_date);
create index if not exists idx_chat_messages_user_date
  on telegram_chat_messages(telegram_user_id, message_date);
create index if not exists idx_broadcast_logs_pending
  on telegram_broadcast_logs(status, created_at);
create index if not exists idx_customers_status
  on telegram_customers(status);
create index if not exists idx_customers_lead_pipeline
  on telegram_customers(is_lead, pipeline_status, updated_at desc);
create index if not exists idx_customers_next_action
  on telegram_customers(next_action_at)
  where is_lead = true and next_action_at is not null;
create index if not exists idx_scheduled_messages_due
  on telegram_scheduled_messages(status, scheduled_at);
create index if not exists idx_scheduled_messages_customer
  on telegram_scheduled_messages(customer_id, kind, status, scheduled_at);
create index if not exists idx_scheduled_recipients_pending
  on telegram_scheduled_recipients(scheduled_message_id, status, created_at);

-- The bot uses only the server-side service_role key. Client roles get no table access.
alter table telegram_customers enable row level security;
alter table telegram_chat_messages enable row level security;
alter table telegram_broadcasts enable row level security;
alter table telegram_broadcast_logs enable row level security;
alter table telegram_scheduled_messages enable row level security;
alter table telegram_scheduled_recipients enable row level security;
alter table crm_settings enable row level security;

revoke all on table telegram_customers from anon, authenticated;
revoke all on table telegram_chat_messages from anon, authenticated;
revoke all on table telegram_broadcasts from anon, authenticated;
revoke all on table telegram_broadcast_logs from anon, authenticated;
revoke all on table telegram_scheduled_messages from anon, authenticated;
revoke all on table telegram_scheduled_recipients from anon, authenticated;
revoke all on table crm_settings from anon, authenticated;

grant usage on schema public to service_role;
grant select, insert, update, delete on table telegram_customers to service_role;
grant select, insert, update, delete on table telegram_chat_messages to service_role;
grant select, insert, update, delete on table telegram_broadcasts to service_role;
grant select, insert, update, delete on table telegram_broadcast_logs to service_role;
grant select, insert, update, delete on table telegram_scheduled_messages to service_role;
grant select, insert, update, delete on table telegram_scheduled_recipients to service_role;
grant select, insert, update, delete on table crm_settings to service_role;
