#include <ArduinoMqttClient.h>
#include <WiFi.h>
#include <Wire.h>
#include <VL53L1X.h>
#include <math.h>
#include <stdlib.h>

#define XSHUT_PIN1 18
#define XSHUT_PIN2 19

VL53L1X sensor1;
VL53L1X sensor2;

char ssid[] = "FIBO_Academy";
char pass[] = "fiboacademy2568";

WiFiClient wifiClient;
MqttClient mqttClient(wifiClient);

const char broker[] = "10.61.24.78";
int port = 1883;

const char topicSensor1[] = "CPRAM/1/sensor/1";
const char topicSensor2[] = "CPRAM/1/sensor/2";

const float ZERO_THRESHOLD = 1.0;
const int END_ON_ZEROS = 1;
const int MIN_RUN = 2;
const int MOVING_AVG_WINDOW = 5;
const int MAX_RUN_SIZE = 100;

float run1[MAX_RUN_SIZE];
int run1_count = 0;
int zeroCount1 = 0;

float run2[MAX_RUN_SIZE];
int run2_count = 0;
int zeroCount2 = 0;

void calculateMovingAverage(float *data, int n, int windowSize, float *out)
{
  if (n == 0)
    return;
  int w = (windowSize > 1) ? windowSize : 1;
  float sum = 0.0;    

  for (int i = 0; i < n; i++)
  {
    if (i < w)
    {
      sum += data[i];
      out[i] = sum / (float)(i + 1);
    }
    else
    {
      sum += data[i] - data[i - w];
      out[i] = sum / (float)w;
    }
  }
}

float findMax(float *data, int n)
{
  if (n == 0)
    return 0.0;
  float maxVal = data[0];
  for (int i = 1; i < n; i++)
  {
    if (data[i] > maxVal)
    {
      maxVal = data[i];
    }
  }
  return maxVal;
}

void publishProcessedData(const char *topic, const char *moduleName, float maxVal)
{
  float distance = 10.03 - maxVal;
  bool status = 0;
  if (maxVal >= 7 && maxVal <= 9)
  {
    status = 1;
  }

  char payload[180];
  char high_str[10];
  char dist_str[10];

  dtostrf(maxVal, 4, 2, high_str);
  dtostrf(distance, 4, 2, dist_str);

  snprintf(payload, sizeof(payload),
           "{\"module\":\"%s\",\"high\":%s,\"distance\":%s,\"status\":%d}",
           moduleName, high_str, dist_str, status);

  mqttClient.beginMessage(topic);
  mqttClient.print(payload);
  mqttClient.endMessage();

  Serial.print("Publish Processed to ");
  Serial.print(topic);
  Serial.print(": ");
  Serial.println(payload);
}

void processSensorData(int raw_data, bool timeoutOccurred, const char *topic,
                       float *run_buffer, int &run_count, int &zero_count, const char *moduleName)
{
  if (timeoutOccurred)
  {
    ESP.restart();
    return;
  }
  float high = (float)fabs(((float)raw_data / 10.0) - 30.5);
  Serial.println(high);
  // Serial.print(",");
  if (high > ZERO_THRESHOLD)
  {
    if (run_count < MAX_RUN_SIZE)
    {
      run_buffer[run_count] = high;
      run_count++;
    }
    else
    {
      Serial.printf("Run buffer overflow for %s. Resetting.\n", moduleName);
      run_count = 0;
    }
    zero_count = 0;
    return;
  }
  if (run_count >= MIN_RUN)
  {
    zero_count++;

    if (zero_count >= END_ON_ZEROS)
    {
      Serial.printf("Processing run for %s. Length: %d\n", moduleName, run_count);
      float smoothData[MAX_RUN_SIZE];
      calculateMovingAverage(run_buffer, run_count, MOVING_AVG_WINDOW, smoothData);
      float maxVal = findMax(smoothData, run_count);
      publishProcessedData(topic, moduleName, maxVal);
      run_count = 0;
      zero_count = 0;
    }
    return;
  }

  run_count = 0;
  zero_count = 0;
  return;
}

void connectMqtt()
{
  Serial.print("Attempting to connect to the MQTT broker: ");
  Serial.println(broker);

  while (!mqttClient.connect(broker, port))
  {
    Serial.print("MQTT connection failed! Error code = ");
    Serial.println(mqttClient.connectError());
    Serial.println("Retrying in 5 seconds...");
    delay(5000);
  }

  Serial.println("You're connected to the MQTT broker!\n");
}


void setup()
{
  Serial.begin(115200);

  Serial.print("Attempting to connect to WPA SSID: ");
  Serial.println(ssid);
  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED)
  {
    delay(1000);
    Serial.println("Connecting to WiFi...");
  }
  Serial.println("You're connected to the network\n");

  connectMqtt();

  Wire.begin();
  Wire.setClock(400000);

  pinMode(XSHUT_PIN1, OUTPUT);
  pinMode(XSHUT_PIN2, OUTPUT);
  
  digitalWrite(XSHUT_PIN1, LOW);
  digitalWrite(XSHUT_PIN2, LOW);
  delay(10);

  Serial.println("Starting Sensor 1");
  pinMode(XSHUT_PIN1, INPUT);
  delay(10);
  sensor1.setTimeout(500);
  if (!sensor1.init())
  {
    Serial.println("Failed to detect and initialize sensor 1!");
    while (1)
      ;
  }
  sensor1.setAddress(0x2A);
  Serial.println("Sensor 1 initialized with new address.");
  sensor1.setDistanceMode(VL53L1X::Long);
  sensor1.setMeasurementTimingBudget(50000);
  sensor1.startContinuous(50);
  
  Serial.println("Starting Sensor 2");
  pinMode(XSHUT_PIN2, INPUT);
  delay(10);
  sensor2.setTimeout(500);
  if (!sensor2.init())
  {
    Serial.println("Failed to detect and initialize sensor 2!");
    while (1)
      ;
  }
  Serial.println("Sensor 2 initialized with default address.");
  sensor2.setDistanceMode(VL53L1X::Long);
  sensor2.setMeasurementTimingBudget(50000);
  sensor2.startContinuous(50);

  Serial.println("\nBoth sensors initialized successfully!");
}

void loop()
{
  if (!mqttClient.connected())
  {
    Serial.println("MQTT connection lost! Reconnecting...");
    connectMqtt();
  }
  mqttClient.poll();
  int data1 = sensor1.read();
  Serial.print("sensor1 ");
  
  processSensorData(data1, sensor1.timeoutOccurred(),
                    topicSensor1, run1, run1_count, zeroCount1, "sensor1");
  int data2 = sensor2.read();
  Serial.print("sensor2 ");
  processSensorData(data2, sensor2.timeoutOccurred(),
                    topicSensor2, run2, run2_count, zeroCount2, "sensor2");
  delay(50);
}