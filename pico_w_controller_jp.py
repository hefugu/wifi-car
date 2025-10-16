import network
import socket
import time
from machine import Pin, ADC

# ====== Wi-Fi設定 ======
SSID = "あなたのSSID"
PASSWORD = "あなたのWiFiパスワード"

# ====== サーバー設定 ======
# ここをRaspberry Pi 4のIPアドレスとポート番号に変更
SERVER_IP = "192.168.0.10"
SERVER_PORT = 5005

# ====== 入力ピン設定 ======
# ボタン
button1 = Pin(21, Pin.IN, Pin.PULL_UP)  # GP21
button2 = Pin(20, Pin.IN, Pin.PULL_UP)  # GP20

# ジョイスティック（アナログ入力）
joystick_x = ADC(26)  # GP26（横方向）
joystick_y = ADC(27)  # GP27（縦方向）

# ====== Wi-Fi接続 ======
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(SSID, PASSWORD)

print("Wi-Fiに接続中...")
while not wlan.isconnected():
    time.sleep(0.5)
print("Wi-Fi接続完了:", wlan.ifconfig())

# ====== UDPソケット作成 ======
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_address = (SERVER_IP, SERVER_PORT)

# ====== メインループ ======
while True:
    # ボタンの状態を読み取る（押すと0、離すと1）
    b1 = 0 if button1.value() == 0 else 1
    b2 = 0 if button2.value() == 0 else 1

    # ジョイスティックの値を取得（範囲 0〜65535）
    x_val = joystick_x.read_u16()
    y_val = joystick_y.read_u16()

    # データをカンマ区切りで整形
    message = f"{b1},{b2},{x_val},{y_val}"
    udp_socket.sendto(message.encode(), server_address)

    # デバッグ出力
    print(message)

    # 約20Hzで送信（0.05秒間隔）
    time.sleep(0.05)
