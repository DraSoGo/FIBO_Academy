import cv2
import numpy as np

# --- 1) Config ---
PIXELS_PER_CM = 19.23
LOWER_BLUE = np.array([100, 50, 50])
UPPER_BLUE = np.array([130, 255, 255])
MIN_DOUGH_AREA = 500

# --- Start cam ---
# ถ้าใช้ Windows ลองเปลี่ยนเป็น cv2.CAP_DSHOW
cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

if not cap.isOpened():
    raise RuntimeError("เปิดกล้องไม่สำเร็จ: ตรวจสอบ device /dev/video0 หรือแอปอื่นที่กำลังใช้กล้องอยู่")

kernel = np.ones((5, 5), np.uint8)
cv2.namedWindow("Live Camera", cv2.WINDOW_NORMAL)
cv2.namedWindow("Output with Measurement", cv2.WINDOW_NORMAL)

try:
    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            print("อ่านเฟรมไม่สำเร็จ (ret=False) — กล้องอาจถูกใช้งานโดยโปรแกรมอื่น")
            continue

        output_frame = frame.copy()

        # --- Image processing ---
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        background_mask = cv2.inRange(hsv, LOWER_BLUE, UPPER_BLUE)
        dough_mask = cv2.bitwise_not(background_mask)
        mask_cleaned = cv2.morphologyEx(dough_mask, cv2.MORPH_CLOSE, kernel)
        mask_cleaned = cv2.morphologyEx(mask_cleaned, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(mask_cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        length_cm = 0.0
        if contours:
            c = max(contours, key=cv2.contourArea)
            if cv2.contourArea(c) > MIN_DOUGH_AREA:
                perimeter_px = cv2.arcLength(c, True)
                length_px = perimeter_px / 2.0
                length_cm = length_px / PIXELS_PER_CM

                cv2.drawContours(output_frame, [c], -1, (0, 255, 0), 2)
                x_b, y_b, w_b, h_b = cv2.boundingRect(c)
                cv2.putText(output_frame, f"{length_cm:.2f} cm", (x_b, y_b - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        # --- Show ---
        # cv2.imshow("Live Camera", frame)
        cv2.imshow("Output with Measurement", output_frame)

        # สำคัญมาก: ต้องมี waitKey เพื่อให้หน้าต่างอัปเดตและรับคีย์
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:  # q หรือ ESC
            break
finally:
    cap.release()
    cv2.destroyAllWindows()
