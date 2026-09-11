"""
Author:helo
Created:2025/9/8
GitHub: https://github.com/hefugu/wifi-car
"""
#!/usr/bin/env python3
# Pico W（UDP送信）→ Raspberry Pi 4 → L293D（左右DCモータ）＋サーボ(GPIO18)

import argparse
import logging
import socket
import time
import pigpio

# ===== ユーザー設定 =====
UDP_PORT = 5005
SERVO_DEADZONE = 0.12      # サーボ用ジョイスティック中央の遊び
MOTOR_DEADZONE = 0.20      # モーター停止を優先して中央を広めに取る
EXPO = 0.6                 # サーボ用入力カーブ
FAILSAFE_SEC = 0.35        # 通信途絶で停止するまでの秒数

# L293D ピン割り当て（BCM番号）
# 実機配線:
#   左 = EN 12 / IN1 5 / IN2 4
#   右 = EN 13 / IN1 14 / IN2 15
EN_L, IN1_L, IN2_L = 12, 5, 4
EN_R, IN1_R, IN2_R = 13, 14, 15

# サーボ
SERVO_PIN = 18


# ===== ユーティリティ =====
def adc_to_unit(v: int, deadzone: float) -> float:
    """0〜65535を-1〜+1へ変換し、中央にデッドゾーンを設ける。"""
    u = (v / 65535.0) * 2.0 - 1.0
    if abs(u) < deadzone:
        return 0.0
    return max(-1.0, min(1.0, u))


def apply_expo(u: float, k: float) -> float:
    return (1 - k) * u + k * (u ** 3)


def set_motor(pi: pigpio.pi, dir_a: int, dir_b: int, en: int, val: float) -> None:
    """
    PWMなしのデジタル制御。
      val > 0 : 前進・全開
      val < 0 : 後退・全開
      val = 0 : 停止
    """
    # 方向ピンを書き換える前に必ずEnableを落とす。
    pi.write(en, 0)

    if val > 0:
        pi.write(dir_a, 1)
        pi.write(dir_b, 0)
        pi.write(en, 1)
    elif val < 0:
        pi.write(dir_a, 0)
        pi.write(dir_b, 1)
        pi.write(en, 1)
    else:
        pi.write(dir_a, 0)
        pi.write(dir_b, 0)
        pi.write(en, 0)


def stop_motor(pi: pigpio.pi, dir_a: int, dir_b: int, en: int) -> None:
    """モーターを確実に停止する。"""
    pi.write(en, 0)
    pi.write(dir_a, 0)
    pi.write(dir_b, 0)


def stop_drive(pi: pigpio.pi) -> None:
    """左右モーターだけを即停止する。"""
    stop_motor(pi, IN1_L, IN2_L, EN_L)
    stop_motor(pi, IN1_R, IN2_R, EN_R)


def servo_from_x(pi: pigpio.pi, x: float, pin: int) -> None:
    """X軸でステアリング。実機の向きに合わせて左右反転済み。"""
    us = int(1500 - x * 1000)
    pi.set_servo_pulsewidth(pin, max(500, min(2500, us)))


def stop_all(pi: pigpio.pi) -> None:
    stop_drive(pi)
    pi.set_servo_pulsewidth(SERVO_PIN, 1500)


def parse_packet(data: bytes) -> tuple[int, int, int, int] | None:
    """Picoからの b1,b2,x_raw,y_raw を解析する。"""
    text = data.decode("utf-8", errors="ignore").strip()
    parts = text.split(",")
    if len(parts) < 4:
        return None

    b1, b2, x_raw, y_raw = parts[:4]
    if not (b1.isdigit() and b2.isdigit() and x_raw.isdigit() and y_raw.isdigit()):
        return None

    x = int(x_raw)
    y = int(y_raw)
    if not (0 <= x <= 65535 and 0 <= y <= 65535):
        return None

    return int(b1), int(b2), x, y


def recv_latest(sock: socket.socket) -> bytes:
    """
    まず1パケット待って受信し、その後キューに既に溜まっている古いUDPを
    ノンブロッキングで捨てて、一番新しいパケットだけを返す。
    """
    data, _ = sock.recvfrom(256)

    while True:
        try:
            newer, _ = sock.recvfrom(256, socket.MSG_DONTWAIT)
            data = newer
        except BlockingIOError:
            break
        except OSError:
            break

    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="UDP RCブリッジ: Pico W -> RasPi 4 -> L293D + サーボ")
    parser.add_argument("--port", type=int, default=UDP_PORT, help="UDP受信ポート")
    parser.add_argument("--servo-deadzone", type=float, default=SERVO_DEADZONE, help="サーボ用デッドゾーン")
    parser.add_argument("--motor-deadzone", type=float, default=MOTOR_DEADZONE, help="モーター用デッドゾーン")
    parser.add_argument("--expo", type=float, default=EXPO, help="サーボ入力カーブ(0〜1)")
    parser.add_argument("--failsafe", type=float, default=FAILSAFE_SEC, help="通信断で停止するまでの秒数")
    parser.add_argument("--verbose", action="store_true", help="受信値を表示")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )

    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit(
            "pigpioデーモンが起動していません。\n"
            "  sudo systemctl start pigpiod\n"
            "  sudo systemctl enable pigpiod"
        )

    sock = None

    try:
        # GPIO初期化。PWMは使用しない。
        for p in (EN_L, IN1_L, IN2_L, EN_R, IN1_R, IN2_R):
            pi.set_mode(p, pigpio.OUTPUT)
            pi.write(p, 0)

        pi.set_mode(SERVO_PIN, pigpio.OUTPUT)
        pi.set_servo_pulsewidth(SERVO_PIN, 1500)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 操作パケットを何秒分も溜めない。
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        sock.bind(("0.0.0.0", args.port))
        sock.settimeout(0.05)

        logging.info("UDP受信をポート %d で開始", args.port)
        logging.info("モーターピン: 左 12/5/4, 右 13/14/15")
        logging.info("モーター制御: DIGITAL HIGH/LOW（PWMなし）")
        logging.info("操作: X=サーボのみ / Y=左右モーター / b1無効 / b2=停止")
        logging.info("停止対策: 最新UDPのみ使用 + モーター中央デッドゾーン %.2f", args.motor_deadzone)

        last_ok = time.monotonic()
        failsafe_active = False
        last_log = 0.0

        while True:
            try:
                data = recv_latest(sock)
            except socket.timeout:
                if time.monotonic() - last_ok > args.failsafe:
                    if not failsafe_active:
                        logging.warning("通信が %.2f 秒以上途絶えたため停止", args.failsafe)
                        failsafe_active = True
                    stop_drive(pi)
                continue

            parsed = parse_packet(data)
            if parsed is None:
                continue

            _b1, b2, x_raw, y_raw = parsed
            last_ok = time.monotonic()

            if failsafe_active:
                logging.info("通信復帰")
                failsafe_active = False

            x_unit = apply_expo(adc_to_unit(x_raw, args.servo_deadzone), args.expo)
            y_unit = adc_to_unit(y_raw, args.motor_deadzone)

            # verboseでも毎パケットprintしない。ログ詰まりによる操作遅延を防ぐ。
            now = time.monotonic()
            if args.verbose and now - last_log >= 0.20:
                logging.debug(
                    "x_raw=%d y_raw=%d x=%.3f y=%.3f b2=%d",
                    x_raw, y_raw, x_unit, y_unit, b2,
                )
                last_log = now

            if b2 == 0 or y_unit == 0.0:
                # 中央に戻った瞬間、左右とも必ずLOWへ。
                stop_drive(pi)
            else:
                # 横入力は絶対にモーターへ混ぜない。
                set_motor(pi, IN1_L, IN2_L, EN_L, y_unit)
                set_motor(pi, IN1_R, IN2_R, EN_R, y_unit)

            # X軸はサーボだけ。
            servo_from_x(pi, x_unit, SERVO_PIN)

    except KeyboardInterrupt:
        logging.info("ユーザーによって中断されました。")
    finally:
        try:
            stop_all(pi)
            pi.set_servo_pulsewidth(SERVO_PIN, 0)
        except Exception:
            pass

        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

        pi.stop()


if __name__ == "__main__":
    main()
