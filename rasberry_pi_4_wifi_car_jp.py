"""
Author:helo
Created:2025/9/8
GitHub: https://github.com/hefugu/wifi-car
"""
#!/usr/bin/env python3
# rc_server.py — Pico W（UDP送信）→ Raspberry Pi 4 → L293D（左右DCモータ）＋サーボ(GPIO18)

import argparse
import logging
import socket
import time
import pigpio

# ===== ユーザー設定（デフォルト値） =====
UDP_PORT = 5005            # Pico W 側と一致させる
DEADZONE = 0.12            # ジョイスティックの遊び（0〜1）。停止時の微振動対策で少し広め
BASE_SPEED = 0.60          # 最高速度（0〜1）
EXPO = 0.6                 # 入力カーブ（0=直線、0.6で低速域が繊細）
PWM_FREQ = 20000           # モーターPWM周波数(Hz)
FAILSAFE_SEC = 0.35        # 通信途絶で停止するまでの秒数
VERBOSE_LOG = False        # Trueにすると受信データを表示

# L293D ピン割り当て（BCM番号）
# 実機配線:
#   左 = EN 12 / IN1 5 / IN2 4
#   右 = EN 13 / IN1 27 / IN2 17
EN_L, IN1_L, IN2_L = 12, 5, 4
EN_R, IN1_R, IN2_R = 13, 27, 17

# サーボ（PWM対応ピン）
SERVO_PIN = 18


# ===== ユーティリティ関数 =====
def adc_to_unit(v: int, deadzone: float) -> float:
    """0〜65535 のADC値を -1〜+1 に正規化し、中央の遊び(deadzone)を適用する"""
    u = (v / 65535.0) * 2.0 - 1.0
    return 0.0 if abs(u) < deadzone else max(-1.0, min(1.0, u))


def apply_expo(u: float, k: float) -> float:
    """スティック入力にエクスポカーブを適用（中央付近を繊細に）"""
    return (1 - k) * u + k * (u ** 3)


def set_motor(pi: pigpio.pi, dir_a: int, dir_b: int, en: int, val: float) -> None:
    """モーターを駆動する。val=-1〜+1、0で停止。"""
    val = max(-1.0, min(1.0, val))

    if val > 0:
        pi.write(dir_a, 1)
        pi.write(dir_b, 0)
    elif val < 0:
        pi.write(dir_a, 0)
        pi.write(dir_b, 1)
    else:
        # 停止時は方向ピンもLOWにして、誤駆動しにくい状態にする
        pi.write(dir_a, 0)
        pi.write(dir_b, 0)

    pi.set_PWM_dutycycle(en, int(abs(val) * 255))


def stop_motor(pi: pigpio.pi, dir_a: int, dir_b: int, en: int) -> None:
    """1台のモーターを確実に停止する"""
    pi.set_PWM_dutycycle(en, 0)
    pi.write(dir_a, 0)
    pi.write(dir_b, 0)


def servo_from_x(pi: pigpio.pi, x: float, pin: int) -> None:
    """X軸でステアリング。実機の向きに合わせて左右を反転している。"""
    # 以前は 1500 + x * 1000 だったため、右入力で左に切れていた。
    us = int(1500 - x * 1000)
    pi.set_servo_pulsewidth(pin, max(500, min(2500, us)))


def stop_all(pi: pigpio.pi) -> None:
    """全モーターを停止し、サーボを中央へ戻す"""
    stop_motor(pi, IN1_L, IN2_L, EN_L)
    stop_motor(pi, IN1_R, IN2_R, EN_R)
    pi.set_servo_pulsewidth(SERVO_PIN, 1500)


def parse_packet(data: bytes) -> tuple[int, int, int, int] | None:
    """PicoからのCSV形式データ b1,b2,x_raw,y_raw を解析"""
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


def main() -> None:
    parser = argparse.ArgumentParser(description="UDP RCブリッジ: Pico W -> RasPi 4 -> L293D + サーボ")
    parser.add_argument("--port", type=int, default=UDP_PORT, help="UDP受信ポート")
    parser.add_argument("--deadzone", type=float, default=DEADZONE, help="ジョイスティックの遊び")
    parser.add_argument("--base-speed", type=float, default=BASE_SPEED, help="最高速度(0〜1)")
    parser.add_argument("--expo", type=float, default=EXPO, help="入力カーブ(0〜1)")
    parser.add_argument("--pwm-freq", type=int, default=PWM_FREQ, help="モーターPWM周波数(Hz)")
    parser.add_argument("--failsafe", type=float, default=FAILSAFE_SEC, help="通信断で停止するまでの秒数")
    parser.add_argument("--verbose", action="store_true", help="受信データを詳細表示")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )

    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit(
            "pigpioデーモンが起動していません。\n"
            "以下で起動できます:\n"
            "  sudo systemctl start pigpiod\n"
            "常時起動するには:\n"
            "  sudo systemctl enable pigpiod"
        )

    sock = None

    try:
        # GPIO設定。まずEnableを0にしてから方向ピンを初期化する。
        for p in (EN_L, EN_R):
            pi.set_mode(p, pigpio.OUTPUT)
            pi.set_PWM_frequency(p, args.pwm_freq)
            pi.set_PWM_dutycycle(p, 0)

        for p in (IN1_L, IN2_L, IN1_R, IN2_R):
            pi.set_mode(p, pigpio.OUTPUT)
            pi.write(p, 0)

        pi.set_mode(SERVO_PIN, pigpio.OUTPUT)
        pi.set_servo_pulsewidth(SERVO_PIN, 1500)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", args.port))
        sock.settimeout(0.05)
        logging.info("UDP受信をポート %d で開始", args.port)
        logging.info("モーターピン: 左 12/5/4, 右 13/27/17")
        logging.info("操作: X=サーボのみ / Y=左右モーター / b1ブーストなし / b2=停止")

        last_ok = time.monotonic()
        failsafe_active = False

        while True:
            try:
                data, _ = sock.recvfrom(256)
            except socket.timeout:
                if time.monotonic() - last_ok > args.failsafe:
                    if not failsafe_active:
                        logging.warning("通信が %.2f 秒以上途絶えたため停止", args.failsafe)
                        failsafe_active = True
                    stop_all(pi)
                continue

            if args.verbose:
                logging.debug("RAWデータ: %r", data)

            parsed = parse_packet(data)
            if parsed is None:
                # 壊れたパケットではlast_okを更新しない。
                # 正常パケットが来なければフェイルセーフで止まる。
                continue

            _b1, b2, x_raw, y_raw = parsed
            last_ok = time.monotonic()

            if failsafe_active:
                logging.info("通信復帰")
                failsafe_active = False

            x_unit = apply_expo(adc_to_unit(x_raw, args.deadzone), args.expo)
            y_unit = apply_expo(adc_to_unit(y_raw, args.deadzone), args.expo)

            # b1は意図的に使わない。ブースト機能は廃止。
            if b2 == 0:
                # b2は緊急停止として残す。
                stop_motor(pi, IN1_L, IN2_L, EN_L)
                stop_motor(pi, IN1_R, IN2_R, EN_R)
            else:
                # ステアリングサーボ車なので、横入力をモーター差動には使わない。
                # Y軸だけで左右モーターを同じ量だけ駆動する。
                drive = y_unit * args.base_speed
                set_motor(pi, IN1_L, IN2_L, EN_L, drive)
                set_motor(pi, IN1_R, IN2_R, EN_R, drive)

            # X軸はサーボだけに使う。
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
