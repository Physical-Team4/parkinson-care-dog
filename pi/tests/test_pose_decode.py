"""YOLOv8-pose 디코딩·letterbox·mock 테스트 (Hailo 없이). 실행: pytest pi/tests"""
import numpy as np
import pytest

from pi.app.adapters import mock
from pi.app.adapters.base import PersonPose
from pi.app.adapters.pose_decode import YoloV8PoseDecoder, letterbox, nms

IN = 640


def fake_outputs(hits, cls_as_prob=False):
    """hits: [(stride, gy, gx, logit)]. 각 hit 셀은 l=t=r=b=2칸, kpt raw (0, 0), conf logit 3."""
    outs = {}
    for k, s in enumerate((8, 16, 32)):
        g = IN // s
        box = np.zeros((g, g, 64), np.float32)
        box.reshape(g, g, 4, 16)[..., 2] = 50.0       # DFL → 거리 2칸
        cls = np.full((g, g, 1), -10.0, np.float32)
        kpt = np.zeros((g, g, 51), np.float32)
        kpt.reshape(g, g, 17, 3)[..., 2] = 3.0
        for hs, gy, gx, logit in hits:
            if hs == s:
                cls[gy, gx, 0] = logit
        if cls_as_prob:
            cls = 1 / (1 + np.exp(-cls))
        # 이름은 실제 모델처럼 순서 없이
        outs[f"m/conv{k}_kpt"] = kpt
        outs[f"m/conv{k}_cls"] = cls
        outs[f"m/conv{k}_box"] = box[None]            # 배치 차원 있어도 됨
    return outs


def decoder():
    return YoloV8PoseDecoder(IN, IN, score_threshold=0.5, iou_threshold=0.7, max_people=3)


def test_letterbox_640x480_pads_only():
    frame = np.full((480, 640, 3), 7, np.uint8)
    img, lb = letterbox(frame, IN, IN)
    assert img.shape == (640, 640, 3) and img.flags.c_contiguous
    assert (lb.scale, lb.pad_x, lb.pad_y) == (1.0, 0, 80)
    assert img[80:560].min() == 7 and img[:80].max() == 114


def test_letterbox_resizes_other_sizes():
    img, lb = letterbox(np.zeros((1080, 1920, 3), np.uint8), IN, IN)
    assert img.shape == (640, 640, 3)
    assert lb.scale == pytest.approx(1 / 3) and lb.pad_x == 0 and lb.pad_y == 140


@pytest.mark.parametrize("as_prob", [False, True])
def test_decode_one_person_to_frame_coords(as_prob):
    _, lb = letterbox(np.zeros((480, 640, 3), np.uint8), IN, IN)
    people = decoder().decode(fake_outputs([(16, 10, 20, 5.0)], cls_as_prob=as_prob), lb)
    assert len(people) == 1
    p = people[0]
    # 입력 픽셀: 중심 (20.5*16, 10.5*16) = (328, 168), 반폭 32 → (296,136,360,200), 패딩 y 80 제거
    assert p.bbox == pytest.approx((296 / 640, 56 / 480, 360 / 640, 120 / 480), abs=1e-4)
    assert p.score == pytest.approx(1 / (1 + np.exp(-5)), abs=1e-4)
    assert p.keypoints.shape == (17, 3)
    assert p.keypoints[0, 0] == pytest.approx(320 / 640) and p.keypoints[0, 1] == pytest.approx(80 / 480)
    assert p.keypoints[:, 2] == pytest.approx(np.full(17, 1 / (1 + np.exp(-3))), abs=1e-4)


def test_decode_empty_and_nms_merges_neighbours():
    _, lb = letterbox(np.zeros((480, 640, 3), np.uint8), IN, IN)
    assert decoder().decode(fake_outputs([]), lb) == []
    # 바로 옆 셀 두 개(박스 32px가 8px 어긋남, IoU 0.6) → 하나, 멀리 떨어진 셀 → 따로
    dec = YoloV8PoseDecoder(IN, IN, score_threshold=0.5, iou_threshold=0.5, max_people=3)
    people = dec.decode(fake_outputs([(8, 30, 30, 4.0), (8, 30, 31, 3.0), (8, 50, 60, 2.0)]), lb)
    assert len(people) == 2
    assert people[0].score > people[1].score


def test_nms_max_det():
    boxes = np.array([[0, 0, 10, 10], [100, 100, 110, 110], [200, 200, 210, 210]], np.float32)
    assert nms(boxes, np.array([0.9, 0.8, 0.7]), 0.5, max_det=2) == [0, 1]


def test_rejects_non_pose_outputs():
    with pytest.raises(ValueError):
        decoder().group_outputs({"x": np.zeros((80, 80, 80), np.float32)})
    outs = fake_outputs([])
    del outs["m/conv0_kpt"]
    with pytest.raises(ValueError):
        decoder().group_outputs(outs)


def test_mocks():
    cam = mock.MockCamera()
    assert cam.capture().shape == (480, 640, 3)
    cam.close()
    assert cam.closed
    p = PersonPose((0.1, 0.1, 0.5, 0.9), 0.9, np.zeros((17, 3), np.float32))
    est = mock.MockPoseEstimator([[], [p]])
    assert est.infer(cam.capture()) == []
    assert est.infer(cam.capture()) == [p]
    assert est.infer(cam.capture()) == [p]
