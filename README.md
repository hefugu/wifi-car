# The code published here is my first public release. It's for a WiFi-controlled radio-controlled car using a Raspberry Pi 4 and a Raspberry Pi Pico W.

## Raspberry Pi 4 UDP Receiver for L293D + Steering Servo

Listens for UDP packets from a Raspberry Pi Pico W transmitter and drives two DC motors via an L293D plus a steering servo on GPIO18.

### Hardware
- **Motor driver**: L293D (or L298N with equivalent wiring)
- **Pins (BCM)**
  - Left motor: `EN_L=12`, `IN1_L=5`, `IN2_L=4`
  - Right motor: `EN_R=13`, `IN1_R=27`, `IN2_R=17`
  - Steering servo: `SERVO_PIN=18`
- **Power**: Use an appropriate external power supply for motors. **Do not power motors from the Pi 5V rail.** Common ground is required.

### Controls
- Joystick X axis: steering servo only
- Joystick Y axis: both drive motors
- Button 1: unused (turbo/boost removed)
- Button 2: motor stop
- Communication timeout: motors stop automatically

### Software
```bash
sudo apt-get install pigpio
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
python3 rasberry_pi_4_wifi_car_jp.py --verbose
```

---

# ここに公開されているコードは自分の初めて公開したもので、Raspberry Pi 4 と Raspberry Pi Pico W を利用した Wi-Fi 制御ラジコンのコードです

## Raspberry Pi 4 UDP レシーバー（L293D＋ステアリングサーボ）

Raspberry Pi Pico W 送信機から UDP パケットを受信し、L293D を介して左右2つのDCモーターと GPIO18 のステアリングサーボを制御します。

### ハードウェア
- **モータードライバ**：L293D（または同等配線の L298N）
- **ピン（BCM番号）**
  - 左モーター：`EN_L=12`, `IN1_L=5`, `IN2_L=4`
  - 右モーター：`EN_R=13`, `IN1_R=27`, `IN2_R=17`
  - ステアリングサーボ：`SERVO_PIN=18`
- **電源**：モーター用には適切な外部電源を使用してください。Pi の 5V レールからモーターを直接駆動しないでください。GND は共通にしてください。

### 操作
- ジョイスティックX軸：ステアリングサーボのみ
- ジョイスティックY軸：左右モーターを同時駆動
- ボタン1：未使用（ブースト機能は廃止）
- ボタン2：モーター停止
- 通信が途絶えた場合：自動停止

### ソフトウェア
```bash
sudo apt-get install pigpio
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
python3 rasberry_pi_4_wifi_car_jp.py --verbose
```

---

# Опубликованный здесь код является моим первым публичным релизом. Он предназначен для радиоуправляемой машины на Raspberry Pi 4 и Raspberry Pi Pico W.

## Приёмник UDP для Raspberry Pi 4 (L293D + рулевой сервопривод)

Принимает UDP-пакеты от Raspberry Pi Pico W и управляет двумя двигателями постоянного тока через L293D и рулевым сервоприводом на GPIO18.

### Аппаратная часть
- **Драйвер двигателей**: L293D (или L298N с аналогичной схемой)
- **Выводы BCM**
  - Левый двигатель: `EN_L=12`, `IN1_L=5`, `IN2_L=4`
  - Правый двигатель: `EN_R=13`, `IN1_R=27`, `IN2_R=17`
  - Рулевой сервопривод: `SERVO_PIN=18`
- Используйте отдельное питание для двигателей и общий GND с Raspberry Pi.

### Управление
- Ось X джойстика: только рулевой сервопривод
- Ось Y джойстика: оба двигателя
- Кнопка 1: не используется (режим boost удалён)
- Кнопка 2: остановка двигателей
- При потере связи двигатели автоматически останавливаются

### Запуск
```bash
sudo apt-get install pigpio
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
python3 rasberry_pi_4_wifi_car_jp.py --verbose
```
