import paho.mqtt.client as mqtt
import time

host = 'test.mosquitto.org'
port = 1883
MQTT_TOPIC = "TEST/MQTT"
# แก้ไข Signature ของ on_connect ให้ถูกต้อง
# (client, userdata, flags, rc)
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        json_message = '{"sensor": "python-script", "value": 123.45, "status": "online"}'
        print("MQTT Connected.")
        # สั่งให้ subscribe (รอรับ) topic เดิม
        client.subscribe("TEST/MQTT")
        print(f"Subscribed to 'TEST/MQTT'")
        print("Publishing message...")
        client.publish(MQTT_TOPIC, json_message)
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    print(f"RECEIVED: Topic='{msg.topic}', Payload='{msg.payload.decode('utf-8')}'")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(host, port, 60)
client.loop_forever()