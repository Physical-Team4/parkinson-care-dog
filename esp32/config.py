# MechDog ESP32 설정. 핀·주소·타이밍은 여기에만 둔다.
# None = 미확정 → 해당 기능 비활성 (docs/todo.md). 추측으로 채우지 말 것.

# ── 시리얼 (docs/serial-protocol.md) ──
HEARTBEAT_EXPECT_MS = 1000
PI_TIMEOUT_MS = 5000        # 이 시간 hb 없으면 Pi 무응답 → MP3 경보로 대체
STATUS_INTERVAL_MS = 1000

# ── 포트 3: 터치 + 레이저 (D-002 방법 1 예정) ──
TOUCH_PIN = None            # TODO(D): IO32 또는 IO33 확인
TOUCH_SOS_HOLD_MS = 3000    # F2: 3초 누르기
LASER_PIN = None            # TODO(C·D): 터치가 안 쓰는 IO. 방법 1 확정 전까지 None

# ── 포트 1: VL53L1X (IIC2) ──
TOF_I2C_BUS = 2
TOF_ADDR = 0x29
TOF_ENABLED = False         # TODO(C): 핀 순서·VCC 전압 확인 후 True

# ── 포트 2: MP3 (IIC1) ──
MP3_I2C_BUS = 1
MP3_TRACK_BEAT = None       # TODO(D): SD카드 트랙 번호 정하기
MP3_TRACK_ALARM = None
MP3_TRACK_MEDICATION = None
MP3_TRACK_PI_LOW = None     # TODO(D): "로봇 배터리를 충전해 주세요" 안내 (pi_low)

# ── F1 복약 (Pi가 settings로 덮어씀) ──
MED_TIMES_DEFAULT = ["08:00", "12:30", "18:00", "22:00"]
MED_CONFIRM_TIMEOUT_MS = 30 * 60 * 1000

# ── F3 박자 보행 ──
BPM_MIN = 80
BPM_MAX = 110
BPM_DEFAULT = 96
FOLLOW_LIMIT_CM_DEFAULT = 150
LASER_BLINK_MS = 100        # 박자마다 켜지는 시간
