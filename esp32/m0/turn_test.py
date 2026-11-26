# M0 turn test (docs/navigation.md section 11-1). MechDog only, no Pi needed.
# Run without saving to the board:
#   mpremote connect <PORT> resume run esp32/m0/turn_test.py
#
# Before each run: mark the robot's facing direction on the floor with tape.
# After each run (robot stops): measure the angle it turned and how far it drifted.
# move(stride_mm, angle_deg): stride -100~100 (+forward), angle -30~30 (+ = left)  (Hiwonder wiki)
# There is no documented in-place turn API, so this checks whether move(0, a) or move(1, a) turns in place.
# Comments/prints are English on purpose (Hiwonder editor drops Korean text).

import time
from HW_MechDog import MechDog

RUN_S = 5          # seconds per motion
PAUSE_S = 10       # time to measure and re-align between motions
CANDIDATES = [     # (stride_mm, angle_deg, note)
    (0, 30, "stride 0, left"),
    (0, -30, "stride 0, right"),
    (1, 30, "stride 1mm (almost stepping in place), left"),
    (1, -30, "stride 1mm, right"),
    (20, 30, "small circle reference, left"),
    (20, -30, "small circle reference, right"),
    (20, 40, "angle outside -30~30: clipped or error?"),
]


def log(text):
    print("# " + str(text))


def countdown(n):
    for i in range(n, 0, -1):
        log("start in %d" % i)
        time.sleep(1)


dog = MechDog()
time.sleep(1)
try:
    for i, (stride, angle, note) in enumerate(CANDIDATES):
        log("[%d/%d] move(%d, %d) for %d s  -- %s" % (i + 1, len(CANDIDATES), stride, angle, RUN_S, note))
        log("mark the start heading now")
        countdown(3)
        try:
            dog.move(stride, angle)
            time.sleep(RUN_S)
        except Exception as e:
            log("error: " + str(e))
        dog.move(0, 0)
        log("stopped. write down: turned angle (deg), drift (cm), turned in place? (y/n)")
        if i + 1 < len(CANDIDATES):
            log("next motion in %d s (re-align the robot)" % PAUSE_S)
            time.sleep(PAUSE_S)
finally:
    dog.move(0, 0)
    time.sleep(0.5)
    dog.set_default_pose()
    log("done")
