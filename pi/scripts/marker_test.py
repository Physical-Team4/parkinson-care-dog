"""M0 마커 인식 거리 측정 (docs/navigation.md §11-③, 담당 A). ArUco DICT_4X4_50.

레포 루트, conda pd-dog 환경에서:
    # 1) 인쇄용 마커 PNG 만들기 (카메라 영상 아님)
    python -m pi.scripts.marker_test --generate 1 2 3 4 10 --out ~/pd-dog-data/markers
    # 2) 인쇄한 마커(한 변 실제 길이 cm)를 정해진 거리에 두고 측정
    python -m pi.scripts.marker_test --marker-cm 12 --at-cm 100 --seconds 10
    # 3) 거리 없이 계속 보기 (Ctrl+C로 끝)
    python -m pi.scripts.marker_test --marker-cm 12

출력: 1초마다 인식된 마커 번호·화면상 한 변(px)·가로 위치. 끝나면 navigation.md 표에 붙일 줄.
--at-cm을 주면 초점거리(px) = 한 변(px) × 거리 / 마커 크기 → 나중에 크기로 거리를 추정할 때 쓴다.
카메라 프레임은 메모리에서 처리 후 바로 버린다. 파일로 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path

from pi.app.config import load_settings

DICT_NAME = "DICT_4X4_50"


def aruco():
    import cv2  # Pi·PC 모두 conda opencv (environment.yml). aruco는 OpenCV 4.7+ 본체에 포함
    return cv2, cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICT_NAME))


def generate(ids: list[int], out: Path, size_px: int) -> None:
    cv2, d = aruco()
    out = out.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    border = size_px // 8   # 흰 여백 (인식에 필요)
    for i in ids:
        img = cv2.aruco.generateImageMarker(d, i, size_px)
        img = cv2.copyMakeBorder(img, border, border, border, border, cv2.BORDER_CONSTANT, value=255)
        path = out / f"aruco_{DICT_NAME}_{i}.png"
        cv2.imwrite(str(path), img)
        print(f"{path}  (검은 사각형 한 변을 자로 재서 --marker-cm에 넣기)")


def measure(args) -> None:
    from pi.app.adapters.camera import PiCamera   # Pi에서만
    from pi.app.adapters.markers import ArucoMarkerDetector

    s = load_settings()
    detector = ArucoMarkerDetector(DICT_NAME)
    cam = PiCamera((s.camera_width, s.camera_height), s.camera_hflip, s.camera_vflip)

    frames = 0
    seen: dict[int, list[float]] = {}
    offsets: dict[int, list[float]] = {}
    times: list[float] = []
    start = last = time.perf_counter()
    try:
        while args.seconds <= 0 or time.perf_counter() - start < args.seconds:
            frame = cam.capture()
            found = detector.detect(frame)
            del frame                       # 프레임 즉시 폐기
            frames += 1
            times.append(detector.last_ms)
            for m in found:
                seen.setdefault(m.marker_id, []).append(m.side_px)
                offsets.setdefault(m.marker_id, []).append(m.cx * 2 - 1)   # -1(왼쪽)~+1(오른쪽)
            if time.perf_counter() - last >= 1.0:
                last = time.perf_counter()
                now = ", ".join(f"#{m.marker_id}: 한 변 {m.side_px:.0f}px, 가로 {m.cx * 2 - 1:+.2f}" for m in found)
                print(f"{frames}프레임 | 인식 {detector.last_ms:.1f}ms | {now or '마커 없음'}")
    except KeyboardInterrupt:
        pass
    finally:
        cam.close()

    print()
    if times:
        print(f"마커 인식 시간: 중앙값 {statistics.median(times):.1f}ms, 최대 {max(times):.1f}ms (CPU)")
    if not seen:
        print(f"{frames}프레임 중 마커 인식 0 → 거리·크기·조명·초점 확인")
        return
    for i, v in sorted(seen.items()):
        rate = len(v) / frames * 100
        med = statistics.median(v)
        focal = med * args.at_cm / args.marker_cm if args.at_cm and args.marker_cm else None
        print(f"#{i}: 인식률 {rate:.0f}% ({len(v)}/{frames}), 한 변 중앙값 {med:.1f}px, "
              f"가로 위치 중앙값 {statistics.median(offsets[i]):+.2f}"
              + (f", 초점거리 추정 {focal:.0f}px (→ .env CAMERA_FOCAL_PX)" if focal else ""))
        size = f"{args.marker_cm:g}cm" if args.marker_cm else "?"
        dist = f"{args.at_cm:g}cm" if args.at_cm else "?"
        print("navigation.md 표에 붙일 줄:")
        print(f"| {size} | {dist} | {rate:.0f}% | {med:.0f} | {f'{focal:.0f}' if focal else '-'} | {args.note} |")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--generate", type=int, nargs="+", metavar="ID", help="인쇄용 마커 PNG 생성 (0~49)")
    ap.add_argument("--out", type=Path, default=Path("~/pd-dog-data/markers"))
    ap.add_argument("--size-px", type=int, default=800, help="생성 PNG의 마커 크기")
    ap.add_argument("--marker-cm", type=float, help="인쇄한 마커 검은 사각형 한 변 (cm)")
    ap.add_argument("--at-cm", type=float, help="카메라~마커 실제 거리 (cm). 주면 초점거리 추정")
    ap.add_argument("--seconds", type=float, default=0, help="측정 시간 (0 = Ctrl+C까지)")
    ap.add_argument("--note", default="", help="표 비고 (조명·각도 등)")
    args = ap.parse_args()
    if args.generate:
        if any(not 0 <= i < 50 for i in args.generate):
            raise SystemExit("DICT_4X4_50 마커 번호는 0~49")
        generate(args.generate, args.out, args.size_px)
    else:
        measure(args)


if __name__ == "__main__":
    main()
