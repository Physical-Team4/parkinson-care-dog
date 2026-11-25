-- PD-Dog 스키마 (Supabase / PostgreSQL 15+). 설명: docs/db.md
-- 규칙: 적용된 파일은 수정하지 않는다. 바꿀 때는 다음 번호의 새 파일.
-- 시각: timestamptz. 일별 집계는 Asia/Seoul 기준 (002_functions.sql).

-- ─────────────────────────────────────────────
-- 보호자·치료사 허용 목록. RLS는 이 표에 있는 로그인 사용자만 통과시킨다 (003_rls.sql)
-- 추가: SQL Editor에서 insert (auth.users의 id). 대시보드에서는 수정 불가
-- ─────────────────────────────────────────────
create table public.care_team (
    user_id  uuid primary key references auth.users (id) on delete cascade,
    role     text not null check (role in ('guardian', 'therapist', 'admin')),
    added_at timestamptz not null default now()
);

-- ─────────────────────────────────────────────
-- 알람 규칙. 심각도·합침 창을 마이그레이션 없이 바꿀 수 있게 표로 둔다
--   window_seconds  : 같은 source를 1건으로 합치는 창
--   merge_into_acked: true = 확인된 알람에도 합침 ("N분에 1번" 재알림 제한용)
--   provisional     : true = 임시값, D와 확정 필요 (docs/todo.md)
-- ─────────────────────────────────────────────
create table public.alert_rules (
    source           text primary key,
    severity         text    not null check (severity in ('critical', 'warning')),
    window_seconds   integer not null check (window_seconds > 0),
    merge_into_acked boolean not null default false,
    provisional      boolean not null default false,
    label            text    not null
);

insert into public.alert_rules (source, severity, window_seconds, merge_into_acked, provisional, label) values
    ('camera',            'critical',   30, false, false, '낙상'),
    ('no_motion',         'critical',   30, false, false, '무움직임'),
    ('touch',             'critical',   30, false, false, '터치 신고'),
    ('voice',             'critical',   30, false, false, '음성 신고'),
    ('medication_missed', 'warning',    30, false, false, '복약 미확인'),
    ('battery_low',       'warning',  1800, true,  false, '배터리 부족'),
    ('robot_tipped',      'warning',   300, true,  false, '로봇 넘어짐'),
    ('overheat',          'warning',   300, true,  true,  '과열'),          -- 심각도·간격 미정
    ('disconnected',      'warning',   300, true,  true,  '로봇 연결 끊김'); -- 심각도·간격 미정

-- ─────────────────────────────────────────────
-- 알람 (위급·주의). 생성은 report_alert() RPC로만 (중복 합치기)
-- ─────────────────────────────────────────────
create table public.alerts (
    id              bigint generated always as identity primary key,
    source          text        not null references public.alert_rules (source),
    severity        text        not null check (severity in ('critical', 'warning')),
    confidence      real        check (confidence between 0 and 1),   -- camera만
    detail          jsonb,      -- 판단 근거 요약. 영상·음성·키포인트 이력 금지
    occurred_at     timestamptz not null default now(),  -- 실제 발생 시각 (대기열 재전송 시 Pi 시각)
    received_at     timestamptz not null default now(),  -- Supabase 도착 시각
    last_seen_at    timestamptz not null default now(),
    merged_count    integer     not null default 1 check (merged_count >= 1),
    acknowledged_at timestamptz,
    acknowledged_by uuid references auth.users (id) on delete set null,
    ack_note        text        check (char_length(ack_note) <= 200)
);
create index alerts_source_occurred_idx on public.alerts (source, occurred_at desc);
create index alerts_unacked_idx on public.alerts (occurred_at desc) where acknowledged_at is null;

-- Pi 대기열 재전송 시 같은 보고를 두 번 처리하지 않기 위한 기록
create table public.alert_reports (
    client_id   uuid primary key,
    alert_id    bigint not null references public.alerts (id) on delete cascade,
    received_at timestamptz not null default now()
);

-- 확인 메모는 처음 적은 것만 유지
create function public.alerts_ack_once() returns trigger
language plpgsql as $$
begin
    if old.acknowledged_at is not null and (
           new.acknowledged_at is distinct from old.acknowledged_at
        or new.ack_note        is distinct from old.ack_note) then
        raise exception 'alert % already acknowledged', old.id using errcode = 'P0001';
    end if;
    return new;
end $$;

create trigger alerts_ack_once
before update on public.alerts
for each row execute function public.alerts_ack_once();

-- ─────────────────────────────────────────────
-- 로봇 상태 이력. 2초마다 1행, 24시간만 보관 (004_cron.sql)
-- 대기열에 넣지 않는다 (오프라인 동안의 상태는 버림)
-- ─────────────────────────────────────────────
create table public.robot_status (
    id                 bigint generated always as identity primary key,
    received_at        timestamptz not null default now(),
    esp32_ok           boolean     not null,
    mode               text,
    dog_battery_pct    real check (dog_battery_pct between 0 and 100),
    pi_battery_pct     real check (pi_battery_pct  between 0 and 100),
    pi_charging        boolean,
    pi_temp_c          real,
    follow_distance_cm real,
    laser_on           boolean,
    bpm                integer,
    robot_tipped       boolean
);
create index robot_status_received_idx on public.robot_status (received_at desc);

-- 포즈(0.4초)는 테이블에 저장하지 않는다 → Realtime Broadcast (docs/db.md)

-- ─────────────────────────────────────────────
-- 설정 (단일 행)
-- ─────────────────────────────────────────────
create table public.settings (
    id              smallint primary key default 1 check (id = 1),
    target_bpm      integer not null default 96  check (target_bpm      between 80 and 110),
    target_db       integer not null default 68  check (target_db       between 50 and 90),
    follow_limit_cm integer not null default 150 check (follow_limit_cm between 50 and 300),
    updated_at      timestamptz not null default now(),
    updated_by      uuid references auth.users (id) on delete set null
);
insert into public.settings (id) values (1);

-- ─────────────────────────────────────────────
-- 복약 시간 (1~8개)
-- ─────────────────────────────────────────────
create table public.medication_schedule (
    id          bigint generated always as identity primary key,
    time_of_day time    not null unique check (extract(second from time_of_day) = 0),
    name        text,   -- 예: '아침 약'
    enabled     boolean not null default true,
    updated_at  timestamptz not null default now()
);
insert into public.medication_schedule (time_of_day) values
    ('08:00'), ('12:30'), ('18:00'), ('22:00');

create function public.medication_schedule_count_guard() returns trigger
language plpgsql as $$
declare
    n integer;
begin
    select count(*) into n from public.medication_schedule;
    if tg_op = 'INSERT' and n >= 8 then
        raise exception 'medication schedule: max 8 times' using errcode = 'P0001';
    elsif tg_op = 'DELETE' and n <= 1 then
        raise exception 'medication schedule: min 1 time' using errcode = 'P0001';
    end if;
    return coalesce(new, old);
end $$;

create trigger medication_schedule_count_guard
before insert or delete on public.medication_schedule
for each row execute function public.medication_schedule_count_guard();

-- ─────────────────────────────────────────────
-- F1 복약 기록. 복약 시간 1회 = 1행 (due_at 기준 upsert)
-- ─────────────────────────────────────────────
create table public.medication_logs (
    id           bigint generated always as identity primary key,
    schedule_id  bigint references public.medication_schedule (id) on delete set null,
    due_at       timestamptz not null unique,
    status       text not null default 'pending' check (status in ('pending', 'confirmed', 'missed')),
    confirmed_at timestamptz,
    method       text check (method in ('touch', 'voice')),
    alert_id     bigint references public.alerts (id) on delete set null,
    check ((status = 'confirmed') = (confirmed_at is not null))
);

-- ─────────────────────────────────────────────
-- F3 보행 훈련 / F4 발성 훈련 / F5 인식 결과
-- client_id: Pi가 만든 UUID. 재전송돼도 1건만 저장 (on conflict do nothing)
-- ─────────────────────────────────────────────
create table public.gait_sessions (
    id            bigint generated always as identity primary key,
    client_id     uuid unique,
    started_at    timestamptz not null,
    ended_at      timestamptz not null,
    avg_bpm       real,
    target_bpm    integer,
    stop_count    integer not null default 0 check (stop_count    >= 0),  -- ToF 대기·"멈춰"
    restart_count integer not null default 0 check (restart_count >= 0),  -- 멈췄다 다시 출발
    check (ended_at >= started_at)
);
create index gait_sessions_started_idx on public.gait_sessions (started_at);

create table public.voice_sessions (
    id            bigint generated always as identity primary key,
    client_id     uuid unique,
    started_at    timestamptz not null,
    ended_at      timestamptz,
    peak_db       real,
    target_db     integer,   -- 그 시점 settings.target_db 스냅샷
    attempts      integer not null default 0 check (attempts >= 0),
    success_count integer not null default 0 check (success_count between 0 and attempts)
);
create index voice_sessions_started_idx on public.voice_sessions (started_at);

-- 화자 임베딩·이름은 Supabase에 올리지 않는다 (Pi 로컬 전용). 여기는 결과만
create table public.speaker_events (
    id               bigint generated always as identity primary key,
    client_id        uuid unique,
    occurred_at      timestamptz not null default now(),
    speaker_local_id integer,   -- Pi 로컬 화자 번호. NULL = 등록 안 된 목소리
    score            real    not null,
    accepted         boolean not null
);
create index speaker_events_occurred_idx on public.speaker_events (occurred_at);

create table public.speaker_stats (
    id               smallint primary key default 1 check (id = 1),
    registered_count integer not null default 0 check (registered_count >= 0),
    updated_at       timestamptz not null default now()
);
insert into public.speaker_stats (id) values (1);

-- ─────────────────────────────────────────────
-- updated_at / updated_by 자동 갱신
-- ─────────────────────────────────────────────
create function public.touch_updated() returns trigger
language plpgsql as $$
begin
    new.updated_at := now();
    if tg_table_name = 'settings' then
        new.updated_by := auth.uid();   -- Pi(service_role)가 바꾸면 NULL
    end if;
    return new;
end $$;

create trigger settings_touch before update on public.settings
for each row execute function public.touch_updated();
create trigger medication_schedule_touch before update on public.medication_schedule
for each row execute function public.touch_updated();
create trigger speaker_stats_touch before update on public.speaker_stats
for each row execute function public.touch_updated();
