#!/usr/bin/env bash
# Pi 5에서 conda 환경과 시스템 패키지(picamera2, libcamera, hailort) 연결 상태를 확인한다.
#   bash pi/scripts/check_pi_env.sh          # 확인만
#   bash pi/scripts/check_pi_env.sh --link   # 버전이 맞으면 시스템 dist-packages 경로 연결
set -u

SYS_PY=/usr/bin/python3
SYS_DIST=/usr/lib/python3/dist-packages

if [ -z "${CONDA_PREFIX:-}" ]; then
  echo "conda 환경이 활성화되지 않았습니다: conda activate pd-dog"
  exit 1
fi

sys_ver=$($SYS_PY -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
env_ver=$(python -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
echo "시스템 Python: $sys_ver / conda Python: $env_ver"

if [ "$sys_ver" != "$env_ver" ]; then
  echo "❌ minor 버전 불일치. environment.yml의 python=$sys_ver 로 맞추고 환경을 다시 만드세요."
  exit 1
fi

site=$(python -c 'import site; print(site.getsitepackages()[0])')
pth="$site/pd_dog_system.pth"

if [ "${1:-}" = "--link" ]; then
  echo "$SYS_DIST" > "$pth"
  echo "연결: $pth → $SYS_DIST"
fi

for mod in picamera2 libcamera hailo_platform; do
  if out=$(python -c "import $mod" 2>&1); then
    echo "✅ $mod"
  else
    echo "❌ $mod — $(echo "$out" | tail -n 1)"
  fi
done

# numpy: conda 것과 시스템(apt) 것 중 어느 쪽이 불리는지 확인 (docs/setup.md 2-3 "numpy 충돌")
#   picamera2·hailo_platform을 import한 뒤에도 conda 경로($CONDA_PREFIX/...)여야 정상.
echo "--- numpy ---"
python - "$CONDA_PREFIX" <<'EOF'
import sys
prefix = sys.argv[1]
try:
    import numpy
except Exception as e:
    print(f"❌ numpy import 실패 — {e}")
    sys.exit(0)
for mod in ("picamera2", "hailo_platform"):
    try:
        __import__(mod)
    except Exception:
        pass
src = "conda" if numpy.__file__.startswith(prefix) else "시스템(apt)"
print(f"numpy {numpy.__version__} ({src}): {numpy.__file__}")
if src != "conda":
    print("⚠️ 시스템 numpy가 불렸습니다. docs/setup.md 2-3 'numpy 충돌' 참고")
EOF
sys_np=$($SYS_PY -c 'import numpy; print(numpy.__version__, numpy.__file__)' 2>/dev/null || echo "없음")
echo "시스템 Python의 numpy: $sys_np"

echo "결과를 docs/setup.md 2-3 섹션에 기록해 주세요."
