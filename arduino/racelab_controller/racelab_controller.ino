// RaceLab controller: 16x2 I2C LCD, joystick with push button, B10K knob.
//
// The board only reads its inputs and draws the text RaceLab sends; the app
// (ui/controller.py) owns the mode, the selected setting and every value.
//
// Protocol, newline-terminated ASCII at 115200 baud:
//   Arduino -> PC every 20 ms:  <knob>,<joy_x>,<joy_y>,<button>   (0-1023, button 0 = pressed)
//   PC -> Arduino:              L|<line 1>|<line 2>               (16 characters each)
// Bytes 1-5 in a line are bar glyphs with 1-5 lit columns.
//
// Wiring: joystick X -> A0, Y -> A1, SW -> D2 (to GND when pressed); knob wiper -> A2;
// LCD backpack SDA/SCL -> A4/A5 on an Uno (I2C address 0x27; try 0x3F if the screen stays blank).

#include <Wire.h>
#include <LiquidCrystal_I2C.h>

LiquidCrystal_I2C lcd(0x27, 16, 2);

const int pinJoyX = A0;
const int pinJoyY = A1;
const int pinKnob = A2;
const int pinButton = 2;

const unsigned long sendPeriodMs = 20;      // 50 Hz input stream
const unsigned long debounceMs = 30;
const unsigned long linkTimeoutMs = 2000;   // no LCD text for this long: show "waiting"

// Bar glyphs 1-5: k columns lit from the left (glyph 0 is unusable in strings).
byte barGlyph[5][8];

char rx[48];            // incoming line, without the newline
byte rxLen = 0;
char shown[2][17];      // what the LCD shows now, to redraw only changed lines
unsigned long lastText = 0;
unsigned long lastSend = 0;

int button = HIGH;      // debounced state
int buttonRaw = HIGH;
unsigned long buttonChanged = 0;

void showLine(byte row, const char* text) {
  char padded[17];
  byte i = 0;
  for (; i < 16 && text[i]; i++) padded[i] = text[i];
  for (; i < 16; i++) padded[i] = ' ';
  padded[16] = '\0';
  if (strcmp(padded, shown[row]) == 0) return;  // no flicker from rewriting the same text
  strcpy(shown[row], padded);
  lcd.setCursor(0, row);
  for (i = 0; i < 16; i++) lcd.write((uint8_t)padded[i]);  // write() so glyph bytes 1-5 draw as bars
}

void handleLine() {
  // Expect "L|line one|line two".
  if (rxLen < 2 || rx[0] != 'L' || rx[1] != '|') return;
  char* first = rx + 2;
  char* bar = strchr(first, '|');
  if (!bar) return;
  *bar = '\0';
  showLine(0, first);
  showLine(1, bar + 1);
  lastText = millis();
}

void readSerial() {
  // Non-blocking: collect characters until a newline, never wait for one.
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n') {
      rx[rxLen] = '\0';
      handleLine();
      rxLen = 0;
    } else if (c != '\r' && rxLen < sizeof(rx) - 1) {
      rx[rxLen++] = c;
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(pinButton, INPUT_PULLUP);

  lcd.init();
  lcd.backlight();
  for (byte k = 0; k < 5; k++) {
    byte row = (byte)(0x1F << (4 - k)) & 0x1F;  // k + 1 columns from the left
    for (byte r = 0; r < 8; r++) barGlyph[k][r] = row;
    lcd.createChar(k + 1, barGlyph[k]);
  }
  shown[0][0] = shown[1][0] = '\0';
  showLine(0, "RaceLab");
  showLine(1, "Waiting for PC");
}

void loop() {
  readSerial();

  int raw = digitalRead(pinButton);
  if (raw != buttonRaw) {
    buttonRaw = raw;
    buttonChanged = millis();
  }
  if (millis() - buttonChanged > debounceMs) button = buttonRaw;

  if (millis() - lastSend >= sendPeriodMs) {
    lastSend = millis();
    Serial.print(analogRead(pinKnob));
    Serial.print(',');
    Serial.print(analogRead(pinJoyX));
    Serial.print(',');
    Serial.print(analogRead(pinJoyY));
    Serial.print(',');
    Serial.println(button == LOW ? 0 : 1);
  }

  if (lastText != 0 && millis() - lastText > linkTimeoutMs) {
    showLine(0, "RaceLab");
    showLine(1, "Waiting for PC");
    lastText = 0;
  }
}
