# Future ESP32 + NEO-6M integration

**Hardware integration is prepared but not physically tested because hardware is currently unavailable.**
The sketch is an integration example. It has not been compiled with an ESP32 board toolchain or tested on a device in this environment.

## Connections

For a classic ESP32 development board with UART2 available on GPIO16/17:

| NEO-6M breakout | ESP32 | Purpose |
| --- | --- | --- |
| TX | GPIO16 (RX2) | GPS transmits NMEA sentences; ESP32 receives them |
| RX | GPIO17 (TX2), optional | ESP32 can transmit configuration; unnecessary for just receiving fixes |
| GND | GND | Shared electrical reference |
| VCC | Appropriate supply for **your specific breakout** | Verify its label/datasheet before connecting |

ESP32 pins use **3.3 V logic** and must not receive 5 V UART signals. A bare NEO-6 module and a breakout with a voltage regulator have different power requirements. Some breakouts accept 5 V power, others do not. Check the actual purchased board; do not assume its VCC rating. Use 3.3 V power only if that breakout specifies it. Some ESP32 variants reserve GPIO16/17 for other functions; adjust the sketch's pins to the selected board.

UART is serial communication: cross TX to RX and connect shared GND. The example assumes 9600 baud, 8 data bits, no parity, 1 stop bit. Confirm the GPS module's configured baud rate.

## Setup after purchasing hardware

1. Install Arduino IDE, Espressif's ESP32 board package, and the **TinyGPSPlus** library by Mikal Hart.
2. Open `fleet_mitra_esp32.ino`, select your actual board and serial port, and check the pins above.
3. Enter your Wi-Fi SSID and password locally. Do not commit real credentials.
4. On the laptop, activate the FleetMitra environment and start Flask on the LAN interface:

   ```powershell
   $env:FLEET_HOST = "0.0.0.0"
   python app.py
   ```

5. Run `ipconfig` and find the laptop's active Wi-Fi IPv4 address. Put it in `LOCATION_URL`, for example `http://192.168.1.100:5000/api/locations`.
6. Both devices must be on the same network. Permit Python's port 5000 on the laptop's private network if Windows asks. Check reachability from a second device before debugging the GPS code.
7. **`localhost` on the ESP32 refers to the ESP32 itself, NOT the laptop.** The ESP32 must use the laptop's LAN IP.
8. Stop the Python simulator. Upload the sketch and open Serial Monitor at 115200 baud.
9. Put the antenna outdoors with a clear sky view. A cold start may take several minutes. A GPS fix requires valid position and UTC date/time; indoor reception may not produce one.
10. Verify a successful 201 response and `HARDWARE` on the dashboard. Test movement, trip distance, geofences, Wi-Fi reconnection, and GPS fix loss with the actual devices. These are future validation steps.

The sketch sends fresh fixes about every three seconds using the same JSON contract as the simulator. Failed sends do not change the backend. Invalid or stale fixes are withheld. Wi-Fi retries continue while the loop reads the UART; HTTP calls have bounded waits. Board-specific UART buffering and real radio behavior must be tested later.

Only one sender should drive FM01 at a time. Replacing the simulator with hardware changes the data source; Flask, SQLite, tracking calculations and dashboard remain the same.

References: [ESP32 UART documentation](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/serial.html), [TinyGPSPlus library](https://github.com/mikalhart/TinyGPSPlus).
