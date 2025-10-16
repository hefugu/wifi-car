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
