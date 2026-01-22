# Configuration for Exam Surveillance

# seconds to wait before flagging 'no face visible'
NO_FACE_TIME = 5

# pixel threshold to consider head movement (center x difference)
HEAD_MOVE_THRESHOLD = 25

# how many head-move events are allowed before flagging
MAX_HEAD_MOVES = 5

# New thresholds for suspicious head-turn detection 
# Pixels of sudden horizontal movement considered a sudden turn
SUDDEN_MOVE_PIXELS = 30
# Time window (seconds) within which a sudden move is considered suspicious
MOVE_TIME_WINDOW = 0.2
# If the face stays looking away beyond this fraction of frame width for this many seconds,
# count as sustained look-away (suspicious)
SUSTAINED_AWAY_TIME = 3.0
# Fraction of frame width used to consider 'looking away' left/right zone
AWAY_ZONE_FRAC = 0.25

# How long to show the on-screen warning popup (seconds)
WARNING_POPUP_DURATION = 4.0

# How many warnings to give before escalation
MAX_WARNINGS = 3

# Writing detection thresholds (vertical head movements)
WRITING_MOVE_PIXELS = 50
WRITING_TIME_WINDOW = 0.8

# Event-based alerting: if this many suspicious events occur within ALERT_EVENT_WINDOW,
# send an immediate alert (escalation)
WRITE_EVENT_COUNT_THRESHOLD = 5
ALERT_EVENT_WINDOW = 30.0
ALERT_POPUP_DURATION = 8.0
ALERT_COOLDOWN = 30.0
MAX_ALERTS = 2

# friendly exam name shown on the overlay
EXAM_NAME = "Sample Exam"

# student identifier shown on the overlay
STUDENT_ID = "student_123" # Example: 1 hour
EXAM_DURATION_MINUTES = 5   # change as needed

# Additional config for web app
SPEAKING_STARTUP_SKIP_FRAMES = 10
MOUTH_ROI_DOWNSCALE = 2
MOUTH_MOTION_THRESHOLD = 50
SPEAKING_FRAME_THRESHOLD = 5
EVENT_MIN_SEPARATION = 2.0
HEAD_TURN_FREQ_WINDOW = 5.0
HEAD_TURN_FREQ_THRESHOLD = 3
SUDDEN_MOVE_VERT_PIXELS = 20
COPYING_WINDOW = 10.0
COPYING_WRITE_COUNT_THRESHOLD = 3
LOOKAWAY_WRITE_MAX_DELAY = 2.0
FACE_MISS_CLEAR_TIME = 5.0
SPEAKING_ALERT_COOLDOWN = 5.0
WARNING_COOLDOWN = 5.0
EXAM_DURATION_SECONDS = EXAM_DURATION_MINUTES * 60

# Email configuration for Gmail alerts
# IMPORTANT: Replace with your real Gmail details
# 1. Enable 2FA on your Gmail account
# 2. Generate an App Password: https://myaccount.google.com/apppasswords
# 3. Use the App Password below (NOT your regular password)
EMAIL_ADDRESS = "yourgmail@gmail.com"  # Your Gmail address
EMAIL_PASSWORD = "abcd-efgh-ijkl-mnop"  # 16-character App Password
AUTHORITY_EMAIL = "authority@gmail.com"  # Email to receive alerts
HIGHER_AUTHORITY_EMAIL = "higherauthority@gmail.com"  # Higher authority email for malpractice booking
