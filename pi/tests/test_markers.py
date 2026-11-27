"""로봇 이동 마커 인식 테스트 (카메라 없이 만든 마커 그림으로). 실행: pytest pi/tests"""
import json
import math
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np
import pytest

from pi.app.adapters import mock
from pi.app.adapters.base import MarkerObs
from pi.app.adapters.markers import estimate_bearing_deg, estimate_distance_cm

cv2 = pytest.importorskip("cv2")


def frame_with_marker(marker_id=7, side=120, x=400, y=150, w=640, h=480):
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    m = cv2.aruco.generateImageMarker(d, marker_id, side)
    frame = np.full((h, w, 3), 230, np.uint8)        # 밝은 벽 (흰 여백 역할)
    frame[y:y + side, x:x + side] = m[:, :, None]
    return frame


def test_detects_marker_id_position_and_size():
    from pi.app.adapters.markers import ArucoMarkerDetector
    det = ArucoMarkerDetector("DICT_4X4_50")
    [m] = det.detect(frame_with_marker(7, side=120, x=400))
    assert m.marker_id == 7 and (m.frame_w, m.frame_h) == (640, 480)
    assert m.side_px == pytest.approx(120, abs=3)
    assert m.cx == pytest.approx((400 + 60) / 640, abs=0.01)
    assert m.corners.shape == (4, 2) and 0 <= m.corners.min() and m.corners.max() <= 1
    assert det.last_ms > 0


def test_no_marker():
    from pi.app.adapters.markers import ArucoMarkerDetector
    det = ArucoMarkerDetector()
    assert det.detect(np.full((480, 640, 3), 230, np.uint8)) == []


def obs(side=60.0, cx=0.5):
    return MarkerObs(3, np.zeros((4, 2), np.float32), cx, side, 640, 480)


def test_distance_and_bearing_need_settings():
    assert estimate_distance_cm(obs(), None, 500) is None
    assert estimate_distance_cm(obs(), 12, None) is None
    assert estimate_bearing_deg(obs(), None) is None
    assert estimate_distance_cm(obs(side=60), 12, 500) == pytest.approx(100)     # 12 × 500 / 60
    assert estimate_bearing_deg(obs(cx=0.5), 500) == pytest.approx(0)
    right = estimate_bearing_deg(obs(cx=0.75), 500)                              # 160px 오른쪽
    assert right == pytest.approx(math.degrees(math.atan(160 / 500)))


def test_viewer_sends_markers():
    from pi.scripts.pose_viewer import Latest, MarkerView, make_handler, run_loop
    m = MarkerObs(3, np.array([[.1, .1], [.2, .1], [.2, .2], [.1, .2]], np.float32), 0.15, 64.0, 640, 480)
    latest, stop = Latest(), threading.Event()
    view = MarkerView(mock.MockMarkerDetector([[m]]), marker_cm=12, focal_px=500)
    worker = threading.Thread(target=run_loop, args=(mock.MockCamera(), mock.MockPoseEstimator(), latest, None,
                                                     stop, 60, 0.01, None, view))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(latest, video=False))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    worker.start()
    try:
        r = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/latest?after=0").read())
        [got] = r["d"]["markers"]["list"]
        assert got["id"] == 3 and got["side_px"] == 64.0 and got["dist_cm"] == pytest.approx(94, abs=1)
        assert got["bearing_deg"] < 0          # 화면 왼쪽
    finally:
        stop.set()
        worker.join(2)
        server.shutdown()
        server.server_close()


def test_viewer_markers_only_without_pose():
    """--markers-only: 포즈 추론·판정 없이 마커만 보낸다 (Hailo 없는 Pi용)."""
    from pi.scripts.pose_viewer import Latest, MarkerView, NoPose, make_handler, run_loop
    m = MarkerObs(7, np.array([[.6, .4], [.7, .4], [.7, .5], [.6, .5]], np.float32), 0.65, 48.0, 640, 480)
    latest, stop = Latest(), threading.Event()
    view = MarkerView(mock.MockMarkerDetector([[m]]), marker_cm=None, focal_px=None)
    worker = threading.Thread(target=run_loop, args=(mock.MockCamera(), NoPose(), latest, None,
                                                     stop, 60, 0.01, None, view))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(latest, video=False))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    worker.start()
    try:
        r = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/latest?after=0").read())
        d = r["d"]
        assert d["people"] == [] and d["judge"] is None and d["jpeg"] is None and d["timing"] == {}
        [got] = d["markers"]["list"]
        assert got["id"] == 7 and got["side_px"] == 48.0
        assert got["dist_cm"] is None and got["bearing_deg"] is None   # 설정 없으면 거리·방향 끔
    finally:
        stop.set()
        worker.join(2)
        server.shutdown()
        server.server_close()
