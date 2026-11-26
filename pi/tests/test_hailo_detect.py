"""일반 물체 검출 출력 해석 테스트 (Hailo 없이). 실행: pytest pi/tests"""
import numpy as np
import pytest

from pi.app.adapters import mock
from pi.app.adapters.base import Detection
from pi.app.adapters.hailo_detect import COCO_NAMES, FURNITURE, parse_nms_by_class, to_detections
from pi.app.adapters.pose_decode import letterbox

BED = [0.70, 0.10, 0.85, 0.60, 0.80]      # y1, x1, y2, x2, score (모델 입력 기준 0~1)
PERSON = [0.20, 0.40, 0.80, 0.55, 0.90]


def test_coco_ids():
    assert len(COCO_NAMES) == 80
    assert COCO_NAMES[0] == "person"
    assert {n: COCO_NAMES[i] for n, i in FURNITURE.items()} == {"chair": "chair", "couch": "couch", "bed": "bed"}


def per_class_list():
    raw = [np.zeros((0, 5), np.float32) for _ in range(80)]
    raw[0] = np.array([PERSON], np.float32)
    raw[59] = np.array([BED], np.float32)
    return raw


@pytest.mark.parametrize("wrap", [False, True])
def test_parse_list_format(wrap):
    raw = per_class_list()
    parsed = parse_nms_by_class([raw] if wrap else raw)
    assert [(c, len(b)) for c, b in parsed] == [(0, 1), (59, 1)]


def test_parse_flat_format():
    flat = []
    for c in range(80):
        boxes = {0: [PERSON], 59: [BED]}.get(c, [])
        flat.append(len(boxes))
        for b in boxes:
            flat.extend(b)
    parsed = parse_nms_by_class(np.array(flat, np.float32))
    assert [c for c, _ in parsed] == [0, 59]
    assert parsed[0][1][0] == pytest.approx(PERSON, abs=1e-6) and parsed[1][1][0] == pytest.approx(BED, abs=1e-6)


def test_parse_flat_broken_raises():
    with pytest.raises(ValueError):
        parse_nms_by_class(np.array([3, 0.1, 0.2], np.float32))   # 박스 3개라는데 값이 모자람


def test_to_detections_undoes_letterbox():
    _, lb = letterbox(np.zeros((480, 640, 3), np.uint8), 640, 640)   # 위아래 80px 패딩
    dets = to_detections(parse_nms_by_class(per_class_list()), lb, 640, 640, score_threshold=0.5)
    assert [d.name for d in dets] == ["person", "bed"]                # 점수 높은 순
    bed = dets[1]
    assert bed.class_id == 59
    x1, y1, x2, y2 = bed.bbox
    assert (x1, x2) == pytest.approx((0.10, 0.60), abs=1e-5)
    assert (y1, y2) == pytest.approx(((0.70 * 640 - 80) / 480, (0.85 * 640 - 80) / 480), abs=1e-5)
    assert to_detections(parse_nms_by_class(per_class_list()), lb, 640, 640, 0.85)[0].name == "person"


def test_box_in_padding_is_clipped():
    _, lb = letterbox(np.zeros((480, 640, 3), np.uint8), 640, 640)
    raw = [np.zeros((0, 5), np.float32) for _ in range(80)]
    raw[59] = np.array([[0.70, 0.10, 0.95, 0.60, 0.8]], np.float32)   # 아래쪽이 패딩 영역까지
    [bed] = to_detections(parse_nms_by_class(raw), lb, 640, 640, 0.5)
    assert bed.bbox[3] == 1.0


def test_mock_object_detector():
    d = Detection(59, "bed", 0.8, (0.1, 0.6, 0.6, 0.9))
    m = mock.MockObjectDetector([[d]])
    assert m.detect(np.zeros((480, 640, 3), np.uint8)) == [d]
    m.close()
    assert m.closed
