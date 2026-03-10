/*
  ESP32 Microphone Input Test
  - Reads analog mic input
  - Prints average signal level to Serial Monitor
  - Use this to verify mic wiring and input response

  Update MIC_PIN to your actual mic output pin.
*/

const int MIC_PIN = 34;      // Common ADC pin on ESP32 (input only)
const int SAMPLE_COUNT = 256;

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("ESP32 mic input test started");
}

void loop() {
  long sum = 0;
  int minVal = 4095;
  int maxVal = 0;

  for (int i = 0; i < SAMPLE_COUNT; i++) {
    int v = analogRead(MIC_PIN);  // 0..4095 on ESP32 ADC
    sum += v;
    if (v < minVal) minVal = v;
    if (v > maxVal) maxVal = v;
    delayMicroseconds(200);
  }

  int avg = (int)(sum / SAMPLE_COUNT);
  int peakToPeak = maxVal - minVal;

  Serial.print("avg=");
  Serial.print(avg);
  Serial.print(" p2p=");
  Serial.println(peakToPeak);

  delay(80);
}
