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

echo "결과를 docs/setup.md 2-3 섹션에 기록해 주세요."
