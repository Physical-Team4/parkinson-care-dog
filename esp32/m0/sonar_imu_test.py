# M0 front sonar + IMU tilt test (docs/navigation.md section 11-2). MechDog only, no Pi needed.
# Run without saving to the board:
#   mpremote connect <PORT> resume run esp32/m0/sonar_imu_test.py
#
# 1) Sonar: place a flat board/box in front of the robot's head at each distance when asked.
#    The script averages 20 readings (0.08 s apart). Compare with the real distance -> unit (cm or mm?) and range.
# 2) Low obstacle (cable, door sill height object) at 30 cm, then nothing in front (max value).
# 3) IMU: tilt the robot by hand (sideways, forward) for 15 s -> read_angle() values for the robot_tipped threshold.
# The robot does not walk in this test.
# Comments/prints are English on purpose (Hiwonder editor drops Korean text).

import time
import Hiwonder_IIC

STEPS_CM = [20, 50, 100, 150, 200, 300]
SAMPLES = 20
SAMPLE_GAP_S = 0.08
PLACE_S = 8        # time to move the board between steps
IMU_S = 15


def log(text):
    print("# " + str(text))


def wait(n, what):
    log(what)
    for i in range(n, 0, -1):
        if i <= 3 or i % 5 == 0:
            log("  measuring in %d" % i)
        time.sleep(1)


def measure(sonar, label):
    vals = []
    for _ in range(SAMPLES):
        try:
            vals.append(sonar.getDistance())
        except Exception as e:
            log("read error: " + str(e))
        time.sleep(SAMPLE_GAP_S)
    if not vals:
        log("%s: no readings" % label)
        return
    avg = sum(vals) / len(vals)
    log("%s: avg %.1f  min %s  max %s  (n=%d)" % (label, avg, min(vals), max(vals), len(vals)))
    log("RESULT | %s | %.1f | %s~%s |" % (label, avg, min(vals), max(vals)))


i2c1 = Hiwonder_IIC.IIC(1)
log("I2C bus 1 scan: " + str(i2c1.scan()) + "  (expect 119 = sonar, 106 = IMU)")
sonar = Hiwonder_IIC.I2CSonar(i2c1)

for cm in STEPS_CM:
    wait(PLACE_S, "place the board %d cm in front of the head" % cm)
    measure(sonar, "%dcm" % cm)

wait(PLACE_S, "place a LOW obstacle (cable / sill height object) 30 cm in front")
measure(sonar, "low obstacle 30cm")
wait(PLACE_S, "remove everything in front (open space)")
measure(sonar, "nothing")

log("IMU: tilt the robot by hand sideways and forward for %d s" % IMU_S)
try:
    imu = Hiwonder_IIC.MPU()
    end = time.time() + IMU_S
    while time.time() < end:
        log("read_angle: " + str(imu.read_angle()))
        time.sleep(0.3)
except Exception as e:
    log("IMU error: " + str(e))
log("done")
