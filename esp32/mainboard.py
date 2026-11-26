# MechDog Rhythmic Cueing (MP3 module)
# Walks with gait timing matched to a fixed BPM and plays a sound on every beat.
# Press the board button to start / stop.

import Hiwonder
import Hiwonder_IIC
import time
from HW_MechDog import MechDog

# ===== Settings =====
BPM = 50             # beats per minute
SPEED = 25           # stride (mm)
CLAP_TRACK = 30      # sound number (change to clap sound later)
VOLUME = 25          # MP3 volume
MP3_BUS = 2          # first bus to try for the MP3 module
AUTO_START = False   # True: start 3 s after power-on

BEAT_MS = int(60000 / BPM)        

# ===== Gait (step timing) =====
STEP_MS = BEAT_MS                 # one step per beat
                                  # if feet land twice per beat: STEP_MS = BEAT_MS * 2
                                  # if feet land once every two beats: STEP_MS = BEAT_MS // 2
LIFT_MS = 150                     # time a leg is in the air (short = less wobble)
TOUCHDOWN_MS = STEP_MS - LIFT_MS  # time a leg stays on the ground
LIFT_HEIGHT = 25                  # leg lift height (mm), lower = more stable

mechdog = MechDog()
button = Hiwonder.Button(1)

# find the MP3 module on bus 1 or 2
mp3 = None
for bus in (MP3_BUS, 1, 2):
    try:
        m = Hiwonder_IIC.MP3(Hiwonder_IIC.IIC(bus))
        m.volume(VOLUME)
        mp3 = m
        print("MP3 found on bus", bus)
        break
    except Exception as e:
        print("No MP3 on bus", bus, e)

running = False
toggle_request = False


def play_beat():
    if mp3 is None:
        print("no MP3 module")
        return
    try:
        mp3.play(CLAP_TRACK)
    except Exception as e:
        print("SOUND ERROR:", e)
    
    


def stop_sound():
    if mp3 is None:
        return
    try:
        mp3.pause()
    except Exception as e:
        print("SOUND ERROR:", e)


def on_button():
    global toggle_request
    toggle_request = True


button.Clicked(on_button)

mechdog.set_default_pose()
time.sleep(1)


def main():
    global running, toggle_request

    print("READY -", BPM, "BPM, beat every", BEAT_MS, "ms")
    print("Gait: lift", LIFT_MS, "ms, touchdown", TOUCHDOWN_MS, "ms, height", LIFT_HEIGHT, "mm")
    print("Press button to start / stop")

    if AUTO_START:
        time.sleep(3)
        toggle_request = True

    next_beat = time.ticks_ms()
    beat_count = 0

    while True:
        if toggle_request:
            toggle_request = False
            running = not running
            if running:
                print("START - MP3:", "OK" if mp3 else "NOT FOUND", "track", CLAP_TRACK)
                mechdog.set_gait_params(LIFT_MS, TOUCHDOWN_MS, LIFT_HEIGHT)
                time.sleep_ms(100)
                mechdog.move(SPEED, 0)
                beat_count = 0
                next_beat = time.ticks_ms()
            else:
                mechdog.move(0, 0)
                stop_sound()
                time.sleep(1)
                mechdog.set_default_pose()
                print("STOP after", beat_count, "beats")

        if running and time.ticks_diff(time.ticks_ms(), next_beat) >= 0:
            play_beat()
            beat_count += 1
            print("beat", beat_count)
            next_beat = time.ticks_add(next_beat, BEAT_MS)

        time.sleep_ms(5)


Hiwonder.startMain(main)