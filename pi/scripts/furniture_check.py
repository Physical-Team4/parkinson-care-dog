"""가구 검출 확인 (담당 A): 낮은 로봇 카메라로 침대·소파·의자가 잡히는지 숫자로 본다 (docs/features.md "가구 검출").

레포 루트, conda pd-dog 환경에서:
    MZ_VERSION=v2.20.0 bash pi/scripts/download_models.sh yolov8s            # 처음 한 번 (일반 물체 검출 모델)
    python -m pi.scripts.furniture_check --inspect                            # 1) 출력 형식 확인 (한 프레임)
    python -m pi.scripts.furniture_check --seconds 20                         # 2) 로봇을 침대·소파 쪽으로 두고 측정
    python -m pi.scripts.furniture_check --seconds 20 --all                   # 다른 물체도 모두 출력

판단 기준: 사람이 카메라 앞에 서면 person(0)으로 잡혀야 종류 번호 순서가 맞다.
침대(bed)·소파(couch)가 로봇 위치·각도별로 얼마나 자주(인식률)·얼마나 확실하게(점수) 잡히는지 기록 → 본격 구현 여부 결정.
카메라 프레임은 메모리에서 처리 후 바로 버린다. 파일로 쓰지 않는다 (숫자만 출력).
"""
from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path

import numpy as np

from pi.app.config import load_settings

WATCH = ("bed", "couch", "chair", "person")


def inspect(det, frame) -> None:
    print("출력:", det.output_info())
    raw, _ = det.infer_raw(frame)
    print("get_buffer() 타입:", type(raw).__name__)
    if isinstance(raw, (list, tuple)):
        print("리스트 길이:", len(raw), "/ 앞 3개 shape:", [np.shape(r) for r in raw[:3]])
        nonempty = [(i, np.shape(r)) for i, r in enumerate(raw) if np.size(r)]
        print("박스가 있는 종류:", nonempty[:10])
    else:
        a = np.asarray(raw)
        print("배열 shape:", a.shape, "dtype:", a.dtype, "앞 12개 값:", a.reshape(-1)[:12].round(3).tolist())
    from pi.app.adapters.hailo_detect import parse_nms_by_class
    try:
        parsed = parse_nms_by_class(raw)
        print("해석 결과 (종류, 박스 수):", [(c, len(b)) for c, b in parsed][:10])
    except ValueError as e:
        print("❌", e, "→ 위 출력을 붙여 주세요")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hef", type=Path, default=None, help="기본: <모델 폴더>/hailo8l/yolov8s.hef")
    ap.add_argument("--score", type=float, default=0.3, help="출력할 최소 점수 (확인용, 낮게)")
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--all", action="store_true", help="가구·사람 외 다른 물체도 출력")
    ap.add_argument("--inspect", action="store_true", help="출력 형식만 확인하고 끝")
    ap.add_argument("--note", default="", help="결과 줄 비고 (로봇 위치·각도·조명)")
    args = ap.parse_args()

    s = load_settings()
    hef = (args.hef or s.model_dir / "hailo8l" / "yolov8s.hef").expanduser()
    from pi.app.adapters.camera import PiCamera           # Pi에서만
    from pi.app.adapters.hailo_detect import HailoObjectDetector

    det = HailoObjectDetector(hef, args.score)
    cam = PiCamera((s.camera_width, s.camera_height), s.camera_hflip, s.camera_vflip)
    frames = 0
    hits: dict[str, list[float]] = {}
    times: list[float] = []
    try:
        if args.inspect:
            frame = cam.capture()
            inspect(det, frame)
            del frame
            return
        start = last = time.perf_counter()
        while time.perf_counter() - start < args.seconds:
            frame = cam.capture()
            found = det.detect(frame)
            del frame                                        # 프레임 즉시 폐기
            frames += 1
            times.append(det.last_ms)
            best: dict[str, float] = {}
            for d in found:
                if args.all or d.name in WATCH:
                    best[d.name] = max(best.get(d.name, 0.0), d.score)
            for name, sc in best.items():
                hits.setdefault(name, []).append(sc)
            if time.perf_counter() - last >= 1.0:
                last = time.perf_counter()
                shown = [f"{d.name} {d.score:.2f} [{', '.join(f'{v:.2f}' for v in d.bbox)}]"
                         for d in found if args.all or d.name in WATCH]
                print(f"{frames}프레임 | {det.last_ms:.0f}ms | " + ("; ".join(shown) or "없음"))
    except KeyboardInterrupt:
        pass
    finally:
        cam.close()
        det.close()

    if not frames:
        return
    print()
    print(f"{frames}프레임, 검출 시간 중앙값 {statistics.median(times):.1f}ms")
    for name in sorted(hits, key=lambda n: -len(hits[n])):
        v = hits[name]
        print(f"| {name} | 인식률 {len(v) / frames * 100:.0f}% | 점수 중앙값 {statistics.median(v):.2f} "
              f"| 최고 {max(v):.2f} | {args.note} |")
    for name in ("bed", "couch"):
        if name not in hits:
            print(f"| {name} | 인식 안 됨 | | | {args.note} |")


if __name__ == "__main__":
    main()
