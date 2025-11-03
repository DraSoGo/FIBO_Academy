import cv2
import numpy as np
import time
import json
import paho.mqtt.client as mqtt
from skimage.morphology import skeletonize

MQTT_HOST = '10.61.24.78'
MQTT_PORT = 1883
MQTT_TOPIC = 'CPRAM/1/cam'
PUBLISH_INTERVAL_SEC = 0.01

client = mqtt.Client(client_id=f"dough-cam-{np.random.randint(0,1e9)}")
client.connect(MQTT_HOST, MQTT_PORT, 60)
client.loop_start()

last_pub_t = 0.0

# Analysis functions
def mask(img_hsv):
    sat_th = 70# S
    val_th = 160 # V
    lower = np.array([0, 0, val_th], np.uint8)
    upper = np.array([179, sat_th, 255], np.uint8)
    m = cv2.inRange(img_hsv, lower, upper)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN,  k, iterations=1)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k, iterations=1)
    return m

# MODIFIED: แก้ไขฟังก์ชันนี้เพื่อแสดงผลทั้ง L และ W
def perform_calculation(data_line1, data_line2, data_line3):
    """
    ฟังก์ชันสำหรับคำนวณหลังจากที่แป้งเคลื่อนที่ผ่านครบ 3 เส้น
    ตอนนี้จะ print ข้อมูลความยาว (L) และความกว้าง (W)
    """
    print("--- CALCULATION TRIGGERED ---")
    
    # แสดงค่า L/W ของแต่ละเส้น
    print(f"Data Line 1 (L/W): {data_line1['length_px']:.1f} / {data_line1['width_px']:.1f} px")
    print(f"Data Line 2 (L/W): {data_line2['length_px']:.1f} / {data_line2['width_px']:.1f} px")
    print(f"Data Line 3 (L/W): {data_line3['length_px']:.1f} / {data_line3['width_px']:.1f} px")
    
    # คำนวณค่าเฉลี่ยความยาว
    avg_length = (data_line1['length_px'] + data_line2['length_px'] + data_line3['length_px']) / 3.0
    
    # คำนวณค่าเฉลี่ยความกว้าง
    avg_width = (data_line1['width_px'] + data_line2['width_px'] + data_line3['width_px']) / 3.0
    
    print(f"Average Length: {avg_length:.2f} px")
    print(f"Average Width:  {avg_width:.2f} px")
    print("-----------------------------")
    
def measure_from_mask(mask_img, min_area=25000):
    mask = (mask_img > 0).astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    no_metrics = {
        "area_px2": 0,
        "perimeter_px": 0,
        "length_px": 0,
        "width_px":  0,
    }
    if not contours:
        return None, no_metrics, 1, None
        
    c = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(c)
    if area < min_area:
        return None, no_metrics, 1, None

    rect = cv2.minAreaRect(c)
    (cx, cy), (w, h), angle = rect
    perimeter = cv2.arcLength(c, True)

    filled = np.zeros_like(mask)
    cv2.drawContours(filled, [c], -1, 255, thickness=-1)

    skeleton = skeletonize(filled > 0)
    skeleton_px_count = int(np.count_nonzero(skeleton))

    skel_pts_yx = np.column_stack(np.where(skeleton))
    if skel_pts_yx.size == 0:
        width_px = float(min(w, h))
    else:
        skel_pts = np.empty((skel_pts_yx.shape[0], 2), dtype=float)
        skel_pts[:, 0] = skel_pts_yx[:, 1]  # x
        skel_pts[:, 1] = skel_pts_yx[:, 0]  # y
        contour_pts = c.reshape(-1, 2).astype(float)
        min_dists = []
        for px, py in skel_pts:
            d = np.hypot(contour_pts[:, 0] - px, contour_pts[:, 1] - py)
            min_dists.append(d.min())
        mean_dist = float(np.mean(min_dists)) if min_dists else 0.0
        width_px = 2.0 * mean_dist

    overlay = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    cv2.drawContours(overlay, [c], -1, (0,255,0), 2)
    ys, xs = np.where(skeleton)
    if ys.size > 0:
        overlay[ys, xs] = (0, 0, 255)

    metrics = {
        "area_px2": float(area),
        "perimeter_px": float(perimeter),
        "length_px": float(skeleton_px_count),
        "width_px":  float(width_px),
    }

    holes = cv2.bitwise_and(filled, cv2.bitwise_not(mask))
    hole_contours, _ = cv2.findContours(holes, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    status = 1
    if hole_contours:
        status = 0

    return overlay, metrics, status, (cx, cy)

# Camera
def run_camera(camera_id=0, resize_to_width=None, print_every=5, ppm=None):
    cap = cv2.VideoCapture(camera_id)

    if not cap.isOpened():
        raise RuntimeError("Error")

    fps_clock = time.time()
    frame_i = 0
    cv2.namedWindow("Live", cv2.WINDOW_NORMAL)

    line_data_storage = [None, None, None]
    trigger_lines_y = [] 

    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break
                
            frame_height, frame_width = frame_bgr.shape[:2]
            if not trigger_lines_y: 
                section_height = frame_height // 4
                trigger_lines_y = [
                    section_height,      # เส้นที่ 1 (25%)
                    section_height * 2,  # เส้นที่ 2 (50%)
                    section_height * 3   # เส้นที่ 3 (75%)
                ]

            if resize_to_width is not None and frame_bgr.shape[1] > resize_to_width:
                scale = resize_to_width / frame_bgr.shape[1]
                frame_bgr = cv2.resize(frame_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                
                frame_height, frame_width = frame_bgr.shape[:2]
                section_height = frame_height // 4
                trigger_lines_y = [section_height, section_height * 2, section_height * 3]


            frame_bgr_blur = cv2.GaussianBlur(frame_bgr, (5,5), 0)

            hsv = cv2.cvtColor(frame_bgr_blur, cv2.COLOR_BGR2HSV)
            mask_img = mask(hsv)

            overlay, metrics, status, centroid = measure_from_mask(mask_img, min_area=30000)

            if overlay is not None:
                roi = (mask_img > 0)
                live_vis = frame_bgr.copy()
                live_vis[roi] = cv2.addWeighted(live_vis[roi], 0.4, overlay[roi], 0.6, 0)
            else:
                live_vis = frame_bgr.copy()
                
            if centroid is not None:
                cx = int(centroid[0])
                cy = int(centroid[1])
                
                cv2.circle(live_vis, (cx, cy), 7, (255, 255, 0), -1)

                # ตรวจสอบการผ่านเส้น (สมมติว่าแป้งเคลื่อนจากบนลงล่าง)
                
                if cy > trigger_lines_y[0] and line_data_storage[0] is None:
                    line_data_storage[0] = metrics.copy()
                    print(f"Event: Crossed Line 1. Data: {line_data_storage[0]}")
                
                elif cy > trigger_lines_y[1] and line_data_storage[0] is not None and line_data_storage[1] is None:
                    line_data_storage[1] = metrics.copy()
                    print(f"Event: Crossed Line 2. Data: {line_data_storage[1]}")

                elif cy > trigger_lines_y[2] and line_data_storage[1] is not None and line_data_storage[2] is None:
                    line_data_storage[2] = metrics.copy()
                    print(f"Event: Crossed Line 3. Data: {line_data_storage[2]}")
                    
                    perform_calculation(line_data_storage[0], line_data_storage[1], line_data_storage[2])
                    
                    line_data_storage = [None, None, None]

            else: 
                if line_data_storage[0] is not None and line_data_storage[2] is None:
                    print("Event: Dough lost mid-run. Resetting...")
                    line_data_storage = [None, None, None]

            frame_i += 1
            if frame_i % 10 == 0:
                now = time.time()
                fps = 10.0 / (now - fps_clock)
                fps_clock = now
            else:
                fps = None

            y0 = 28
            cv2.putText(live_vis, f"status: {'OK' if status==1 else 'NG'}", (10, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0,255,0) if status==1 else (0,0,255), 2, cv2.LINE_AA)
            y0 += 24
            if metrics:
                if ppm:
                    mm_per_px = 1.0/ppm
                    length_mm = metrics["length_px"] * mm_per_px
                    width_mm  = metrics["width_px"]  * mm_per_px
                    txt = f"L={metrics['length_px']:.1f}px ({length_mm:.2f}mm), W={metrics['width_px']:.1f}px ({width_mm:.2f}mm)"
                else:
                    # แสดงค่า L/W ล่าสุดบนจอ
                    txt = f"L={metrics['length_px']:.1f}px, W={metrics['width_px']:.1f}px"
                cv2.putText(live_vis, txt, (10, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2, cv2.LINE_AA)
                y0 += 24
                cv2.putText(live_vis, f"Area={metrics['area_px2']:.0f}px^2  Perim={metrics['perimeter_px']:.1f}px",
                            (10, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 2, cv2.LINE_AA)
                y0 += 24

            if fps is not None:
                cv2.putText(live_vis, f"FPS: {fps:.1f}", (10, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2, cv2.LINE_AA)

            for i, y_pos in enumerate(trigger_lines_y):
                color = (0, 255, 0) if line_data_storage[i] is not None else (0, 255, 255) # เขียว / เหลือง
                cv2.line(live_vis, (0, y_pos), (frame_width, y_pos), color, 2)
                cv2.putText(live_vis, f"L{i+1}", (5, y_pos - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


            cv2.imshow("Live", live_vis)

            if frame_i % max(1, int(print_every)) == 0:
                out = {"status": int(status), **{k: float(v) for k,v in metrics.items()}}
                if ppm:
                    mm_per_px = 1.0/ppm
                    out.update({
                        "length_mm": metrics.get("length_px", 0.0) * mm_per_px,
                        "width_mm":  metrics.get("width_px", 0.0)  * mm_per_px,
                    })
                    
                
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord('q')):
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    run_camera(camera_id=0, resize_to_width=960, print_every=5, ppm=None)