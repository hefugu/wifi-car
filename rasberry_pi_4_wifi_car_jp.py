"""
Author:helo
Created:2025/9/8
GitHub: https://github.com/hefugu/wifi-car
"""
#!/usr/bin/env python3
# rc_server.py — Pico W（UDP送信）→ Raspberry Pi 4 → L293D（左右DCモータ）＋サーボ(GPIO18)

import argparse
import logging
import select
import socket
import time
import pigpio

# ===== ユーザー設定 ======
UDP_PORT = 5005
DEADZONE = 0.12            # ジョイスティック中央の遊び
EXPO = 0.6                 # サーボ用入力カーブ
FAILSAFE_SEC = 0.35        # 通信途絶で停止するまでの秒数

# L293D ピン割り当て（BCM番号）
# 実機配線:
#   左 = EN 12 / IN1 5 / IN2 4
#   右 = EN 13 / IN1 23 / IN2 22
EN_L, IN1_L, IN2_L = 12, 5, 4
EN_R, IN1_R, IN2_R = 13, 23, 22

# サーボ
SERVO_PIN = 18


# ===== ユーティリティ関数 ======
def adc_to_unit(v: int, deadzone: float) -> float:
    """0〜65535 のADC値を -1〜+1 に正規化し、中央の遊びを適用する"""
    u = (v / 65535.0) * 2.0 - 1.0
    return 0.0 if abs(u) < deadzone else max(-1.0, min(1.0, u))


def apply_expo(u: float, k: float) -> float:
    """サーボ操作用のエクスポカーブ"""
    return (1 - k) * u + k * (u ** 3)


def set_motor(pi: pigpio.pi, dir_a: int, dir_b: int, en: int, val: float) -> None:
    """
    モーターをデジタル制御する。
    PWMは一切使わない。
      val > 0 : 前進・全開
      val < 0 : 後退・全開
      val = 0 : 停止
    """
    # 方向を変える前にEnableを落として、瞬間的な誤駆動を防ぐ
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
    """モーターを確実に停止する"""
    pi.write(en, 0)
    pi.write(dir_a, 0)
    pi.write(dir_b, 0)


def servo_from_x(pi: pigpio.pi, x: float, pin: int) -> None:
    """X軸でステアリング。実機の向きに合わせて左右反転済み。"""
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


def recv_latest(sock: socket.socket) -> bytes:
    """
    UDP受信キューに複数パケットが溜まっていたら古いものを捨て、
    必ず最新の1パケットだけを返す。

    長時間スティックを倒した後に、古い前進/後退命令を順番に処理して
    センターへ戻しても走り続ける現象を防ぐ。
    """
    data, _ = sock.recvfrom(256)

    while True:
        readable, _, _ = select.select([sock], [], [], 0)
        if not readable:
            break
        try:
            newer, _ = sock.recvfrom(256)
            data = newer
        except (BlockingIOError, socket.timeout):
            break

    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="UDP RCブリッジ: Pico W -> RasPi 4 -> L293D + サーボ")
    parser.add_argument("--port", type=int, default=UDP_PORT, help="UDP受信ポート")
    parser.add_argument("--deadzone", type=float, default=DEADZONE, help="ジョイスティックの遊び")
    parser.add_argument("--expo", type=float, default=EXPO, help="サーボ入力カーブ(0〜1)")
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
        # GPIO設定
        # PWMは使用しない。ENも通常のデジタル出力として扱う。
        for p in (EN_L, IN1_L, IN2_L, EN_R, IN1_R, IN2_R):
            pi.set_mode(p, pigpio.OUTPUT)
            pi.write(p, 0)

        pi.set_mode(SERVO_PIN, pigpio.OUTPUT)
        pi.set_servo_pulsewidth(SERVO_PIN, 1500)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # 受信バッファを小さめにして、古い操作命令が大量に残りにくくする。
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2048)
        sock.bind(("0.0.0.0", args.port))
        sock.settimeout(0.05)

        logging.info("UDP受信をポート %d で開始", args.port)
        logging.info("モーターピン: 左 12/5/4, 右 13/23/22")
        logging.info("モーター制御方式: DIGITAL HIGH/LOW（PWMなし）")
        logging.info("UDP制御: 最新パケット優先（古い操作命令は破棄）")
        logging.info("操作: X=サーボのみ / Y=左右モーター全開 / b1無効 / b2=停止")

        last_ok = time.monotonic()
        failsafe_active = False

        while True:
            try:
                # 1個ずつ処理せず、溜まっている場合は最新パケットまで一気に進む。
                data = recv_latest(sock)
            except socket.timeout:
                if time.monotonic() - last_ok > args.failsafe:
                    if not failsafe_active:
                        logging.warning("通信が %.2f 秒以上途絶えたため停止", args.failsafe)
                        failsafe_active = True
                    stop_all(pi)
                continue

            if args.verbose:
                logging.debug("LATESTデータ: %r", data)

            parsed = parse_packet(data)
            if parsed is None:
                continue

            _b1, b2, x_raw, y_raw = parsed
            last_ok = time.monotonic()

            if failsafe_active:
                logging.info("通信復帰")
                failsafe_active = False

            # サーボは滑らかに動かす
            x_unit = apply_expo(adc_to_unit(x_raw, args.deadzone), args.expo)

            # モーターはPWMなしなので、Y軸は方向判定だけに使う
            y_unit = adc_to_unit(y_raw, args.deadzone)

            if b2 == 0:
                stop_motor(pi, IN1_L, IN2_L, EN_L)
                stop_motor(pi, IN1_R, IN2_R, EN_R)
            elif y_unit == 0.0:
                # センターへ戻ったら両モーターを即停止。
                stop_motor(pi, IN1_L, IN2_L, EN_L)
                stop_motor(pi, IN1_R, IN2_R, EN_R)
            else:
                # ステアリング車なので左右モーターは常に同じ方向・同じ全開出力
                set_motor(pi, IN1_L, IN2_L, EN_L, y_unit)
                set_motor(pi, IN1_R, IN2_R, EN_R, y_unit)

            # X軸はサーボ専用
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
