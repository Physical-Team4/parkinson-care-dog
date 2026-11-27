-- F1 복약 미확인 기록: 이미 확인(confirmed)된 복약을 missed로 덮지 않는다. 설명: docs/db.md, docs/api.md
--   Pi가 재부팅되며 로봇도 리셋되면 로봇이 확인된 복약을 다시 알리고 30분 뒤 med_missed를 보낸다.
--   Pi는 재부팅으로 확인 사실을 잊으므로 DB에서 막는다 (2026-11-27 실기기 시험에서 확인, D).
-- mark_medication_missed: 기록이 없으면 missed로 새로 만들고, pending이면 missed로 바꾼다.
--   confirmed·missed는 그대로. Pi가 service_role로 호출 (대기열 재전송해도 결과 같음).
-- 반환: 호출 후 그 복약의 status
create function public.mark_medication_missed(p_due_at timestamptz) returns text
language plpgsql
security definer
set search_path = public
as $$
declare
    v_status text;
begin
    insert into public.medication_logs (due_at, status)
    values (p_due_at, 'missed')
    on conflict (due_at) do update
        set status = 'missed'
        where public.medication_logs.status = 'pending';
    select status into v_status from public.medication_logs where due_at = p_due_at;
    return v_status;
end;
$$;

-- 새 함수는 기본으로 public·anon·authenticated가 실행 가능 → Pi(service_role)만
revoke execute on function public.mark_medication_missed(timestamptz) from public, anon, authenticated;
grant execute on function public.mark_medication_missed(timestamptz) to service_role;
