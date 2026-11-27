// Mock 데이터 소스 — Supabase·로봇 없이 화면과 흐름을 시험하는 용도 (시연 패널·가상 로봇 포함).
// DB 규칙(001~003)을 흉내 낸다: 알람 합치기(alert_rules), 복약 1~8개·시각 중복 금지, 설정 범위, 확인 메모 1번.
// ⚠ 여기 값은 실제 측정값이 아니다. 화면에는 항상 "예시 데이터 (Mock)"로 표시된다.

const STORE_KEY = "pd-dog-mock-v1";
const RULES = {   // 001_schema.sql alert_rules와 같은 값
  camera: ["critical", 30, false], no_motion: ["critical", 30, false], touch: ["critical", 30, false],
  voice: ["critical", 30, false], medication_missed: ["warning", 30, false], battery_low: ["warning", 1800, true],
  robot_tipped: ["warning", 300, true], overheat: ["warning", 300, true], disconnected: ["warning", 300, true],
  test: ["critical", 30, false],
};
const COMMAND_DELAY_MS = 500;

function safeStorage(){
  try{ const s = window.localStorage; s.getItem("x"); return s; }catch(e){ return null; }
}
const clone = v => JSON.parse(JSON.stringify(v));
const dbError = (code, message) => Object.assign(new Error(message), {code});

export class MockStore {
  constructor(demo, {storage = (typeof window !== "undefined" ? safeStorage() : null), now = () => Date.now(),
                     commandDelayMs = COMMAND_DELAY_MS} = {}){
    this.mode = "mock";
    this.capabilities = {demo: true, rhythmCommands: true};
    this.demoData = demo || {doses: [["08:00", "아침 약"]], week: {}, voiceId: {}};
    this.storage = storage; this.now = now; this.commandDelayMs = commandDelayMs;
    this.lastOkAt = 0; this.online = true;
    this.state = this._load() || this._seed();
    this.status = null; this.hist = [];
    this.robotNet = true; this.outbox = [];          // 로봇 인터넷 끊김 흉내 (Pi 대기열)
    this.dashboardNet = true;                        // 대시보드 인터넷 끊김 흉내
    this.commandFail = null; this.rhythm = null;     // 리듬 명령 실패 흉내 / 적용된 명령
    this.alertListeners = new Set(); this.poseSubs = new Set();
    this.demo = this._demoApi();
  }

  _seed(){
    const week = this.demoData.week || {};
    return {
      nextId: 1, alerts: [],
      settings: {target_bpm: 96, target_db: week.voiceTarget || 68, follow_limit_cm: 150, updated_at: null},
      schedule: (this.demoData.doses || []).map(([t, name], i) => ({id: i + 1, time_of_day: t + ":00", name, enabled: true, updated_at: null})),
      nextScheduleId: (this.demoData.doses || []).length + 1,
    };
  }
  _load(){
    if (!this.storage) return null;
    try{ const s = JSON.parse(this.storage.getItem(STORE_KEY)); return s && s.schedule ? s : null; }catch(e){ return null; }
  }
  _save(){
    if (!this.storage) return;
    try{ this.storage.setItem(STORE_KEY, JSON.stringify(this.state)); }catch(e){ /* 저장 공간 없음 → 이번 접속에서만 유지 */ }
  }
  _check(){
    if (!this.dashboardNet){ this.online = false; const e = new Error("Failed to fetch"); e.name = "NetworkError"; throw e; }
    this.lastOkAt = this.now(); this.online = true;
  }
  _iso(t = this.now()){ return new Date(t).toISOString(); }

  // ── 로그인 (Mock은 로그인 없음) ──
  async session(){ return {user: {email: "mock@local"}}; }
  async signIn(){}
  async signOut(){}
  async isCareTeam(){ this._check(); return true; }

  // ── 알람 ──
  async listAlerts(){ this._check(); return clone(this.state.alerts); }
  async alertsSince(sinceIso){ this._check(); return clone(this.state.alerts.filter(a => a.occurred_at >= sinceIso)); }
  async ackAlert(id, note){
    this._check();
    const a = this.state.alerts.find(x => x.id === id);
    if (!a || a.acknowledged_at) return false;                  // ack_alert: 처음 1번만
    a.acknowledged_at = this._iso(); a.ack_note = (note || "").trim().slice(0, 200) || null;
    this._save(); this._emit(a);
    return true;
  }
  onAlertsChange(cb, onStatus = () => {}){
    this.alertListeners.add(cb); onStatus("SUBSCRIBED");
    return () => this.alertListeners.delete(cb);
  }
  _emit(row){ for (const cb of this.alertListeners) cb(clone(row)); }

  /** report_alert 흉내: 같은 source가 창 안이면 merged_count+1 */
  _report(source, confidence, occurredMs, detail = null, simulated = true){
    const [severity, windowS, mergeAcked] = RULES[source] || RULES.test;
    const ex = this.state.alerts
      .filter(a => a.source === source && (mergeAcked || !a.acknowledged_at)
                   && Math.abs(Date.parse(a.occurred_at) - occurredMs) < windowS * 1000)
      .sort((a, b) => b.occurred_at.localeCompare(a.occurred_at))[0];
    if (ex){
      ex.merged_count += 1; ex.last_seen_at = this._iso(Math.max(Date.parse(ex.last_seen_at), occurredMs));
      if (confidence != null) ex.confidence = Math.max(ex.confidence ?? 0, confidence);
      this._save(); this._emit(ex);
      return {alert_id: ex.id, merged: true, duplicate: false};
    }
    const row = {id: this.state.nextId++, source, severity, confidence: source === "camera" ? confidence ?? null : null,
                 detail, occurred_at: this._iso(occurredMs), received_at: this._iso(), last_seen_at: this._iso(occurredMs),
                 merged_count: 1, acknowledged_at: null, ack_note: null, simulated};
    this.state.alerts.push(row);
    this._save(); this._emit(row);
    return {alert_id: row.id, merged: false, duplicate: false};
  }

  // ── 로봇 상태 ──
  async robotLatest(){
    this._check();
    if (!this.status) return null;
    return {...clone(this.status), connected: this.now() - Date.parse(this.status.received_at) <= 10_000};
  }
  async followHistory(sinceMs){
    this._check();
    return this.hist.filter(h => Date.parse(h.received_at) > sinceMs).map(h => ({...h}));
  }

  // ── 설정 ──
  async getSettings(){ this._check(); return clone(this.state.settings); }
  async updateSettings(patch){
    this._check();
    const range = {target_bpm: [80, 110], target_db: [50, 90], follow_limit_cm: [50, 300]};
    for (const [k, v] of Object.entries(patch)){
      if (!range[k]) throw dbError("42501", "permission denied for column " + k);
      if (!Number.isInteger(v) || v < range[k][0] || v > range[k][1]) throw dbError("23514", "check constraint " + k);
    }
    Object.assign(this.state.settings, patch, {updated_at: this._iso()});
    this._save();
    return clone(this.state.settings);
  }

  // ── 복약 일정 ──
  async listSchedule(){
    this._check();
    return clone(this.state.schedule).sort((a, b) => a.time_of_day.localeCompare(b.time_of_day));
  }
  _normTime(t){ return t && t.length === 5 ? t + ":00" : t; }
  _uniqueTime(t, exceptId){
    if (this.state.schedule.some(s => s.id !== exceptId && s.time_of_day === t))
      throw dbError("23505", "duplicate key value violates unique constraint");
  }
  async addSchedule(row){
    this._check();
    if (this.state.schedule.length >= 8) throw dbError("P0001", "medication schedule: max 8 times");
    const t = this._normTime(row.time_of_day); this._uniqueTime(t, null);
    const s = {id: this.state.nextScheduleId++, time_of_day: t, name: row.name ?? null,
               enabled: row.enabled ?? true, updated_at: this._iso()};
    this.state.schedule.push(s); this._save();
    return clone(s);
  }
  async updateSchedule(id, patch){
    this._check();
    const s = this.state.schedule.find(x => x.id === id);
    if (!s) throw dbError("PGRST116", "not found");
    if (patch.time_of_day){ patch = {...patch, time_of_day: this._normTime(patch.time_of_day)}; this._uniqueTime(patch.time_of_day, id); }
    Object.assign(s, patch, {updated_at: this._iso()}); this._save();
    return clone(s);
  }
  async deleteSchedule(id){
    this._check();
    if (this.state.schedule.length <= 1) throw dbError("P0001", "medication schedule: min 1 time");
    this.state.schedule = this.state.schedule.filter(x => x.id !== id); this._save();
  }

  /** 예시 복약 기록: demo-data의 하루 복용 횟수만큼 앞 시각부터 확인, 나머지는 미확인 */
  _logs(){
    const out = [], now = this.now(), taken = this.demoData.week?.dosesTaken || [];
    const doses = this.state.schedule.filter(s => s.enabled).sort((a, b) => a.time_of_day.localeCompare(b.time_of_day));
    for (let back = 6; back >= 0; back--){
      const k = taken[taken.length - 1 - back] ?? doses.length;
      doses.forEach((s, i) => {
        const [h, m] = s.time_of_day.split(":").map(Number);
        const due = new Date(now); due.setDate(due.getDate() - back); due.setHours(h, m, 0, 0);
        const t = due.getTime();
        if (t > now) return;
        const status = now - t < 30 * 60_000 ? "pending" : i < k ? "confirmed" : "missed";
        out.push({id: out.length + 1, schedule_id: s.id, due_at: new Date(t).toISOString(), status,
                  confirmed_at: status === "confirmed" ? new Date(t + 3 * 60_000).toISOString() : null,
                  method: status === "confirmed" ? "touch" : null});
      });
    }
    return out;
  }
  async medicationLogs(sinceIso){ this._check(); return this._logs().filter(l => l.due_at >= sinceIso).reverse(); }

  async dailyStats(days = 7){
    this._check();
    const w = this.demoData.week || {}, logs = this._logs(), out = [];
    for (let i = days - 1; i >= 0; i--){
      const d = new Date(this.now()); d.setDate(d.getDate() - i);
      const day = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      const idx = (w.voiceDb?.length || 7) - 1 - i;
      const dayLogs = logs.filter(l => { const x = new Date(l.due_at); return x.toDateString() === d.toDateString(); });
      out.push({day,
        medication: {scheduled: dayLogs.length, confirmed: dayLogs.filter(l => l.status === "confirmed").length},
        gait: {sessions: w.walkSessions?.[idx] ?? 0, minutes: w.walkMinutes?.[idx] ?? 0, avg_bpm: w.walkBpm?.[idx] ?? null,
               restart_count: w.restarts?.[idx] ?? 0},
        voice: {peak_db: w.voiceDb?.[idx] ?? null, target_db: w.voiceTarget ?? null},
        speaker: {success_rate_pct: this.demoData.voiceId?.successRate ?? null}});
    }
    return {registered_speakers: this.demoData.voiceId?.registered ?? 0, days: out};
  }

  // ── 자세: 구독자가 있을 때만 가상 로봇이 보낸다 ──
  subscribePose({onPose, onState}){
    const sub = {onPose, onState};
    const t = setTimeout(() => {
      if (!this.dashboardNet){ onState("CHANNEL_ERROR", new Error("Failed to fetch")); return; }
      this.poseSubs.add(sub); onState("SUBSCRIBED");
    }, 200);
    return {close: () => { clearTimeout(t); this.poseSubs.delete(sub); }};
  }
  get poseViewers(){ return this.poseSubs.size; }

  // ── 리듬 큐잉 명령 (Mock: 실제 장치 없음) ──
  async sendRhythmCommand(cmd, {bpm} = {}){
    await new Promise(r => setTimeout(r, this.commandDelayMs));
    if (!this.dashboardNet) return {ok: false, error: "network"};
    const live = this.status && this.robotNet && this.now() - Date.parse(this.status.received_at) <= 10_000;
    if (!live) return {ok: false, error: "robot_offline"};
    if (this.commandFail) return {ok: false, error: this.commandFail};
    if (cmd === "start"){
      if (!Number.isInteger(bpm) || bpm < 80 || bpm > 110) return {ok: false, error: "rejected"};
      this.rhythm = {mode: "walking", bpm};
    } else if (cmd === "stop") this.rhythm = {mode: "idle", bpm: null};
    else return {ok: false, error: "rejected"};
    if (this.status) Object.assign(this.status, {mode: this.rhythm.mode, bpm: this.rhythm.bpm});
    return {ok: true};
  }

  // ── 시연 패널 · 가상 로봇 ──
  _demoApi(){
    const self = this;
    return {
      /** 알람 보내기 (로봇 오프라인이면 로봇 대기열에 쌓임) */
      raiseAlert(source, confidence = null){
        if (!self.robotNet){ self.outbox.push({source, confidence, at: self.now()}); return {queued: true}; }
        return self._report(source, confidence, self.now());
      },
      /** 상태 보내기 (Pi 2초 주기 흉내). 로봇 오프라인이면 버림 (status는 대기열 없음) */
      pushStatus(row){
        if (!self.robotNet) return false;
        const s = {...row, received_at: self._iso()};
        if (self.rhythm) Object.assign(s, {mode: self.rhythm.mode, bpm: self.rhythm.bpm});
        self.status = s;
        self.hist.push({received_at: s.received_at, follow_distance_cm: s.follow_distance_cm ?? null});
        while (self.hist.length && self.now() - Date.parse(self.hist[0].received_at) > 60_000) self.hist.shift();
        // 002 robot_status_rules 흉내
        if (s.dog_battery_pct < 20 || s.pi_battery_pct < 20) self._report("battery_low", null, self.now());
        if (s.robot_tipped) self._report("robot_tipped", null, self.now());
        if (s.pi_temp_c >= 75) self._report("overheat", null, self.now());
        return true;
      },
      pushPose(pose){
        if (!self.robotNet || !self.poseSubs.size) return false;   // 보는 사람이 없으면 보내지 않음
        for (const sub of self.poseSubs) sub.onPose(clone(pose));
        return true;
      },
      setRobotNet(on){
        self.robotNet = on;
        if (on){   // 재연결 → 대기열 순서대로 재전송 (발생 시각 유지, 도착 시각은 지금)
          const q = self.outbox.splice(0);
          q.forEach(x => self._report(x.source, x.confidence, x.at));
          return q.length;
        }
        return 0;
      },
      setDashboardNet(on){ self.dashboardNet = on; },
      setCommandFail(kind){ self.commandFail = kind; },
      get robotNet(){ return self.robotNet; },
      get dashboardNet(){ return self.dashboardNet; },
      get queued(){ return self.outbox.length; },
      reset(){ self.state = self._seed(); self._save(); },
    };
  }
}
