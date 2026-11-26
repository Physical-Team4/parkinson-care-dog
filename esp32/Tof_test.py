# Rear ToF sensor (VL53L1X) test
# 1) finds the sensor (address 41 = 0x29) on I2C bus 1 or 2
# 2) prints the distance every 0.2 s for 30 seconds
# Move your hand / walk in front of the sensor and check the numbers.

import time
import Hiwonder_IIC


class _NoLock:
  def acquire(self):
    pass
  def release(self):
    pass

bus_lock = _NoLock()

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


tof = None
for bus in (1, 2):
  try:
    i2c = Hiwonder_IIC.IIC(bus)
    found = i2c.scan()
    print("bus", bus, "devices:", found)
    if 0x29 in found:
      t = VL53L1X(i2c)
      t.init()
      tof = t
      print("ToF OK on bus", bus, "access mode:", t.mode)
      break
  except Exception as e:
    print("bus", bus, "error:", e)

if tof is None:
  print("ToF NOT FOUND - check wiring (VCC, GND, SCL, SDA)")
else:
  end = time.ticks_add(time.ticks_ms(), 30000)
  while time.ticks_diff(end, time.ticks_ms()) > 0:
    v = tof.read()
    if v == -1:
      time.sleep_ms(10)
      continue
    if v is None:
      print("distance: no target")
    else:
      print("distance:", v, "mm")
    time.sleep_ms(200)
  print("END")
