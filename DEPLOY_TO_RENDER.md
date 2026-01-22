# Deploying Exam Surveillance to Render

## Quick Start Guide

### Prerequisites
1. A [GitHub account](https://github.com)
2. A [Render account](https://render.com) (free tier works!)
3. Your Gmail App Password (for email alerts)

---

## Step 1: Push to GitHub

If you haven't already, create a GitHub repository:

```bash
# Initialize git (if not already done)
cd e:\tech_sprint\Exam_SurveillanceSystem
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit - Exam Surveillance System"

# Create repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/Exam_SurveillanceSystem.git
git branch -M main
git push -u origin main
```

---

## Step 2: Deploy on Render

### Option A: Using render.yaml (Recommended)

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **New** → **Blueprint**
3. Connect your GitHub repository
4. Render will auto-detect `render.yaml` and configure everything
5. Click **Apply**

### Option B: Manual Setup

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **New** → **Web Service**
3. Connect your GitHub repository
4. Configure:
   - **Name**: `exam-surveillance`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app_cloud:app --bind 0.0.0.0:$PORT`
5. Click **Create Web Service**

---

## Step 3: Set Environment Variables

In Render Dashboard → Your Service → **Environment**:

| Variable | Value | Description |
|----------|-------|-------------|
| `SECRET_KEY` | (auto-generated) | Flask session secret |
| `EMAIL_ADDRESS` | your.email@gmail.com | Your Gmail address |
| `EMAIL_PASSWORD` | xxxx-xxxx-xxxx-xxxx | Gmail App Password |
| `AUTHORITY_EMAIL` | authority@email.com | Receives violation alerts |
| `HIGHER_AUTHORITY_EMAIL` | higher@email.com | Receives malpractice bookings |

### Getting Gmail App Password
1. Enable 2FA on your Google Account
2. Go to https://myaccount.google.com/apppasswords
3. Generate a new App Password for "Mail"
4. Use this 16-character password (not your regular password)

---

## Step 4: Add Persistent Disk (Optional)

For data persistence across deployments:

1. Go to **Disks** in your Render service
2. Add a disk:
   - **Name**: `data`
   - **Mount Path**: `/data`
   - **Size**: 1 GB

---

## Accessing Your App

After deployment completes:
- Your app URL: `https://exam-surveillance.onrender.com`
- Login: `Authority1` / `authority1@examsurveillance`

---

## Local Detection Setup

The cloud dashboard is view-only. For live detection:

1. Install local requirements:
```bash
pip install -r requirements-local.txt
```

2. Run detection locally:
```bash
python main.py
```

This will:
- Use your webcam for monitoring
- Save violations to local `violations.db`
- Send email alerts

To sync with cloud dashboard, you'll need to upload the database or use a cloud database service.

---

## Troubleshooting

### Build Fails
- Check Render logs for specific errors
- Ensure `requirements.txt` has correct packages

### App Crashes
- Memory limit exceeded (free tier = 512MB)
- Check logs: Render Dashboard → Logs

### Database Not Persisting
- Ensure disk is mounted at `/data`
- The app auto-uses `/data/violations.db` when on Render

---

## Files Created for Deployment

| File | Purpose |
|------|---------|
| `render.yaml` | Render deployment configuration |
| `Procfile` | Process file for Gunicorn |
| `requirements.txt` | Cloud dependencies (lightweight) |
| `requirements-local.txt` | Full dependencies for local dev |
| `app_cloud.py` | Cloud-optimized Flask app |
| `.gitignore` | Excludes unnecessary files |

---

## Support

If you encounter issues:
1. Check Render logs
2. Verify environment variables are set
3. Ensure GitHub repo is up to date
