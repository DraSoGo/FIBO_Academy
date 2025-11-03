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
    sat_th = 70    # S
    val_th = 160   # V
    lower = np.array([0, 0, val_th], np.uint8)
    upper = np.array([179, sat_th, 255], np.uint8)
    m = cv2.inRange(img_hsv, lower, upper)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN,  k, iterations=1)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k, iterations=1)
    return m

def measure_from_mask(mask_img, min_area=30000):
    mask = (mask_img > 0).astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    no_metrics = {
        "area_px2": 0,
        "perimeter_px": 0,
        "length_px": 0,
        "width_px":  0,
    }
    if not contours:
        return None, no_metrics, 1
    c = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(c)
    if area < min_area:
        return None, no_metrics, 1

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

    return overlay, metrics, status

# Camera
def run_camera(camera_id=0, resize_to_width=None, print_every=5, ppm=None):
    cap = cv2.VideoCapture(camera_id)

    if not cap.isOpened():
        raise RuntimeError("Error")

    fps_clock = time.time()
    frame_i = 0
    cv2.namedWindow("Live", cv2.WINDOW_NORMAL)

    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break

            # ย่อภาพถ้าต้องการ
            if resize_to_width is not None and frame_bgr.shape[1] > resize_to_width:
                scale = resize_to_width / frame_bgr.shape[1]
                frame_bgr = cv2.resize(frame_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

            frame_bgr_blur = cv2.GaussianBlur(frame_bgr, (5,5), 0)

            hsv = cv2.cvtColor(frame_bgr_blur, cv2.COLOR_BGR2HSV)
            mask_img = mask(hsv)

            overlay, metrics, status = measure_from_mask(mask_img, min_area=30000)

            if overlay is not None:
                roi = (mask_img > 0)
                live_vis = frame_bgr.copy()
                live_vis[roi] = cv2.addWeighted(live_vis[roi], 0.4, overlay[roi], 0.6, 0)
            else:
                live_vis = frame_bgr.copy()

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
                    txt = f"L={metrics['length_px']:.1f}px, W={metrics['width_px']:.1f}px"
                cv2.putText(live_vis, txt, (10, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2, cv2.LINE_AA)
                y0 += 24
                cv2.putText(live_vis, f"Area={metrics['area_px2']:.0f}px^2  Perim={metrics['perimeter_px']:.1f}px",
                            (10, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 2, cv2.LINE_AA)
                y0 += 24

            if fps is not None:
                cv2.putText(live_vis, f"FPS: {fps:.1f}", (10, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2, cv2.LINE_AA)

            cv2.imshow("Live", live_vis)

            if frame_i % max(1, int(print_every)) == 0:
                out = {"status": int(status), **{k: float(v) for k,v in metrics.items()}}
                if ppm:
                    mm_per_px = 1.0/ppm
                    out.update({
                        "length_mm": metrics.get("length_px", 0.0) * mm_per_px,
                        "width_mm":  metrics.get("width_px", 0.0)  * mm_per_px,
                    })
                print(json.dumps(out, ensure_ascii=False))
                client.publish(MQTT_TOPIC, json.dumps(out), qos=2)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord('q')):
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    run_camera(camera_id=0, resize_to_width=960, print_every=5, ppm=None)