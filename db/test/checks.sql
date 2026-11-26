-- 로컬 PostgreSQL 검증용 (Supabase 아님). 사용법: db/README.md
\set ON_ERROR_STOP 0
insert into auth.users values ('11111111-1111-1111-1111-111111111111'), ('22222222-2222-2222-2222-222222222222');
insert into care_team values ('11111111-1111-1111-1111-111111111111','guardian');
-- report_alert 합치기
select report_alert('camera', 0.7, '2026-11-26 10:00:00+09', null, 'aaaaaaaa-0000-0000-0000-000000000001') as r1;
select report_alert('camera', 0.9, '2026-11-26 10:00:20+09', null, 'aaaaaaaa-0000-0000-0000-000000000002') as r2_merge;
select report_alert('camera', 0.9, '2026-11-26 10:00:20+09', null, 'aaaaaaaa-0000-0000-0000-000000000002') as r2_dup;
select report_alert('camera', 0.5, '2026-11-26 10:00:40+09') as r3_new_after_30s;
select report_alert('touch', 0.9) as touch_conf_dropped;
select id, source, severity, confidence, merged_count from alerts order by id;
-- 서버 규칙: 배터리 (확인 후에도 30분 내 합침)
insert into robot_status (esp32_ok, dog_battery_pct) values (true, 15);
update alerts set acknowledged_at = now() where source = 'battery_low';
insert into robot_status (esp32_ok, dog_battery_pct, pi_temp_c, robot_tipped) values (true, 14, 80, true);
select source, severity, merged_count, acknowledged_at is not null as acked from alerts where source in ('battery_low','overheat','robot_tipped') order by id;
-- 메모 1회
update alerts set ack_note = '덮어쓰기' where source = 'battery_low';
-- 복약 최대 8
insert into medication_schedule (time_of_day) values ('06:00'),('07:00'),('09:00'),('10:00');
insert into medication_schedule (time_of_day) values ('11:00');
-- 집계 데이터
insert into medication_logs (due_at, status, confirmed_at, method) values (now(), 'confirmed', now(), 'touch'), (now() - interval '1 minute', 'missed', null, null);
insert into gait_sessions (started_at, ended_at, avg_bpm, restart_count) values (now() - interval '10 min', now(), 96, 2);
insert into speaker_events (score, accepted) values (0.8, true), (0.2, false);
-- 권한: anon
set role anon; select count(*) from alerts; reset role;
-- 권한: 로그인했지만 care_team 아님
set role authenticated; set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
select count(*) as outsider_sees from alerts;
select ack_alert(1, 'x') as outsider_ack;
reset role;
-- 권한: care_team
set role authenticated; set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
select count(*) as member_sees from alerts;
select ack_alert(1, '확인했습니다') as ack1, ack_alert(1, '두번째') as ack2;
update alerts set ack_note = 'direct' where id = 1;
update settings set target_bpm = 100;
update settings set target_bpm = 200;
update settings set updated_at = now();
select target_bpm, updated_by from settings;
select connected, dog_battery_pct from robot_latest;
select jsonb_pretty(daily_stats(2));
reset role;
select id, ack_note, acknowledged_by from alerts where id = 1;
