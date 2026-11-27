// node --test dashboard/tests   (Mock store: DB 규칙 흉내·오프라인·명령)
import test from "node:test";
import assert from "node:assert/strict";
import {MockStore} from "../static/js/store-mock.js";
import * as M from "../static/js/model.js";

const DEMO = {doses: [["08:00", "아침 약"], ["12:30", "점심 약"]], week: {voiceTarget: 68, dosesTaken: [2, 2, 2, 2, 2, 2, 1]}, voiceId: {registered: 3, successRate: 90}};
function make(){
  let t = Date.parse("2026-11-26T03:00:00Z");
  const clock = {now: () => t, advance: s => { t += s * 1000; }};
  const store = new MockStore(DEMO, {storage: null, now: clock.now, commandDelayMs: 0});
  return {store, clock};
}

test("복약 알림 추가·수정·삭제 + DB 규칙 (중복 시각·최대 8개·최소 1개)", async () => {
  const {store} = make();
  const added = await store.addSchedule({time_of_day: "18:00", name: "저녁 약", enabled: true});
  assert.equal(added.time_of_day, "18:00:00");
  await assert.rejects(store.addSchedule({time_of_day: "18:00", name: "x"}), e => e.code === "23505");
  const upd = await store.updateSchedule(added.id, {name: "저녁 혈압약", enabled: false});
  assert.equal(upd.name, "저녁 혈압약"); assert.equal(upd.enabled, false);
  for (let h = 1; h <= 5; h++) await store.addSchedule({time_of_day: `0${h}:00`});
  await assert.rejects(store.addSchedule({time_of_day: "23:00"}), e => /max 8/.test(e.message));
  const all = await store.listSchedule();
  assert.equal(all.length, 8);
  for (const s of all.slice(1)) await store.deleteSchedule(s.id);
  await assert.rejects(store.deleteSchedule(all[0].id), e => /min 1/.test(e.message));
});

test("설정은 DB 범위 밖이면 거절, 허용 컬럼만", async () => {
  const {store} = make();
  const s = await store.updateSettings({target_bpm: 100});
  assert.equal(s.target_bpm, 100);
  await assert.rejects(store.updateSettings({target_bpm: 130}), e => e.code === "23514");
  await assert.rejects(store.updateSettings({updated_by: "x"}), e => e.code === "42501");
});

test("알람 합치기 (30초 창) + 확인 메모는 처음 1번만", async () => {
  const {store, clock} = make();
  store.demo.raiseAlert("touch");
  clock.advance(10);
  const r = store.demo.raiseAlert("touch");
  assert.equal(r.merged, true);
  const [a] = await store.listAlerts();
  assert.equal(a.merged_count, 2);
  assert.equal(await store.ackAlert(a.id, "직접 확인"), true);
  assert.equal(await store.ackAlert(a.id, "다른 메모"), false);
  assert.equal((await store.listAlerts())[0].ack_note, "직접 확인");
});

test("로봇 오프라인: 알람은 대기열, 재연결하면 발생 시각 유지 → 늦게 도착", async () => {
  const {store, clock} = make();
  store.demo.setRobotNet(false);
  assert.equal(store.demo.raiseAlert("camera", 0.9).queued, true);
  assert.equal(store.demo.pushStatus({esp32_ok: true}), false);           // status는 버림
  assert.equal((await store.listAlerts()).length, 0);
  clock.advance(300);
  assert.equal(store.demo.setRobotNet(true), 1);
  const [ev] = (await store.listAlerts()).map(M.toEvent);
  assert.equal(ev.delayed_ms, 300_000);
});

test("대시보드 오프라인: 모든 조회가 네트워크 오류, 다시 연결되면 정상", async () => {
  const {store} = make();
  store.demo.setDashboardNet(false);
  await assert.rejects(store.listAlerts(), e => M.isNetworkError(e));
  assert.equal(store.online, false);
  store.demo.setDashboardNet(true);
  await store.listAlerts();
  assert.equal(store.online, true);
});

test("로봇 연결: 10초 지나면 connected=false, 서버 규칙(배터리 < 20%) 알람", async () => {
  const {store, clock} = make();
  store.demo.pushStatus({esp32_ok: true, dog_battery_pct: 15});
  assert.equal((await store.robotLatest()).connected, true);
  assert.equal((await store.listAlerts())[0].source, "battery_low");
  clock.advance(11);
  assert.equal((await store.robotLatest()).connected, false);
});

test("자세: 보는 사람이 있을 때만 전달, 닫으면 중단", async () => {
  const {store} = make();
  const got = [];
  assert.equal(store.demo.pushPose({state: "standing"}), false);           // 구독 전 → 안 보냄
  const sub = store.subscribePose({onPose: p => got.push(p), onState: () => {}});
  await new Promise(r => setTimeout(r, 250));
  assert.equal(store.poseViewers, 1);
  assert.equal(store.demo.pushPose({state: "standing"}), true);
  sub.close();
  assert.equal(store.demo.pushPose({state: "lying"}), false);
  assert.equal(got.length, 1);
});

test("리듬 큐잉 명령: 성공·로봇 오프라인·실패·범위", async () => {
  const {store, clock} = make();
  assert.deepEqual(await store.sendRhythmCommand("start", {bpm: 96}), {ok: false, error: "robot_offline"});
  store.demo.pushStatus({esp32_ok: true, mode: "idle"});
  assert.deepEqual(await store.sendRhythmCommand("start", {bpm: 96}), {ok: true});
  assert.equal((await store.robotLatest()).mode, "walking");
  assert.equal((await store.sendRhythmCommand("start", {bpm: 150})).error, "rejected");
  store.demo.setCommandFail("timeout");
  assert.equal((await store.sendRhythmCommand("stop")).error, "timeout");
  store.demo.setCommandFail(null);
  assert.deepEqual(await store.sendRhythmCommand("stop"), {ok: true});
  clock.advance(20);
  assert.equal((await store.sendRhythmCommand("stop")).error, "robot_offline");
});

test("daily_stats 형식 그대로 (7일, 복약은 일정 기준 예시 기록)", async () => {
  const {store} = make();
  const st = await store.dailyStats(7);
  assert.equal(st.days.length, 7);
  assert.equal(st.registered_speakers, 3);
  const v = M.dailyView(st);
  assert.ok(v.dosesScheduled.slice(0, 6).every(n => n === 2));
});
