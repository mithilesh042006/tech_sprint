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
