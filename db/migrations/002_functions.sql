-- 알람 RPC, 서버 자동 규칙, 일별 집계. 설명: docs/db.md, docs/api.md

-- ─────────────────────────────────────────────
-- report_alert: 알람 보고 + 중복 합치기 (Pi가 service_role로 호출)
--   같은 source의 최근 알람이 window_seconds 안이면 merged_count+1
--   (merge_into_acked=false인 규칙은 확인 안 된 알람에만 합침)
--   p_client_id가 이미 처리된 보고면 아무것도 바꾸지 않고 같은 결과 반환
-- 반환: {"alert_id": <id>, "merged": <bool>, "duplicate": <bool>}
-- ─────────────────────────────────────────────
create function public.report_alert(
    p_source      text,
    p_confidence  real        default null,
    p_occurred_at timestamptz default null,
    p_detail      jsonb       default null,
    p_client_id   uuid        default null
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_rule     public.alert_rules%rowtype;
    v_at       timestamptz := coalesce(p_occurred_at, now());
    v_conf     real := case when p_source = 'camera' then p_confidence end;
    v_existing bigint;
    v_id       bigint;
    v_merged   boolean;
begin
    if p_client_id is not null then
        select alert_id into v_existing from public.alert_reports where client_id = p_client_id;
        if found then
            return jsonb_build_object('alert_id', v_existing, 'merged', false, 'duplicate', true);
        end if;
    end if;

    select * into v_rule from public.alert_rules where source = p_source;
    if not found then
        raise exception 'unknown alert source: %', p_source using errcode = '22023';
    end if;

    -- 같은 source 동시 보고 직렬화
    perform pg_advisory_xact_lock(hashtext('pd_dog.report_alert.' || p_source));

    select a.id into v_id
    from public.alerts a
    where a.source = p_source
      and (v_rule.merge_into_acked or a.acknowledged_at is null)
      and abs(extract(epoch from (v_at - a.occurred_at))) < v_rule.window_seconds
    order by a.occurred_at desc
    limit 1;

    if found then
        update public.alerts
           set merged_count = merged_count + 1,
               last_seen_at = greatest(last_seen_at, v_at),
               confidence   = greatest(confidence, v_conf)
         where id = v_id;
        v_merged := true;
    else
        insert into public.alerts (source, severity, confidence, detail, occurred_at, last_seen_at)
        values (p_source, v_rule.severity, v_conf, p_detail, v_at, v_at)
        returning id into v_id;
        v_merged := false;
    end if;

    if p_client_id is not null then
        insert into public.alert_reports (client_id, alert_id) values (p_client_id, v_id);
    end if;

    return jsonb_build_object('alert_id', v_id, 'merged', v_merged, 'duplicate', false);
end $$;

-- ─────────────────────────────────────────────
-- ack_alert: 대시보드 알람 확인 (처음 1번만). 반환 true = 이번에 확인됨
-- ─────────────────────────────────────────────
create function public.ack_alert(p_alert_id bigint, p_note text default null)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
begin
    if not public.is_care_team() then
        raise exception 'not allowed' using errcode = '42501';
    end if;
    update public.alerts
       set acknowledged_at = now(),
           acknowledged_by = auth.uid(),
           ack_note        = nullif(btrim(p_note), '')
     where id = p_alert_id
       and acknowledged_at is null;
    return found;
end $$;

-- ─────────────────────────────────────────────
-- 서버 자동 규칙: status가 들어올 때마다 검사
-- ─────────────────────────────────────────────
create function public.robot_status_rules() returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if new.dog_battery_pct < 20 or new.pi_battery_pct < 20 then
        perform public.report_alert('battery_low', null, new.received_at,
            jsonb_build_object('dog_battery_pct', new.dog_battery_pct,
                               'pi_battery_pct',  new.pi_battery_pct));
    end if;
    if new.robot_tipped then
        perform public.report_alert('robot_tipped', null, new.received_at, null);
    end if;
    if new.pi_temp_c >= 75 then
        perform public.report_alert('overheat', null, new.received_at,
            jsonb_build_object('pi_temp_c', new.pi_temp_c));
    end if;
    return new;
end $$;

create trigger robot_status_rules
after insert on public.robot_status
for each row execute function public.robot_status_rules();

-- status 10초 끊김 검사 (pg_cron이 10초마다 호출, 004_cron.sql)
create function public.check_robot_disconnected() returns void
language plpgsql
security definer
set search_path = public
as $$
declare
    v_last timestamptz;
begin
    select max(received_at) into v_last from public.robot_status;
    if v_last is not null and v_last < now() - interval '10 seconds' then
        perform public.report_alert('disconnected', null, now(),
            jsonb_build_object('last_status_at', v_last));
    end if;
end $$;

create function public.prune_robot_status(p_keep interval default interval '24 hours')
returns integer
language sql
security definer
set search_path = public
as $$
    with d as (delete from public.robot_status where received_at < now() - p_keep returning 1)
    select count(*)::integer from d;
$$;

-- ─────────────────────────────────────────────
-- 최신 상태 + 연결 여부 (대시보드)
-- ─────────────────────────────────────────────
create view public.robot_latest with (security_invoker = true) as
select s.*,
       s.received_at > now() - interval '10 seconds' as connected
from public.robot_status s
order by s.received_at desc
limit 1;

-- ─────────────────────────────────────────────
-- 일별 집계 뷰 (Asia/Seoul 날짜). security_invoker → RLS 적용
-- ─────────────────────────────────────────────
create view public.daily_medication with (security_invoker = true) as
select (due_at at time zone 'Asia/Seoul')::date             as day,
       count(*)                                             as scheduled,
       count(*) filter (where status = 'confirmed')         as confirmed,
       count(*) filter (where status = 'missed')            as missed
from public.medication_logs
group by 1;

create view public.daily_gait with (security_invoker = true) as
select (started_at at time zone 'Asia/Seoul')::date         as day,
       count(*)                                             as sessions,
       round((extract(epoch from sum(ended_at - started_at)) / 60)::numeric, 1) as minutes,
       round((sum(avg_bpm * extract(epoch from (ended_at - started_at)))
              / nullif(sum(extract(epoch from (ended_at - started_at)))
                       filter (where avg_bpm is not null), 0))::numeric, 1) as avg_bpm,
       sum(restart_count)                                   as restart_count
from public.gait_sessions
group by 1;

create view public.daily_voice with (security_invoker = true) as
select (started_at at time zone 'Asia/Seoul')::date         as day,
       max(peak_db)                                         as peak_db,
       max(target_db)                                       as target_db,
       sum(attempts)                                        as attempts,
       sum(success_count)                                   as success_count
from public.voice_sessions
group by 1;

create view public.daily_speaker with (security_invoker = true) as
select (occurred_at at time zone 'Asia/Seoul')::date        as day,
       count(*)                                             as events,
       count(*) filter (where accepted)                     as accepted,
       round(100.0 * count(*) filter (where accepted) / count(*), 1) as success_rate_pct
from public.speaker_events
group by 1;

-- 대시보드 7일 카드: 기록 없는 날도 채워서 반환 (docs/api.md 형식)
create function public.daily_stats(p_days integer default 7)
returns jsonb
language sql
stable
security invoker
set search_path = public
as $$
    with days as (
        select (now() at time zone 'Asia/Seoul')::date - g as day
        from generate_series(least(greatest(p_days, 1), 90) - 1, 0, -1) as g
    )
    select jsonb_build_object(
        'registered_speakers', (select registered_count from public.speaker_stats where id = 1),
        'days', coalesce(jsonb_agg(jsonb_build_object(
            'day', d.day,
            'medication', jsonb_build_object('scheduled', coalesce(m.scheduled, 0),
                                             'confirmed', coalesce(m.confirmed, 0)),
            'gait',       jsonb_build_object('sessions', coalesce(g.sessions, 0),
                                             'minutes', coalesce(g.minutes, 0),
                                             'avg_bpm', g.avg_bpm,
                                             'restart_count', coalesce(g.restart_count, 0)),
            'voice',      jsonb_build_object('peak_db', v.peak_db, 'target_db', v.target_db),
            'speaker',    jsonb_build_object('success_rate_pct', s.success_rate_pct)
        ) order by d.day), '[]'::jsonb)
    )
    from days d
    left join public.daily_medication m on m.day = d.day
    left join public.daily_gait       g on g.day = d.day
    left join public.daily_voice      v on v.day = d.day
    left join public.daily_speaker    s on s.day = d.day;
$$;
