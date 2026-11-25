-- RLS·권한. 설명: docs/db.md "보안 구조"
--   Pi        : service_role(secret) 키 → RLS 우회. 키는 Pi의 .env에만
--   대시보드   : anon(publishable) 키 + Supabase Auth 로그인 → authenticated 역할
--               care_team 표에 있는 사용자만 읽기/설정 변경 가능
--   로그인 안 한 anon: 아무것도 못 읽음

-- 로그인 사용자가 care_team인지 (RLS 정책에서 사용)
create function public.is_care_team() returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (select 1 from public.care_team where user_id = auth.uid());
$$;

-- ── RLS 켜기 (모든 표) ──
alter table public.care_team           enable row level security;
alter table public.alert_rules         enable row level security;
alter table public.alerts              enable row level security;
alter table public.alert_reports       enable row level security;
alter table public.robot_status        enable row level security;
alter table public.settings            enable row level security;
alter table public.medication_schedule enable row level security;
alter table public.medication_logs     enable row level security;
alter table public.gait_sessions       enable row level security;
alter table public.voice_sessions      enable row level security;
alter table public.speaker_events      enable row level security;
alter table public.speaker_stats       enable row level security;

-- ── 기본 권한 정리: anon은 전부 회수, authenticated는 필요한 것만 ──
revoke all on all tables    in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke execute on all functions in schema public from public, anon, authenticated;

grant all on all tables    in schema public to service_role;
grant all on all sequences in schema public to service_role;
grant execute on all functions in schema public to service_role;

grant select on public.care_team, public.alert_rules, public.alerts, public.robot_status,
                public.robot_latest, public.settings, public.medication_schedule,
                public.medication_logs, public.gait_sessions, public.voice_sessions,
                public.speaker_events, public.speaker_stats,
                public.daily_medication, public.daily_gait, public.daily_voice, public.daily_speaker
      to authenticated;
grant update (target_bpm, target_db, follow_limit_cm) on public.settings to authenticated;
grant insert (time_of_day, name, enabled),
      update (time_of_day, name, enabled),
      delete on public.medication_schedule to authenticated;

grant execute on function public.is_care_team()          to authenticated;
grant execute on function public.ack_alert(bigint, text) to authenticated;
grant execute on function public.daily_stats(integer)    to authenticated;

-- ── 정책 (authenticated + care_team) ──
create policy care_team_self on public.care_team
    for select to authenticated using (user_id = auth.uid());

create policy read_alert_rules on public.alert_rules
    for select to authenticated using (public.is_care_team());
create policy read_alerts on public.alerts
    for select to authenticated using (public.is_care_team());
-- 알람 확인은 ack_alert() RPC로만 (직접 update 권한 없음)

create policy read_robot_status on public.robot_status
    for select to authenticated using (public.is_care_team());

create policy read_settings on public.settings
    for select to authenticated using (public.is_care_team());
create policy update_settings on public.settings
    for update to authenticated using (public.is_care_team()) with check (public.is_care_team());

create policy read_schedule on public.medication_schedule
    for select to authenticated using (public.is_care_team());
create policy insert_schedule on public.medication_schedule
    for insert to authenticated with check (public.is_care_team());
create policy update_schedule on public.medication_schedule
    for update to authenticated using (public.is_care_team()) with check (public.is_care_team());
create policy delete_schedule on public.medication_schedule
    for delete to authenticated using (public.is_care_team());

create policy read_medication_logs on public.medication_logs
    for select to authenticated using (public.is_care_team());
create policy read_gait_sessions on public.gait_sessions
    for select to authenticated using (public.is_care_team());
create policy read_voice_sessions on public.voice_sessions
    for select to authenticated using (public.is_care_team());
create policy read_speaker_events on public.speaker_events
    for select to authenticated using (public.is_care_team());
create policy read_speaker_stats on public.speaker_stats
    for select to authenticated using (public.is_care_team());
-- alert_reports: 정책 없음 → service_role만

-- 앞으로 만드는 표·함수도 anon에 자동 노출되지 않게
alter default privileges in schema public revoke all on tables    from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke execute on functions from public, anon, authenticated;
