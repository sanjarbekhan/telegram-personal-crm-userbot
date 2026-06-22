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

create index if not exists idx_chat_messages_date on telegram_chat_messages(message_date);
create index if not exists idx_chat_messages_user_date on telegram_chat_messages(telegram_user_id, message_date);
create index if not exists idx_broadcast_logs_pending on telegram_broadcast_logs(status, created_at);
create index if not exists idx_customers_status on telegram_customers(status);
