import cv2
import numpy as np
import json, time
import paho.mqtt.client as mqtt

# --- 1) ค่าคงที่ที่ปรับจูน ---
PIXELS_PER_CM = 19.23

LOWER_DOUGH_COLOR = np.array([0, 0, 150])
UPPER_DOUGH_COLOR = np.array([179, 55, 255])

LOWER_BLUE_BG = np.array([100, 50, 50])
UPPER_BLUE_BG = np.array([130, 255, 255])

MIN_DOUGH_AREA = 500
MIN_CONTAMINANT_AREA = 20

# --- 2) MQTT ---
MQTT_HOST = 'test.mosquitto.org'
MQTT_PORT = 1883
MQTT_TOPIC = 'CPRAM/1/cam'
PUBLISH_INTERVAL_SEC = 0.01 # กันสแปม topic

client = mqtt.Client(client_id=f"dough-cam-{np.random.randint(0,1e9)}")
client.connect(MQTT_HOST, MQTT_PORT, 60)
client.loop_start()

def publish_measure(length_cm, contaminant_status):
    payload = {"module": "cam", "data": f"{int(round(length_cm))},{int(contaminant_status)}"}
    client.publish(MQTT_TOPIC, json.dumps(payload), qos=0)

last_pub_t = 0.0

# --- 3) กล้อง ---
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Error: ไม่สามารถเปิดกล้องได้"); raise SystemExit

print("เปิดกล้องเรียบร้อย กด 'q' เพื่อออกจากโปรแกรม")
print("-" * 30)

kernel5 = np.ones((5, 5), np.uint8)

while True:
    ret, frame = cap.read()
    if not ret:
        print("ไม่สามารถรับเฟรมภาพได้ สิ้นสุดการทำงาน")
        break

    output_frame = frame.copy()
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # --- หาแป้งโด ---
    dough_mask = cv2.inRange(hsv, LOWER_DOUGH_COLOR, UPPER_DOUGH_COLOR)
    dough_mask_cleaned = cv2.morphologyEx(dough_mask, cv2.MORPH_CLOSE, kernel5)
    dough_mask_cleaned = cv2.morphologyEx(dough_mask_cleaned, cv2.MORPH_OPEN, kernel5)
    contours_dough, _ = cv2.findContours(dough_mask_cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # ค่า default
    found_dough = False
    length_cm = 0.0
    contaminant_status = 0

    if contours_dough:
        c_dough = max(contours_dough, key=cv2.contourArea)
        if cv2.contourArea(c_dough) > MIN_DOUGH_AREA:
            found_dough = True

            # ---- วัดความยาว (แนวเดิมของคุณ) ----
            perimeter_px = cv2.arcLength(c_dough, True)
            length_px = perimeter_px / 2.0
            length_cm = length_px / PIXELS_PER_CM
            cv2.drawContours(output_frame, [c_dough], -1, (0, 255, 0), 2)

            # ---- ตรวจสิ่งแปลกปลอมแบบลด false positive ----
            # 1) mask แป้งแบบเติมเต็ม + เอาแต่ "ไส้ใน" (ตัดขอบ)
            dough_filled = np.zeros_like(dough_mask_cleaned)
            cv2.drawContours(dough_filled, [c_dough], -1, 255, thickness=cv2.FILLED)

            margin_px = max(8, int(0.4 * PIXELS_PER_CM))  # จูนได้ 0.3–0.8 * PIXELS_PER_CM
            dist = cv2.distanceTransform(dough_filled, cv2.DIST_L2, 3)
            interior = np.uint8((dist > margin_px) * 255)

            # 2) Black-hat บน L-channel (LAB)
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            L = lab[:, :, 0]
            L_blur = cv2.GaussianBlur(L, (5, 5), 0)
            kernel_bh = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
            blackhat = cv2.morphologyEx(L_blur, cv2.MORPH_BLACKHAT, kernel_bh)
            bh_in = cv2.bitwise_and(blackhat, blackhat, mask=interior)

            # 3) Threshold แบบสถิติ (กันแสงแปรผัน)
            vals = bh_in[interior > 0]
            if vals.size > 0:
                mu = float(vals.mean())
                sigma = float(vals.std())
            else:
                mu = sigma = 0.0
            t = mu + 2.5 * sigma   # k=2.5 จูนได้ 2.0–3.0
            _, spots = cv2.threshold(bh_in, t, 255, cv2.THRESH_BINARY)

            # 4) ทำความสะอาด
            spots = cv2.morphologyEx(spots, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
            spots = cv2.morphologyEx(spots, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=1)

            # 5) กรองคอนทัวร์ (กันเงาแถวยาว/ใกล้ขอบ)
            contours_contaminant, _ = cv2.findContours(spots, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c_cont in contours_contaminant:
                area = cv2.contourArea(c_cont)
                if area < MIN_CONTAMINANT_AREA:
                    continue
                per = cv2.arcLength(c_cont, True) + 1e-6
                circ = 4 * np.pi * area / (per * per)
                x, y, w, h = cv2.boundingRect(c_cont)
                extent = area / (w * h + 1e-6)
                cx, cy = np.mean(c_cont.reshape(-1, 2), axis=0).astype(int)
                if dist[cy, cx] < margin_px:
                    continue
                if extent < 0.15 and circ < 0.20:
                    continue

                contaminant_status = 1
                cv2.rectangle(output_frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
                break  # เอาแค่ชิ้นแรกก็พอ

    # --- แสดงผล + พิมพ์ ---
    if found_dough:
        x_b, y_b, w_b, h_b = cv2.boundingRect(c_dough)
        cv2.putText(output_frame, f"{length_cm:.2f} cm", (x_b, y_b - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        if contaminant_status == 1:
            cv2.putText(output_frame, "Contaminant Found!", (x_b, y_b - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        print(f"ความยาว: {length_cm:.2f} cm, สิ่งแปลกปลอม: {contaminant_status}")
    else:
        print("ความยาว: 0.00 cm, สิ่งแปลกปลอม: 0")

    cv2.imshow("Output with Measurement", output_frame)

    # --- ส่ง MQTT (ทุก ๆ PUBLISH_INTERVAL_SEC วินาที) ---
    now = time.monotonic()
    if now - last_pub_t >= PUBLISH_INTERVAL_SEC:
        publish_measure(length_cm if found_dough else 0.0, contaminant_status if found_dough else 0)
        last_pub_t = now

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

print("-" * 30)
print("ปิดโปรแกรม")
cap.release()
cv2.destroyAllWindows()
client.loop_stop()
client.disconnect()