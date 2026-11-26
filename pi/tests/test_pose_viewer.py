"""개발용 pose 뷰어 서버를 mock으로 한 번 돌려 본다 (영상 없음)."""
import json
import threading
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer

import numpy as np

from pi.app.adapters import mock
from pi.app.adapters.base import PersonPose
from pi.app.config import Settings
from pi.scripts.pose_viewer import Judge, Latest, make_handler, run_loop


SETTINGS = Settings(mock_hardware=True, supabase_url=None, supabase_service_key=None, esp32_serial_port=None,
                    esp32_serial_baud=115200, queue_path=Path(":memory:"), log_dir=Path("."), model_dir=Path("."))


def test_viewer_serves_keypoints_without_video():
    k = np.full((17, 3), 0.5, np.float32)  # 관절이 한 점에 겹침 → 판정 불가(none)
    est = mock.MockPoseEstimator([[PersonPose((0.1, 0.2, 0.3, 0.9), 0.8, k)]])
    latest, stop = Latest(), threading.Event()
    worker = threading.Thread(target=run_loop, args=(mock.MockCamera(), est, latest, None, stop, 60, 0.01, Judge(SETTINGS)))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(latest, video=False))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    worker.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        assert b"<canvas" in urllib.request.urlopen(base + "/").read()
        r = json.loads(urllib.request.urlopen(base + "/latest?after=0").read())
        assert r["video"] is False and r["seq"] >= 1
        d = r["d"]
        assert (d["w"], d["h"]) == (640, 480) and d["jpeg"] is None
        assert d["people"][0]["score"] == 0.8 and len(d["people"][0]["kpts"]) == 17
        assert d["judge"]["state"] == "none" and d["judge"]["alarms"] == []
    finally:
        stop.set()
        worker.join(2)
        server.shutdown()
        server.server_close()
