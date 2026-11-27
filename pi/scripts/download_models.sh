#!/usr/bin/env bash
# Hailo Model Zoo의 hailo8l용 기성 pose 모델(.hef)을 Pi에 받는다. 가중치는 레포에 넣지 않는다.
#
#   bash pi/scripts/download_models.sh --probe                 # 1) 어떤 Model Zoo 버전이 이 Pi(HailoRT)에서 열리는지 확인
#   MZ_VERSION=v2.xx.0 bash pi/scripts/download_models.sh      # 2) 고른 버전으로 받기 (기본 모델: yolov8s_pose yolov8m_pose)
#   MZ_VERSION=v2.xx.0 bash pi/scripts/download_models.sh yolov8s_pose   # 모델 지정
#   MZ_VERSION=v2.20.0 bash pi/scripts/download_models.sh yolov8s        # 일반 물체 검출 (가구 확인, pi/scripts/furniture_check.py)
#
# 저장 위치: ${PD_DOG_MODEL_DIR:-~/pd-dog-models}/hailo8l/<모델>.hef  (+ 같은 폴더 SOURCES.txt에 출처·sha256)
# .env에 POSE_HEF=hailo8l/<모델>.hef 로 고른 모델을 지정한다.
#
# 버전 주의 (docs/setup.md 2-3-2):
#   - Model Zoo v2.x = Hailo-8/8L용. master(v5.x)는 Hailo-10/15 전용이므로 쓰지 않는다.
#   - .hef는 컴파일한 DFC 버전에 따라 설치된 HailoRT(4.23.0)에서 안 열릴 수 있다.
#     공식 표에 HailoRT 4.23 ↔ Model Zoo 버전 대응이 없어서 --probe로 실제로 열어 보고 고른다.
#   - 반드시 hailo8l 폴더의 파일만 (Hailo-8용 .hef는 8L에서 안 됨, setup.md 2-3-1).
set -euo pipefail

BASE_URL="https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled"
ARCH="hailo8l"
MODEL_DIR="${PD_DOG_MODEL_DIR:-$HOME/pd-dog-models}"
OUT_DIR="$MODEL_DIR/$ARCH"
PROBE_VERSIONS="v2.12.0 v2.13.0 v2.14.0 v2.15.0 v2.16.0 v2.17.0 v2.18.0 v2.19.0 v2.20.0"
PROBE_MODEL="yolov8s_pose"

need() { command -v "$1" >/dev/null || { echo "❌ $1 없음"; exit 1; }; }
need curl
need hailortcli
need sha256sum

# .hef를 HailoRT로 열어 보고 대상이 HAILO8L인지 확인. 성공 시 0.
check_hef() {
  local f="$1" out
  if ! out=$(hailortcli parse-hef "$f" 2>&1); then
    echo "   ❌ parse-hef 실패: $(echo "$out" | grep -iE 'error|fail|version' | head -n 2 | tr '\n' ' ')"
    return 1
  fi
  if ! echo "$out" | grep -qi "HAILO8L"; then
    echo "   ❌ HAILO8L 대상이 아님: $(echo "$out" | grep -i 'architecture' | head -n 1)"
    return 1
  fi
  echo "   ✅ $(echo "$out" | grep -i 'architecture' | head -n 1 | sed 's/^ *//')"
}

if [ "${1:-}" = "--probe" ]; then
  echo "HailoRT: $(hailortcli --version 2>/dev/null | head -n 1)"
  echo "장치: $(hailortcli fw-control identify 2>/dev/null | grep -ai 'architecture' | head -n 1)"
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  for v in $PROBE_VERSIONS; do
    url="$BASE_URL/$v/$ARCH/$PROBE_MODEL.hef"
    code=$(curl -s -o /dev/null -w '%{http_code}' -I "$url" || true)
    if [ "$code" != "200" ]; then
      echo "$v: 파일 없음 (HTTP $code)"
      continue
    fi
    echo "$v: 있음 → 받아서 열어 봄"
    curl -fsSL --retry 3 -o "$tmp/$v.hef" "$url"
    check_hef "$tmp/$v.hef" || true
    rm -f "$tmp/$v.hef"
  done
  echo
  echo "✅가 나온 버전 중 가장 높은 것을 골라 MZ_VERSION=<버전> 으로 다시 실행하세요."
  echo "결과를 docs/setup.md 2-3-2에 기록해 주세요."
  exit 0
fi

if [ -z "${MZ_VERSION:-}" ]; then
  echo "MZ_VERSION이 없습니다. 먼저 --probe로 이 Pi에서 열리는 버전을 확인하세요."
  echo "  bash pi/scripts/download_models.sh --probe"
  exit 1
fi

models=("$@")
[ ${#models[@]} -eq 0 ] && models=(yolov8s_pose yolov8m_pose)

mkdir -p "$OUT_DIR"
for m in "${models[@]}"; do
  url="$BASE_URL/$MZ_VERSION/$ARCH/$m.hef"
  dst="$OUT_DIR/$m.hef"
  echo "▶ $m ($MZ_VERSION)"
  curl -fL --retry 3 --progress-bar -o "$dst.part" "$url"
  if ! check_hef "$dst.part"; then
    rm -f "$dst.part"
    echo "   이 버전은 이 Pi에서 쓸 수 없습니다. --probe 결과의 다른 버전을 쓰세요."
    exit 1
  fi
  mv "$dst.part" "$dst"
  sum=$(sha256sum "$dst" | cut -d' ' -f1)
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $m $MZ_VERSION $url sha256=$sum" >> "$OUT_DIR/SOURCES.txt"
  echo "   → $dst"
  echo "   sha256 $sum"
done

echo
echo "받은 모델: $OUT_DIR"
echo ".env에 예: POSE_HEF=$ARCH/${models[0]}.hef"
echo "하드웨어 단독 추론 속도 확인(선택): hailortcli run $OUT_DIR/${models[0]}.hef"
echo "벤치마크: python -m pi.scripts.bench_pose --hef $OUT_DIR/${models[0]}.hef"
