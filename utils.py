import os
import datetime


def log_violation(message, log_file="violations.log"):
    """Append a timestamped violation message to a log file and print it."""
    ts = datetime.datetime.now().isoformat()
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{ts} - {message}\n")
    except Exception:
        # If logging fails, still print to console
        pass
    print(f"[VIOLATION] {ts} - {message}")


def save_screenshot(frame, tag, screenshots_dir="screenshots"):
    """Save a BGR frame to disk with a timestamped filename and return the path."""
    os.makedirs(screenshots_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{tag}_{ts}.png"
    path = os.path.join(screenshots_dir, filename)
    try:
        import cv2
        cv2.imwrite(path, frame)
        print(f"[SCREENSHOT] Saved to {path}")
        return path  # Return path for DB storage
    except Exception as e:
        print(f"Failed to save screenshot: {e}")
        return None


def send_alert(frame, message, alerts_log="alerts.log"):
    """Record and persist an alert: log, save a screenshot, and print."""
    ts = datetime.datetime.now().isoformat()
    try:
        with open(alerts_log, "a", encoding="utf-8") as f:
            f.write(f"{ts} - {message}\n")
    except Exception:
        pass
    print(f"[ALERT] {ts} - {message}")
    # Save a screenshot tagged for alerts
    try:
        save_screenshot(frame, "alert")
    except Exception:
        pass