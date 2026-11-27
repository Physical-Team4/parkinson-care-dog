"""개발용 pose 뷰어: 노트북 브라우저에서 인식 결과(bbox·뼈대)를 실시간으로 본다. (담당 A, D-011)

    # Pi (레포 루트, pd-dog 환경)
    python -m pi.scripts.pose_viewer --hef ~/pd-dog-models/hailo8l/yolov8s_pose.hef            # 뼈대만
    python -m pi.scripts.pose_viewer --hef ~/pd-dog-models/hailo8l/yolov8s_pose.hef --video    # 카메라 화면 + 뼈대
    python -m pi.scripts.pose_viewer --markers --video                                         # + 로봇 이동 마커 표시
    # 노트북
    ssh -L 8765:127.0.0.1:8765 <user>@<pi>     → 브라우저 http://localhost:8765

영상 규칙 예외 (docs/decisions.md D-011):
- 개발용으로만. 앱 본체(pi.main)에서 import·실행하지 않는다.
- 카메라 화면은 --video를 켰을 때만 보낸다. 기본은 키포인트만.
- 디스크에 쓰지 않는다. 메모리에 최신 1장만 두고 다음 프레임이 덮어쓴다.
- 127.0.0.1에만 열어 SSH 터널로만 본다 (같은 와이파이의 다른 기기에서 접속 불가).
- 화면에 찍히는 사람은 동의한 팀원만.
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

from pi.app.config import load_settings

log = logging.getLogger("pose_viewer")
PAGE = Path(__file__).with_name("pose_viewer.html")


class Latest:
    """최신 결과 1개만 메모리에 둔다 (프레임 JPEG 포함 시에도 1장)."""

    def __init__(self) -> None:
        self.cond = threading.Condition()
        self.seq = 0
        self.payload = b"{}"

    def put(self, payload: dict) -> None:
        data = json.dumps(payload).encode()
        with self.cond:
            self.seq += 1
            self.payload = data
            self.cond.notify_all()

    def wait_after(self, seq: int, timeout: float) -> tuple[int, bytes]:
        with self.cond:
            self.cond.wait_for(lambda: self.seq > seq, timeout=timeout)
            return self.seq, self.payload


def run_loop(camera, estimator, latest: Latest, encode_jpeg, stop: threading.Event, quality: int,
             min_interval_s: float = 0.0, judge=None, markers=None) -> None:
    """judge: (people, now_s) -> dict 이면 F6·F7 판정 결과를 화면에 같이 보낸다.
    markers: (frame) -> dict 이면 로봇 이동 마커 인식 결과를 같이 보낸다."""
    try:
        _loop(camera, estimator, latest, encode_jpeg, stop, quality, min_interval_s, judge, markers)
    except Exception as e:
        log.exception("추론 루프 중단")
        latest.put({"error": f"{type(e).__name__}: {e}"})


def _loop(camera, estimator, latest: Latest, encode_jpeg, stop: threading.Event, quality: int,
          min_interval_s: float, judge, markers=None) -> None:
    fps_t, fps_n, fps = time.perf_counter(), 0, 0.0
    while not stop.is_set():
        t0 = time.perf_counter()
        frame = camera.capture()
        people = estimator.infer(frame)
        marker_info = markers(frame) if markers else None
        h, w = frame.shape[:2]
        jpeg = encode_jpeg(frame, quality) if encode_jpeg else None
        del frame  # 원본 프레임 즉시 폐기 (JPEG는 latest에서 다음 프레임이 덮어씀)
        fps_n += 1
        if (now := time.perf_counter()) - fps_t >= 1.0:
            fps, fps_t, fps_n = fps_n / (now - fps_t), now, 0
        latest.put({
            "w": w, "h": h, "fps": round(fps, 1),
            "ms": round((time.perf_counter() - t0) * 1e3, 1),
            "timing": {k: round(v, 1) for k, v in getattr(estimator, "last_timing", {}).items()},
            "people": [{"bbox": [round(v, 4) for v in p.bbox], "score": round(p.score, 3),
                        "kpts": np.round(p.keypoints, 4).tolist()} for p in people],
            "jpeg": base64.b64encode(jpeg).decode() if jpeg else None,
            "judge": judge(people, t0) if judge else None,
            "markers": marker_info,
        })
        if min_interval_s:
            stop.wait(max(0.0, min_interval_s - (time.perf_counter() - t0)))


class Judge:
    """F6·F7 판정을 화면 확인용으로 돌린다. 알람은 Supabase로 보내지 않고 메모리 가짜(MockRemote)에만 쌓인다.
    로봇은 정지 상태로 가정 (ESP32 연결 없이 뷰어만 켜므로)."""

    def __init__(self, settings, marker_view=None) -> None:
        from pi.app.adapters.mock import MockRemote
        from pi.app.models.outbox import Outbox
        from pi.app.services.sync import SyncService
        from pi.app.services.vision.monitor import VisionMonitor

        self.remote = MockRemote()
        self.monitor = VisionMonitor.from_settings(settings, SyncService(Outbox(":memory:"), self.remote))
        self.alarms: list[dict] = []
        self.marker_view = marker_view   # --markers면 같은 프레임 마커로 잠자리 판단

    def __call__(self, people, now_s: float) -> dict:
        markers = self.marker_view.last if self.marker_view else None
        pose = self.monitor.update(people, now_s, "idle", True, markers)
        while self.remote.executed:
            pl = self.remote.executed.pop(0).payload
            self.alarms.append({"at": time.strftime("%H:%M:%S"), "source": pl["p_source"],
                                "confidence": pl["p_confidence"], "detail": pl["p_detail"]})
            log.warning("판정 알람 (전송 안 함): %s", self.alarms[-1])
        self.alarms = self.alarms[-5:]
        return {"state": pose.state, "resting": self.monitor.resting, "sleep": self.monitor.sleep_mode,
                "still_s": round(self.monitor.no_motion.still_s(now_s)),
                "persons": [{"id": p.track_id, "state": p.state, "resting": p.resting, "focus": p.focus,
                             "spot": p.at_sleep_spot,
                             "bbox": [round(v, 4) for v in p.bbox]} for p in self.monitor.people],
                "alarms": self.alarms}


class MarkerView:
    """로봇 이동 마커를 화면 확인용으로 인식한다 (docs/navigation.md M1). 거리·방향은 설정값이 있을 때만."""

    def __init__(self, detector, marker_cm: float | None, focal_px: float | None) -> None:
        self.detector = detector
        self.marker_cm, self.focal_px = marker_cm, focal_px
        self.last = []          # 마지막 프레임 마커 (Judge가 잠자리 판단에 씀)

    def __call__(self, frame) -> dict:
        from pi.app.adapters.markers import estimate_bearing_deg, estimate_distance_cm

        found = self.detector.detect(frame)
        self.last = found
        def r(v, n=1):
            return None if v is None else round(v, n)
        return {"ms": round(self.detector.last_ms, 1), "list": [
            {"id": m.marker_id, "corners": np.round(m.corners, 4).tolist(), "cx": round(m.cx, 3),
             "side_px": round(m.side_px, 1),
             "dist_cm": r(estimate_distance_cm(m, self.marker_cm, self.focal_px), 0),
             "bearing_deg": r(estimate_bearing_deg(m, self.focal_px))} for m in found]}


def make_handler(latest: Latest, video: bool, judge: Judge | None = None):
    page = PAGE.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # 요청마다 찍지 않음
            pass

        def _send(self, code: int, ctype: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                self._send(200, "text/html; charset=utf-8", page)
            elif url.path == "/sleep" and judge is not None:   # 시험용: 취침 선언·해제 ("잘게" 대신)
                on = parse_qs(url.query).get("on", ["0"])[0] == "1"
                judge.monitor.set_sleep_mode(on, time.perf_counter())
                self._send(200, "text/plain", b"ok")
            elif url.path == "/latest":
                after = int(parse_qs(url.query).get("after", ["0"])[0])
                seq, data = latest.wait_after(after, timeout=2.0)
                self._send(200, "application/json",
                           b'{"seq":%d,"video":%s,"d":' % (seq, b"true" if video else b"false") + data + b"}")
            else:
                self._send(404, "text/plain", b"not found")

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hef", type=Path, help="기본: .env POSE_HEF")
    ap.add_argument("--video", action="store_true", help="카메라 화면도 보냄 (개발용 예외, D-011)")
    ap.add_argument("--quality", type=int, default=60, help="--video JPEG 품질")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--mock", action="store_true", help="하드웨어 없이 (PC에서 화면 확인용)")
    ap.add_argument("--markers", action="store_true", help="로봇 이동 마커(ArUco) 인식·표시 (CPU 추가 사용)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    s = load_settings()

    encode_jpeg = None
    if args.mock:
        from pi.app.adapters import mock
        from pi.app.adapters.base import PersonPose
        k = np.array([[0.5, 0.2 + 0.04 * i, 0.9] for i in range(17)], np.float32)  # 대충 세로로 선 사람
        camera = mock.MockCamera(s.camera_width, s.camera_height)
        estimator = mock.MockPoseEstimator([[PersonPose((0.4, 0.15, 0.6, 0.9), 0.9, k)]])
    else:
        from pi.app.adapters.camera import PiCamera
        from pi.app.adapters.hailo import HailoPoseEstimator
        hef = (args.hef or s.pose_hef)
        if hef is None:
            raise SystemExit("--hef 또는 .env POSE_HEF가 필요합니다.")
        estimator = HailoPoseEstimator(hef.expanduser(), s.pose_score_threshold,
                                       s.pose_iou_threshold, s.pose_max_people)
        camera = PiCamera((s.camera_width, s.camera_height), s.camera_hflip, s.camera_vflip)
    if args.video:
        import simplejpeg  # picamera2와 함께 apt로 설치됨
        encode_jpeg = lambda f, q: simplejpeg.encode_jpeg(f, quality=q, colorspace="RGB")  # noqa: E731
        log.warning("⚠️ --video: 카메라 화면을 SSH 터널로 보냅니다 (개발용, 저장 안 함, D-011)")

    marker_view = None
    if args.markers:
        if args.mock:
            from pi.app.adapters.mock import MockMarkerDetector
            detector = MockMarkerDetector()
        else:
            from pi.app.adapters.markers import ArucoMarkerDetector
            detector = ArucoMarkerDetector(s.marker_dict)
        marker_view = MarkerView(detector, s.marker_size_cm, s.camera_focal_px)
        if not (s.marker_size_cm and s.camera_focal_px):
            log.warning("MARKER_SIZE_CM·CAMERA_FOCAL_PX 미설정 → 마커 거리·방향 추정 끔 (M0 측정 후 .env)")

    latest, stop, judge = Latest(), threading.Event(), Judge(s, marker_view)
    if s.sleep_marker_ids and not args.markers:
        log.warning("잠자리 마커가 설정돼 있지만 --markers가 꺼져 있음 → 잠자리 판단 안 함")
    worker = threading.Thread(target=run_loop, args=(camera, estimator, latest, encode_jpeg, stop, args.quality,
                                    0.1 if args.mock else 0.0, judge, marker_view),
                              daemon=True)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(latest, args.video, judge))
    server.daemon_threads = True
    worker.start()
    log.info("http://127.0.0.1:%d  (노트북: ssh -L %d:127.0.0.1:%d <user>@<pi> 후 http://localhost:%d)",
             args.port, args.port, args.port, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        worker.join(timeout=2)
        server.server_close()
        camera.close()
        estimator.close()


if __name__ == "__main__":
    main()
