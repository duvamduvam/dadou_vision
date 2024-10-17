import board
import neopixel
from adafruit_led_animation.animation.blink import Blink

# Update to match the pin connected to your NeoPixels
pixel_pin = board.D18
# Update to match the number of NeoPixels you have connected
pixel_num = 64*8

pixels = neopixel.NeoPixel(pixel_pin, pixel_num, brightness=0.5, auto_write=False)

blink = Blink(pixels, speed=0.5, color=(255, 0, 0))

while True:
    blink.animate()