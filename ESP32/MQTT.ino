#include <ArduinoMqttClient.h>
#include <WiFi.h>

char ssid[] = "FIBO_Academy";
char pass[] = "fiboacademy2568";

WiFiClient wifiClient;
MqttClient mqttClient(wifiClient);

const char broker[] = "10.61.24.78";
int        port     = 1883;

const char cam[]     = "CPRAM/1/cam";
const char sensor1[] = "CPRAM/1/sensor/1";
const char sensor2[] = "CPRAM/1/sensor/2";

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
double A[50] = {0.0,0.0,0.0,0.0,0.0,1.2,5.2,6.7,9.3,10.1,12.3,13.5,15.3,17.1,18.2,55.0,21.0,22.8,24.3,24.1,26.1,26.6,28.1,28.5,29.8,29.6,29.5,29.8,28.2,28.0,27.8,26.1,24.2,23.9,23.3,21.3,19.9,18.5,4.0,15.8,14.7,12.1,10.5,8.4,6.5,0.0,0.0,0.0,0.0,0.0};

void loop()
{
  mqttClient.poll(); // keep-alive
  double data = 0;
  data = A[count];
  if(count == 49)
  {
    count = 0;
  }
  char payload[180];
  String ip = WiFi.localIP().toString();
  snprintf(payload, sizeof(payload),
            "{\"module\":\"sensor2\",\"data\":\"%f\"}",data);
  mqttClient.beginMessage(sensor2);
  mqttClient.print(payload);
  mqttClient.endMessage();

  Serial.print("Publish: ");
  Serial.println(payload);
  delay(1000); // เล็กน้อยกัน loop เร็วเกิน
  count++;
}
