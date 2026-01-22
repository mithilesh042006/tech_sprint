from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for, send_from_directory, Response
import sqlite3
import os
import cv2
import time
import threading
import queue
import numpy as np
import mediapipe as mp
mp_face_mesh = mp.solutions.face_mesh
mp_hands = mp.solutions.hands
import pyttsx3
import config
from utils import log_violation, save_screenshot
from ultralytics import YOLO
import smtplib
import ssl

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Secure random secret key for sessions

# Detection globals
yolo_model = YOLO('yolov8n.pt')
engine = pyttsx3.init()
engine.setProperty('rate', 150)

face_mesh = mp_face_mesh.FaceMesh(refine_landmarks=True, max_num_faces=1)

hands = mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.6, min_tracking_confidence=0.6)

# Global variables for detection state
cap = None
detection_thread = None
frame_queue = queue.Queue(maxsize=30)
detection_running = False
detection_stopped = False
alert_message = ""

# Detection state variables (similar to main.py)
last_face_center = None
no_face_start = None
head_move_count = 0
warning_count = 0
last_sudden_move_time = 0
last_writing_move_time = 0
alert_count = 0
last_alert_time = 0
last_warning_time = 0
malpractice_pending = False


# Additional for web
phone_start_time = None
phone_shot_saved = False
speaking_shot_saved = False
hand_shot_saved = False
head_turn_shot_saved = False
last_mouth_ratio = None
mouth_motion_counter = 0
speaking_start_time = None
head_turn_timestamps = []
last_turn_direction = None
hand_start_time = None
hand_near_mouth = False
popup_message = ""
popup_end_time = 0
exam_start_time = None
first_frame_seen = False
exam_ended_announced = False
voice_queue = queue.Queue()

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

def lip_distance_ratio(landmarks):
    top = landmarks[13].y
    bottom = landmarks[14].y
    left = landmarks[78].x
    right = landmarks[308].x
    return abs(bottom - top) / (abs(right - left) + 1e-6)

def save_violation_to_db(violation_name, warning_count, screenshot_path):
    """Save violation record to SQLite database."""
    try:
        conn = sqlite3.connect('violations.db')
        c = conn.cursor()
        c.execute("INSERT INTO violations (student_id, exam_name, violation, time, warning_count, screenshot) VALUES (?, ?, ?, ?, ?, ?)",
                  (config.STUDENT_ID, config.EXAM_NAME, violation_name, time.strftime('%Y-%m-%d %H:%M:%S'), warning_count, screenshot_path))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving to DB: {e}")

def send_email_alert(violation_name, warning_count):
    """Send Gmail alert for malpractice warning."""
    def send_email():
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
            server.starttls()
            server.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
            server.sendmail(config.EMAIL_ADDRESS, config.AUTHORITY_EMAIL, msg)
            server.quit()
            print("Email sent successfully")
        except Exception as e:
            print(f"Failed to send email: {e}")

    threading.Thread(target=send_email, daemon=True).start()

def send_malpractice_email():
    """Send Gmail alert for malpractice booking to higher authority."""
    def send_email():
        subject = f"URGENT: Malpractice Booked - Student {config.STUDENT_ID}"
        body = f"""
URGENT MALPRACTICE ALERT

Student has been booked for malpractice during the exam.

Details:
- Student ID: {config.STUDENT_ID}
- Exam Name: {config.EXAM_NAME}
- Total Warnings: {config.MAX_WARNINGS}
- Time of Booking: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}
- Status: Exam Terminated

All violation records have been logged and screenshots saved.

Please take immediate action.

Exam Surveillance Authority
"""
        msg = f"Subject: {subject}\n\n{body}"

        try:
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
            server.sendmail(config.EMAIL_ADDRESS, config.HIGHER_AUTHORITY_EMAIL, msg)
            server.quit()
            print("Malpractice booking email sent successfully")
        except Exception as e:
            print(f"Failed to send malpractice email: {e}")

    threading.Thread(target=send_email, daemon=True).start()

def detection_loop():
    global cap, detection_running, frame_queue, warning_count, last_alert_time
    global phone_start_time, phone_shot_saved, speaking_shot_saved
    global hand_shot_saved, head_turn_shot_saved, last_mouth_ratio
    global mouth_motion_counter, speaking_start_time
    global head_turn_timestamps, last_turn_direction
    global hand_start_time, hand_near_mouth
    global popup_message, popup_end_time
    global exam_start_time, first_frame_seen, exam_ended_announced
    global detection_stopped, malpractice_pending
    global alert_message   # 🔥 THIS IS THE FIX

    try:
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not cap.isOpened():
            print("Camera not found in detection_loop")
            return

        EXAM_DURATION_SECONDS = config.EXAM_DURATION_MINUTES * 60

        while detection_running:
            ret, frame = cap.read()
            if not ret:
                break

            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                now = time.time()

                # Exam timer
                if not first_frame_seen:
                    first_frame_seen = True
                    exam_start_time = time.time()
                    speak("Your exam starts now")

                elapsed = int(time.time() - exam_start_time)

                if elapsed >= EXAM_DURATION_SECONDS and not exam_ended_announced:
                    speak("The exam has ended")
                    exam_ended_announced = True

                detection_enabled = warning_count < config.MAX_WARNINGS

                # Phone detection
                phone_detected = False
                if detection_enabled:
                    results = yolo_model(frame, conf=0.5, iou=0.5, verbose=False)
                    for r in results:
                        for box in r.boxes:
                            cls = int(box.cls[0])
                            name = yolo_model.names[cls]
                            if name == "cell phone":
                                x1, y1, x2, y2 = map(int, box.xyxy[0])
                                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                                cv2.putText(frame, "Phone", (x1, y1-8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                                if phone_start_time is None:
                                    phone_start_time = now
                                if now - phone_start_time > 1.0:
                                    phone_detected = True

                # Face & speak
                speaking_detected = False
                face_results = face_mesh.process(rgb)

                if detection_enabled and face_results.multi_face_landmarks:
                    for fl in face_results.multi_face_landmarks:
                        ratio = lip_distance_ratio(fl.landmark)
                        if last_mouth_ratio is None:
                            last_mouth_ratio = ratio
                        diff = abs(ratio - last_mouth_ratio)
                        last_mouth_ratio = ratio

                        if ratio > 0.01 and diff > 0.002:
                            mouth_motion_counter += 1
                        else:
                            mouth_motion_counter = 0
                            speaking_start_time = None

                        if mouth_motion_counter > 3 and not hand_near_mouth:
                            if speaking_start_time is None:
                                speaking_start_time = now
                            if now - speaking_start_time > 1.0:
                                speaking_detected = True
                                cv2.putText(frame, "Speaking", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

                # Hand detection
                hand_suspicious = False
                hand_results = hands.process(rgb)
                if detection_enabled and hand_results.multi_hand_landmarks and face_results.multi_face_landmarks:
                    mouth_y = fl.landmark[13].y
                    for hl in hand_results.multi_hand_landmarks:
                        palm_y = hl.landmark[0].y
                        distance = abs(palm_y - mouth_y)
                        if distance < 0.035:
                            hand_near_mouth = True
                        if distance < 0.04:
                            hand_start_time = None
                            continue
                        if hand_start_time is None:
                            hand_start_time = now
                        if now - hand_start_time > 1.0:
                            hand_suspicious = True
                            cv2.putText(frame, "Hand Gesture", (10, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

                # Head turn
                head_turn_detected = False
                if detection_enabled and face_results.multi_face_landmarks:
                    nose_x = fl.landmark[1].x
                    eye_center_x = (fl.landmark[33].x + fl.landmark[263].x) / 2
                    diff = nose_x - eye_center_x
                    turn_direction = None
                    if diff < -0.06:
                        turn_direction = 'left'
                    elif diff > 0.06:
                        turn_direction = 'right'
                    if turn_direction and turn_direction != last_turn_direction:
                        head_turn_timestamps.append(now)
                        last_turn_direction = turn_direction
                    head_turn_timestamps = [t for t in head_turn_timestamps if now - t <= 5]
                    if len(head_turn_timestamps) >= 4:
                        head_turn_detected = True

                # Violation
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
                    speak(popup_message)
                    popup_end_time = now + config.WARNING_POPUP_DURATION
                    log_violation(popup_message)

                    # Save screenshot for every warning
                    screenshot_path = save_screenshot(frame, violation_name.lower().replace(" ", "_"))

                    save_violation_to_db(violation_name, warning_count, screenshot_path)
                    send_email_alert(violation_name, warning_count)

                    if warning_count >= config.MAX_WARNINGS:
                        malpractice_pending = True
                        alert_message = "🚨 MALPRACTICE BOOKED! "


                # UI
                cv2.putText(frame, f"Student ID: {config.STUDENT_ID}", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cv2.putText(frame, f"Exam: {config.EXAM_NAME}", (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cv2.putText(frame, f"Time: {elapsed//60:02d}:{elapsed%60:02d}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                if time.time() < popup_end_time:
                    cv2.putText(frame, popup_message, (160, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

                if malpractice_pending and now >= popup_end_time:
                    popup_message = "Malpractice Booked - Exam Terminated"
                    speak("Malpractice detected. Exam terminated.")
                    send_malpractice_email()
                    popup_end_time = now + 5  # show for 5 seconds
                    detection_stopped = True
                    detection_running = False
                    malpractice_pending = False

                # Put frame in queue
                if not frame_queue.full():
                    frame_queue.put(frame)

            except Exception as e:
                print(f"Error processing frame: {e}")
                continue

    except Exception as e:
        print(f"Error in detection loop: {e}")
    finally:
        if cap is not None:
            cap.release()

# HTML Templates
LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Authority Login - Exam Surveillance</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            animation: gradientShift 15s ease infinite, float 6s ease-in-out infinite;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        @keyframes gradientShift {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        @keyframes float {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-10px); }
        }
        .card {
            border: none;
            border-radius: 20px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.3);
            backdrop-filter: blur(15px);
            background: rgba(255, 255, 255, 0.9);
            transition: all 0.4s ease;
        }
        .card:hover {
            transform: translateY(-10px) scale(1.02);
            box-shadow: 0 20px 40px rgba(0,0,0,0.4);
        }
        .btn-primary {
            background: linear-gradient(45deg, #007bff, #0056b3);
            border: none;
            border-radius: 30px;
            animation: pulse 2s infinite;
        }
        .btn-primary:hover {
            background: linear-gradient(45deg, #0056b3, #004085);
            transform: translateY(-3px);
            box-shadow: 0 10px 20px rgba(0,123,255,0.4);
        }
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(0,123,255,0.7); }
            70% { box-shadow: 0 0 0 10px rgba(0,123,255,0); }
            100% { box-shadow: 0 0 0 0 rgba(0,123,255,0); }
        }
        .form-control {
            border-radius: 15px;
            border: 2px solid #ddd;
            transition: border-color 0.3s;
        }
        .form-control:focus {
            border-color: #007bff;
            box-shadow: 0 0 10px rgba(0,123,255,0.3);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="row justify-content-center">
            <div class="col-md-6">
                <div class="card shadow-lg">
                    <div class="card-header bg-primary text-white text-center" style="border-radius: 15px 15px 0 0;">
                        <h2 class="mb-0"><i class="fas fa-shield-alt"></i> Authority Login</h2>
                    </div>
                    <div class="card-body p-4">
                        <form method="post" action="/login">
                            <div class="mb-4">
                                <label for="username" class="form-label fw-bold">Username</label>
                                <input type="text" name="username" class="form-control form-control-lg" id="username" required style="border-radius: 10px;">
                            </div>
                            <div class="mb-4">
                                <label for="password" class="form-label fw-bold">Password</label>
                                <input type="password" name="password" class="form-control form-control-lg" id="password" required style="border-radius: 10px;">
                            </div>
                            <button type="submit" class="btn btn-primary btn-lg w-100">Login</button>
                        </form>
                        {% if error %}
                        <div class="alert alert-danger mt-3" style="border-radius: 10px;">{{ error }}</div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Authority Dashboard - Exam Surveillance</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            min-height: 100vh;
            animation: gradientShift 15s ease infinite, float 6s ease-in-out infinite;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        @keyframes gradientShift {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        @keyframes float {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-10px); }
        }
        .navbar {
            background: linear-gradient(45deg, #007bff, #0056b3) !important;
            animation: navbarGlow 3s ease-in-out infinite alternate;
        }
        @keyframes navbarGlow {
            from { box-shadow: 0 0 20px rgba(0,123,255,0.5); }
            to { box-shadow: 0 0 30px rgba(0,123,255,0.8); }
        }
        .card {
            border: none;
            border-radius: 20px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.2);
            transition: all 0.4s ease;
            backdrop-filter: blur(15px);
            background: rgba(255, 255, 255, 0.9);
        }
        .card:hover {
            transform: translateY(-10px) scale(1.02);
            box-shadow: 0 20px 40px rgba(0,0,0,0.4);
        }
        .btn {
            border-radius: 30px;
            font-weight: bold;
            animation: btnPulse 2s infinite;
        }
        .btn-success {
            background: linear-gradient(45deg, #28a745, #20c997);
            border: none;
        }
        .btn-success:hover {
            transform: scale(1.05);
            box-shadow: 0 10px 20px rgba(40,167,69,0.4);
        }
        .btn-danger {
            background: linear-gradient(45deg, #dc3545, #c82333);
            border: none;
        }
        .btn-danger:hover {
            transform: scale(1.05);
            box-shadow: 0 10px 20px rgba(220,53,69,0.4);
        }
        @keyframes btnPulse {
            0% { box-shadow: 0 0 0 0 rgba(0,0,0,0.2); }
            50% { box-shadow: 0 0 10px 5px rgba(0,0,0,0.1); }
            100% { box-shadow: 0 0 0 0 rgba(0,0,0,0.2); }
        }
    </style>
</head>
<body class="bg-light">
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container">
            <a class="navbar-brand" href="#"><i class="fas fa-shield-alt"></i> Exam Surveillance</a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/dashboard"><i class="fas fa-tachometer-alt"></i> Dashboard</a>
                <a class="nav-link" href="/live"><i class="fas fa-video"></i> Live Camera</a>
                <a class="nav-link" href="/logout"><i class="fas fa-sign-out-alt"></i> Logout</a>
            </div>
        </div>
    </nav>
    <div class="container mt-5">
        <div class="row">
            <div class="col-md-12">
                <div class="card shadow-lg">
                    <div class="card-header bg-primary text-white text-center">
                        <h2 class="mb-0"><i class="fas fa-user-shield"></i> Authority Dashboard</h2>
                    </div>
                    <div class="card-body p-4">
                        <div class="row">
                            <div class="col-md-6 mb-3">
                                <a href="/records" class="btn btn-success btn-lg w-100 py-3">
                                    <i class="fas fa-list"></i> View Malpractice Records
                                </a>
                            </div>
                            <div class="col-md-6 mb-3">
                                <button class="btn btn-danger btn-lg w-100 py-3" data-bs-toggle="modal" data-bs-target="#deleteModal">
                                    <i class="fas fa-trash"></i> Delete All Records
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Delete Confirmation Modal -->
    <div class="modal fade" id="deleteModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content" style="border-radius: 15px;">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="fas fa-exclamation-triangle"></i> Confirm Deletion</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    Are you sure you want to delete ALL malpractice records? This action cannot be undone.
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <form method="post" action="/delete_all" style="display:inline;">
                        <button type="submit" class="btn btn-danger">Delete All</button>
                    </form>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

def get_records_from_db():
    """Fetch all violation records from SQLite DB."""
    conn = sqlite3.connect('violations.db')
    c = conn.cursor()
    # Ensure table exists
    c.execute('''CREATE TABLE IF NOT EXISTS violations (
        id INTEGER PRIMARY KEY,
        student_id TEXT,
        exam_name TEXT,
        violation TEXT,
        time TEXT,
        warning_count INTEGER,
        screenshot TEXT
    )''')
    c.execute("SELECT id, student_id, exam_name, violation, time, warning_count, screenshot FROM violations ORDER BY time DESC")
    rows = c.fetchall()
    conn.close()
    records = []
    for row in rows:
        records.append({
            'id': row[0],
            'student_id': row[1],
            'exam_name': row[2],
            'violation': row[3],
            'time': row[4],
            'warning_count': row[5],
            'screenshot': row[6] or ''
        })
    return records

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return render_template_string(LOGIN_HTML)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'Authority1' and password == 'authority1@examsurveillance':
            session['user'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template_string(LOGIN_HTML, error='Invalid credentials')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('index'))
    records = get_records_from_db()
    return render_template_string(DASHBOARD_HTML, records=records)

@app.route('/screenshots/<path:filename>')
def serve_screenshot(filename):
    screenshots_dir = os.path.join(os.getcwd(), 'screenshots')
    if not os.path.exists(screenshots_dir):
        return ('', 404)
    return send_from_directory(screenshots_dir, filename)

@app.route('/delete/<int:record_id>', methods=['POST'])
def delete_record(record_id):
    if 'user' not in session:
        return redirect(url_for('index'))
    conn = sqlite3.connect('violations.db')
    c = conn.cursor()
    c.execute("DELETE FROM violations WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/delete_all', methods=['POST'])
def delete_all_records():
    if 'user' not in session:
        return redirect(url_for('index'))
    conn = sqlite3.connect('violations.db')
    c = conn.cursor()
    c.execute("DELETE FROM violations")
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/records')
def records():
    if 'user' not in session:
        return redirect(url_for('index'))
    conn = sqlite3.connect('violations.db')
    c = conn.cursor()
    c.execute("SELECT student_id, COUNT(*) as count FROM violations GROUP BY student_id ORDER BY count DESC")
    rows = c.fetchall()
    conn.close()
    students = [{'id': row[0], 'count': row[1]} for row in rows]
    return render_template_string(RECORDS_HTML, students=students)

RECORDS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Malpractice Records - Exam Surveillance</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            animation: gradientShift 15s ease infinite;
        }
        @keyframes gradientShift {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        .navbar {
            background: linear-gradient(45deg, #007bff, #0056b3) !important;
        }
        .card {
            border: none;
            border-radius: 20px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.2);
            transition: all 0.4s ease;
            backdrop-filter: blur(15px);
            background: rgba(255, 255, 255, 0.9);
        }
        .card:hover {
            transform: translateY(-10px) scale(1.02);
            box-shadow: 0 20px 40px rgba(0,0,0,0.4);
        }
        .btn {
            border-radius: 25px;
            font-weight: bold;
        }
        h2 {
            color: white;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        }
    </style>
</head>
<body class="bg-light">
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container">
            <a class="navbar-brand" href="#"><i class="fas fa-shield-alt"></i> Exam Surveillance</a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/dashboard"><i class="fas fa-tachometer-alt"></i> Dashboard</a>
                <a class="nav-link" href="/live"><i class="fas fa-video"></i> Live Camera</a>
                <a class="nav-link" href="/logout"><i class="fas fa-sign-out-alt"></i> Logout</a>
            </div>
        </div>
    </nav>
    <div class="container mt-4">
        <h2 class="mb-4"><i class="fas fa-users"></i> Student Malpractice Records</h2>
        <div class="row">
            {% for student in students %}
            <div class="col-md-4 mb-3">
                <div class="card shadow">
                    <div class="card-body text-center">
                        <h5 class="card-title"><i class="fas fa-user"></i> Student ID: {{ student.id }}</h5>
                        <p class="card-text">Total Violations: <span class="badge bg-danger">{{ student.count }}</span></p>
                        <a href="/student/{{ student.id }}" class="btn btn-primary"><i class="fas fa-eye"></i> View Details</a>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

@app.route('/student/<student_id>')
def student_records(student_id):
    if 'user' not in session:
        return redirect(url_for('index'))
    conn = sqlite3.connect('violations.db')
    c = conn.cursor()
    c.execute("SELECT id, exam_name, violation, time, warning_count, screenshot FROM violations WHERE student_id = ? ORDER BY time DESC", (student_id,))
    rows = c.fetchall()
    conn.close()
    records = []
    for row in rows:
        records.append({
            'id': row[0],
            'exam_name': row[1],
            'violation': row[2],
            'time': row[3],
            'warning_count': row[4],
            'screenshot': row[5] or ''
        })
    return render_template_string(STUDENT_HTML, student_id=student_id, records=records)

STUDENT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Student Records - Exam Surveillance</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            min-height: 100vh;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            animation: gradientShift 15s ease infinite;
        }
        @keyframes gradientShift {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        .navbar {
            background: linear-gradient(45deg, #007bff, #0056b3) !important;
        }
        .table {
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            backdrop-filter: blur(10px);
            background: rgba(255, 255, 255, 0.9);
        }
        .btn {
            border-radius: 25px;
            font-weight: bold;
        }
        h2 {
            color: white;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        }
        .table-hover tbody tr:hover {
            background-color: rgba(0,0,0,0.05);
            transform: scale(1.01);
            transition: all 0.2s;
        }
    </style>
</head>
<body class="bg-light">
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container">
            <a class="navbar-brand" href="#"><i class="fas fa-shield-alt"></i> Exam Surveillance</a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/dashboard"><i class="fas fa-tachometer-alt"></i> Dashboard</a>
                <a class="nav-link" href="/records"><i class="fas fa-list"></i> Records</a>
                <a class="nav-link" href="/live"><i class="fas fa-video"></i> Live Camera</a>
                <a class="nav-link" href="/logout"><i class="fas fa-sign-out-alt"></i> Logout</a>
            </div>
        </div>
    </nav>
    <div class="container mt-4">
        <h2 class="mb-4"><i class="fas fa-user"></i> Records for Student: {{ student_id }}</h2>
        <div class="table-responsive">
            <table class="table table-striped table-hover">
                <thead class="table-dark">
                    <tr>
                        <th>Exam</th>
                        <th>Violation</th>
                        <th>Time</th>
                        <th>Warning Count</th>
                        <th>Screenshot</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for record in records %}
                    <tr>
                        <td>{{ record.exam_name }}</td>
                        <td>{{ record.violation }}</td>
                        <td>{{ record.time }}</td>
                        <td>{{ record.warning_count }}</td>
                        <td>{% if record.screenshot %}<a href="/screenshots/{{ record.screenshot }}" class="btn btn-sm btn-info" target="_blank"><i class="fas fa-image"></i> View</a>{% else %}No Screenshot{% endif %}</td>
                        <td>
                            <form method="post" action="/delete/{{ record.id }}" style="display:inline;">
                                <button type="submit" class="btn btn-sm btn-danger" onclick="return confirm('Delete this record?')"><i class="fas fa-trash"></i> Delete</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        <a href="/records" class="btn btn-secondary"><i class="fas fa-arrow-left"></i> Back to Students</a>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

@app.route('/live')
def live():
    if 'user' not in session:
        return redirect(url_for('index'))
    return render_template_string(LIVE_HTML)

LIVE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Live Camera - Exam Surveillance</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
            min-height: 100vh;
            animation: gradientShift 15s ease infinite, wave 8s ease-in-out infinite;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        @keyframes gradientShift {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        @keyframes wave {
            0%, 100% { transform: translateX(0px); }
            50% { transform: translateX(10px); }
        }
        .navbar {
            background: linear-gradient(45deg, #007bff, #0056b3) !important;
            animation: navbarGlow 3s ease-in-out infinite alternate;
        }
        @keyframes navbarGlow {
            from { box-shadow: 0 0 20px rgba(0,123,255,0.5); }
            to { box-shadow: 0 0 30px rgba(0,123,255,0.8); }
        }
        .card {
            border: none;
            border-radius: 20px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.2);
            backdrop-filter: blur(15px);
            background: rgba(255, 255, 255, 0.9);
            transition: all 0.4s ease;
        }
        .card:hover {
            transform: translateY(-10px) scale(1.02);
            box-shadow: 0 20px 40px rgba(0,0,0,0.4);
        }
        .btn {
            border-radius: 30px;
            font-weight: bold;
            animation: btnPulse 2s infinite;
        }
        .btn-success {
            background: linear-gradient(45deg, #28a745, #20c997);
            border: none;
        }
        .btn-success:hover {
            transform: scale(1.05);
            box-shadow: 0 10px 20px rgba(40,167,69,0.4);
        }
        .btn-danger {
            background: linear-gradient(45deg, #dc3545, #c82333);
            border: none;
        }
        .btn-danger:hover {
            transform: scale(1.05);
            box-shadow: 0 10px 20px rgba(220,53,69,0.4);
        }
        @keyframes btnPulse {
            0% { box-shadow: 0 0 0 0 rgba(0,0,0,0.2); }
            50% { box-shadow: 0 0 10px 5px rgba(0,0,0,0.1); }
            100% { box-shadow: 0 0 0 0 rgba(0,0,0,0.2); }
        }
        .img-fluid {
            border-radius: 15px;
            transition: transform 0.3s;
        }
        .img-fluid:hover {
            transform: scale(1.05);
        }
    </style>
</head>
<body class="bg-light">
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container">
            <a class="navbar-brand" href="#"><i class="fas fa-shield-alt"></i> Exam Surveillance</a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/dashboard"><i class="fas fa-tachometer-alt"></i> Dashboard</a>
                <a class="nav-link" href="/live"><i class="fas fa-video"></i> Live Camera</a>
                <a class="nav-link" href="/logout"><i class="fas fa-sign-out-alt"></i> Logout</a>
            </div>
        </div>
    </nav>
    <div class="container mt-4">
        <div class="row">
            <div class="col-md-8">
                <div class="card shadow-lg">
                    <div class="card-header bg-success text-white text-center">
                        <h2 class="mb-0"><i class="fas fa-camera"></i> Live Camera Feed</h2>
                    </div>
                    <div class="card-body text-center p-4">
                        <img src="/video_feed" class="img-fluid border rounded shadow" alt="Live Feed" style="max-height: 500px;">
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card shadow-lg mb-3">
                    <div class="card-header bg-info text-white text-center">
                        <h5 class="mb-0"><i class="fas fa-cogs"></i> Controls</h5>
                    </div>
                    <div class="card-body p-4">
                        <button id="startBtn" class="btn btn-success btn-lg w-100 mb-3 py-3">
                            <i class="fas fa-play"></i> Start Detection
                        </button>
                        <button id="stopBtn" class="btn btn-danger btn-lg w-100 py-3">
                            <i class="fas fa-stop"></i> Stop Detection
                        </button>
                    </div>
                </div>
                <div class="card shadow-lg">
                    <div class="card-header bg-warning text-dark text-center">
                        <h6 class="mb-0"><i class="fas fa-info-circle"></i> Status</h6>
                    </div>
                    <div class="card-body p-4">
                        <p id="status" class="mb-0 fw-bold">Detection not started</p>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        document.getElementById('startBtn').addEventListener('click', function() {
            fetch('/start_detection').then(() => {
                document.getElementById('status').innerText = 'Detection running...';
            });
        });
        document.getElementById('stopBtn').addEventListener('click', function() {
            fetch('/stop_detection').then(() => {
                document.getElementById('status').innerText = 'Detection stopped';
                document.querySelector('img').src = '/stopped';
            });
        });

        // Poll for alerts every 2 seconds
        setInterval(function() {
            fetch('/get_alert')
                .then(response => response.text())
                .then(data => {
                    if (data) {
                        alert(data);
                    }
                });
        }, 2000);
    </script>
</body>
</html>
"""

@app.route('/start_detection')
def start_detection():
    global detection_running, detection_thread, warning_count, last_alert_time, phone_start_time, phone_shot_saved, speaking_shot_saved, hand_shot_saved, head_turn_shot_saved, last_mouth_ratio, mouth_motion_counter, speaking_start_time, head_turn_timestamps, last_turn_direction, hand_start_time, hand_near_mouth, popup_message, popup_end_time, exam_start_time, first_frame_seen, exam_ended_announced, detection_stopped, malpractice_pending
    if not detection_running:
        # Reset global variables for new session
        warning_count = 0
        last_alert_time = 0
        phone_start_time = None
        phone_shot_saved = False
        speaking_shot_saved = False
        hand_shot_saved = False
        head_turn_shot_saved = False
        last_mouth_ratio = None
        mouth_motion_counter = 0
        speaking_start_time = None
        head_turn_timestamps = []
        last_turn_direction = None
        hand_start_time = None
        hand_near_mouth = False
        popup_message = ""
        popup_end_time = 0
        exam_start_time = None
        first_frame_seen = False
        exam_ended_announced = False
        detection_stopped = False
        malpractice_pending = False
        detection_running = True
        detection_thread = threading.Thread(target=detection_loop)
        detection_thread.start()
    return '', 204

@app.route('/stop_detection')
def stop_detection():
    global detection_running, frame_queue
    detection_running = False
    if detection_thread:
        detection_thread.join()
    # Clear the queue to prevent stuck frames
    while not frame_queue.empty():
        frame_queue.get()
    return '', 204

def gen_frames():
    global detection_stopped
    while True:
        if detection_stopped:
            img = np.zeros((240, 320, 3), dtype=np.uint8)
            cv2.putText(img, "Detection Stopped", (80, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            ret, buffer = cv2.imencode('.jpg', img)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.1)  # Prevent flooding
        elif not frame_queue.empty():
            frame = frame_queue.get()
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        else:
            time.sleep(0.01)  # Wait for frames

@app.route('/stopped')
def stopped():
    # Create a blank image with "Detection Stopped" text
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(img, "Detection Stopped", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    ret, buffer = cv2.imencode('.jpg', img)
    return Response(buffer.tobytes(), mimetype='image/jpeg')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/get_alert')
def get_alert():
    global alert_message
    msg = alert_message
    alert_message = ""
    return msg

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    try:
        print("Starting Exam Surveillance Web App...")
        app.run(debug=True, port=5000)  # Run on port 5000
    except Exception as e:
        print(f"Error starting app: {e}")
        import traceback
        traceback.print_exc()