#!/usr/bin/env bash
# Pi에서 PD-Dog 앱 실행. 레포 루트 기준으로 동작한다.
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ "${CONDA_DEFAULT_ENV:-}" != "pd-dog" ]; then
  # shellcheck disable=SC1091
  source "$(conda info --base)/etc/profile.d/conda.sh"
  conda activate pd-dog
fi

exec python -m pi.main "$@"
