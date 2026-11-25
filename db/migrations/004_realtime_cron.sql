-- Realtime·예약 작업. Supabase 전용 기능이라 일반 PostgreSQL에서는 실패한다.
-- pg_cron이 꺼져 있으면: Dashboard → Database → Extensions → pg_cron 켜고 다시 실행.

-- ─────────────────────────────────────────────
-- Realtime: 알람 실시간 수신 (postgres_changes, RLS 적용됨)
-- robot_status는 2초마다라 메시지 수가 많아 넣지 않음 → 대시보드가 robot_latest를 주기 조회
-- ─────────────────────────────────────────────
alter publication supabase_realtime add table public.alerts;

-- ─────────────────────────────────────────────
-- Realtime Broadcast: 포즈 (topic 'robot:pose', private 채널)
-- Pi는 service_role로 보냄. 대시보드는 로그인한 care_team만 받음
-- ─────────────────────────────────────────────
create policy care_team_receive_robot_broadcast on realtime.messages
    for select to authenticated
    using (
        realtime.messages.extension = 'broadcast'
        and realtime.topic() like 'robot:%'
        and public.is_care_team()
    );

-- ─────────────────────────────────────────────
-- pg_cron: 연결 끊김 검사(10초), status 이력 정리(매시)
-- ─────────────────────────────────────────────
create extension if not exists pg_cron;

select cron.schedule('pd-dog-check-disconnected', '10 seconds',
                     $$select public.check_robot_disconnected()$$);
select cron.schedule('pd-dog-prune-robot-status', '7 * * * *',
                     $$select public.prune_robot_status()$$);
