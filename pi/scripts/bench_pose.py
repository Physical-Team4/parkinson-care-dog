"""Pi에서 pose 모델 속도·자원 벤치마크 → docs/benchmarks.md "결과: 속도·자원" 표 한 줄을 출력한다.

레포 루트, conda pd-dog 환경에서:
    python -m pi.scripts.bench_pose --hef ~/pd-dog-models/hailo8l/yolov8s_pose.hef
    python -m pi.scripts.bench_pose --hef ... --seconds 600        # 10분 발열 측정
    python -m pi.scripts.bench_pose --hef ... --no-camera          # 카메라 없이 (빈 프레임)

측정 (docs/benchmarks.md "측정 방법"):
  1) 전체 파이프라인: 캡처 → letterbox → Hailo 추론 → 디코딩. --seconds 동안. FPS, 지연 중앙값/p95.
  2) 추론만: 같은 입력 하나로 Hailo 추론만 --infer-seconds 동안.
  3) 1) 동안 CPU 사용률(이 프로세스·시스템), SoC 온도, vcgencmd get_throttled.
프레임은 메모리에서 처리 후 바로 버린다. 파일로 쓰지 않는다 (결과 숫자만 출력).
전력(W)은 USB 전력계로 따로 재서 표에 직접 적는다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
import statistics
import subprocess
import time
from pathlib import Path

import numpy as np

from pi.app.adapters.pose_decode import letterbox
from pi.app.config import load_settings

THERMAL = Path("/sys/class/thermal/thermal_zone0/temp")


def soc_temp_c() -> float | None:
    try:
        return int(THERMAL.read_text()) / 1000.0
    except (OSError, ValueError):
        return None


def throttled() -> int | None:
    try:
        out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=2).stdout
        return int(out.strip().split("=")[1], 16)
    except (OSError, IndexError, ValueError, subprocess.SubprocessError):
        return None


def cpu_times() -> tuple[int, int] | None:
    """(전체, idle) jiffies, /proc/stat 첫 줄."""
    try:
        vals = [int(v) for v in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
        return sum(vals), vals[3] + vals[4]
    except (OSError, ValueError, IndexError):
        return None


def pct(values: list[float], q: float) -> float:
    return float(np.percentile(values, q)) if values else float("nan")


def hef_source(hef: Path) -> str:
    """download_models.sh가 남긴 SOURCES.txt에서 이 파일의 Model Zoo 버전."""
    try:
        for line in reversed((hef.parent / "SOURCES.txt").read_text().splitlines()):
            parts = line.split()
            if len(parts) >= 3 and parts[1] == hef.stem:
                return f"Model Zoo {parts[2]} hailo8l"
    except OSError:
        pass
    return "(출처 기록 없음)"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hef", type=Path, help="기본: .env POSE_HEF")
    ap.add_argument("--seconds", type=float, default=60.0, help="전체 파이프라인 측정 시간 (기본 60)")
    ap.add_argument("--infer-seconds", type=float, default=10.0, help="추론만 측정 시간 (기본 10)")
    ap.add_argument("--warmup", type=int, default=10, help="측정 전 버리는 프레임 수")
    ap.add_argument("--sample-interval", type=float, default=5.0, help="온도·throttled 샘플 주기 (초)")
    ap.add_argument("--no-camera", action="store_true", help="카메라 대신 빈 프레임 (카메라 대기 시간 제외)")
    ap.add_argument("--note", default="", help="표 비고 칸에 덧붙일 말")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    s = load_settings()
    hef = (args.hef or s.pose_hef)
    if hef is None:
        raise SystemExit("--hef 또는 .env POSE_HEF가 필요합니다.")
    hef = hef.expanduser()

    from pi.app.adapters.hailo import HailoPoseEstimator  # Pi에서만

    est = HailoPoseEstimator(hef, s.pose_score_threshold, s.pose_iou_threshold, s.pose_max_people)
    cam = None
    if args.no_camera:
        blank = np.zeros((s.camera_height, s.camera_width, 3), dtype=np.uint8)
        capture = lambda: blank  # noqa: E731
    else:
        from pi.app.adapters.camera import PiCamera
        cam = PiCamera((s.camera_width, s.camera_height), s.camera_hflip, s.camera_vflip)
        capture = cam.capture

    lat, pre, inf, post, cap = [], [], [], [], []
    frames_with_person, top_scores, top_kconf = 0, [], []
    temps: list[float] = []
    thr_any, thr_last = 0, None
    try:
        for _ in range(args.warmup):
            frame = capture()
            est.infer(frame)
            del frame

        t_start_temp = soc_temp_c()
        cpu0, proc0 = cpu_times(), time.process_time()
        start = last_sample = time.perf_counter()
        n = 0
        while (now := time.perf_counter()) - start < args.seconds:
            t0 = time.perf_counter()
            frame = capture()
            t1 = time.perf_counter()
            people = est.infer(frame)
            t2 = time.perf_counter()
            del frame  # 프레임 즉시 폐기
            n += 1
            lat.append((t2 - t0) * 1e3)
            cap.append((t1 - t0) * 1e3)
            pre.append(est.last_timing["pre_ms"])
            inf.append(est.last_timing["infer_ms"])
            post.append(est.last_timing["post_ms"])
            if people:
                frames_with_person += 1
                top_scores.append(people[0].score)
                top_kconf.append(float(people[0].keypoints[:, 2].mean()))
            if now - last_sample >= args.sample_interval:
                last_sample = now
                if (t := soc_temp_c()) is not None:
                    temps.append(t)
                if (th := throttled()) is not None:
                    thr_any |= th
                    thr_last = th
        wall = time.perf_counter() - start
        proc_cpu = (time.process_time() - proc0) / wall * 100
        cpu1 = cpu_times()
        sys_cpu = (100 * (1 - (cpu1[1] - cpu0[1]) / max(1, cpu1[0] - cpu0[0]))
                   if cpu0 and cpu1 else float("nan"))
        end_temp = soc_temp_c()
        if (th := throttled()) is not None:
            thr_any |= th
            thr_last = th
        full_fps = n / wall

        # 추론만: letterbox된 입력 하나를 반복 추론
        img, _ = letterbox(capture(), *est.input_size)
        img = img.copy()
        times = []
        t_end = time.perf_counter() + args.infer_seconds
        while time.perf_counter() < t_end:
            t0 = time.perf_counter()
            est.infer_raw(img)
            times.append(time.perf_counter() - t0)
        del img
        infer_fps = len(times) / sum(times) if times else float("nan")
    finally:
        if cam is not None:
            cam.close()
        est.close()

    # ── 출력 ──
    w, h = est.input_size
    m = re.match(r"yolo(?:v8|11|26)([nsmlx])", hef.stem)
    size = m.group(1) if m else "?"
    thr_txt = "?" if thr_last is None else f"{thr_last:#x} (기간 중 {thr_any:#x})"
    if end_temp is None:
        temp_txt = "? (/sys/class/thermal 읽기 실패)"
    else:
        start_txt = "?" if t_start_temp is None else f"{t_start_temp:.1f}"
        temp_txt = f"{end_temp:.1f}°C (시작 {start_txt}, 최고 {max(temps + [end_temp]):.1f})"
    print()
    print(f"모델 {hef.name}  입력 {w}x{h}  카메라 {'없음(빈 프레임)' if args.no_camera else f'{s.camera_width}x{s.camera_height}'}")
    print(f"측정 {wall:.0f}초, {n}프레임")
    print(f"전체 FPS {full_fps:.1f} / 추론만 FPS {infer_fps:.1f}")
    print(f"지연(캡처~키포인트) 중앙값 {statistics.median(lat):.1f} ms, p95 {pct(lat, 95):.1f} ms")
    print("단계별 중앙값 ms: "
          f"캡처 {statistics.median(cap):.1f} / 전처리 {statistics.median(pre):.1f} / "
          f"추론 {statistics.median(inf):.1f} / 후처리 {statistics.median(post):.1f}")
    print(f"CPU: 이 프로세스 {proc_cpu:.0f}% (코어 1개=100%), 시스템 전체 {sys_cpu:.0f}%")
    print(f"SoC 온도 {temp_txt}, throttled {thr_txt}")
    if frames_with_person:
        print(f"사람 검출 프레임 {frames_with_person / n * 100:.0f}%, "
              f"최고 점수 중앙값 {statistics.median(top_scores):.2f}, 키포인트 평균 신뢰도 중앙값 {statistics.median(top_kconf):.2f}")
    else:
        print("사람 검출 프레임 0% (화면에 사람이 없었으면 정상)")

    note = (f"{wall / 60:.0f}분 측정" if wall >= 90 else f"{wall:.0f}초 측정") + ("" if not args.no_camera else ", 카메라 없음") + (f", {args.note}" if args.note else "")
    row = [
        dt.date.today().isoformat(), hef.stem, size, str(w), "Hailo-8L", hef_source(hef),
        f"{full_fps:.1f}", f"{infer_fps:.1f}", f"{statistics.median(lat):.0f} / {pct(lat, 95):.0f}",
        f"proc {proc_cpu:.0f}% / sys {sys_cpu:.0f}%",
        "?" if end_temp is None else f"{end_temp:.1f}°C",
        "?" if thr_last is None else f"{thr_any:#x}",
        "(전력계)", note,
    ]
    print("\ndocs/benchmarks.md 표에 붙일 줄:")
    print("| " + " | ".join(row) + " |")


if __name__ == "__main__":
    main()
