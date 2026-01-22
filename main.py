import cv2
import time
import threading
import queue
import numpy as np
import mediapipe as mp
import pyttsx3
import config
from utils import log_violation, save_screenshot
from ultralytics import YOLO
import smtplib
import ssl
import sqlite3

# ================= DATABASE SETUP =================
conn = sqlite3.connect('violations.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS violations (
    id INTEGER PRIMARY KEY,
    student_id TEXT,
    exam_name TEXT,
    violation TEXT,
    time TEXT,
    warning_count INTEGER,
    screenshot TEXT
)''')
conn.commit()
# ===============================================

def send_email_alert(violation_name, warning_count):
    """Send Gmail alert for malpractice warning."""
    subject = f"Malpractice Warning: {violation_name}"
    body = f"""
Student ID: {config.STUDENT_ID}
Exam Name: {config.EXAM_NAME}
Violation Type: {violation_name}
Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}
Warning Count: {warning_count}
"""
    msg = f"Subject: {subject}\n\n{body}"

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()  # Secure the connection
        server.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
        server.sendmail(config.EMAIL_ADDRESS, config.AUTHORITY_EMAIL, msg)
        server.quit()
        print("Email sent successfully")
    except Exception as e:
        print(f"Failed to send email: {e}")

def save_violation_to_db(violation_name, warning_count, screenshot_path):
    """Save violation record to SQLite database."""
    c.execute("INSERT INTO violations (student_id, exam_name, violation, time, warning_count, screenshot) VALUES (?, ?, ?, ?, ?, ?)",
              (config.STUDENT_ID, config.EXAM_NAME, violation_name, time.strftime('%Y-%m-%d %H:%M:%S'), warning_count, screenshot_path))
    conn.commit()

# ================= YOLO =========================
yolo_model = YOLO("yolov8n.pt")
PHONE_CLASS_NAME = "cell phone"
PHONE_MIN_CONF = 0.25
PHONE_MIN_TIME = 0.6
phone_start_time = None
# ===============================================

# ================= VOICE ========================
voice_queue = queue.Queue()
engine = pyttsx3.init()
engine.setProperty("rate", 140)
engine.setProperty("volume", 1.0)

def voice_worker():
    while True:
        text = voice_queue.get()
        engine.say(text)
        engine.runAndWait()
        voice_queue.task_done()

threading.Thread(target=voice_worker, daemon=True).start()

def speak(text):
    if voice_queue.empty():
        voice_queue.put(text)
# ===============================================

# ================= MEDIAPIPE ====================
mp_face = mp.solutions.face_mesh
face_mesh = mp_face.FaceMesh(refine_landmarks=True, max_num_faces=1)

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=2,
                       min_detection_confidence=0.6,
                       min_tracking_confidence=0.6)
# ===============================================

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Camera not found")
    exit()

# ================= TIMER ========================
EXAM_DURATION_SECONDS = 120
first_frame_seen = False
exam_start_time = None
exam_ended_announced = False
# ===============================================

last_alert_time = 0
popup_message = ""
popup_end_time = 0

phone_shot_saved = False
speaking_shot_saved = False
hand_shot_saved = False
head_turn_shot_saved = False

warning_count = 0
MAX_WARNINGS = 3

# ================= SPEAK SETTINGS ===============
SPEAK_MIN_TIME = 0.8
MOUTH_OPEN_MIN = 0.006
last_mouth_ratio = None
mouth_motion_counter = 0
MOUTH_MOTION_DIFF = 0.0012
speaking_start_time = None
# ===============================================

# ================= HAND + HEAD ==================
HEAD_TURN_THRESHOLD = 0.05
HEAD_TURN_WINDOW = 5
head_turn_timestamps = []
last_turn_direction = None
hand_start_time = None
hand_near_mouth = False
# ===============================================

def lip_distance_ratio(landmarks):
    top = landmarks[13].y
    bottom = landmarks[14].y
    left = landmarks[78].x
    right = landmarks[308].x
    return abs(bottom - top) / (abs(right - left) + 1e-6)

# ================= LOOP =========================
while True:
    ret, frame = cap.read()
    if not ret:
        break

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    now = time.time()

    # ================= EXAM TIMER =================
    if not first_frame_seen:
        first_frame_seen = True
        exam_start_time = time.time()
        speak("Your exam starts now")

    elapsed = int(time.time() - exam_start_time)

    if elapsed >= EXAM_DURATION_SECONDS and not exam_ended_announced:
        speak("The exam has ended")
        exam_ended_announced = True

    detection_enabled = warning_count < MAX_WARNINGS

    # ================= PHONE DETECTION =================
    phone_detected = False
    if detection_enabled:
        results = yolo_model(frame, conf=PHONE_MIN_CONF, iou=0.45, verbose=False)
        for r in results:
            for box in r.boxes:
                cls = int(box.cls[0])
                name = yolo_model.names[cls]
                if name == PHONE_CLASS_NAME:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    cv2.putText(frame, "Phone", (x1, y1-8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                    if phone_start_time is None:
                        phone_start_time = now
                    if now - phone_start_time > PHONE_MIN_TIME:
                        phone_detected = True
    else:
        phone_start_time = None

    # ================= FACE & SPEAK =================
    speaking_detected = False
    face_results = face_mesh.process(rgb)

    if detection_enabled and face_results.multi_face_landmarks:
        for fl in face_results.multi_face_landmarks:
            ratio = lip_distance_ratio(fl.landmark)
            if last_mouth_ratio is None:
                last_mouth_ratio = ratio
            diff = abs(ratio - last_mouth_ratio)
            last_mouth_ratio = ratio

            if ratio > MOUTH_OPEN_MIN and diff > MOUTH_MOTION_DIFF:
                mouth_motion_counter += 1
            else:
                mouth_motion_counter = 0
                speaking_start_time = None

            if mouth_motion_counter > 2 and not hand_near_mouth:
                if speaking_start_time is None:
                    speaking_start_time = now
                if now - speaking_start_time > SPEAK_MIN_TIME:
                    speaking_detected = True
                    cv2.putText(frame, "Speaking", (10, 100),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # ================= HAND DETECTION =================
    hand_suspicious = False
    hand_results = hands.process(rgb)
    if detection_enabled and hand_results.multi_hand_landmarks and face_results.multi_face_landmarks:
        mouth_y = fl.landmark[13].y
        for hl in hand_results.multi_hand_landmarks:
            palm_y = hl.landmark[0].y
            distance = abs(palm_y - mouth_y)
            if distance < 0.035:
                hand_near_mouth = True
            if distance < 0.05:
                hand_start_time = None
                continue
            if hand_start_time is None:
                hand_start_time = now
            if now - hand_start_time > 0.7:
                hand_suspicious = True
                cv2.putText(frame, "Hand Gesture", (10, 130),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
    else:
        hand_start_time = None

    # ================= HEAD TURN =================
    head_turn_detected = False
    if detection_enabled and face_results.multi_face_landmarks:
        nose_x = fl.landmark[1].x
        eye_center_x = (fl.landmark[33].x + fl.landmark[263].x) / 2
        diff = nose_x - eye_center_x
        turn_direction = None
        if diff < -HEAD_TURN_THRESHOLD:
            turn_direction = 'left'
        elif diff > HEAD_TURN_THRESHOLD:
            turn_direction = 'right'
        if turn_direction and turn_direction != last_turn_direction:
            head_turn_timestamps.append(now)
            last_turn_direction = turn_direction
        head_turn_timestamps = [t for t in head_turn_timestamps if now - t <= HEAD_TURN_WINDOW]
        if len(head_turn_timestamps) >= 3:
            head_turn_detected = True

    # ================= ALERT & VIOLATION =================
    violation_name = None
    if phone_detected:
        violation_name = "Phone Detected"
    elif speaking_detected:
        violation_name = "Speaking Detected"
    elif hand_suspicious:
        violation_name = "Hand Gesture Detected"
    elif head_turn_detected:
        violation_name = "Head Turn Detected"

    if violation_name and now - last_alert_time > 6 and detection_enabled:
        last_alert_time = now
        warning_count += 1
        popup_message = f"Warning {warning_count}: {violation_name}"
        popup_end_time = now + config.WARNING_POPUP_DURATION
        log_violation(popup_message)

        screenshot_path = None
        if phone_detected and not phone_shot_saved:
            screenshot_path = save_screenshot(frame, "phone")
            phone_shot_saved = True
        if speaking_detected and not speaking_shot_saved:
            screenshot_path = save_screenshot(frame, "speaking")
            speaking_shot_saved = True
        if hand_suspicious and not hand_shot_saved:
            screenshot_path = save_screenshot(frame, "hand")
            hand_shot_saved = True
        if head_turn_detected and not head_turn_shot_saved:
            screenshot_path = save_screenshot(frame, "head_turn")
            head_turn_shot_saved = True

        save_violation_to_db(violation_name, warning_count, screenshot_path)
        speak(popup_message)
        send_email_alert(violation_name, warning_count)

    # ================= UI ========================
    cv2.putText(frame, f"Student ID: {config.STUDENT_ID}", (10, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, f"Exam: {config.EXAM_NAME}", (10, 45),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, f"Time: {elapsed//60:02d}:{elapsed%60:02d}", (10, 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    if time.time() < popup_end_time:
        cv2.putText(frame, popup_message, (160, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    cv2.imshow("AI Exam Surveillance System", frame)
    if cv2.waitKey(1) & 0xFF in [27, ord("q")]:
        break

cap.release()
cv2.destroyAllWindows()
