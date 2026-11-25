"""F4 발성 훈련: RMS → dB (담당: B).

주의: 마이크 보정 전이라 값은 dBFS 기반 상대값 + 보정 오프셋이다.
TODO(B): 소음계로 USB 핀마이크 보정 후 calibration_offset_db 확정 (config로).
측정은 서보 정지 상태에서만 (호출 전에 ESP32 stop).
"""
from __future__ import annotations

import numpy as np

_EPS = 1e-10


def rms(samples: np.ndarray) -> float:
    x = samples.astype(np.float64)
    return float(np.sqrt(np.mean(x * x))) if x.size else 0.0


def dbfs(samples: np.ndarray) -> float:
    """풀스케일(1.0) 기준 dB. 무음은 매우 작은 음수."""
    return 20.0 * float(np.log10(max(rms(samples), _EPS)))


def estimated_db_spl(samples: np.ndarray, calibration_offset_db: float) -> float:
    return dbfs(samples) + calibration_offset_db


def peak_db(samples: np.ndarray, sample_rate: int, calibration_offset_db: float,
            window_s: float = 0.1) -> float:
    """짧은 창 단위 dB 중 최고값 (세션의 peak_db)."""
    n = max(1, int(sample_rate * window_s))
    if samples.size < n:
        return estimated_db_spl(samples, calibration_offset_db)
    frames = samples[: samples.size // n * n].reshape(-1, n)
    return max(estimated_db_spl(f, calibration_offset_db) for f in frames)
