import network
import socket
import time
from machine import Pin, ADC

# ====== Настройки Wi-Fi ======
SSID = "Ваш_SSID"
PASSWORD = "Ваш_пароль"

# ====== Настройки сервера ======
# Укажите IP-адрес и порт вашего Raspberry Pi 4
SERVER_IP = "192.168.0.10"
SERVER_PORT = 5005

# ====== Настройки входных пинов ======
# Кнопки
button1 = Pin(21, Pin.IN, Pin.PULL_UP)  # GP21
button2 = Pin(20, Pin.IN, Pin.PULL_UP)  # GP20

# Джойстик (аналоговые входы)
joystick_x = ADC(26)  # GP26 (горизонталь)
joystick_y = ADC(27)  # GP27 (вертикаль)

# ====== Подключение к Wi-Fi ======
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(SSID, PASSWORD)

print("Подключение к Wi-Fi...")
while not wlan.isconnected():
    time.sleep(0.5)
print("Wi-Fi подключен:", wlan.ifconfig())

# ====== Создание UDP-сокета ======
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_address = (SERVER_IP, SERVER_PORT)

# ====== Основной цикл ======
while True:
    # Чтение состояния кнопок (0 — нажата, 1 — отпущена)
    b1 = 0 if button1.value() == 0 else 1
    b2 = 0 if button2.value() == 0 else 1

    # Чтение значений джойстика (диапазон 0–65535)
    x_val = joystick_x.read_u16()
    y_val = joystick_y.read_u16()

    # Формирование данных в виде строки (через запятую)
    message = f"{b1},{b2},{x_val},{y_val}"
    udp_socket.sendto(message.encode(), server_address)

    # Отладочный вывод
    print(message)

    # Отправка примерно 20 раз в секунду (каждые 0.05 секунды)
    time.sleep(0.05)
