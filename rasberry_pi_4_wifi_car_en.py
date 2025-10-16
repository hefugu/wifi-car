"""
Author:helo
Created:2025/9/8
GitHub: https://github.com/hefugu/wifi-car
"""
#!/usr/bin/env python3
# rc_server.py — Pico W (UDP) -> Raspberry Pi 4 -> L293D (dual DC) + Servo (GPIO18)

import argparse
import logging
import socket
import time

import pigpio


# ===== User Configuration (defaults) =====
UDP_PORT = 5005            # must match the Pico W sender
DEADZONE = 0.08            # joystick deadband (0..1 in unit space)
BASE_SPEED = 0.60          # normal max speed (0..1)
TURBO_SPEED = 1.00         # max speed when b1 is held
EXPO = 0.6                 # input curve (0=linear, 0.6 = finer low-speed control)
PWM_FREQ = 20000           # motor PWM frequency (Hz)
FAILSAFE_SEC = 0.5         # stop if no packets within this window
VERBOSE_LOG = False        # print raw packets if True

# L293D pin mapping (BCM numbering)
EN_L, IN1_L, IN2_L = 12, 5, 6      # Left: Enable, IN1, IN2
EN_R, IN1_R, IN2_R = 13, 23, 24    # Right: Enable, IN3, IN4

# Servo
SERVO_PIN = 18                     # PWM-capable pin for servo signal


# ===== Utilities =====
def adc_to_unit(v: int, deadzone: float) -> float:
    """Map 0..65535 -> -1..+1 (center 0), applying deadzone around 0."""
    u = (v / 65535.0) * 2.0 - 1.0
    return 0.0 if abs(u) < deadzone else max(-1.0, min(1.0, u))


def apply_expo(u: float, k: float) -> float:
    """Apply exponential-like curve: mix linear and cubic for finer control near zero."""
    return (1 - k) * u + k * (u ** 3)


def set_motor(pi: pigpio.pi, dir_a: int, dir_b: int, en: int, val: float) -> None:
    """
    Command motor with value in [-1..+1].
    Positive: forward, Negative: reverse, Zero: coast (inputs LOW, PWM=0).
    """
    val = max(-1.0, min(1.0, val))
    if val > 0:
        pi.write(dir_a, 1)
        pi.write(dir_b, 0)
    elif val < 0:
        pi.write(dir_a, 0)
        pi.write(dir_b, 1)
    else:
        pi.write(dir_a, 0)
        pi.write(dir_b, 0)  # coast
    pi.set_PWM_dutycycle(en, int(abs(val) * 255))


def brake(pi: pigpio.pi, dir_a: int, dir_b: int, en: int) -> None:
    """Active braking: both inputs HIGH, PWM 0."""
    pi.write(dir_a, 1)
    pi.write(dir_b, 1)
    pi.set_PWM_dutycycle(en, 0)


def servo_from_x(pi: pigpio.pi, x: float, pin: int) -> None:
    """
    Map x in [-1..+1] to servo pulse width 500..2500 µs.
    If travel is too wide, reduce scale to e.g. ±600 µs.
    """
    us = int(1500 + x * 1000)  # ±1000 µs
    pi.set_servo_pulsewidth(pin, max(500, min(2500, us)))


def stop_all(pi: pigpio.pi) -> None:
    brake(pi, IN1_L, IN2_L, EN_L)
    brake(pi, IN1_R, IN2_R, EN_R)
    pi.set_servo_pulsewidth(SERVO_PIN, 1500)


def parse_packet(data: bytes) -> tuple[int, int, int, int] | None:
    """Robust CSV parse: b1,b2,x_raw,y_raw — all must be digits."""
    text = data.decode("utf-8", errors="ignore").strip()
    if text.count(",") < 3:
        return None
    b1, b2, x_raw, y_raw = text.split(",")[:4]
    if not (b1.isdigit() and b2.isdigit() and x_raw.isdigit() and y_raw.isdigit()):
        return None
    return int(b1), int(b2), int(x_raw), int(y_raw)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="UDP RC bridge: Pico W -> RasPi 4 -> L293D + Servo"
    )
    parser.add_argument("--port", type=int, default=UDP_PORT, help="UDP listen port")
    parser.add_argument("--deadzone", type=float, default=DEADZONE, help="Joystick deadband")
    parser.add_argument("--base-speed", type=float, default=BASE_SPEED, help="Base max speed 0..1")
    parser.add_argument("--turbo-speed", type=float, default=TURBO_SPEED, help="Turbo max speed 0..1 (b1 pressed)")
    parser.add_argument("--expo", type=float, default=EXPO, help="Input curve mix 0..1")
    parser.add_argument("--pwm-freq", type=int, default=PWM_FREQ, help="Motor PWM frequency (Hz)")
    parser.add_argument("--failsafe", type=float, default=FAILSAFE_SEC, help="Failsafe timeout seconds")
    parser.add_argument("--verbose", action="store_true", help="Print raw packets")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )

    # pigpio setup
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit(
            "pigpio daemon is not running.\n"
            "Start it with: sudo systemctl start pigpiod\n"
            "Enable on boot: sudo systemctl enable pigpiod"
        )

    try:
        # GPIO modes
        for p in (IN1_L, IN2_L, IN1_R, IN2_R):
            pi.set_mode(p, pigpio.OUTPUT)
            pi.write(p, 0)  # safe state

        for p in (EN_L, EN_R):
            pi.set_mode(p, pigpio.OUTPUT)
            pi.set_PWM_frequency(p, args.pwm_freq)
            pi.set_PWM_dutycycle(p, 0)

        pi.set_mode(SERVO_PIN, pigpio.OUTPUT)
        pi.set_servo_pulsewidth(SERVO_PIN, 1500)  # center

        # UDP setup
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", args.port))
        sock.settimeout(0.1)  # allow loop to run to check failsafe
        logging.info(f"Listening UDP on {args.port} ...")

        last_ok = time.time()

        while True:
            try:
                data, _ = sock.recvfrom(256)
            except socket.timeout:
                # no data this tick — check failsafe
                if time.time() - last_ok > args.failsafe:
                    stop_all(pi)
                continue

            if args.verbose:
                logging.debug("RAW: %r", data)

            parsed = parse_packet(data)
            if parsed is None:
                continue

            b1, b2, x_raw, y_raw = parsed

            # Normalize, deadzone, expo
            x_unit = apply_expo(adc_to_unit(x_raw, args.deadzone), args.expo)
            y_unit = apply_expo(adc_to_unit(y_raw, args.deadzone), args.expo)  # up = forward

            last_ok = time.time()

            # Speed mode
            max_speed = args.turbo_speed if b1 == 0 else args.base_speed

            if b2 == 0:
                # b2 pressed: brake
                brake(pi, IN1_L, IN2_L, EN_L)
                brake(pi, IN1_R, IN2_R, EN_R)
            else:
                # differential mixing (tank drive)
                left = max(-1.0, min(1.0, y_unit + x_unit)) * max_speed
                right = max(-1.0, min(1.0, y_unit - x_unit)) * max_speed
                set_motor(pi, IN1_L, IN2_L, EN_L, left)
                set_motor(pi, IN1_R, IN2_R, EN_R, right)

            # Servo for steering/pan (disable here if unused)
            servo_from_x(pi, x_unit, SERVO_PIN)

            # Extra failsafe barrier in-loop
            if time.time() - last_ok > args.failsafe:
                stop_all(pi)

    except KeyboardInterrupt:
        logging.info("Interrupted by user.")
    finally:
        # Always leave things safe
        try:
            stop_all(pi)
            pi.set_servo_pulsewidth(SERVO_PIN, 0)  # stop servo signal
        except Exception:
            pass
        pi.stop()


if __name__ == "__main__":
    main()

