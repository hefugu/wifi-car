"""
Author:helo

"""
#!/usr/bin/env python3
# rc_server.py — Pico W (UDP) → Raspberry Pi 4 → L293D (два двигателя) + Серво (GPIO18)

import argparse
import logging
import socket
import time
import pigpio

# ===== Пользовательские настройки (по умолчанию) =====
UDP_PORT = 5005            # должен совпадать с портом Pico W
DEADZONE = 0.08            # мёртвая зона джойстика (0..1)
BASE_SPEED = 0.60          # обычная максимальная скорость (0..1)
TURBO_SPEED = 1.00         # максимальная скорость при нажатой кнопке b1
EXPO = 0.6                 # кривая чувствительности (0 = линейная, 0.6 = более плавно на малых ходах)
PWM_FREQ = 20000           # частота PWM двигателей (Гц)
FAILSAFE_SEC = 0.5         # остановка при отсутствии пакетов (сек)
VERBOSE_LOG = False        # выводить «сырые» пакеты, если True

# Пины L293D (нумерация BCM)
EN_L, IN1_L, IN2_L = 12, 5, 6      # Левый: Enable, IN1, IN2
EN_R, IN1_R, IN2_R = 13, 23, 24    # Правый: Enable, IN3, IN4

# Серво
SERVO_PIN = 18                     # пин PWM для сигнала сервопривода


# ===== Вспомогательные функции =====
def adc_to_unit(v: int, deadzone: float) -> float:
    """Преобразует 0..65535 в −1..+1 (центр 0) с учётом мёртвой зоны."""
    u = (v / 65535.0) * 2.0 - 1.0
    return 0.0 if abs(u) < deadzone else max(-1.0, min(1.0, u))


def apply_expo(u: float, k: float) -> float:
    """Применяет экспоненциальную кривую — делает управление плавнее около нуля."""
    return (1 - k) * u + k * (u ** 3)


def set_motor(pi: pigpio.pi, dir_a: int, dir_b: int, en: int, val: float) -> None:
    """
    Управление мотором (val = −1..+1).
    Положительное — вперёд, отрицательное — назад, 0 — накат (coast).
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
        pi.write(dir_b, 0)
    pi.set_PWM_dutycycle(en, int(abs(val) * 255))


def brake(pi: pigpio.pi, dir_a: int, dir_b: int, en: int) -> None:
    """Активное торможение — оба входа HIGH, PWM = 0."""
    pi.write(dir_a, 1)
    pi.write(dir_b, 1)
    pi.set_PWM_dutycycle(en, 0)


def servo_from_x(pi: pigpio.pi, x: float, pin: int) -> None:
    """Преобразует x (−1..+1) в длительность импульса 500–2500 мкс и подаёт на сервопривод."""
    us = int(1500 + x * 1000)  # ±1000 мкс
    pi.set_servo_pulsewidth(pin, max(500, min(2500, us)))


def stop_all(pi: pigpio.pi) -> None:
    """Полная остановка двигателей и возврат сервопривода в центр."""
    brake(pi, IN1_L, IN2_L, EN_L)
    brake(pi, IN1_R, IN2_R, EN_R)
    pi.set_servo_pulsewidth(SERVO_PIN, 1500)


def parse_packet(data: bytes) -> tuple[int, int, int, int] | None:
    """Разбирает CSV-пакет b1,b2,x_raw,y_raw (все поля должны быть цифрами)."""
    text = data.decode("utf-8", errors="ignore").strip()
    if text.count(",") < 3:
        return None
    b1, b2, x_raw, y_raw = text.split(",")[:4]
    if not (b1.isdigit() and b2.isdigit() and x_raw.isdigit() and y_raw.isdigit()):
        return None
    return int(b1), int(b2), int(x_raw), int(y_raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="UDP RC-мост: Pico W → Raspberry Pi 4 → L293D + Servo")
    parser.add_argument("--port", type=int, default=UDP_PORT, help="порт UDP для прослушивания")
    parser.add_argument("--deadzone", type=float, default=DEADZONE, help="мёртвая зона джойстика")
    parser.add_argument("--base-speed", type=float, default=BASE_SPEED, help="базовая максимальная скорость 0..1")
    parser.add_argument("--turbo-speed", type=float, default=TURBO_SPEED, help="турбо-скорость (при нажатой b1)")
    parser.add_argument("--expo", type=float, default=EXPO, help="экспо-кривая входа 0..1")
    parser.add_argument("--pwm-freq", type=int, default=PWM_FREQ, help="частота PWM двигателя (Гц)")
    parser.add_argument("--failsafe", type=float, default=FAILSAFE_SEC, help="время отключения при потере связи (сек)")
    parser.add_argument("--verbose", action="store_true", help="подробный вывод пакетов")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )

    # Инициализация pigpio
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit(
            "pigpio-демон не запущен.\n"
            "Запуск: sudo systemctl start pigpiod\n"
            "Автозапуск: sudo systemctl enable pigpiod"
        )

    try:
        # Настройка GPIO
        for p in (IN1_L, IN2_L, IN1_R, IN2_R):
            pi.set_mode(p, pigpio.OUTPUT)
            pi.write(p, 0)

        for p in (EN_L, EN_R):
            pi.set_mode(p, pigpio.OUTPUT)
            pi.set_PWM_frequency(p, args.pwm_freq)
            pi.set_PWM_dutycycle(p, 0)

        pi.set_mode(SERVO_PIN, pigpio.OUTPUT)
        pi.set_servo_pulsewidth(SERVO_PIN, 1500)  # центр

        # Настройка UDP-сокета
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", args.port))
        sock.settimeout(0.1)  # таймаут для проверки failsafe
        logging.info(f"Прослушивание UDP на порту {args.port} ...")

        last_ok = time.time()

        while True:
            try:
                data, _ = sock.recvfrom(256)
            except socket.timeout:
                # нет данных — проверка failsafe
                if time.time() - last_ok > args.failsafe:
                    stop_all(pi)
                continue

            if args.verbose:
                logging.debug("RAW: %r", data)

            parsed = parse_packet(data)
            if parsed is None:
                continue

            b1, b2, x_raw, y_raw = parsed

            # нормализация и применение экспо
            x_unit = apply_expo(adc_to_unit(x_raw, args.deadzone), args.expo)
            y_unit = apply_expo(adc_to_unit(y_raw, args.deadzone), args.expo)  # вверх = вперёд

            last_ok = time.time()

            # режим скорости
            max_speed = args.turbo_speed if b1 == 0 else args.base_speed

            if b2 == 0:
                # b2 нажата — тормоз
                brake(pi, IN1_L, IN2_L, EN_L)
                brake(pi, IN1_R, IN2_R, EN_R)
            else:
                # дифференциальное управление (танковое)
                left = max(-1.0, min(1.0, y_unit + x_unit)) * max_speed
                right = max(-1.0, min(1.0, y_unit - x_unit)) * max_speed
                set_motor(pi, IN1_L, IN2_L, EN_L, left)
                set_motor(pi, IN1_R, IN2_R, EN_R, right)

            # управление сервоприводом (руль)
            servo_from_x(pi, x_unit, SERVO_PIN)

            # проверка failsafe
            if time.time() - last_ok > args.failsafe:
                stop_all(pi)

    except KeyboardInterrupt:
        logging.info("Остановка пользователем.")
    finally:
        # безопасное завершение
        try:
            stop_all(pi)
            pi.set_servo_pulsewidth(SERVO_PIN, 0)  # выключить сигнал серво
        except Exception:
            pass
        pi.stop()


if __name__ == "__main__":
    main()
