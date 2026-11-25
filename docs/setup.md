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
  - 확인됨 (2026-11-26, A): Debian 13 **trixie**, 커널 6.18, 시스템 Python **3.13.5** → `environment.yml`은 `python=3.13` ([decisions.md](decisions.md) D-007).
  - 하드웨어 인식 확인됨: `lspci`에 Hailo, `rpicam-hello --list-cameras`에 imx708(카메라 모듈 3), `vcgencmd get_throttled` = `0x0`.
- `sudo raspi-config` → I²C 켜기 (X1200 잔량 칩).
- EEPROM `PSU_MAX_CURRENT=5000`: 절차는 [2-6](#2-6-x1200-ups).
- 시리얼 권한: `sudo usermod -aG dialout,video,i2c,gpio $USER` 후 재로그인.
- 시스템 패키지 (apt):
  ```bash
  sudo apt install -y python3-picamera2 --no-install-recommends
  sudo apt install -y dkms linux-headers-rpi-2712   # ⚠️ hailo-all보다 먼저 (Hailo 드라이버 빌드용)
  sudo apt install -y hailo-all          # AI HAT+
  sudo apt install -y python3-gpiozero python3-lgpio i2c-tools   # X1200 GPIO6·I²C (2-6)
  sudo reboot
  ```
- Hailo 확인: `hailortcli fw-control identify` → `Device Architecture: HAILO8L`.
  - 확인됨 (2026-11-26, A): hailort 4.23.0, 펌웨어 4.23.0, 커널 6.18.60.
- ⚠️ Hailo PCIe 드라이버(`hailo_pci`)는 **DKMS로 커널마다 빌드**된다. dkms 없이 `hailo-all`을 깔면
  패키지는 설치돼도 모듈이 없어서 `/dev/hailo0`이 안 생기고 `hailortcli`가 아무것도 출력하지 않는다.
  - 증상 확인: `lsmod | grep hailo` 비어 있음, `modprobe hailo_pci` → "not found".
  - 해결: `sudo apt install -y dkms linux-headers-rpi-2712` → `sudo apt install --reinstall -y hailort-pcie-driver`
    → `dkms status`에 `hailo_pci/<버전>, <uname -r>, aarch64: installed` → 재부팅.
  - **커널 업데이트(`apt full-upgrade`) 후**에는 재부팅하고 `dkms status`와 `ls /dev/hailo0`을 확인한다.

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

**numpy 충돌 확인**
방법 A에서는 conda numpy와 시스템(apt) numpy가 둘 다 경로에 있다. `.pth`가 시스템 경로를 맨 뒤에 붙이므로
정상이면 **conda numpy**가 불린다. `check_pi_env.sh`가 picamera2·hailo_platform import 후의 `numpy.__file__`과
시스템 numpy 버전을 출력한다.
- `numpy.__file__`이 `$CONDA_PREFIX/...` → 정상.
- `/usr/lib/python3/dist-packages/...` → 시스템 numpy가 먼저 불림. `python -c "import sys; print(sys.path)"`로
  `pd_dog_system.pth` 경로가 맨 뒤인지, `PYTHONPATH`에 시스템 경로가 들어가 있지 않은지 확인.
- import 중 `numpy.dtype size changed`, `module compiled against ABI version ...`, `_ARRAY_API not found` 같은 오류
  → apt 확장 모듈(libcamera·simplejpeg·hailort 바인딩 등)은 **시스템 numpy 버전으로 빌드**돼 있어서 conda numpy와
  major(1.x/2.x)가 다르면 깨진다. 정리 방법 (위에서부터 시도):
  1. `environment.yml`의 numpy를 시스템 numpy와 같은 major.minor로 고정 (예: 시스템이 2.2.x면 `numpy=2.2`) 후
     `conda env update -f environment.yml --prune`. 고정했으면 이 섹션과 [decisions.md](decisions.md)에 기록.
  2. 그래도 안 되면 conda numpy를 빼고 시스템 numpy를 쓰는 방법은 쓰지 않는다 (conda 패키지들이 깨짐) → 방법 B 검토.

결과(어떤 방법이 됐는지, 필요한 추가 명령)를 이 섹션에 기록한다.
- [ ] picamera2 import: (결과 기록)
- [ ] libcamera import: (결과 기록)
- [ ] hailo_platform import: (결과 기록)
- [ ] numpy: conda / 시스템 중 어느 쪽, 버전 (결과 기록)

### 2-3-1. AI HAT+ 13T = Hailo-8L
- AI HAT+ 13 TOPS의 칩은 **Hailo-8L**이다 (`lspci`에는 "Hailo-8"로 나올 수 있음 → `hailortcli fw-control identify`의
  Device Architecture가 `HAILO8L`인지 확인).
- **`.hef`는 hailo8l 대상으로 컴파일된 것만 사용한다.** Hailo-8(26T)용 `.hef`는 Hailo-8L에서 로드되지 않거나
  제대로 동작하지 않는다. Model Zoo에서 받을 때도 `hailo8l` 폴더·파일을 고르고, DFC로 변환할 때도 대상 `hailo8l`.

### 2-4. ESP32 시리얼 포트 고정 (TODO)
`/dev/ttyUSB0` 번호가 바뀔 수 있으니 udev 규칙으로 `/dev/pd-dog-esp32` 고정 예정.
`udevadm info -a /dev/ttyUSB0`로 idVendor/idProduct 확인 후 `/etc/udev/rules.d/99-pd-dog.rules` 작성.

### 2-5. 실행
```bash
bash pi/scripts/run.sh
```
자동 시작(systemd 서비스)은 TODO.

### 2-6. X1200 UPS
부품·충전 방법은 [hardware.md](hardware.md#전원), 배터리 셀 선택 이유는 [decisions.md](decisions.md) D-008.

**1) EEPROM 전류 한도** — X1200은 Pi 5 공식 27W 어댑터처럼 5A를 알리지 않으므로 직접 설정.
그대로 두면 USB 출력이 600mA로 제한되고 "전원 부족" 경고가 뜰 수 있다.
```bash
sudo rpi-eeprom-config --edit
#   [all] 아래 맨 끝에 한 줄 추가:  PSU_MAX_CURRENT=5000
#   nano 저장: Ctrl+O → Enter → Ctrl+X
sudo reboot
sudo rpi-eeprom-config | grep PSU_MAX_CURRENT    # 재부팅 후 확인
```
값 5000은 X1200 위키에서 재확인 (todo.md).

**2) I²C 잔량 칩 확인** (2-1에서 I²C를 켠 뒤)
```bash
i2cdetect -y 1          # 표에 36 이 보이면 OK
```

**3) GPIO6 전원 감지 극성 실측** → `.env`의 `X1200_PLD_POWER_OK_LEVEL`
레포 루트, `pd-dog` 환경에서:
```bash
python -m pi.app.adapters.x1200
```
1초마다 `SOC`·`VCELL`·`GPIO6`·`CPU` 값이 나온다. X1200 USB-C 충전기를 꽂았다 뺐다 하며 `GPIO6` 값을 본다.
충전기를 꽂았을 때 값(0 또는 1)을 Pi의 `.env`에 `X1200_PLD_POWER_OK_LEVEL=<값>`으로 넣는다.
비워 두면 전원 감지와 `pi_charging`이 꺼진다 (null). 결과는 이 섹션에 기록:
- [ ] `i2cdetect` 0x36: (결과)
- [ ] SOC·VCELL이 멀티미터 전압과 맞는지: (결과)
- [ ] 충전기 연결 시 GPIO6 = (0/1)

**4) 안전 종료 권한** — 앱이 배터리 10% 미만에서 `sudo -n /usr/sbin/shutdown -h now`를 실행한다.
비밀번호 없이 이 명령 하나만 허용 (`<user>`는 Pi 사용자 이름):
```bash
echo '<user> ALL=(root) NOPASSWD: /usr/sbin/shutdown' | sudo tee /etc/sudoers.d/pd-dog-shutdown
sudo chmod 440 /etc/sudoers.d/pd-dog-shutdown
sudo visudo -c                       # 문법 확인 (오류면 바로 지울 것)
sudo -n /usr/sbin/shutdown --help >/dev/null && echo OK
```

**배터리 정책** (`pi/app/services/power.py`, 값은 `pi/app/config.py`):

| 조건 | 동작 |
|---|---|
| 잔량 < 20% | ESP32에 `pi_low` 1번 → 경보 모드 준비 + MP3 안내. 25% 이상 회복·충전 시 다시 보낼 수 있음 |
| 잔량 < 10%가 5초 간격 3번 연속 (충전 중 제외) | ESP32에 `shutdown` → 대기열 재전송 시도 → 대기열 닫기 → OS 종료 |
| 외부 전원 차단 3번 연속 | `PI_SHUTDOWN_ON_POWER_LOSS=true`일 때만 위와 같이 종료 (기본 꺼짐, todo.md) |

- 대기열(SQLite)은 알람이 생길 때마다 바로 디스크에 저장되므로 종료 후 다음 부팅에 재전송된다.
- 대시보드 battery_low 알람은 DB 트리거가 `robot_status`에서 만든다 (Pi가 따로 안 보냄).

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
Hailo용 `.hef`는 hailo8l 대상만 ([2-3-1](#2-3-1-ai-hat-13t--hailo-8l)).
