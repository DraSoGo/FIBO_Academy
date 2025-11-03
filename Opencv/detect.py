import cv2
import numpy as np
from collections import deque

# ------------------------
# 1) ปุ่มจูนหลัก
# ------------------------
PIXELS_PER_CM = 19.23

# ช่วงสี "แป้ง" (ต้องจูนให้ตรงกับแป้งของคุณ)
LOWER_DOUGH_HSV = np.array([0, 0, 150])
UPPER_DOUGH_HSV = np.array([179, 55, 255])

MIN_DOUGH_AREA     = 500     # px
MIN_CONTAM_AREA    = 25      # px (เพิ่มขึ้นเล็กน้อยลดฟอลส์พอส)
MARGIN_FRAC        = 0.5     # ส่วนของ PIXELS_PER_CM เพื่อตัดขอบ (0.4–0.8)
DOG_SIGMA_SMALL    = 1.2     # ขนาดรายละเอียดที่อยากจับ (px)
DOG_SIGMA_LARGE    = 4.0     # ควร > small ~3–5 เท่า
Z_THR              = 3.5     # เกณฑ์ z-score (robust) สำหรับผิดปกติ
POS_STREAK_N       = 4       # ต้องเจอติดกันกี่เฟรม ถึงจะขึ้น 1
NEG_STREAK_N       = 6       # ต้องไม่เจอติดกันกี่เฟรม ถึงจะกลับเป็น 0
SHOW_DEBUG         = False   # True เพื่อดูหน้าต่าง debug

# ------------------------
# 2) กล้อง
# ------------------------
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Error: เปิดกล้องไม่ได้")
    raise SystemExit

# (ตัวเลือก) ลองปิด auto exposure/auto white balance ถ้ากล้องรองรับ
try:
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # บางไดรเวอร์: 0.25=manual, 0.75=auto
    cap.set(cv2.CAP_PROP_EXPOSURE, -6)         # ค่านี้ต้องลองจูนตามกล้อง (อาจไม่รองรับ)
    cap.set(cv2.CAP_PROP_AUTO_WB, 0)
except Exception:
    pass

kernel3 = np.ones((3, 3), np.uint8)
kernel5 = np.ones((5, 5), np.uint8)

status_stable = 0
pos_streak = 0
neg_streak = 0

print("กด q เพื่อออก")

while True:
    ok, frame = cap.read()
    if not ok:
        break

    out = frame.copy()

    # ------------------------
    # 3) หา mask ของแป้ง
    # ------------------------
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    dough_mask = cv2.inRange(hsv, LOWER_DOUGH_HSV, UPPER_DOUGH_HSV)
    dough_mask = cv2.morphologyEx(dough_mask, cv2.MORPH_CLOSE, kernel5)
    dough_mask = cv2.morphologyEx(dough_mask, cv2.MORPH_OPEN,  kernel5)

    contours, _ = cv2.findContours(dough_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    contaminant_now = 0

    if contours:
        c = max(contours, key=cv2.contourArea)
        if cv2.contourArea(c) > MIN_DOUGH_AREA:
            cv2.drawContours(out, [c], -1, (0, 255, 0), 2)

            # mask แป้งแบบเติม + เอาเฉพาะ "ไส้ใน" (กันขอบ)
            filled = np.zeros_like(dough_mask)
            cv2.drawContours(filled, [c], -1, 255, thickness=cv2.FILLED)
            margin_px = max(8, int(MARGIN_FRAC * PIXELS_PER_CM))
            dist = cv2.distanceTransform(filled, cv2.DIST_L2, 3)
            interior = np.uint8((dist > margin_px) * 255)

            # ------------------------
            # 4) ทำให้แสงนิ่งขึ้น + ดึงจุดผิดปกติด้วย DoG
            # ------------------------
            # a) L-channel + CLAHE (flatten แสง)
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            L = lab[:, :, 0]
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            Lc = clahe.apply(L)

            # b) Difference-of-Gaussians (band-pass)
            g1 = cv2.GaussianBlur(Lc, (0, 0), DOG_SIGMA_SMALL)
            g2 = cv2.GaussianBlur(Lc, (0, 0), DOG_SIGMA_LARGE)
            dog = cv2.absdiff(g1, g2)

            dog_in = cv2.bitwise_and(dog, dog, mask=interior)

            # ------------------------
            # 5) Robust z-score (median + MAD)
            # ------------------------
            vals = dog_in[interior > 0]
            if vals.size > 0:
                med = np.median(vals)
                mad = np.median(np.abs(vals - med)) + 1e-6
                z = (dog_in - med) / (1.4826 * mad)
                _, spots = cv2.threshold(z.astype(np.float32), Z_THR, 255, cv2.THRESH_BINARY)
                spots = spots.astype(np.uint8)
            else:
                spots = np.zeros_like(dog_in, dtype=np.uint8)

            # ทำความสะอาด
            spots = cv2.morphologyEx(spots, cv2.MORPH_OPEN, kernel3, iterations=1)
            spots = cv2.morphologyEx(spots, cv2.MORPH_CLOSE, kernel5, iterations=1)

            # ------------------------
            # 6) กรองคอนทัวร์ + กันเงา/ขอบ
            # ------------------------
            cs, _ = cv2.findContours(spots, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cc in cs:
                area = cv2.contourArea(cc)
                if area < MIN_CONTAM_AREA:
                    continue
                x, y, w, h = cv2.boundingRect(cc)
                per = cv2.arcLength(cc, True) + 1e-6
                circ = 4.0 * np.pi * area / (per * per)
                extent = area / (w * h + 1e-6)
                cx, cy = np.mean(cc.reshape(-1, 2), axis=0).astype(int)

                # ไม่เอาจุดที่อยู่ใกล้ขอบแป้งเกินไป (มักเป็นเงา)
                if dist[cy, cx] < margin_px:
                    continue
                # ไม่เอาเส้นยาวบาง ๆ
                if extent < 0.15 and circ < 0.20:
                    continue

                contaminant_now = 1
                cv2.rectangle(out, (x, y), (x + w, y + h), (0, 0, 255), 2)
                break

            # ข้อความบนภาพ
            x_b, y_b, w_b, h_b = cv2.boundingRect(c)
            color = (0, 0, 255) if status_stable == 1 else (0, 180, 0)
            cv2.putText(out, f"Contaminant: {status_stable}", (x_b, y_b - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

            if SHOW_DEBUG:
                cv2.imshow("interior", interior)
                cv2.imshow("dog_in", dog_in)
                cv2.imshow("spots", spots)
        else:
            cv2.putText(out, "No dough / too small", (20, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
            contaminant_now = 0
    else:
        cv2.putText(out, "No dough", (20, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
        contaminant_now = 0

    # ------------------------
    # 7) Temporal debouncing
    # ------------------------
    if contaminant_now == 1:
        pos_streak += 1
        neg_streak = 0
        if status_stable == 0 and pos_streak >= POS_STREAK_N:
            status_stable = 1
    else:
        neg_streak += 1
        pos_streak = 0
        if status_stable == 1 and neg_streak >= NEG_STREAK_N:
            status_stable = 0

    print(status_stable)  # พิมพ์ 0/1 แบบนิ่ง ๆ

    cv2.imshow("Dough QC (stable)", out)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
