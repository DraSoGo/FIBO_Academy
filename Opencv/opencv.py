import cv2
import numpy as np

# --- 1. ค่าคงที่ที่ต้องปรับจูน (สำคัญมาก) ---

# อัตราส่วน พิกเซลต่อเซนติเมตร (ต้องหาเองจากการ Calibration)
PIXELS_PER_CM = 19.23 

# === ช่วงสีสำหรับการตรวจจับ ===
# ช่วงสีของ "แป้งโด (สีขาว/เนื้อ)" ในระบบสี HSV
LOWER_DOUGH_COLOR = np.array([0, 0, 150])
UPPER_DOUGH_COLOR = np.array([179, 55, 255])

# ช่วงสีของ "พื้นหลังสีฟ้า" ในระบบสี HSV (ยังต้องใช้เพื่อแยกสิ่งแปลกปลอม)
LOWER_BLUE_BG = np.array([100, 50, 50])
UPPER_BLUE_BG = np.array([130, 255, 255])

# === ค่า Thresholds ===
# ขนาดพื้นที่ (Area) ขั้นต่ำของวัตถุที่จะนับว่าเป็นแป้งโด (หน่วย: พิกเซล)
MIN_DOUGH_AREA = 500

# ขนาดพื้นที่ขั้นต่ำของสิ่งแปลกปลอมที่จะแจ้งเตือน (หน่วย: พิกเซล)
MIN_CONTAMINANT_AREA = 20

# --- 2. เริ่มต้นการทำงานกับกล้อง ---

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Error: ไม่สามารถเปิดกล้องได้")
    exit()

print("เปิดกล้องเรียบร้อย กด 'q' เพื่อออกจากโปรแกรม")
print("-" * 30)

# --- 3. Loop การทำงานแบบ Real-time ---

while True:
    ret, frame = cap.read()
    if not ret:
        print("ไม่สามารถรับเฟรมภาพได้ สิ้นสุดการทำงาน")
        break

    output_frame = frame.copy()
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # --- ส่วนที่ 1: การหาแป้งโด (เหมือนเดิม) ---
    dough_mask = cv2.inRange(hsv, LOWER_DOUGH_COLOR, UPPER_DOUGH_COLOR)
    kernel = np.ones((5, 5), np.uint8)
    dough_mask_cleaned = cv2.morphologyEx(dough_mask, cv2.MORPH_CLOSE, kernel)
    dough_mask_cleaned = cv2.morphologyEx(dough_mask_cleaned, cv2.MORPH_OPEN, kernel)
    
    contours_dough, _ = cv2.findContours(dough_mask_cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # รีเซ็ตค่าสำหรับ Loop นี้
    length_cm_str = "0.00 cm"
    contaminant_status = 0 # 0 = ไม่พบ, 1 = พบ
    found_dough = False

    # --- ส่วนที่ 2: การวัดขนาดและตรวจจับสิ่งแปลกปลอม (ถ้าเจอแป้งโด) ---
    if contours_dough:
        c_dough = max(contours_dough, key=cv2.contourArea)
        
        if cv2.contourArea(c_dough) > MIN_DOUGH_AREA:
            found_dough = True
            
            # 1. คำนวณความยาว
            perimeter_px = cv2.arcLength(c_dough, True)
            length_px = perimeter_px / 2.0
            length_cm = length_px / PIXELS_PER_CM
            length_cm_str = f"{length_cm:.2f} cm"

            # วาดเส้นขอบแป้งโด
            cv2.drawContours(output_frame, [c_dough], -1, (0, 255, 0), 2)
            
    # --- ⭐️ ตรวจสิ่งแปลกปลอม (ลด false positive ที่ขอบ/แสงไม่สม่ำเสมอ) ⭐️ ---

    # 1) มาสก์แป้งแบบเติมเต็มทั้งก้อน
    dough_filled = np.zeros_like(dough_mask_cleaned)
    cv2.drawContours(dough_filled, [c_dough], -1, 255, thickness=cv2.FILLED)

    # 2) เอาเฉพาะ "ไส้ใน" ของแป้ง เพื่อตัดขอบออกไป margin_px พิกเซล
    margin_px = max(8, int(0.4 * PIXELS_PER_CM))  # ปรับได้ 0.3–0.8 * PIXELS_PER_CM
    dist = cv2.distanceTransform(dough_filled, cv2.DIST_L2, 3)
    interior = np.uint8((dist > margin_px) * 255)

    # 3) ทำ black-hat บน L-channel (LAB) เพื่อหา "จุดมืดบนพื้นสว่าง"
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    L = lab[:, :, 0]
    L_blur = cv2.GaussianBlur(L, (5, 5), 0)
    kernel_bh = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))  # ลอง 7/9/11/13
    blackhat = cv2.morphologyEx(L_blur, cv2.MORPH_BLACKHAT, kernel_bh)

    bh_in = cv2.bitwise_and(blackhat, blackhat, mask=interior)

    # 4) ตั้ง threshold แบบสถิติ (robust กว่า Otsu ในฉากแสงแปรผัน)
    vals = bh_in[interior > 0]
    mu, sigma = float(vals.mean()), float(vals.std()) if vals.size else (0.0, 0.0)
    k = 2.5  # 2.0–3.0 ตามความเข้มจุดที่อยากจับ
    t = mu + k * sigma
    _, spots = cv2.threshold(bh_in, t, 255, cv2.THRESH_BINARY)

    # 5) ทำความสะอาด
    spots = cv2.morphologyEx(spots, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    spots = cv2.morphologyEx(spots, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=1)

    # 6) หาและกรองคอนทัวร์
    contours_contaminant, _ = cv2.findContours(spots, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    contaminant_status = 0
    for c_cont in contours_contaminant:
        area = cv2.contourArea(c_cont)
        if area < MIN_CONTAMINANT_AREA:
            continue

        per = cv2.arcLength(c_cont, True) + 1e-6
        circ = 4 * np.pi * area / (per * per)       # 0..1 (กลมสูง = ค่าสูง)
        x, y, w, h = cv2.boundingRect(c_cont)
        extent = area / (w * h + 1e-6)              # 0..1 (ยิ่งตันยิ่งสูง)
        # ตัดเส้นยาวบางๆ/เงาขอบ และจุดที่อยู่ใกล้ขอบเกินไป
        cx, cy = np.mean(c_cont.reshape(-1, 2), axis=0).astype(int)
        if dist[cy, cx] < margin_px:                # ใกล้ขอบก้อนแป้ง
            continue
        if extent < 0.15 and circ < 0.20:           # เส้นยาวบาง แปลว่าเงาหรือขอบ
            continue

        contaminant_status = 1
        cv2.rectangle(output_frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
        # ถ้าต้องการแสดงความมืดเฉลี่ยของก้อน (ช่วยจูน k)
        # mask_c = np.zeros_like(spots); cv2.drawContours(mask_c, [c_cont], -1, 255, cv2.FILLED)
        # mean_dark = int(cv2.mean(bh_in, mask=mask_c)[0])
        # cv2.putText(output_frame, f"{mean_dark}", (x, y-5),
        #             cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        break

    # (debug) เปิดดูได้เวลาจูน
    # cv2.imshow("interior", interior)
    # cv2.imshow("blackhat_interior", bh_in)
    # cv2.imshow("spots", spots)



    # --- ส่วนที่ 3: พิมพ์ผลลัพธ์ ---
    if found_dough:
        # ถ้าเจอแป้งโด จะพิมพ์ความยาวและสถานะสิ่งแปลกปลอม
        print(f"ความยาว: {length_cm_str}, สิ่งแปลกปลอม: {contaminant_status}")
        
        # แสดงข้อความบนหน้าจอ
        x_b, y_b, w_b, h_b = cv2.boundingRect(c_dough)
        cv2.putText(output_frame, length_cm_str, (x_b, y_b - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        if contaminant_status == 1:
            cv2.putText(output_frame, "Contaminant Found!", (x_b, y_b - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    else:
        # ถ้าไม่เจอแป้งโดเลย
        print(f"ความยาว: 0.00 cm, สิ่งแปลกปลอม: 0")

    # --- แสดงผลลัพธ์ ---
    # cv2.imshow("Live Camera", frame)
    cv2.imshow("Output with Measurement", output_frame)
    # cv2.imshow("Dough Mask", dough_mask_cleaned) # Uncomment เพื่อดู mask แป้งโด
    # cv2.imshow("Contaminant on Dough", contaminant_on_dough_mask) # Uncomment เพื่อดู mask สิ่งแปลกปลอม

    # รอรับการกดปุ่ม 'q' เพื่อออกจาก loop
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# --- 4. คืนทรัพยากรและปิดหน้าต่าง ---
print("-" * 30)
print("ปิดโปรแกรม")
cap.release()
cv2.destroyAllWindows()