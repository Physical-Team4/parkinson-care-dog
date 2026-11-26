# Hiwonder MechDog
# MicroPython - APP Bluetooth control + Rhythmic Cueing
#
# Original app control code is kept as it was.
# Added: rhythmic cueing (walk with gait timed to a BPM, clap sound on every beat)
#   - Touch sensor (port 3, IO33): tap to start / stop rhythmic cueing
#   - Bluetooth: "CMD|7|1|$" start, "CMD|7|0|$" stop
#   - Any other app motion command also stops rhythmic cueing
# Added: rear VL53L1X ToF distance sensor
#   - Not in rhythmic cueing: stop when something is too close behind (rear obstacle guard)
#   - In rhythmic cueing: follow the person behind
#       person near -> normal stride, person farther -> smaller stride
#       person lost -> stop and blink eyes, lost too long -> end rhythmic cueing

import Hiwonder
import time
import Hiwonder_IIC
from Hiwonder_BLE import BLE
from HW_MechDog import MechDog
import machine
try:
  import _thread
  bus_lock = _thread.allocate_lock()
except Exception:
  class _NoLock:
    def acquire(self):
      pass
    def release(self):
      pass
  bus_lock = _NoLock()

_BLE_REC_DATA = 0
_COMMAND = 0
_SEND_DATA = 0
_DATA = 0
_distance = 0
_SONER_DISTANCE = 0
_self_balancing_flag = 0
_RUN_STEP = 0
_obstacle_avoidance_flag = 0
_Pitch_angle = 0
_Roll_angle = 0
_ACTION_TYPE = 0
_ACTION_NUM = 0
_RUN_DIR = 0
_REC_PARSE_VALUE = []
_High_mm = 0
_rhythm_flag = 0
_REAR_DISTANCE = None
_rear_blocked = False

# ===== Rhythmic cueing settings =====
RHYTHM_BPM = 50              # beats per minute
RHYTHM_STRIDE = 25           # stride (mm)
CLAP_TRACK = 25              # clap sound number on the MP3 card
RHYTHM_VOLUME = 25           # MP3 volume (0-30)
MP3_BUS = 2                  # first I2C bus to try for the MP3 module
TOUCH_PIN = 33               # touch sensor on port 3 (IO33): touched = 0, released = 1
TOUCH_DEBOUNCE_MS = 500      # ignore extra taps within this time

# ===== Rear ToF sensor (VL53L1X) settings =====
TOF_BUS = 2                  # first I2C bus to try for the rear sensor (address 41 = 0x29)
TOF_ADDR = 0x29
REAR_STOP_MM = 200           # rear obstacle closer than this -> stop (not in rhythmic cueing)
REAR_STOP_ALL = False        # False: stop only backward walking, True: stop any walking
DEBUG_REAR = False           # True: print rear distance every 0.5 s (for testing)

# person following (rhythmic cueing only)
FOLLOW_NEAR_MM = 500         # person this close or closer -> full stride
FOLLOW_FAR_MM = 1200         # person this far -> smallest stride
LOST_MM = 1500               # farther than this (or nothing detected) = person lost
RHYTHM_STRIDE_MIN = 10       # smallest stride (mm) when the person falls behind
LOST_CONFIRM_MS = 1000       # person missing this long -> stop and wait (blink eyes)
FOUND_CONFIRM_MS = 700       # person seen again this long -> walk again
LOST_END_MS = 10000          # person missing this long -> end rhythmic cueing
BEAT_WHILE_WAITING = True    # keep the clap beat while waiting for the person

BEAT_MS = int(60000 / RHYTHM_BPM)      # 50 BPM -> 1200 ms
STEP_MS = BEAT_MS                      # one step per beat
LIFT_MS = 150                          # leg in the air (short = less wobble)
TOUCHDOWN_MS = STEP_MS - LIFT_MS       # leg on the ground
LIFT_HEIGHT = 25                       # leg lift height (mm)
DEFAULT_GAIT = (150, 500, 40)          # gait restored after cueing (block default values)

mac = machine.unique_id()
ble = BLE(BLE.MODE_BLE_SLAVE,"MechDog_{:02X}".format(mac[5]))
mechdog = MechDog()
i2c1 = Hiwonder_IIC.IIC(1)
i2csonar = Hiwonder_IIC.I2CSonar(i2c1)
touch = machine.Pin(TOUCH_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
_last_touch_ms = 0

_buses = {1: i2c1}
def get_bus(n):
  if n not in _buses:
    _buses[n] = Hiwonder_IIC.IIC(n)
  return _buses[n]

# find the MP3 module on bus 2 or 1
mp3 = None
for _bus in (MP3_BUS, 1, 2):
  try:
    _m = Hiwonder_IIC.MP3(get_bus(_bus))
    bus_lock.acquire()
    try:
      _m.volume(RHYTHM_VOLUME)
    finally:
      bus_lock.release()
    mp3 = _m
    print("MP3 found on bus", _bus)
    break
  except Exception as e:
    print("No MP3 on bus", _bus, e)

# ===== VL53L1X ToF distance sensor (rear) =====
# Minimal driver based on ST's VL53L1X ULD default configuration.

VL53L1X_DEFAULT_CONFIG = bytes([
  0x00, 0x00, 0x00, 0x01, 0x02, 0x00, 0x02, 0x08, 0x00, 0x08, 0x10, 0x01, 0x01, 0x00, 0x00, 0x00,
  0x00, 0xff, 0x00, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x20, 0x0b, 0x00, 0x00, 0x02, 0x0a, 0x21,
  0x00, 0x00, 0x05, 0x00, 0x00, 0x00, 0x00, 0xc8, 0x00, 0x00, 0x38, 0xff, 0x01, 0x00, 0x08, 0x00,
  0x00, 0x01, 0xcc, 0x0f, 0x01, 0xf1, 0x0d, 0x01, 0x68, 0x00, 0x80, 0x08, 0xb8, 0x00, 0x00, 0x00,
  0x00, 0x0f, 0x89, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x0f, 0x0d, 0x0e, 0x0e, 0x00,
  0x00, 0x02, 0xc7, 0xff, 0x9B, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00,
])   # registers 0x2D ~ 0x87


class VL53L1X:
  def __init__(self, i2c, addr=0x29):
    self.i2c = i2c
    self.addr = addr
    self.mode = "mem16"

  def _w(self, reg, data):
    bus_lock.acquire()
    try:
      if self.mode == "mem16":
        self.i2c.writeto_mem(self.addr, reg, data, addrsize=16)
      else:
        self.i2c.writeto(self.addr, bytes([reg >> 8, reg & 0xFF]) + data)
    finally:
      bus_lock.release()

  def _r(self, reg, n):
    bus_lock.acquire()
    try:
      if self.mode == "mem16":
        return self.i2c.readfrom_mem(self.addr, reg, n, addrsize=16)
      self.i2c.writeto(self.addr, bytes([reg >> 8, reg & 0xFF]))
      return self.i2c.readfrom(self.addr, n)
    finally:
      bus_lock.release()

  def _find_access_mode(self):
    # the sensor uses 16-bit register addresses; try both ways and check the model id (0xEACC)
    for mode in ("mem16", "raw"):
      self.mode = mode
      try:
        idb = self._r(0x010F, 2)
        if idb[0] == 0xEA and idb[1] == 0xCC:
          return True
      except Exception:
        pass
    return False

  def init(self):
    if not self._find_access_mode():
      raise OSError("VL53L1X model id not found")
    for i in range(100):                      # wait for sensor boot
      if self._r(0x00E5, 1)[0] & 0x01:
        break
      time.sleep_ms(10)
    self._w(0x002D, VL53L1X_DEFAULT_CONFIG)
    self._w(0x0087, b"\x40")                  # start ranging (first run)
    for i in range(100):
      if self.data_ready():
        break
      time.sleep_ms(10)
    self._w(0x0086, b"\x01")                  # clear interrupt
    self._w(0x0087, b"\x00")                  # stop ranging
    self._w(0x0008, b"\x09")
    self._w(0x000B, b"\x00")
    self._w(0x0087, b"\x40")                  # start continuous ranging

  def data_ready(self):
    pol = 0 if (self._r(0x0030, 1)[0] & 0x10) else 1
    return (self._r(0x0031, 1)[0] & 0x01) == pol

  def read(self):
    # returns distance in mm, None (no valid target), or -1 (no new measurement yet)
    if not self.data_ready():
      return -1
    status = self._r(0x0089, 1)[0] & 0x1F
    d = self._r(0x0096, 2)
    mm = (d[0] << 8) | d[1]
    self._w(0x0086, b"\x01")                  # clear interrupt for next measurement
    if status != 9 or mm == 0:                # 9 = valid range
      return None
    return mm


# find the rear ToF sensor on bus 2 or 1
tof = None
for _bus in (TOF_BUS, 1, 2):
  try:
    if TOF_ADDR not in get_bus(_bus).scan():
      continue
    _t = VL53L1X(get_bus(_bus), TOF_ADDR)
    _t.init()
    tof = _t
    print("Rear ToF found on bus", _bus, "mode", _t.mode)
    break
  except Exception as e:
    print("Rear ToF init failed on bus", _bus, e)
if tof is None:
  print("No rear ToF sensor - rear guard and person following disabled")

time.sleep(1)

def start_main():
  global ble
  global _BLE_REC_DATA
  global _COMMAND
  global _SEND_DATA
  global _DATA
  global _distance
  global _SONER_DISTANCE
  global _self_balancing_flag
  global _RUN_STEP
  global _obstacle_avoidance_flag
  global _Pitch_angle
  global _Roll_angle
  global mechdog
  global _ACTION_TYPE
  global _ACTION_NUM
  global _RUN_DIR
  global _REC_PARSE_VALUE
  global _High_mm
  global _rhythm_flag

  dir_flag = 1
  while True:
    if ble.is_connected():
      if ble.contains_data("CMD"):
        _BLE_REC_DATA = ble.read_uart_cmd()
        if not _BLE_REC_DATA:
          continue
        _REC_PARSE_VALUE = ble.parse_uart_cmd(_BLE_REC_DATA)
        _COMMAND = _REC_PARSE_VALUE[0]
        _COMMAND = int(_COMMAND)
        if (_COMMAND==6):
          _SEND_DATA = "CMD|6|{}|$".format(Hiwonder.Battery_power())
          ble.send_data(_SEND_DATA)
          continue
        if (_COMMAND==7):
          # rhythmic cueing: CMD|7|1|$ start, CMD|7|0|$ stop
          _DATA = int(_REC_PARSE_VALUE[1])
          if (_DATA==1):
            if (_rhythm_flag==0) and (_obstacle_avoidance_flag==0) and (_self_balancing_flag==0):
              _RUN_STEP = 70
          else:
            if (_rhythm_flag==1):
              _RUN_STEP = 71
          continue
        if (_COMMAND==4):
          _DATA = int(_REC_PARSE_VALUE[1])
          if (_DATA==1):
            _distance = round((_SONER_DISTANCE*10))
            if (_distance>5000):
              _distance = 5000
            _SEND_DATA = "CMD|4|{}|$".format(_distance)
            ble.send_data(_SEND_DATA)
          elif ((_DATA==2) and (_self_balancing_flag==0)):
            if ((int(_REC_PARSE_VALUE[2]))==1):
              mechdog.set_default_pose()
              _Pitch_angle = 0
              _Roll_angle = 0
              _High_mm = 0
              time.sleep(1)
              _RUN_STEP = 41
            else:
              _RUN_STEP = 40
          elif (_DATA==3):
            i2csonar.setRGB(0,(int(_REC_PARSE_VALUE[2])),(int(_REC_PARSE_VALUE[3])),(int(_REC_PARSE_VALUE[4])))
          continue
        if ((_COMMAND==1) and (_obstacle_avoidance_flag==0)):
          _DATA = int(_REC_PARSE_VALUE[1])
          if (_DATA==3):
            _DATA = int(_REC_PARSE_VALUE[2])
            if (_DATA==1):
              mechdog.set_default_pose()
              _Pitch_angle = 0
              _Roll_angle = 0
              _High_mm = 0
              time.sleep(1)
              _RUN_STEP = 131
            else:
              _RUN_STEP = 130
          if ((_obstacle_avoidance_flag==0) and (_self_balancing_flag==0)):
            if (_DATA==1):
              _DATA = int(_REC_PARSE_VALUE[2])
              if (_DATA==1):
                if (_Roll_angle<17):
                  _Roll_angle+=1
                  mechdog.transform([0, 0, 0], [-1, 0, 0], 80)
              else:
                if (_Roll_angle>-17):
                  _Roll_angle-=1
                  mechdog.transform([0, 0, 0], [1, 0, 0], 80)
            if (_DATA==2):
              _DATA = int(_REC_PARSE_VALUE[2])
              if (_DATA==1):
                if (_Pitch_angle<17):
                  _Pitch_angle+=1
                  mechdog.transform([0, 0, 0], [0, 1, 0], 80)
              else:
                if (_Pitch_angle>-17):
                  _Pitch_angle-=1
                  mechdog.transform([0, 0, 0], [0, -1, 0], 80)
            if (_DATA==4):
              _DATA = int(_REC_PARSE_VALUE[2])
              if (_DATA==1):
                if (_High_mm < 15):
                  _High_mm += 1
                  mechdog.transform([0, 0, 1], [0, 0, 0], 80)
              else:
                if _High_mm > -25:
                  _High_mm -= 1
                  mechdog.transform([0, 0, -1], [0, 0, 0], 80)
            if (_DATA==5):
              mechdog.set_default_pose()
              _Pitch_angle = 0
              _Roll_angle = 0
              _High_mm = 0
              time.sleep(1)
            continue
        if (_COMMAND==2) and (_obstacle_avoidance_flag==0) and (_self_balancing_flag==0):
          _RUN_STEP = 2
          _ACTION_TYPE = int(_REC_PARSE_VALUE[1])
          _ACTION_NUM = int(_REC_PARSE_VALUE[2])
        if (_COMMAND==3) and (_obstacle_avoidance_flag==0) and (_self_balancing_flag==0):
          _RUN_STEP = 3
          _RUN_DIR = int(_REC_PARSE_VALUE[1])
          if _rear_blocked and ((_RUN_DIR >= 6) or REAR_STOP_ALL):
            _RUN_DIR = 0                        # rear obstacle: do not walk into it
          if _RUN_DIR < 6:
            if dir_flag != 1:
              dir_flag = 1
              mechdog.transform([10 , 0 , 0] , [0 , 0 , 0] , 100)
          else:
            if dir_flag != -1:
              dir_flag = -1
              mechdog.transform([-10 , 0 , 0] , [0 , 0 , 0] , 100)
      else:
        time.sleep(0.03)


def start_main1():
  global ble
  global _SONER_DISTANCE
  global _self_balancing_flag
  global _RUN_STEP
  global _obstacle_avoidance_flag
  global mechdog
  global _ACTION_TYPE
  global _ACTION_NUM
  global _RUN_DIR
  global i2csonar
  global _Pitch_angle
  global _Roll_angle
  global _High_mm
  global _rhythm_flag

  step = 0
  while True:
    if (step==0):
      step = _RUN_STEP
      _RUN_STEP = 0
      time.sleep(0.05)
    else:
      if (step==41):
        _obstacle_avoidance_flag = 1
        forward_flag = 1
        while True:
          if ((_RUN_STEP==40) or (_obstacle_avoidance_flag==0)):
            _obstacle_avoidance_flag = 0
            mechdog.move(0,0)
            i2csonar.setRGB(0,0x33,0x33,0xff)
            if forward_flag == 0:
                forward_flag = 1
                mechdog.transform([10 , 0 , 0] , [0 , 0 , 0] , 100)
            time.sleep(1)
            break
          if (_SONER_DISTANCE<10):
            i2csonar.setRGB(0,0xff,0x00,0x00)
            if forward_flag == 1:
              forward_flag = 0
              mechdog.transform([-10 , 0 , 0] , [0 , 0 , 0] , 100)
            mechdog.move(-40,0)
            for count in range(30):
              if (_RUN_STEP==40):
                break
              time.sleep(0.1)
          else:
            if forward_flag == 0:
                forward_flag = 1
                mechdog.transform([10 , 0 , 0] , [0 , 0 , 0] , 100)
            if (_SONER_DISTANCE<40):
              i2csonar.setRGB(0,0xff,0xcc,0x00)
              mechdog.move(80,-50)
              for count in range(50):
                if (_RUN_STEP==40):
                  break
                time.sleep(0.1)
            else:
              i2csonar.setRGB(0,0xcc,0x33,0xcc)
              mechdog.move(120,0)
          time.sleep(0.02)
      if (step==131):
        _self_balancing_flag = 1
        mechdog.homeostasis(True)
        time.sleep(2)
        while True:
          if (_RUN_STEP==130):
            _self_balancing_flag = 0
            mechdog.homeostasis(False)
            time.sleep(2)
            break
          if not (mechdog.read_homeostasis_status()):
            ble.send_data("CMD|1|3|0|$")
            _self_balancing_flag = 0
            break
      if (step==70):
        rhythmic_cueing()
      if (step==2):
        if (_ACTION_TYPE==1):
          mechdog.set_default_pose(duration = 500)
          _Pitch_angle = 0
          _Roll_angle = 0
          _High_mm = 0
          time.sleep(1)
          dong_zuo_zu_yun_xing(_ACTION_NUM)
        else:
          mechdog.set_default_pose(duration = 500)
          _Pitch_angle = 0
          _Roll_angle = 0
          _High_mm = 0
          time.sleep(1)
          mechdog.action_run(str(_ACTION_NUM))
      if (step==3):
        while True:
          if (_RUN_DIR==0):
            mechdog.move(0,0)
            break
          elif (_RUN_DIR==1):
            mechdog.move(80,-40)
            continue
          elif (_RUN_DIR==2):
            mechdog.move(90,-25)
            continue
          elif (_RUN_DIR==3):
            mechdog.move(120,0)
            continue
          elif (_RUN_DIR==4):
            mechdog.move(90,25)
            continue
          elif (_RUN_DIR==5):
            mechdog.move(80,40)
            continue
          elif (_RUN_DIR==6):
            mechdog.move(-40,-20)
            continue
          elif (_RUN_DIR==7):
            mechdog.move(-40,0)
            continue
          elif (_RUN_DIR==8):
            mechdog.move(-40,20)
            continue
      step = 0

def dong_zuo_zu_yun_xing(dong_zuo):
  global mechdog

  if (dong_zuo==1):
    mechdog.action_run("left_foot_kick")
    time.sleep(3)
    return
  if (dong_zuo==2):
    mechdog.action_run("right_foot_kick")
    time.sleep(3)
    return
  if (dong_zuo==3):
    mechdog.action_run("stand_four_legs")
    time.sleep(2)
    return
  if (dong_zuo==4):
    mechdog.action_run("sit_dowm")
    time.sleep(2)
    return
  if (dong_zuo==5):
    mechdog.action_run("go_prone")
    time.sleep(2)
    return
  if (dong_zuo==6):
    mechdog.action_run("stand_two_legs")
    time.sleep(4)
    return
  if (dong_zuo==7):
    mechdog.action_run("handshake")
    time.sleep(4)
    return
  if (dong_zuo==8):
    mechdog.action_run("scrape_a_bow")
    time.sleep(4)
    return
  if (dong_zuo==9):
    mechdog.action_run("nodding_motion")
    time.sleep(2)
    return
  if (dong_zuo==10):
    mechdog.action_run("boxing")
    time.sleep(2)
    return
  if (dong_zuo==11):
    mechdog.action_run("stretch_oneself")
    time.sleep(2)
    return
  if (dong_zuo==12):
    mechdog.action_run("pee")
    time.sleep(2)
    return
  if (dong_zuo==13):
    mechdog.action_run("press_up")
    time.sleep(2)
    return
  if (dong_zuo==14):
    mechdog.action_run("rotation_pitch")
    time.sleep(2)
    return
  if (dong_zuo==15):
    mechdog.action_run("rotation_roll")
    time.sleep(2)
    return


def play_beat():
  if mp3 is None:
    print("no MP3 module")
    return
  bus_lock.acquire()
  try:
    mp3.play(CLAP_TRACK)
  except Exception as e:
    print("SOUND ERROR:", e)
  finally:
    bus_lock.release()


def stop_sound():
  if mp3 is None:
    return
  bus_lock.acquire()
  try:
    mp3.pause()
  except Exception as e:
    print("SOUND ERROR:", e)
  finally:
    bus_lock.release()


def eyes(r, g, b):
  try:
    i2csonar.setRGB(0, r, g, b)
  except Exception:
    pass


_rear_hist = []
_rear_debug_ms = 0

def update_rear():
  # read the rear sensor, keep the median of the last 5 readings in _REAR_DISTANCE
  global _REAR_DISTANCE
  global _rear_debug_ms
  if tof is None:
    return
  try:
    v = tof.read()
  except Exception as e:
    v = None
  if v == -1:
    return                                    # no new measurement yet
  _rear_hist.append(v)
  if len(_rear_hist) > 5:
    _rear_hist.pop(0)
  valid = sorted([x for x in _rear_hist if x is not None])
  if len(valid) * 2 > len(_rear_hist):
    _REAR_DISTANCE = valid[len(valid) // 2]
  else:
    _REAR_DISTANCE = None
  if DEBUG_REAR and time.ticks_diff(time.ticks_ms(), _rear_debug_ms) > 500:
    _rear_debug_ms = time.ticks_ms()
    print("rear:", _REAR_DISTANCE, "mm")
  rear_guard()


def rear_guard():
  # not in rhythmic cueing: stop walking when something is too close behind
  global _RUN_DIR
  global _rear_blocked
  if (_rhythm_flag==1):
    _rear_blocked = False
    return
  d = _REAR_DISTANCE
  blocked = (d is not None) and (d < REAR_STOP_MM)
  if blocked:
    if (_RUN_DIR >= 6) or (REAR_STOP_ALL and _RUN_DIR != 0):
      _RUN_DIR = 0                            # ends the app walking loop -> move(0,0)
      print("REAR OBSTACLE", d, "mm - stop")
    if not _rear_blocked:
      eyes(0xff, 0x00, 0x00)                  # red while something is close behind
  elif _rear_blocked:
    eyes(0x00, 0x00, 0x00)
  _rear_blocked = blocked


def follow_stride(d):
  # person near -> full stride, farther -> smaller stride
  if d <= FOLLOW_NEAR_MM:
    return RHYTHM_STRIDE
  if d >= FOLLOW_FAR_MM:
    return RHYTHM_STRIDE_MIN
  ratio = (d - FOLLOW_NEAR_MM) / (FOLLOW_FAR_MM - FOLLOW_NEAR_MM)
  return int(RHYTHM_STRIDE - ratio * (RHYTHM_STRIDE - RHYTHM_STRIDE_MIN))


def rhythmic_cueing():
  global _RUN_STEP
  global _rhythm_flag
  global _Pitch_angle
  global _Roll_angle
  global _High_mm

  _rhythm_flag = 1
  print("RHYTHM START -", RHYTHM_BPM, "BPM, MP3:", "OK" if mp3 else "NOT FOUND",
        ", rear ToF:", "OK" if tof else "NOT FOUND")
  mechdog.set_default_pose()
  _Pitch_angle = 0
  _Roll_angle = 0
  _High_mm = 0
  time.sleep(1)
  mechdog.set_gait_params(LIFT_MS, TOUCHDOWN_MS, LIFT_HEIGHT)
  time.sleep_ms(100)

  following = tof is not None
  walking = False
  stride_now = 0
  last_stride_ms = 0
  lost_since = None
  found_since = None
  blink_ms = 0
  blink_on = False
  end_reason = "stopped"

  if following:
    eyes(0xff, 0x60, 0x00)                    # orange = waiting for the person
  else:                                       # no rear sensor: just walk to the beat
    mechdog.move(RHYTHM_STRIDE, 0)
    walking = True
    stride_now = RHYTHM_STRIDE
    eyes(0x00, 0xff, 0x00)

  next_beat = time.ticks_ms()
  beat_count = 0
  while True:
    # any new command (stop, app motion, ...) ends rhythmic cueing
    if (_RUN_STEP!=0):
      break
    now = time.ticks_ms()

    if following:
      d = _REAR_DISTANCE
      person = (d is not None) and (d <= LOST_MM)
      if person:
        lost_since = None
        if not walking:
          if found_since is None:
            found_since = now
          elif time.ticks_diff(now, found_since) >= FOUND_CONFIRM_MS:
            walking = True                    # person is there -> walk
            stride_now = follow_stride(d)
            mechdog.move(stride_now, 0)
            last_stride_ms = now
            eyes(0x00, 0xff, 0x00)            # green = following well
            print("PERSON FOUND", d, "mm - walk, stride", stride_now)
        else:
          target = follow_stride(d)
          if abs(target - stride_now) >= 3 and time.ticks_diff(now, last_stride_ms) >= 300:
            stride_now = target
            mechdog.move(stride_now, 0)
            last_stride_ms = now
            print("follow", d, "mm -> stride", stride_now)
      else:
        found_since = None
        if lost_since is None:
          lost_since = now
        lost_ms = time.ticks_diff(now, lost_since)
        if walking and lost_ms >= LOST_CONFIRM_MS:
          walking = False                     # person lost -> stop and wait
          mechdog.move(0, 0)
          print("PERSON LOST - waiting")
        if lost_ms >= LOST_END_MS:
          end_reason = "person lost too long"
          break

      if not walking and time.ticks_diff(now, blink_ms) >= 400:
        blink_ms = now                        # blink orange while waiting
        blink_on = not blink_on
        if blink_on:
          eyes(0xff, 0x60, 0x00)
        else:
          eyes(0x00, 0x00, 0x00)

    if time.ticks_diff(now, next_beat) >= 0:
      if walking or BEAT_WHILE_WAITING:
        play_beat()
      beat_count += 1
      next_beat = time.ticks_add(next_beat, BEAT_MS)
    time.sleep_ms(5)

  if (_RUN_STEP==71):
    _RUN_STEP = 0
  mechdog.move(0,0)
  stop_sound()
  time.sleep(1)
  mechdog.set_gait_params(DEFAULT_GAIT[0], DEFAULT_GAIT[1], DEFAULT_GAIT[2])
  mechdog.set_default_pose()
  eyes(0x00, 0x00, 0x00)
  _rhythm_flag = 0
  print("RHYTHM STOP after", beat_count, "beats -", end_reason)


def on_touch(pin):
  # called the moment the sensor is touched (signal goes 1 -> 0)
  global _RUN_STEP
  global _last_touch_ms
  now = time.ticks_ms()
  if time.ticks_diff(now, _last_touch_ms) < TOUCH_DEBOUNCE_MS:
    return
  _last_touch_ms = now
  if (_rhythm_flag==1):
    _RUN_STEP = 71
  elif (_obstacle_avoidance_flag==0) and (_self_balancing_flag==0):
    _RUN_STEP = 70


touch.irq(trigger=machine.Pin.IRQ_FALLING, handler=on_touch)


def start_main2():
  global _SONER_DISTANCE
  global i2csonar

  time.sleep(2)
  while True:
    _SONER_DISTANCE = i2csonar.getDistance()
    update_rear()
    time.sleep(0.08)

Hiwonder.startMain(start_main)
Hiwonder.startMain(start_main1)
Hiwonder.startMain(start_main2)
