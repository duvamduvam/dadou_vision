import time
import unittest

import board
from digitalio import DigitalInOut, Direction


class MyTestCase(unittest.TestCase):
    def test_led(self):
        self.status_led = DigitalInOut(board.D16)
        self.status_led.direction = Direction.OUTPUT
        self.status_led.value = True
        time.sleep(10)


if __name__ == '__main__':
    unittest.main()
