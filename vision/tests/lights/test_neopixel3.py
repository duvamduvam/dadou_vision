# SPDX-FileCopyrightText: 2021 Kattni Rembor for Adafruit Industries
# SPDX-License-Identifier: MIT

"""
This example shows usage of the PixelMap helper to easily treat a single strip as a horizontal or
vertical grid for animation purposes.

For NeoPixel FeatherWing. Update pixel_pin and pixel_num to match your wiring if using
a different form of NeoPixels. Note that if you are using a number of pixels other than 32, you
will need to alter the PixelMap values as well for this example to work.

This example does not work on SAMD21 (M0) boards.
"""
import board
import neopixel
from adafruit_led_animation import helper
from adafruit_led_animation.animation.chase import Chase
from adafruit_led_animation.animation.comet import Comet
from adafruit_led_animation.animation.rainbow import Rainbow
from adafruit_led_animation.animation.rainbowchase import RainbowChase
from adafruit_led_animation.animation.rainbowcomet import RainbowComet
from adafruit_led_animation.color import PURPLE, JADE, AMBER
from adafruit_led_animation.helper import PixelMap
from adafruit_led_animation.sequence import AnimationSequence

# Update to match the pin connected to your NeoPixels
pixel_pin = board.D18
# Update to match the number of NeoPixels you have connected
pixel_num = 64*16

pixels = neopixel.NeoPixel(pixel_pin, pixel_num, brightness=0.01, auto_write=False)

#pixel_wing_vertical = helper.PixelMap.vertical_lines(
#    pixels, 24, 32, helper.horizontal_strip_gridmap(24, alternating=True)
#)


pixel_map = []
for y in range(1, 24):
    res = y + (256 * (y // 8)-1)
    print(res)
    for x in range(1, 32):
        pixel_map.append(res)
        res += 8


print(pixel_map)


pixel_wing_horizontal = PixelMap(pixels, [
    pixel_map,
], individual_pixels=True)

#pixel_wing_horizontal = helper.PixelMap(pixels, [
#    (0,31), (32, 63)
#], individual_pixels=True)
#pixel_wing_horizontal = helper.PixelMap.horizontal_lines(
#    pixels, 32, 32, helper.vertical_strip_gridmap(32, alternating=False)
#)

comet_h = Comet(
    pixel_wing_horizontal, speed=0.1, color=PURPLE, tail_length=3, bounce=True
)
#comet_v = Comet(pixel_wing_vertical, speed=0.1, color=AMBER, tail_length=6, bounce=True)
chase_h = Chase(pixel_wing_horizontal, speed=0.1, size=3, spacing=6, color=JADE)
#rainbow_chase_v = RainbowChase(
#    pixel_wing_vertical, speed=0.1, size=3, spacing=2, step=8
#)
#rainbow_comet_v = RainbowComet(
#    pixel_wing_vertical, speed=0.1, tail_length=7, bounce=True
#)
#rainbow_v = Rainbow(pixel_wing_vertical, speed=0.1, period=2)
rainbow_chase_h = RainbowChase(pixel_wing_horizontal, speed=0.1, size=3, spacing=3)

animations = AnimationSequence(
#    rainbow_v,
    comet_h,
#    rainbow_comet_v,
    chase_h,
#    rainbow_chase_v,
#    comet_v,
    rainbow_chase_h,
    advance_interval=5,
)

while True:
    animations.animate()
