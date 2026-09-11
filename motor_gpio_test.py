#!/usr/bin/env python3
"""
L293D motor GPIO diagnostic test.

IMPORTANT:
- This script assumes the L293D EN pins are hard-wired HIGH separately.
- Do NOT connect 5V to Raspberry Pi GPIO12/GPIO13.
- Lift the drive wheels off the ground before running this test.

Actual wiring:
  Left : IN1=GPIO5,  IN2=GPIO4
  Right: IN1=GPIO27, IN2=GPIO17
"""

import time
import pigpio

LEFT_A = 5
LEFT_B = 4
RIGHT_A = 27
RIGHT_B = 17

TEST_SEC = 1.0
STOP_SEC = 0.7


def drive(pi, a, b, direction):
    # EN is assumed to be hard-wired HIGH at the L293D.
    if direction > 0:
        pi.write(a, 1)
        pi.write(b, 0)
    elif direction < 0:
        pi.write(a, 0)
        pi.write(b, 1)
    else:
        pi.write(a, 0)
        pi.write(b, 0)


def stop_all(pi):
    drive(pi, LEFT_A, LEFT_B, 0)
    drive(pi, RIGHT_A, RIGHT_B, 0)


def run_test(pi, name, a, b, direction):
    stop_all(pi)
    time.sleep(STOP_SEC)

    expected_a = 1 if direction > 0 else 0
    expected_b = 0 if direction > 0 else 1
    print(f"\n{name}")
    print(f"  GPIO{a}={expected_a}, GPIO{b}={expected_b}")

    drive(pi, a, b, direction)
    time.sleep(0.05)
    print(f"  readback: GPIO{a}={pi.read(a)}, GPIO{b}={pi.read(b)}")
    time.sleep(TEST_SEC)

    stop_all(pi)
    time.sleep(STOP_SEC)


def main():
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("pigpiod is not running: sudo systemctl start pigpiod")

    try:
        for pin in (LEFT_A, LEFT_B, RIGHT_A, RIGHT_B):
            pi.set_mode(pin, pigpio.OUTPUT)
            pi.write(pin, 0)

        print("L293D motor GPIO diagnostic")
        print("EN pins must be hard-wired HIGH separately; never feed 5V into Pi GPIO12/13.")
        print("Lift the wheels before testing.")

        run_test(pi, "LEFT forward", LEFT_A, LEFT_B, +1)
        run_test(pi, "LEFT reverse", LEFT_A, LEFT_B, -1)
        run_test(pi, "RIGHT forward", RIGHT_A, RIGHT_B, +1)
        run_test(pi, "RIGHT reverse", RIGHT_A, RIGHT_B, -1)

        print("\nDone.")
        print("If RIGHT forward works but RIGHT reverse does not, check GPIO17 -> L293D right input first.")

    finally:
        try:
            stop_all(pi)
        finally:
            pi.stop()


if __name__ == "__main__":
    main()
