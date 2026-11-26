"""여러 사람 추적 (담당: A). 프레임 사이에서 같은 사람에게 같은 번호를 붙인다. 프레임은 다루지 않는다.

매칭 순서:
  1) 박스 겹침(IoU) 큰 쌍부터
  2) 남은 것끼리 중심 거리 / 이전 박스 높이 < center_max_ratio (빠른 낙상은 박스 모양이 급히 바뀌어 IoU가 작다)
  3) 그래도 남은 추적 1개 + 검출 1개면 그냥 이음 (한 명뿐인 집에서 쓰러지는 순간 추적이 끊기지 않게)
max_age_s 동안 안 보인 추적은 끝낸다 (expired로 돌려줌).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pi.app.adapters.base import PersonPose


@dataclass
class Track:
    track_id: int
    person: PersonPose
    last_s: float
    seen_now: bool = field(default=True)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return self.person.bbox


def iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def center_dist_ratio(prev, cur, frame_aspect: float) -> float:
    """중심 거리 / 이전 박스 높이 (가로는 픽셀 비율 보정)."""
    dx = ((cur[0] + cur[2]) - (prev[0] + prev[2])) / 2 * frame_aspect
    dy = ((cur[1] + cur[3]) - (prev[1] + prev[3])) / 2
    return (dx * dx + dy * dy) ** 0.5 / max(prev[3] - prev[1], 1e-6)


class PersonTracker:
    def __init__(self, iou_min: float, center_max_ratio: float, max_age_s: float, frame_aspect: float) -> None:
        self.iou_min = iou_min
        self.center_max_ratio = center_max_ratio
        self.max_age_s = max_age_s
        self.frame_aspect = frame_aspect
        self.tracks: dict[int, Track] = {}
        self._next_id = 1

    def update(self, people: list[PersonPose], now: float) -> tuple[list[Track], list[Track]]:
        """반환: (지금 보이는 추적, 이번에 끝난 추적). 새로 생긴 추적은 보이는 추적에 포함."""
        old = list(self.tracks.values())
        for t in old:
            t.seen_now = False
        free_t = set(range(len(old)))
        free_p = set(range(len(people)))
        pairs: list[tuple[int, int]] = []

        cand = sorted(((iou(old[i].bbox, people[j].bbox), i, j) for i in free_t for j in free_p), reverse=True)
        for v, i, j in cand:
            if v < self.iou_min:
                break
            if i in free_t and j in free_p:
                pairs.append((i, j))
                free_t.discard(i)
                free_p.discard(j)

        cand = sorted((center_dist_ratio(old[i].bbox, people[j].bbox, self.frame_aspect), i, j)
                      for i in free_t for j in free_p)
        for d, i, j in cand:
            if d > self.center_max_ratio:
                break
            if i in free_t and j in free_p:
                pairs.append((i, j))
                free_t.discard(i)
                free_p.discard(j)

        if len(free_t) == 1 and len(free_p) == 1 and len(old) == 1:
            pairs.append((free_t.pop(), free_p.pop()))

        for i, j in pairs:
            t = old[i]
            t.person, t.last_s, t.seen_now = people[j], now, True
        for j in sorted(free_p):
            t = Track(self._next_id, people[j], now)
            self._next_id += 1
            self.tracks[t.track_id] = t

        expired = [t for t in self.tracks.values() if not t.seen_now and now - t.last_s > self.max_age_s]
        for t in expired:
            del self.tracks[t.track_id]
        visible = [t for t in self.tracks.values() if t.seen_now]
        return visible, expired
