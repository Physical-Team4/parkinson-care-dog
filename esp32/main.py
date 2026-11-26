# MechDog 진입점: 모드 루프. 블로킹 없이 각 서비스의 tick()을 짧게 돈다.
import utime

import config
from controllers.serial_cmd import SerialCommands, log
from controllers.heartbeat import Heartbeat
from drivers.eyes import Eyes
from drivers.laser import Laser
from drivers.mp3 import Mp3
from services.gait import Gait
from services.rhythm import Rhythm
from services.medication import Medication
from services.touch import Touch


def main():
    laser = Laser(config.LASER_PIN)
    laser.off()
    hb = Heartbeat(config.PI_TIMEOUT_MS)
    mp3 = Mp3()
    gait = Gait()
    rhythm = Rhythm(laser, gait, mp3)
    medication = Medication()
    eyes = Eyes()
    touch = Touch(medication, mp3, eyes)
    serial = SerialCommands(hb, rhythm, medication)

    last_status = 0
    try:
        while True:
            now = utime.ticks_ms()
            serial.poll()
            rhythm.tick(now)
            medication.tick(now, serial, hb)
            touch.tick(now, serial, hb)
            if utime.ticks_diff(now, last_status) >= config.STATUS_INTERVAL_MS:
                serial.send_status(rhythm, laser)
                last_status = now
            utime.sleep_ms(5)
    except Exception as e:
        log("crash " + repr(e))
        raise
    finally:
        laser.off()


main()
