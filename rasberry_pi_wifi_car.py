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
DEADZONE = 0.08            # ジョイスティックの遊び（0〜1）
BASE_SPEED = 0.60          # 通常の最高速度（0〜1）
TURBO_SPEED = 1.00         # b1押下時の最大速度
EXPO = 0.6                 # 入力カーブ（0=直線、0.6で低速域が繊細）
PWM_FREQ = 20000           # モーターPWM周波数(Hz)
FAILSAFE_SEC = 0.5         # 通信途絶で停止するまでの秒数
VERBOSE_LOG = False        # Trueにすると受信データを表示

# L293D ピン割り当て（BCM番号）
EN_L, IN1_L, IN2_L = 12, 5, 6      # 左モーター: Enable, IN1, IN2
EN_R, IN1_R, IN2_R = 13, 23, 24    # 右モーター: Enable, IN3, IN4

# サーボ（PWM対応ピン）
SERVO_PIN = 18                     # サーボ信号出力ピン


# ===== ユーティリティ関数 =====
def adc_to_unit(v: int, deadzone: float) -> float:
    """0〜65535 のADC値を -1〜+1 に正規化し、中央の遊び(deadzone)を適用する"""
    u = (v / 65535.0) * 2.0 - 1.0
    return 0.0 if abs(u) < deadzone else max(-1.0, min(1.0, u))


def apply_expo(u: float, k: float) -> float:
    """スティック入力にエクスポカーブを適用（中央付近を繊細に）"""
    return (1 - k) * u + k * (u ** 3)


def set_motor(pi: pigpio.pi, dir_a: int, dir_b: int, en: int, val: float) -> None:
    """
    モーターを駆動する（val = -1〜+1）
    正: 前進、負: 後退、0: 惰性（コースト）
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
        pi.write(dir_b, 0)  # コースト
    pi.set_PWM_dutycycle(en, int(abs(val) * 255))


def brake(pi: pigpio.pi, dir_a: int, dir_b: int, en: int) -> None:
    """ブレーキ（両入力をHIGHにして電気的に停止）"""
    pi.write(dir_a, 1)
    pi.write(dir_b, 1)
    pi.set_PWM_dutycycle(en, 0)


def servo_from_x(pi: pigpio.pi, x: float, pin: int) -> None:
    """x値(-1〜+1)をサーボのパルス幅(500〜2500µs)に変換して出力"""
    us = int(1500 + x * 1000)  # ±1000µs
    pi.set_servo_pulsewidth(pin, max(500, min(2500, us)))


def stop_all(pi: pigpio.pi) -> None:
    """全モーターとサーボを安全状態にする"""
    brake(pi, IN1_L, IN2_L, EN_L)
    brake(pi, IN1_R, IN2_R, EN_R)
    pi.set_servo_pulsewidth(SERVO_PIN, 1500)


def parse_packet(data: bytes) -> tuple[int, int, int, int] | None:
    """PicoからのCSV形式データ b1,b2,x_raw,y_raw を解析"""
    text = data.decode("utf-8", errors="ignore").strip()
    if text.count(",") < 3:
        return None
    b1, b2, x_raw, y_raw = text.split(",")[:4]
    if not (b1.isdigit() and b2.isdigit() and x_raw.isdigit() and y_raw.isdigit()):
        return None
    return int(b1), int(b2), int(x_raw), int(y_raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="UDP RCブリッジ: Pico W -> RasPi 4 -> L293D + サーボ")
    parser.add_argument("--port", type=int, default=UDP_PORT, help="UDP受信ポート")
    parser.add_argument("--deadzone", type=float, default=DEADZONE, help="ジョイスティックの遊び")
    parser.add_argument("--base-speed", type=float, default=BASE_SPEED, help="通常時の最高速度(0〜1)")
    parser.add_argument("--turbo-speed", type=float, default=TURBO_SPEED, help="b1押下時の最高速度(0〜1)")
    parser.add_argument("--expo", type=float, default=EXPO, help="入力カーブ(0〜1)")
    parser.add_argument("--pwm-freq", type=int, default=PWM_FREQ, help="モーターPWM周波数(Hz)")
    parser.add_argument("--failsafe", type=float, default=FAILSAFE_SEC, help="通信断で停止するまでの秒数")
    parser.add_argument("--verbose", action="store_true", help="受信データを詳細表示")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )

    # pigpio初期化
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit(
            "pigpioデーモンが起動していません。\n"
            "以下で起動できます:\n"
            "  sudo systemctl start pigpiod\n"
            "常時起動するには:\n"
            "  sudo systemctl enable pigpiod"
        )

    try:
        # GPIO設定
        for p in (IN1_L, IN2_L, IN1_R, IN2_R):
            pi.set_mode(p, pigpio.OUTPUT)
            pi.write(p, 0)  # 初期状態をLOWに

        for p in (EN_L, EN_R):
            pi.set_mode(p, pigpio.OUTPUT)
            pi.set_PWM_frequency(p, args.pwm_freq)
            pi.set_PWM_dutycycle(p, 0)

        pi.set_mode(SERVO_PIN, pigpio.OUTPUT)
        pi.set_servo_pulsewidth(SERVO_PIN, 1500)  # 中立位置

        # UDP待ち受け設定
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", args.port))
        sock.settimeout(0.1)  # フェイルセーフ監視のため定期的に抜ける
        logging.info(f"UDP受信をポート {args.port} で開始")

        last_ok = time.time()

        while True:
            try:
                data, _ = sock.recvfrom(256)
            except socket.timeout:
                # タイムアウト時：通信が途絶えていれば停止
                if time.time() - last_ok > args.failsafe:
                    stop_all(pi)
                continue

            if args.verbose:
                logging.debug("RAWデータ: %r", data)

            parsed = parse_packet(data)
            if parsed is None:
                continue

            b1, b2, x_raw, y_raw = parsed

            # 正規化＋遊び＋エクスポ
            x_unit = apply_expo(adc_to_unit(x_raw, args.deadzone), args.expo)
            y_unit = apply_expo(adc_to_unit(y_raw, args.deadzone), args.expo)  # 上方向 = 前進

            last_ok = time.time()

            # スピードモード切替
            max_speed = args.turbo_speed if b1 == 0 else args.base_speed

            if b2 == 0:
                # b2押下時: ブレーキ
                brake(pi, IN1_L, IN2_L, EN_L)
                brake(pi, IN1_R, IN2_R, EN_R)
            else:
                # 差動ミキシング（左右独立二輪）
                left = max(-1.0, min(1.0, y_unit + x_unit)) * max_speed
                right = max(-1.0, min(1.0, y_unit - x_unit)) * max_speed
                set_motor(pi, IN1_L, IN2_L, EN_L, left)
                set_motor(pi, IN1_R, IN2_R, EN_R, right)

            # サーボ（ステアリング用）
            servo_from_x(pi, x_unit, SERVO_PIN)

            # フェイルセーフ確認
            if time.time() - last_ok > args.failsafe:
                stop_all(pi)

    except KeyboardInterrupt:
        logging.info("ユーザーによって中断されました。")
    finally:
        # 安全に終了
        try:
            stop_all(pi)
            pi.set_servo_pulsewidth(SERVO_PIN, 0)  # サーボ信号停止
        except Exception:
            pass
        pi.stop()


if __name__ == "__main__":
    main()
