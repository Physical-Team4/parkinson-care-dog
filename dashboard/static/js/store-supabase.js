// 실제 연동: Supabase (docs/api.md "대시보드 ← Supabase"). anon 키 + 로그인 세션만 사용 → RLS(care_team) 안에서 동작.
// service_role 키는 여기 절대 넣지 않는다 (CLAUDE.md).
import {createClient} from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/+esm";

const TIMEOUT_MS = 8000;
const POSE_TOPIC = "robot:pose", POSE_EVENT = "pose";   // 004_realtime_cron.sql, pi/app/config.py pose_topic

function fetchWithTimeout(url, opts = {}){
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  if (opts.signal) opts.signal.addEventListener("abort", () => ctrl.abort());
  return fetch(url, {...opts, signal: ctrl.signal})
    .catch(e => { const err = new Error(e.name === "AbortError" ? "timeout" : "Failed to fetch"); err.name = "NetworkError"; throw err; })
    .finally(() => clearTimeout(timer));
}

export class SupabaseStore {
  constructor(cfg){
    this.mode = "supabase";
    this.capabilities = {demo: false, rhythmCommands: false};   // 원격 보행 명령 통로 없음 (PROJECT_PLAN.md 1-3 #9)
    this.sb = createClient(cfg.supabaseUrl, cfg.supabaseAnonKey, {
      auth: {persistSession: true, autoRefreshToken: true},
      global: {fetch: fetchWithTimeout},
    });
    this.lastOkAt = 0;
    this.online = true;
  }

  async _q(builder){
    let res;
    try{ res = await builder; }
    catch(e){ this.online = false; throw e; }
    if (res.error){
      if (/Failed to fetch|NetworkError|timeout/i.test(res.error.message || "")) this.online = false;
      throw res.error;
    }
    this.lastOkAt = Date.now(); this.online = true;
    return res.data;
  }

  // ── 로그인 (Supabase Auth, 공개 가입 끔 → 초대받은 계정만) ──
  async session(){ return (await this.sb.auth.getSession()).data.session; }
  async signIn(email, password){
    const {error} = await this.sb.auth.signInWithPassword({email, password});
    if (error) throw error;
  }
  async signOut(){ await this.sb.auth.signOut(); }
  async isCareTeam(){ return !!(await this._q(this.sb.rpc("is_care_team"))); }

  // ── 알람 ──
  async listAlerts(){
    const cols = "id,source,severity,confidence,occurred_at,received_at,last_seen_at,merged_count,acknowledged_at,ack_note";
    const [recent, open] = await Promise.all([
      this._q(this.sb.from("alerts").select(cols).order("occurred_at", {ascending: false}).limit(50)),
      this._q(this.sb.from("alerts").select(cols).is("acknowledged_at", null).order("occurred_at", {ascending: false}).limit(200)),
    ]);
    return [...recent, ...open];
  }
  async alertsSince(sinceIso){
    return this._q(this.sb.from("alerts")
      .select("id,source,severity,confidence,occurred_at,received_at,merged_count,acknowledged_at,ack_note")
      .gte("occurred_at", sinceIso).order("occurred_at", {ascending: false}).limit(1000));
  }
  async ackAlert(id, note){
    return this._q(this.sb.rpc("ack_alert", {p_alert_id: id, p_note: note || null}));
  }
  /** Realtime postgres_changes (INSERT·UPDATE). 끊겨도 화면은 5초 확인 조회로 보완 */
  onAlertsChange(cb, onStatus = () => {}){
    const ch = this.sb.channel("alerts-changes")
      .on("postgres_changes", {event: "*", schema: "public", table: "alerts"}, p => p.new && cb(p.new))
      .subscribe(status => onStatus(status));
    return () => this.sb.removeChannel(ch);
  }

  // ── 로봇 상태 ──
  async robotLatest(){ return this._q(this.sb.from("robot_latest").select("*").maybeSingle()); }
  async followHistory(sinceMs){
    return this._q(this.sb.from("robot_status").select("received_at,follow_distance_cm")
      .gt("received_at", new Date(sinceMs).toISOString()).order("received_at", {ascending: true}).limit(60));
  }

  // ── 설정 (settings 단일 행, 컬럼 단위 권한: target_bpm·target_db·follow_limit_cm) ──
  async getSettings(){
    return this._q(this.sb.from("settings").select("target_bpm,target_db,follow_limit_cm,updated_at").eq("id", 1).single());
  }
  async updateSettings(patch){
    return this._q(this.sb.from("settings").update(patch).eq("id", 1)
      .select("target_bpm,target_db,follow_limit_cm,updated_at").single());
  }

  // ── 복약 일정 (medication_schedule: time_of_day·name·enabled, 1~8개는 DB가 막음) ──
  async listSchedule(){
    return this._q(this.sb.from("medication_schedule").select("id,time_of_day,name,enabled,updated_at").order("time_of_day"));
  }
  async addSchedule(row){
    return this._q(this.sb.from("medication_schedule").insert(row).select("id,time_of_day,name,enabled,updated_at").single());
  }
  async updateSchedule(id, patch){
    return this._q(this.sb.from("medication_schedule").update(patch).eq("id", id)
      .select("id,time_of_day,name,enabled,updated_at").single());
  }
  async deleteSchedule(id){ return this._q(this.sb.from("medication_schedule").delete().eq("id", id)); }
  async medicationLogs(sinceIso){
    return this._q(this.sb.from("medication_logs").select("id,schedule_id,due_at,status,confirmed_at,method")
      .gte("due_at", sinceIso).order("due_at", {ascending: false}).limit(500));
  }

  // ── 7일 통계 ──
  async dailyStats(days = 7){ return this._q(this.sb.rpc("daily_stats", {p_days: days})); }

  // ── 자세 (Realtime Broadcast, private). 자세 보기를 열었을 때만 구독 → 닫으면 채널 제거 ──
  subscribePose({onPose, onState}){
    let ch = null, closed = false;
    (async () => {
      const s = await this.session();
      if (s) this.sb.realtime.setAuth(s.access_token);   // private 채널은 로그인 토큰 필요 (004 정책: care_team만)
      if (closed) return;
      ch = this.sb.channel(POSE_TOPIC, {config: {private: true}})
        .on("broadcast", {event: POSE_EVENT}, m => onPose(m.payload))
        .subscribe((status, err) => onState(status, err));
    })().catch(e => onState("CHANNEL_ERROR", e));
    return {close: () => { closed = true; if (ch) this.sb.removeChannel(ch); }};
  }

  // ── 리듬 큐잉 원격 명령: 통로 미연동 (실제로 보낸 것처럼 꾸미지 않음) ──
  async sendRhythmCommand(){ return {ok: false, error: "not_connected"}; }
}
