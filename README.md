# The code published here is my first public release. It's for a WiFi-controlled radio-controlled car using a Raspberry Pi 4 and a Raspberry Pi Pico W.

## Raspberry Pi 4 UDP Receiver for L293D + Servo

Listens for UDP packets from a Raspberry Pi Pico W transmitter and drives two DC motors via L293D (tank drive) plus an optional servo on GPIO18.

### Hardware
- **Motor driver**: L293D (or L298N with equivalent wiring)
- **Pins (BCM)**  
  - Left: `EN_L=12`, `IN1_L=5`, `IN2_L=6`  
  - Right: `EN_R=13`, `IN1_R=23`, `IN2_R=24`  
  - Servo: `SERVO_PIN=18` (pigpio servo pulses)
- **Power**: Use an appropriate external power supply for motors. **Do not power motors from the Pi 5V rail.** Common ground is required.

### Software
```bash
sudo apt-get install pigpio
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
python3 rc_server.py --verbose
```
# ここに公開さているコードは自分の初めて公開したもので、ラズパイ4とラパイ pico wを利用したwifi制御のラジコンのコードです
## Raspberry Pi 4 UDP レシーバー（L293D＋サーボ対応）

Raspberry Pi Pico W 送信機からの UDP パケットを受信し、L293D モータードライバを介して 2 つの DC モーター（タンク駆動方式）と、オプションで GPIO18 のサーボモーターを制御します。

---

### ハードウェア
- **モータードライバ**：L293D（または同等配線の L298N）
- **ピン（BCM 番号）**
  - 左モーター：`EN_L=12`, `IN1_L=5`, `IN2_L=6`
  - 右モーター：`EN_R=13`, `IN1_R=23`, `IN2_R=24`
  - サーボ：`SERVO_PIN=18`（pigpio によるサーボパルス制御）
- **電源**：モーター用には外部電源を使用してください。  
  **Pi の 5V レールからモーターを駆動しないでください。**  
  共通グラウンド（GND）は必須です。

---

### ソフトウェア
```bash
sudo apt-get install pigpio
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
python3 rc_server.py --verbose
```
# Опубликованный здесь код является моим первым публичным релизом. Он предназначен для радиоуправляемого автомобиля с управлением по WiFi, в котором используются Raspberry Pi 4 и Raspberry Pi Pico W.
## Приёмник UDP для Raspberry Pi 4 (L293D + Серво)

Принимает UDP-пакеты от передатчика Raspberry Pi Pico W и управляет двумя двигателями постоянного тока через драйвер L293D (танковое управление), а также опционально сервоприводом на GPIO18.

---

### Аппаратная часть
- **Драйвер двигателей**: L293D (или L298N с аналогичным подключением)
- **Выводы (BCM)**
  - Левый мотор: `EN_L=12`, `IN1_L=5`, `IN2_L=6`
  - Правый мотор: `EN_R=13`, `IN1_R=23`, `IN2_R=24`
  - Серво: `SERVO_PIN=18` (управление импульсами pigpio)
- **Питание**: используйте отдельный внешний источник питания для двигателей.  
  **Не подключайте двигатели к 5V линии Raspberry Pi.**  
  Общий «минус» (GND) обязателен.

---

### Программная часть
```bash
sudo apt-get install pigpio
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
python3 rc_server.py --verbose

