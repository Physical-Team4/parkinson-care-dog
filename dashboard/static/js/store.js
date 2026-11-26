// 데이터 소스 선택 (팀 규칙의 adapter + mock 구조와 같은 방식).
// 화면은 store의 같은 함수만 부른다 → Supabase / Mock을 바꿔도 화면 코드는 같다.
//
// store 공통 함수 (모두 async, 실패하면 throw):
//   session() signIn(email, pw) signOut() isCareTeam()
//   listAlerts() ackAlert(id, note) onAlertsChange(cb, onStatus) → unsubscribe()
//   robotLatest() followHistory(sinceMs)
//   getSettings() updateSettings(patch)
//   listSchedule() addSchedule(row) updateSchedule(id, patch) deleteSchedule(id)
//   medicationLogs(sinceIso) dailyStats(days) alertsSince(sinceIso)
//   subscribePose({onPose, onState}) → {close()}       (자세 보기를 열었을 때만)
//   sendRhythmCommand(cmd, {bpm}) → {ok, error?}        ("start" | "stop")
//   mode ("supabase" | "mock"), capabilities {demo, rhythmCommands}, lastOkAt, online

export async function createStore(){
  const cfg = window.PD_CONFIG || {dataSource: "mock"};
  if (cfg.dataSource === "supabase"){
    const {SupabaseStore} = await import("./store-supabase.js");
    return new SupabaseStore(cfg);
  }
  const {MockStore} = await import("./store-mock.js");
  return new MockStore(window.PD_DEMO);
}

/** 로그인 확인. Supabase 모드에서 세션이 없으면 /login 으로 */
export async function requireLogin(store){
  if (store.mode === "mock") return true;
  try{
    if (await store.session()) return true;
  }catch(e){ /* 세션 확인 실패 → 로그인 화면에서 다시 */ }
  location.href = "/login";
  return false;
}

/** 오류 화면에 공통으로 쓰는 "데이터 소스" 표시 문구 */
export const sourceLabel = store => store.mode === "supabase" ? "실시간" : "예시 데이터 (Mock)";
