create table public.chat_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  title text not null default 'Cuộc trò chuyện mới'
    check (char_length(title) between 1 and 80),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id)
);

alter table public.chat_sessions enable row level security;

create policy "Users can read their own chat sessions"
  on public.chat_sessions
  for select
  to authenticated
  using ((select auth.uid()) = user_id);

create policy "Users can create their own chat sessions"
  on public.chat_sessions
  for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

create policy "Users can update their own chat sessions"
  on public.chat_sessions
  for update
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "Users can delete their own chat sessions"
  on public.chat_sessions
  for delete
  to authenticated
  using ((select auth.uid()) = user_id);

grant select, insert, update, delete on public.chat_sessions to authenticated;

alter table public.chat_messages
  add column session_id uuid;

insert into public.chat_sessions (user_id, title, created_at, updated_at)
select
  user_id,
  'Cuộc trò chuyện trước đây',
  min(created_at),
  max(created_at)
from public.chat_messages
group by user_id;

update public.chat_messages as messages
set session_id = sessions.id
from public.chat_sessions as sessions
where sessions.user_id = messages.user_id;

alter table public.chat_messages
  alter column session_id set not null,
  add constraint chat_messages_session_user_fkey
    foreign key (session_id, user_id)
    references public.chat_sessions (id, user_id)
    on delete cascade;

create index chat_sessions_user_updated_at_idx
  on public.chat_sessions (user_id, updated_at desc);

create index chat_messages_session_created_at_idx
  on public.chat_messages (session_id, created_at);
