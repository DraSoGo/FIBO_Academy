#include <ArduinoMqttClient.h>
#include <WiFi.h>

char ssid[] = "FIBO_Academy";
char pass[] = "fiboacademy2568";

WiFiClient wifiClient;
MqttClient mqttClient(wifiClient);

const char broker[] = "test.mosquitto.org";
int        port     = 1883;

const char cam[]     = "CPRAM/1/cam";
const char sensor1[] = "CPRAM/1/sensor/1";
const char sensor2[] = "CPRAM/1/sensor/1";

void setup() {
  Serial.begin(115200);

  Serial.print("Attempting to connect to WPA SSID: ");
  Serial.println(ssid);
  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.println("Connecting to WiFi...");
  }
  Serial.println("You're connected to the network\n");

  Serial.print("Attempting to connect to the MQTT broker: ");
  Serial.println(broker);
  if (!mqttClient.connect(broker, port)) {
    Serial.print("MQTT connection failed! Error code = ");
    Serial.println(mqttClient.connectError());
    while (1);
  }
  Serial.println("You're connected to the MQTT broker!\n");
}

int count = 0;

void loop()
{
  mqttClient.poll(); // keep-alive
  int data = 0;
  if(count >= 3 && count <= 5)
  {
    data = 141;
  }
  if(count >= 5 && count <= 7)
  {
    data = 145;
  }
  if(count >= 7)
  {
    count = 0;
  }
  char payload[180];
  String ip = WiFi.localIP().toString();
  snprintf(payload, sizeof(payload),
            "{\"module\":\"cam\",\"data\":\"%d\"}",data);
  mqttClient.beginMessage(cam);
  mqttClient.print(payload);
  mqttClient.endMessage();

  Serial.print("Publish: ");
  Serial.println(payload);
  delay(1000); // เล็กน้อยกัน loop เร็วเกิน
  count++;
}
