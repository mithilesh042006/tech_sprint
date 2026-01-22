"""
Exam Surveillance System - Cloud Dashboard
This version is designed for cloud deployment (Render, Heroku, etc.)
Camera detection features are disabled - use main.py locally for detection.
"""

from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for, send_from_directory, Response
import sqlite3
import os
import time

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')


# Database setup
def get_db_path():
    """Get database path - use current directory (works on all platforms)"""
    # Use current directory for database (works on Render free tier)
    return os.path.join(os.getcwd(), 'violations.db')

def init_db():
    """Initialize the database with required tables."""
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
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
        conn.close()
        print(f"Database initialized at: {db_path}")
    except Exception as e:
        print(f"Warning: Could not initialize database: {e}")

# Initialize database on startup
init_db()


def get_records_from_db():
    """Fetch all violation records from SQLite DB."""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
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

# HTML Templates
LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Authority Login - Exam Surveillance</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .card {
            border: none;
            border-radius: 20px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.3);
            backdrop-filter: blur(15px);
            background: rgba(255, 255, 255, 0.95);
            transition: all 0.4s ease;
        }
        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 20px 40px rgba(0,0,0,0.4);
        }
        .btn-primary {
            background: linear-gradient(45deg, #667eea, #764ba2);
            border: none;
            border-radius: 30px;
            padding: 12px 30px;
            font-weight: 600;
        }
        .btn-primary:hover {
            background: linear-gradient(45deg, #764ba2, #667eea);
            transform: translateY(-2px);
        }
        .form-control {
            border-radius: 15px;
            border: 2px solid #e0e0e0;
            padding: 12px 15px;
        }
        .form-control:focus {
            border-color: #667eea;
            box-shadow: 0 0 15px rgba(102,126,234,0.3);
        }
        .logo-icon {
            font-size: 4rem;
            background: linear-gradient(45deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="row justify-content-center">
            <div class="col-md-5">
                <div class="card shadow-lg">
                    <div class="card-body p-5">
                        <div class="text-center mb-4">
                            <i class="fas fa-shield-alt logo-icon"></i>
                            <h2 class="mt-3 fw-bold">Authority Login</h2>
                            <p class="text-muted">Exam Surveillance Dashboard</p>
                        </div>
                        <form method="post" action="/login">
                            <div class="mb-4">
                                <label for="username" class="form-label fw-bold">Username</label>
                                <input type="text" name="username" class="form-control form-control-lg" id="username" required>
                            </div>
                            <div class="mb-4">
                                <label for="password" class="form-label fw-bold">Password</label>
                                <input type="password" name="password" class="form-control form-control-lg" id="password" required>
                            </div>
                            <button type="submit" class="btn btn-primary btn-lg w-100">
                                <i class="fas fa-sign-in-alt me-2"></i>Login
                            </button>
                        </form>
                        {% if error %}
                        <div class="alert alert-danger mt-3" style="border-radius: 10px;">{{ error }}</div>
                        {% endif %}
                    </div>
                </div>
                <p class="text-center text-white mt-3">
                    <i class="fas fa-cloud me-1"></i> Cloud Dashboard Mode
                </p>
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
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .navbar {
            background: linear-gradient(45deg, #667eea, #764ba2) !important;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }
        .card {
            border: none;
            border-radius: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
        }
        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 40px rgba(0,0,0,0.15);
        }
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .stat-card .stat-number {
            font-size: 3rem;
            font-weight: bold;
        }
        .btn-action {
            border-radius: 30px;
            padding: 15px 30px;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        .btn-action:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
        }
        .cloud-notice {
            background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%);
            border-radius: 15px;
            padding: 15px 20px;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container">
            <a class="navbar-brand fw-bold" href="#">
                <i class="fas fa-shield-alt me-2"></i>Exam Surveillance
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/dashboard"><i class="fas fa-tachometer-alt me-1"></i> Dashboard</a>
                <a class="nav-link" href="/records"><i class="fas fa-list me-1"></i> Records</a>
                <a class="nav-link" href="/logout"><i class="fas fa-sign-out-alt me-1"></i> Logout</a>
            </div>
        </div>
    </nav>
    
    <div class="container mt-4">
        <div class="cloud-notice mb-4">
            <i class="fas fa-cloud me-2"></i>
            <strong>Cloud Dashboard Mode:</strong> This is the cloud-hosted dashboard. 
            Run detection locally using <code>main.py</code> to capture violations.
        </div>
        
        <div class="row mb-4">
            <div class="col-md-4">
                <div class="card stat-card">
                    <div class="card-body text-center p-4">
                        <i class="fas fa-users fa-2x mb-3"></i>
                        <div class="stat-number">{{ total_students }}</div>
                        <div>Total Students</div>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card stat-card">
                    <div class="card-body text-center p-4">
                        <i class="fas fa-exclamation-triangle fa-2x mb-3"></i>
                        <div class="stat-number">{{ total_violations }}</div>
                        <div>Total Violations</div>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card stat-card">
                    <div class="card-body text-center p-4">
                        <i class="fas fa-clipboard-list fa-2x mb-3"></i>
                        <div class="stat-number">{{ total_exams }}</div>
                        <div>Exams Monitored</div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="row">
            <div class="col-md-6 mb-3">
                <div class="card h-100">
                    <div class="card-body p-4 text-center">
                        <i class="fas fa-list fa-3x text-primary mb-3"></i>
                        <h4>View Records</h4>
                        <p class="text-muted">View all student malpractice records</p>
                        <a href="/records" class="btn btn-primary btn-action">
                            <i class="fas fa-eye me-2"></i>View Records
                        </a>
                    </div>
                </div>
            </div>
            <div class="col-md-6 mb-3">
                <div class="card h-100">
                    <div class="card-body p-4 text-center">
                        <i class="fas fa-trash fa-3x text-danger mb-3"></i>
                        <h4>Manage Data</h4>
                        <p class="text-muted">Delete all violation records</p>
                        <button class="btn btn-danger btn-action" data-bs-toggle="modal" data-bs-target="#deleteModal">
                            <i class="fas fa-trash me-2"></i>Delete All
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Delete Modal -->
    <div class="modal fade" id="deleteModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content" style="border-radius: 20px;">
                <div class="modal-header border-0">
                    <h5 class="modal-title"><i class="fas fa-exclamation-triangle text-warning me-2"></i>Confirm Deletion</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    Are you sure you want to delete <strong>ALL</strong> malpractice records? This cannot be undone.
                </div>
                <div class="modal-footer border-0">
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
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .navbar {
            background: linear-gradient(45deg, #667eea, #764ba2) !important;
        }
        .card {
            border: none;
            border-radius: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
        }
        .card:hover {
            transform: translateY(-5px);
        }
        .badge-violation {
            background: linear-gradient(45deg, #ff6b6b, #ee5a5a);
            padding: 8px 15px;
            border-radius: 20px;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container">
            <a class="navbar-brand fw-bold" href="#"><i class="fas fa-shield-alt me-2"></i>Exam Surveillance</a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/dashboard"><i class="fas fa-tachometer-alt me-1"></i> Dashboard</a>
                <a class="nav-link" href="/records"><i class="fas fa-list me-1"></i> Records</a>
                <a class="nav-link" href="/logout"><i class="fas fa-sign-out-alt me-1"></i> Logout</a>
            </div>
        </div>
    </nav>
    <div class="container mt-4">
        <h2 class="mb-4"><i class="fas fa-users me-2"></i>Student Malpractice Records</h2>
        {% if students %}
        <div class="row">
            {% for student in students %}
            <div class="col-md-4 mb-4">
                <div class="card">
                    <div class="card-body text-center p-4">
                        <i class="fas fa-user-circle fa-4x text-primary mb-3"></i>
                        <h5 class="card-title">{{ student.id }}</h5>
                        <span class="badge badge-violation mb-3">{{ student.count }} Violations</span>
                        <br>
                        <a href="/student/{{ student.id }}" class="btn btn-primary mt-2">
                            <i class="fas fa-eye me-1"></i>View Details
                        </a>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="alert alert-info">
            <i class="fas fa-info-circle me-2"></i>No violation records found.
        </div>
        {% endif %}
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

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
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .navbar {
            background: linear-gradient(45deg, #667eea, #764ba2) !important;
        }
        .table {
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            background: white;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container">
            <a class="navbar-brand fw-bold" href="#"><i class="fas fa-shield-alt me-2"></i>Exam Surveillance</a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/dashboard"><i class="fas fa-tachometer-alt me-1"></i> Dashboard</a>
                <a class="nav-link" href="/records"><i class="fas fa-list me-1"></i> Records</a>
                <a class="nav-link" href="/logout"><i class="fas fa-sign-out-alt me-1"></i> Logout</a>
            </div>
        </div>
    </nav>
    <div class="container mt-4">
        <h2 class="mb-4"><i class="fas fa-user me-2"></i>Records for: {{ student_id }}</h2>
        <div class="table-responsive">
            <table class="table table-striped table-hover">
                <thead class="table-dark">
                    <tr>
                        <th>Exam</th>
                        <th>Violation</th>
                        <th>Time</th>
                        <th>Warning #</th>
                        <th>Screenshot</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for record in records %}
                    <tr>
                        <td>{{ record.exam_name }}</td>
                        <td><span class="badge bg-danger">{{ record.violation }}</span></td>
                        <td>{{ record.time }}</td>
                        <td>{{ record.warning_count }}</td>
                        <td>
                            {% if record.screenshot %}
                            <a href="/screenshots/{{ record.screenshot }}" class="btn btn-sm btn-info" target="_blank">
                                <i class="fas fa-image"></i> View
                            </a>
                            {% else %}
                            <span class="text-muted">N/A</span>
                            {% endif %}
                        </td>
                        <td>
                            <form method="post" action="/delete/{{ record.id }}" style="display:inline;">
                                <button type="submit" class="btn btn-sm btn-danger" onclick="return confirm('Delete?')">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        <a href="/records" class="btn btn-secondary mt-3">
            <i class="fas fa-arrow-left me-1"></i>Back to Students
        </a>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# Routes
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
        # In production, use proper password hashing!
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
    
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Get stats
    c.execute("SELECT COUNT(DISTINCT student_id) FROM violations")
    total_students = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM violations")
    total_violations = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(DISTINCT exam_name) FROM violations")
    total_exams = c.fetchone()[0] or 0
    
    conn.close()
    
    return render_template_string(DASHBOARD_HTML, 
                                  total_students=total_students,
                                  total_violations=total_violations,
                                  total_exams=total_exams)

@app.route('/records')
def records():
    if 'user' not in session:
        return redirect(url_for('index'))
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("SELECT student_id, COUNT(*) as count FROM violations GROUP BY student_id ORDER BY count DESC")
    rows = c.fetchall()
    conn.close()
    students = [{'id': row[0], 'count': row[1]} for row in rows]
    return render_template_string(RECORDS_HTML, students=students)

@app.route('/student/<student_id>')
def student_records(student_id):
    if 'user' not in session:
        return redirect(url_for('index'))
    conn = sqlite3.connect(get_db_path())
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

@app.route('/screenshots/<path:filename>')
def serve_screenshot(filename):
    screenshots_dir = os.path.join(os.getcwd(), 'screenshots')
    if os.environ.get('RENDER'):
        screenshots_dir = '/data/screenshots'
    if not os.path.exists(screenshots_dir):
        return ('Screenshot not found', 404)
    return send_from_directory(screenshots_dir, filename)

@app.route('/delete/<int:record_id>', methods=['POST'])
def delete_record(record_id):
    if 'user' not in session:
        return redirect(url_for('index'))
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("DELETE FROM violations WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for('records'))

@app.route('/delete_all', methods=['POST'])
def delete_all_records():
    if 'user' not in session:
        return redirect(url_for('index'))
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("DELETE FROM violations")
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

@app.route('/health')
def health():
    """Health check endpoint for Render"""
    return jsonify({"status": "healthy", "mode": "cloud-dashboard"})

# For local development
if __name__ == '__main__':
    print("Starting Exam Surveillance Cloud Dashboard...")
    print("Note: Camera detection is disabled in cloud mode.")
    print("Run main.py locally for camera-based detection.")
    app.run(debug=True, port=5000)
