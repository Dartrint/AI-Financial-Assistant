create table public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null check (char_length(content) between 1 and 12000),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index chat_messages_user_created_at_idx
  on public.chat_messages (user_id, created_at desc);

alter table public.chat_messages enable row level security;

create policy "Users can read their own chat messages"
  on public.chat_messages
  for select
  to authenticated
  using ((select auth.uid()) = user_id);

create policy "Users can create their own chat messages"
  on public.chat_messages
  for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

revoke all on public.chat_messages from anon;
grant select, insert on public.chat_messages to authenticated;
