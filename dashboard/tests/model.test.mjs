// node --test dashboard/tests   (Model: 순수 함수)
import test from "node:test";
import assert from "node:assert/strict";
import * as M from "../static/js/model.js";

const row = (o = {}) => ({id: 1, source: "camera", severity: "critical", confidence: 0.9, occurred_at: "2026-11-26T01:00:00Z",
  received_at: "2026-11-26T01:00:01Z", last_seen_at: "2026-11-26T01:00:00Z", merged_count: 1, acknowledged_at: null, ack_note: null, ...o});

test("toEvent: 팀 스키마 → 기존 화면 이름 (created_at·status·note)", () => {
  const e = M.toEvent(row({acknowledged_at: "2026-11-26T01:01:00Z", ack_note: "확인함"}));
  assert.equal(e.created_at, "2026-11-26T01:00:00Z");
  assert.equal(e.status, "acknowledged");
  assert.equal(e.note, "확인함");
  assert.equal(e.level, "crit");
  assert.equal(e.delayed_ms, 0);
});

test("toEvent: 등급은 severity 기준, 늦게 도착(대기열) 표시", () => {
  const e = M.toEvent(row({source: "battery_low", severity: "warning", received_at: "2026-11-26T01:10:00Z"}));
  assert.equal(e.level, "warn");
  assert.equal(e.delayed_ms, 10 * 60 * 1000);
});

test("mergeAlerts: 폴링·Realtime으로 같은 id가 와도 1건, 최신값으로 갱신", () => {
  const map = new Map();
  M.mergeAlerts(map, [row(), row({id: 2, occurred_at: "2026-11-26T02:00:00Z"})]);
  const out = M.mergeAlerts(map, [row({merged_count: 3}), row()]);
  assert.equal(out.length, 2);
  assert.equal(out[0].id, 2);                       // 최신순
  assert.equal(out.find(e => e.id === 1).merged_count, 1);   // 마지막으로 온 값
  const again = M.mergeAlerts(map, [row({acknowledged_at: "2026-11-26T03:00:00Z"})]);
  assert.equal(again.find(e => e.id === 1).status, "acknowledged");
});

test("alertsView: 50건 밖의 오래된 미확인 알람도 빠지지 않음", () => {
  const evs = Array.from({length: 60}, (_, i) => M.toEvent(row({id: i + 1, occurred_at: new Date(Date.UTC(2026, 10, 26, 0, 60 - i)).toISOString(),
    acknowledged_at: i === 59 ? null : "2026-11-26T05:00:00Z"})));
  const v = M.alertsView(evs);
  assert.equal(v.unacknowledged, 1);
  assert.ok(v.events.some(e => e.id === 60));
  assert.equal(v.events.length, 51);
});

test("robotView: connected·나이, 조회 실패면 알 수 없음(null)", () => {
  const now = Date.parse("2026-11-26T01:00:05Z");
  assert.equal(M.robotView({received_at: "2026-11-26T01:00:00Z", connected: true}, now).online, true);
  assert.equal(M.robotView({received_at: "2026-11-26T01:00:00Z", connected: false}, now).online, false);
  assert.equal(M.robotView(null, now).online, false);
  assert.equal(M.robotView({received_at: "2026-11-26T01:00:00Z"}, now, false).online, null);
  assert.equal(M.robotView({received_at: "2026-11-26T00:59:00Z"}, now).online, false);   // connected 없으면 10초 기준
});

test("connectionRows: 안 보낸 값은 측정값처럼 보이지 않게 미연동/데이터 없음", () => {
  const v = {status: {esp32_ok: true, mode: "walking", dog_battery_pct: null, pi_battery_pct: 55, pi_charging: null, received_at: "x"}, online: true};
  const c = M.connectionRows(v);
  assert.deepEqual(c.dogBattery, ["none", "미연동 (ESP32가 아직 안 보냄)"]);
  assert.deepEqual(c.piBattery, ["value", 55]);
  assert.equal(c.charging[0], "none");
  assert.equal(c.esp[0], "ok");
  const off = M.connectionRows({...v, online: false});
  assert.equal(off.esp[0], "unknown");
  assert.equal(off.mode, "-");
  // 로봇 충전 중: ESP32가 외부 전원을 감지하면 mode "charging" + 잔량 null
  const chg = M.connectionRows({...v, status: {...v.status, mode: "charging"}});
  assert.equal(chg.mode, "충전 중");
  assert.match(chg.dogBattery[1], /충전 중/);
  assert.deepEqual(M.connectionRows({...v, status: {...v.status, mode: "charging", dog_battery_pct: 80}}).dogBattery, ["value", 80]);
});

test("syncView: 대시보드 오프라인 / 로봇 오프라인 / 정상 + 지연 도착 건수", () => {
  const now = Date.parse("2026-11-26T02:00:00Z");
  const evs = [M.toEvent(row({received_at: "2026-11-26T01:30:00Z"}))];
  assert.equal(M.syncView({dashboardOnline: false, robot: {status: {}}, events: evs, nowMs: now}).state, "dashboard_offline");
  assert.equal(M.syncView({dashboardOnline: true, robot: {status: null}, events: [], nowMs: now}).state, "never");
  assert.equal(M.syncView({dashboardOnline: true, robot: {status: {}, online: false}, events: [], nowMs: now}).state, "robot_offline");
  const ok = M.syncView({dashboardOnline: true, robot: {status: {}, online: true}, events: evs, nowMs: now});
  assert.equal(ok.state, "synced");
  assert.equal(ok.delayedCount, 1);
});

test("medicationToday: 기록이 있으면 기록대로, 없으면 지어내지 않음", () => {
  const now = new Date(2026, 10, 26, 13, 0);
  const schedule = [{id: 1, time_of_day: "08:00:00", name: "아침 약", enabled: true},
                    {id: 2, time_of_day: "12:30:00", name: "점심 약", enabled: true},
                    {id: 3, time_of_day: "18:00:00", name: "저녁 약", enabled: true},
                    {id: 4, time_of_day: "22:00:00", name: "", enabled: false}];
  const logs = [{schedule_id: 1, due_at: new Date(2026, 10, 26, 8, 0).toISOString(), status: "confirmed", confirmed_at: new Date(2026, 10, 26, 8, 3).toISOString(), method: "touch"},
                {schedule_id: 1, due_at: new Date(2026, 10, 25, 8, 0).toISOString(), status: "missed"}];   // 어제 기록은 무시
  const r = M.medicationToday(schedule, logs, now);
  assert.deepEqual(r.map(x => x.status), ["confirmed", "nolog", "upcoming", "off"]);
  assert.equal(r[0].method, "touch");
});

test("validateDose: 형식·중복·이름 길이·최대 8개", () => {
  const sch = [{id: 1, time_of_day: "08:00:00"}];
  assert.equal(M.validateDose({time_of_day: "09:00", name: "약"}, sch), null);
  assert.match(M.validateDose({time_of_day: "08:00"}, sch), /이미/);
  assert.equal(M.validateDose({time_of_day: "08:00"}, sch, 1), null);          // 자기 자신은 중복 아님
  assert.match(M.validateDose({time_of_day: "25:00"}, sch), /HH:MM/);
  assert.match(M.validateDose({time_of_day: "09:00", name: "가".repeat(21)}, sch), /20자/);
  const full = Array.from({length: 8}, (_, i) => ({id: i, time_of_day: `0${i}:00:00`}));
  assert.match(M.validateDose({time_of_day: "09:00"}, full), /최대 8/);
});

test("rhythmStartBlock: 팀 안전 조건 (범위·연결·ESP32·넘어짐·배터리)", () => {
  const ok = {status: {esp32_ok: true, robot_tipped: false, mode: "idle", dog_battery_pct: 60}, online: true};
  assert.equal(M.rhythmStartBlock(ok, 96), null);
  assert.match(M.rhythmStartBlock(ok, 120), /80~110/);
  assert.match(M.rhythmStartBlock({...ok, online: false}, 96), /연결/);
  assert.match(M.rhythmStartBlock({...ok, status: {...ok.status, esp32_ok: false}}, 96), /ESP32/);
  assert.match(M.rhythmStartBlock({...ok, status: {...ok.status, robot_tipped: true}}, 96), /넘어져/);
  assert.match(M.rhythmStartBlock({...ok, status: {...ok.status, dog_battery_pct: 10}}, 96), /배터리/);
  assert.equal(M.rhythmStartBlock({...ok, status: {...ok.status, dog_battery_pct: null}}, 96), null);   // 미연동은 막지 않음
});

test("validSetting: DB CHECK 범위와 같음", () => {
  assert.ok(M.validSetting("target_bpm", 80) && M.validSetting("target_bpm", 110));
  assert.ok(!M.validSetting("target_bpm", 111) && !M.validSetting("target_bpm", 95.5));
  assert.ok(M.validSetting("follow_limit_cm", 300) && !M.validSetting("follow_limit_cm", 40));
  assert.ok(!M.validSetting("unknown", 1));
});

test("dailyView: daily_stats 형식(docs/api.md) → 배열, 없는 값은 null 유지", () => {
  const v = M.dailyView({registered_speakers: 2, days: [
    {day: "2026-11-25", medication: {scheduled: 4, confirmed: 3}, gait: {sessions: 0, minutes: 0, avg_bpm: null, restart_count: 0}, voice: {peak_db: null, target_db: null}, speaker: {success_rate_pct: null}},
    {day: "2026-11-26", medication: {scheduled: 4, confirmed: 4}, gait: {sessions: 2, minutes: 18.5, avg_bpm: 95.2, restart_count: 3}, voice: {peak_db: 71.4, target_db: 68}, speaker: {success_rate_pct: 92}}]});
  assert.deepEqual(v.voiceDb, [null, 71.4]);
  assert.deepEqual(v.walkMinutes, [0, 18.5]);
  assert.equal(v.registeredSpeakers, 2);
  assert.ok(M.anyValue(v.walkSessions));
  assert.ok(!M.anyValue([0, null]));
});

test("errorMessage: DB 오류 코드 → 쉬운 문장", () => {
  assert.match(M.errorMessage({code: "P0001", message: "medication schedule: max 8 times"}), /최대 8/);
  assert.match(M.errorMessage({code: "P0001", message: "medication schedule: min 1 time"}), /최소 1/);
  assert.match(M.errorMessage({code: "23505", message: "dup"}), /이미/);
  assert.match(M.errorMessage({code: "42501", message: "not allowed"}), /권한/);
  assert.match(M.errorMessage({name: "NetworkError", message: "Failed to fetch"}), /인터넷/);
  assert.ok(M.isNetworkError(new TypeError("Failed to fetch")));
});
