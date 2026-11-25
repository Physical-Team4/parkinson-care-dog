# 환경 세팅

## 1. PC (Windows/macOS/Linux) — 개발·테스트
```bash
conda env create -f environment.yml
conda activate pd-dog
pre-commit install
cp .env.example .env            # Windows PowerShell: Copy-Item .env.example .env
PD_DOG_MOCK_HARDWARE=true python -m pi.main
pytest pi/tests
```
PC에서는 하드웨어·Supabase adapter 대신 mock이 동작한다 (인터넷·키 불필요).

## 2. Raspberry Pi 5

### 2-1. OS·기본 설정
- Raspberry Pi OS Lite (64-bit), 호스트명 `pd-dog`, 시간대 `Asia/Seoul` (일별 집계 기준).
- `sudo raspi-config` → I²C 켜기 (X1200 잔량 칩).
- EEPROM: `sudo rpi-eeprom-config --edit` → `PSU_MAX_CURRENT=5000` (X1200 위키에서 재확인).
- 시리얼 권한: `sudo usermod -aG dialout,video,i2c,gpio $USER` 후 재로그인.
- 시스템 패키지 (apt):
  ```bash
  sudo apt install -y python3-picamera2 --no-install-recommends
  sudo apt install -y hailo-all          # AI HAT+ 사용 시 (A의 벤치마크 결과에 따라)
  ```

### 2-2. Miniforge + conda 환경
```bash
curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-aarch64.sh
bash Miniforge3-Linux-aarch64.sh
conda env create -f environment.yml
conda activate pd-dog
```

### 2-3. ⚠️ picamera2·libcamera·hailort를 conda에서 쓰기 (확인 필요)
이 셋은 apt로 **시스템 Python**에 설치되고, conda-forge/pip에는 Pi용 빌드가 없거나 버전이 맞지 않는다.
먼저 확인 스크립트를 돌린다:
```bash
bash pi/scripts/check_pi_env.sh
```

**방법 A (먼저 시도): 시스템 dist-packages 경로 연결**
- 조건: conda 환경 Python과 시스템 Python의 **minor 버전이 같아야** 함 (`environment.yml`의 `python=` 값).
- `check_pi_env.sh --link`가 conda 환경의 site-packages에 `pd_dog_system.pth`를 만들어
  `/usr/lib/python3/dist-packages`를 경로 **맨 뒤**에 추가한다 (conda 패키지가 우선).
- 알려진 문제: conda의 `libstdc++`가 시스템 것보다 오래되면 `libcamera` import 시 `GLIBCXX_... not found`.
  → `conda install -c conda-forge "libstdcxx-ng>=13"` 또는 `LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libstdc++.so.6`.

**방법 B: Pi에서만 venv (방법 A 실패 시, 팀 상의 필요)**
```bash
python3 -m venv --system-site-packages ~/pd-dog-venv
~/pd-dog-venv/bin/pip install -r pi/requirements-pi.txt   # TODO: environment.yml에서 생성
```
- PC는 conda, Pi는 venv로 갈리게 되므로 **결정 전에 팀에 알릴 것** ([todo.md](todo.md)).

결과(어떤 방법이 됐는지, 필요한 추가 명령)를 이 섹션에 기록한다.
- [ ] picamera2 import: (결과 기록)
- [ ] libcamera import: (결과 기록)
- [ ] hailo_platform import: (결과 기록)

### 2-4. ESP32 시리얼 포트 고정 (TODO)
`/dev/ttyUSB0` 번호가 바뀔 수 있으니 udev 규칙으로 `/dev/pd-dog-esp32` 고정 예정.
`udevadm info -a /dev/ttyUSB0`로 idVendor/idProduct 확인 후 `/etc/udev/rules.d/99-pd-dog.rules` 작성.

### 2-5. 실행
```bash
bash pi/scripts/run.sh
```
자동 시작(systemd 서비스)은 TODO.

## 3. Supabase (D가 1회)
1. Supabase에서 프로젝트 생성 (리전: 서울 `ap-northeast-2` 권장).
2. SQL Editor에서 [db/migrations/](../db/migrations/) 001 → 004 순서대로 실행 ([db/README.md](../db/README.md)).
   004가 pg_cron 때문에 실패하면 Database → Extensions에서 `pg_cron` 켜고 다시 실행.
3. Authentication → Sign In / Providers: **공개 가입 끄기**. 보호자·치료사는 Users → Invite로 추가 후
   SQL Editor: `insert into care_team (user_id, role) values ('<사용자 uuid>', 'guardian');`
4. Project Settings → API Keys에서 키 확인 후 각자의 `.env`에만 넣기 (커밋 금지):
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY` → 대시보드 (새 프로젝트면 publishable 키)
   - `SUPABASE_SERVICE_ROLE_KEY` → **Pi에만** (새 프로젝트면 secret 키). 메신저·카톡 등으로 공유하지 말고 직접 입력
5. Realtime → Settings: "Allow public access" 끄기 (private 채널만 사용).
6. 적용 기록을 [decisions.md](decisions.md) "DB 적용 기록"에 남기기.

### 3-1. 로컬 Supabase로 테스트 (선택, 각자 PC)
클라우드 Supabase 없이 내 PC의 Docker에서 Supabase를 띄워 마이그레이션·RLS·API를 시험한다.
하드웨어와 무관하므로 Docker 사용 OK ([decisions.md](decisions.md) D-006). Docker Desktop 실행 필요.

```bash
# 레포 루트에서. supabase/ 폴더는 개인용 → 커밋하지 않게 .git/info/exclude에 '/supabase/' 추가
npx -y supabase@2.122.1 init --with-vscode-settings=false --with-intellij-settings=false
npx -y supabase@2.122.1 start -x storage-api,imgproxy,edge-runtime,logflare,vector,supavisor
npx -y supabase@2.122.1 status      # URL·로컬 키 확인 (로컬 전용 기본값)
npx -y supabase@2.122.1 stop        # 끄기 (데이터 유지). 지우려면 stop --no-backup
```

마이그레이션 적용 (로컬 DB 컨테이너의 psql 사용, 001 → 004 순서):
```bash
for f in db/migrations/*.sql; do
  docker exec -i supabase_db_parkinson-care-dog psql -U postgres -d postgres -v ON_ERROR_STOP=1 < "$f"
done
```
- 로컬 Studio: http://localhost:54323
- 로컬 API: http://localhost:54321 → 로컬 테스트 때만 `.env`의 `SUPABASE_URL`·키를 `status`에 나온 값으로

### 3-2. Claude Code에 로컬 Supabase MCP 연결 (선택, 각자 PC)
레포 루트에 `.mcp.json`을 만든다 (`.gitignore`에 있음, 커밋 금지):
```json
{
  "mcpServers": {
    "supabase-local": { "type": "http", "url": "http://localhost:54321/mcp" }
  }
}
```
- 로컬 Supabase가 켜져 있어야 연결된다. Claude Code를 다시 열면 이 서버를 쓸지 묻는다 → 허용.
- 로컬 MCP는 로그인 없이 로컬 DB 전체에 접근한다. **클라우드(실제 데이터) 프로젝트에 연결할 때는 `read_only=true`로.**

## 4. ESP32
[esp32/README.md](../esp32/README.md) 참고.

## 5. 모델 파일
가중치는 레포에 넣지 않는다. `PD_DOG_MODEL_DIR`(기본 `~/pd-dog-models`)에 받는다.
받는 명령: `pi/scripts/download_models.sh` (TODO: A·B가 모델 확정 후 작성).
