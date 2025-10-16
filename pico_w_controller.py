import network
import socket
import time
from machine import Pin, ADC

# ====== Wi-Fi Configuration ======
SSID = "Your_SSID"
PASSWORD = "Your_Password"

# ====== Server Configuration ======
# Set this to your Raspberry Pi 4's IP address and desired port
SERVER_IP = "192.168.0.10"
SERVER_PORT = 5005

# ====== Input Pins ======
# Buttons
button1 = Pin(21, Pin.IN, Pin.PULL_UP)  # GP21
button2 = Pin(20, Pin.IN, Pin.PULL_UP)  # GP20

# Joystick (Analog input)
joystick_x = ADC(26)  # GP26 (Horizontal)
joystick_y = ADC(27)  # GP27 (Vertical)

# ====== Wi-Fi Connection ======
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(SSID, PASSWORD)

print("Connecting to Wi-Fi...")
while not wlan.isconnected():
    time.sleep(0.5)
print("Wi-Fi connected:", wlan.ifconfig())

# ====== UDP Socket ======
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_address = (SERVER_IP, SERVER_PORT)

# ====== Main Loop ======
while True:
    # Button readings (0 when pressed, 1 when released)
    b1 = 0 if button1.value() == 0 else 1
    b2 = 0 if button2.value() == 0 else 1

    # Joystick readings (0–65535 range)
    x_val = joystick_x.read_u16()
    y_val = joystick_y.read_u16()

    # Format data (comma-separated)
    message = f"{b1},{b2},{x_val},{y_val}"
    udp_socket.sendto(message.encode(), server_address)

    # Debug output
    print(message)

    # Send at ~20Hz
    time.sleep(0.05)
