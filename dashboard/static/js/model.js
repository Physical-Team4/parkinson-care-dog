// Model — DB 행(docs/db.md) → 화면 값, 입력 검증, 상태 판단. 순수 함수만 (DOM·네트워크 없음 → node로 테스트)

// ── 팀 설계 값 (db/migrations 001 CHECK, esp32/config.py, docs/db.md) ──
export const LIMITS = {
  BPM_MIN: 80, BPM_MAX: 110,                // settings.target_bpm, esp32 BPM_MIN/MAX
  FOLLOW_MIN: 50, FOLLOW_MAX: 300,          // settings.follow_limit_cm
  DB_MIN: 50, DB_MAX: 90,                   // settings.target_db
  DOSES_MIN: 1, DOSES_MAX: 8,               // medication_schedule 트리거
  DOSE_NAME_MAX: 20,
  NOTE_MAX: 200,                            // alerts.ack_note
  ONLINE_WINDOW_S: 10,                      // robot_latest.connected
  MED_CONFIRM_MIN: 30,                      // F1: 30분 미확인 → 알림
};
export const DELAY_MS = 60_000;             // 발생→도착이 이보다 늦으면 "로봇 대기열에서 늦게 도착"

// 알람 source → 화면 이름. 등급은 alerts.severity가 기준 (없으면 level)
export const KIND = {
  camera:            {name: "낙상 감지",            title: "낙상 감지!",       icon: "🧍", level: "crit"},
  no_motion:         {name: "움직임 없음",          title: "움직임 없음!",     icon: "⏸️", level: "crit"},
  touch:             {name: "위급 신고 (터치)",     title: "위급 신고!",       icon: "🆘", level: "crit"},
  voice:             {name: '위급 신고 ("도와줘")', title: "위급 신고!",       icon: "🆘", level: "crit"},
  medication_missed: {name: "복약 미확인",          title: "복약 미확인",      icon: "💊", level: "warn"},
  battery_low:       {name: "배터리 부족",          title: "로봇 배터리 부족", icon: "🔋", level: "warn"},
  robot_tipped:      {name: "로봇 넘어짐",          title: "로봇이 넘어졌어요", icon: "🐕", level: "warn"},
  overheat:          {name: "과열",                title: "라즈베리파이 과열", icon: "🌡️", level: "warn"},
  disconnected:      {name: "로봇 연결 끊김",       title: "로봇 연결 끊김",   icon: "📶", level: "warn"},
  test:              {name: "테스트",               title: "테스트 알람",      icon: "🧪", level: "crit"},   // Mock 전용
};
export const kind = s => KIND[s] || {name: s, title: "알람", icon: "⚠️", level: "crit"};
export const CRIT_SOURCES = ["camera", "no_motion", "touch", "voice"];

export const MODE_LABEL = {   // docs/serial-protocol.md mode (+ 기존 대시보드 명세의 값)
  idle: "대기", walking: "보행 훈련 중", paused: "기다리는 중 (사용자가 멀어짐)", medication: "복약 알림 중",
  alarm: "경보 중", voice: "발성 훈련 중", approaching: "환자에게 가는 중", charging: "충전 중",
};

const ms = iso => (iso ? Date.parse(iso) : NaN);

// ── 알람 ──
export function levelOf(row){
  if (row.severity === "critical") return "crit";
  if (row.severity === "warning") return "warn";
  return kind(row.source).level;
}

/** alerts 행 → 화면 이벤트 (기존 화면 코드가 쓰던 이름 유지: created_at·status·note) */
export function toEvent(row){
  const occurred = ms(row.occurred_at), received = ms(row.received_at);
  const delay = Number.isFinite(occurred) && Number.isFinite(received) ? received - occurred : 0;
  return {
    id: row.id, source: row.source, level: levelOf(row), confidence: row.confidence ?? null,
    created_at: row.occurred_at, received_at: row.received_at, last_seen_at: row.last_seen_at || row.occurred_at,
    merged_count: row.merged_count || 1,
    status: row.acknowledged_at ? "acknowledged" : "new",
    acknowledged_at: row.acknowledged_at || null, note: row.ack_note || "",
    delayed_ms: delay > DELAY_MS ? delay : 0,
    simulated: !!row.simulated,
  };
}

/** id 기준으로 합쳐서 중복 없이 최신순. 같은 id가 여러 번 와도(폴링 + Realtime) 1건 */
export function mergeAlerts(byId, rows){
  for (const r of rows || []) if (r && r.id != null) byId.set(r.id, {...(byId.get(r.id) || {}), ...r});
  return [...byId.values()].map(toEvent).sort((a, b) => ms(b.created_at) - ms(a.created_at) || b.id - a.id);
}

export function alertsView(events, limit = 50){
  const open = events.filter(e => e.status === "new");
  const recent = events.slice(0, limit);
  const shown = [...recent, ...open.filter(e => !recent.includes(e))];   // 오래된 미확인도 빠지지 않게
  return {events: shown, unacknowledged: open.length};
}

// ── 로봇 상태 ──
/** robot_latest 행 → {status, online, age_seconds}. 조회 실패(대시보드 오프라인)면 online=null(알 수 없음) */
export function robotView(latest, nowMs, fetchOk = true){
  if (!fetchOk) return {status: latest || null, online: null, age_seconds: null};
  if (!latest) return {status: null, online: false, age_seconds: null};
  const age = Math.max(0, (nowMs - ms(latest.received_at)) / 1000);
  const online = typeof latest.connected === "boolean" ? latest.connected && age <= LIMITS.ONLINE_WINDOW_S + 5
                                                       : age <= LIMITS.ONLINE_WINDOW_S;
  return {status: latest, online, age_seconds: age};
}

/** 표시용: null/undefined는 "데이터 없음"과 0을 구분 */
export const has = v => v !== null && v !== undefined;

/** 연결 항목별 표시 값. 받지 못한 값은 측정값처럼 보이지 않게 "미연동"/"데이터 없음" */
export function connectionRows(view){
  const s = view.status, on = view.online;
  if (!s) return {pi: ["never", "아직 신호 없음"], esp: ["unknown", "알 수 없음"], mode: "-", dogBattery: ["none", "데이터 없음"],
                  piBattery: ["none", "데이터 없음"], charging: ["none", "데이터 없음"]};
  const stale = on !== true;
  return {
    pi: on === null ? ["unknown", "확인 불가 (대시보드 인터넷 끊김)"] : on ? ["ok", "응답 중"] : ["off", "끊김"],
    esp: stale ? ["unknown", "알 수 없음 (로봇 신호 끊김)"] : s.esp32_ok ? ["ok", "응답 중"] : ["off", "응답 없음"],
    mode: stale ? "-" : (MODE_LABEL[s.mode] || (s.mode ? s.mode : "데이터 없음")),
    dogBattery: has(s.dog_battery_pct) ? ["value", Math.round(s.dog_battery_pct)] : ["none", "미연동 (ESP32가 아직 안 보냄)"],
    piBattery: has(s.pi_battery_pct) ? ["value", Math.round(s.pi_battery_pct)] : ["none", "측정 안 됨 (X1200 미연결)"],
    charging: s.pi_charging === true ? ["on", "충전기 연결됨 ⚡"] : s.pi_charging === false ? ["off", "충전기 없음"] : ["none", "데이터 없음"],
  };
}

// ── 오프라인·동기화 ──
/**
 * dashboardOnline: 대시보드가 Supabase에 닿는지, robot: robotView 결과, events: 화면 이벤트
 * 반환 {state, title, detail, delayedCount}
 */
export function syncView({dashboardOnline, robot, events, nowMs}){
  const dayAgo = nowMs - 24 * 3600 * 1000;
  const delayed = (events || []).filter(e => e.delayed_ms && ms(e.received_at) >= dayAgo);
  if (!dashboardOnline)
    return {state: "dashboard_offline", title: "대시보드 인터넷 끊김",
            detail: "마지막으로 받은 내용을 보여주는 중이에요. 연결되면 자동으로 새로 받아요.", delayedCount: delayed.length};
  if (!robot.status)
    return {state: "never", title: "로봇 신호를 받은 적 없음", detail: "로봇(라즈베리파이)이 켜지고 인터넷에 연결되면 표시돼요.",
            delayedCount: delayed.length};
  if (!robot.online)
    return {state: "robot_offline", title: "로봇 오프라인",
            detail: "로봇이 알람·훈련 기록을 내부에 보관 중일 수 있어요. 다시 연결되면 자동으로 올라와요 (상태·자세는 버려짐).",
            delayedCount: delayed.length};
  return {state: "synced", title: "동기화 정상",
          detail: delayed.length ? `최근 24시간에 늦게 도착한 알람 ${delayed.length}건 (로봇 오프라인 중 발생)` : "로봇 데이터가 바로 들어오고 있어요.",
          delayedCount: delayed.length};
}

// ── 복약 ──
export const hm = t => (t || "").slice(0, 5);   // "08:00:00" → "08:00"
const sameLocalDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

/** 오늘 복약 일정 + 기록(medication_logs) → 줄마다 상태. 기록이 없으면 지어내지 않음 */
export function medicationToday(schedule, logs, now = new Date()){
  const today = (logs || []).filter(l => sameLocalDay(new Date(l.due_at), now));
  return [...(schedule || [])].sort((a, b) => hm(a.time_of_day).localeCompare(hm(b.time_of_day))).map(s => {
    const t = hm(s.time_of_day);
    const [h, m] = t.split(":").map(Number);
    const due = new Date(now); due.setHours(h, m, 0, 0);
    const log = today.find(l => l.schedule_id === s.id) ||
                today.find(l => { const d = new Date(l.due_at); return d.getHours() === h && d.getMinutes() === m; });
    let status;
    if (!s.enabled) status = "off";
    else if (log) status = log.status;                                   // pending | confirmed | missed
    else status = now < due ? "upcoming" : "nolog";
    return {id: s.id, time: t, name: s.name || "", enabled: s.enabled, status,
            confirmed_at: log?.confirmed_at || null, method: log?.method || null};
  });
}
export const DOSE_STATUS = {
  confirmed: ["done", "✓ 복용 확인"], pending: ["now", "⏰ 알림 중"], missed: ["miss", "✗ 미확인"],
  upcoming: ["later", "예정"], nolog: ["later", "기록 없음"], off: ["later", "알림 꺼짐"],
};

/** 복약 일정 입력 검증. 반환: 오류 문장 또는 null */
export function validateDose(row, schedule, editingId = null){
  const t = hm(row.time_of_day);
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(t)) return "시각을 HH:MM 형식으로 넣어 주세요";
  if ((row.name || "").length > LIMITS.DOSE_NAME_MAX) return `약 이름은 ${LIMITS.DOSE_NAME_MAX}자 이하로 적어 주세요`;
  if ((schedule || []).some(s => s.id !== editingId && hm(s.time_of_day) === t)) return `${t}에 이미 복약 알림이 있어요`;
  if (editingId == null && (schedule || []).length >= LIMITS.DOSES_MAX) return `복약 알림은 최대 ${LIMITS.DOSES_MAX}개예요`;
  return null;
}

// ── 리듬 큐잉 ──
export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
export function validSetting(key, v){
  const r = {target_bpm: [LIMITS.BPM_MIN, LIMITS.BPM_MAX], follow_limit_cm: [LIMITS.FOLLOW_MIN, LIMITS.FOLLOW_MAX],
             target_db: [LIMITS.DB_MIN, LIMITS.DB_MAX]}[key];
  return !!r && Number.isInteger(v) && v >= r[0] && v <= r[1];
}

/** 원격 보행 시작 전 안전 조건 (정지는 항상 허용). 반환 null=가능, 문장=불가 이유 */
export function rhythmStartBlock(robot, bpm){
  if (!Number.isInteger(bpm) || bpm < LIMITS.BPM_MIN || bpm > LIMITS.BPM_MAX) return `박자는 ${LIMITS.BPM_MIN}~${LIMITS.BPM_MAX}보/분만 보낼 수 있어요`;
  if (!robot.status || robot.online !== true) return "로봇이 연결돼 있지 않아요";
  const s = robot.status;
  if (!s.esp32_ok) return "MechDog 몸(ESP32)이 응답하지 않아요";
  if (s.robot_tipped) return "로봇이 넘어져 있어요. 먼저 세워 주세요";
  if (s.mode === "alarm" || s.mode === "medication") return "로봇이 경보·복약 알림 중이에요";
  if (has(s.dog_battery_pct) && s.dog_battery_pct < 20) return "MechDog 배터리가 20% 미만이에요";
  return null;
}
export const COMMAND_ERROR = {
  not_connected: "로봇 원격 명령 통로가 아직 연동되지 않았어요 (팀 합의 대기). 로봇에서 \"출발\"·\"멈춰\" 음성이나 터치로 조작하세요.",
  robot_offline: "로봇이 오프라인이라 명령을 보내지 못했어요.",
  timeout: "로봇이 응답하지 않았어요 (시간 초과). 로봇 상태를 확인하세요.",
  rejected: "로봇이 명령을 거절했어요.",
  network: "인터넷 연결이 끊겨 명령을 보내지 못했어요.",
};

// ── 7일 통계 (rpc daily_stats) → 화면 배열 ──
export function dailyView(stats){
  const days = stats?.days || [];
  const pick = f => days.map(f);
  return {
    days: pick(d => d.day),
    voiceDb: pick(d => d.voice?.peak_db ?? null), voiceTarget: pick(d => d.voice?.target_db ?? null),
    walkSessions: pick(d => d.gait?.sessions ?? 0), walkMinutes: pick(d => Number(d.gait?.minutes ?? 0)),
    walkBpm: pick(d => d.gait?.avg_bpm ?? null), restarts: pick(d => d.gait?.restart_count ?? 0),
    dosesScheduled: pick(d => d.medication?.scheduled ?? 0), dosesTaken: pick(d => d.medication?.confirmed ?? 0),
    speakerRate: pick(d => d.speaker?.success_rate_pct ?? null),
    registeredSpeakers: stats?.registered_speakers ?? null,
  };
}
export const anyValue = arr => arr.some(v => has(v) && v !== 0);

// ── 오류 → 사용자 문장 ──
export function errorMessage(err){
  const code = err?.code, msg = String(err?.message || err || "");
  if (/max 8/.test(msg)) return `복약 알림은 최대 ${LIMITS.DOSES_MAX}개예요`;
  if (/min 1/.test(msg)) return "복약 알림은 최소 1개는 있어야 해요";
  if (code === "23505") return "같은 시각의 복약 알림이 이미 있어요";
  if (code === "23514") return "허용 범위를 벗어난 값이에요";
  if (code === "42501" || /not allowed|permission denied/i.test(msg)) return "권한이 없어요 (돌봄팀에 등록된 계정인지 확인하세요)";
  if (code === "PGRST301" || /JWT|token/i.test(msg)) return "로그인이 만료됐어요. 다시 로그인해 주세요";
  if (err?.name === "NetworkError" || /fetch|network|Failed to fetch|timeout/i.test(msg)) return "인터넷 연결을 확인해 주세요";
  return msg || "알 수 없는 오류";
}
export const isNetworkError = err => err?.name === "NetworkError" || /Failed to fetch|NetworkError|network|timeout/i.test(String(err?.message || err || ""));

// ── 형식 ──
export function fmtDuration(msv){
  if (msv == null || msv < 0) return "-";
  const s = Math.round(msv / 1000);
  if (s < 60) return `${s}초`;
  if (s < 3600) return `${Math.floor(s / 60)}분 ${s % 60}초`;
  return `${Math.floor(s / 3600)}시간 ${Math.floor((s % 3600) / 60)}분`;
}
export const fmtAge = s => s == null ? "-" : s < 2 ? "방금" : s < 60 ? `${Math.round(s)}초 전` : s < 3600 ? `${Math.round(s / 60)}분 전` : `${Math.round(s / 3600)}시간 전`;
