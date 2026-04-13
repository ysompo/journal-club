# Journal Club Deployment Guide

## Quick Start: Deploy to Render.com

### 1. Create a Render account
- Go to https://render.com (free tier available)
- Sign up with GitHub

### 2. Push code to GitHub
```bash
cd "C:\Users\ysomp\OneDrive\Documents\Journal Club"
git remote add origin https://github.com/YOUR-USERNAME/journal-club.git
git push -u origin main
```

### 3. Create a new Web Service on Render
- Dashboard → New → Web Service
- Connect your GitHub repo (`journal-club`)
- Configure:
  - **Name:** `journal-club` (or any name)
  - **Runtime:** Python 3.11+
  - **Build Command:** `pip install -r requirements.txt`
  - **Start Command:** `gunicorn wsgi:app`
  - **Environment Variables:**
    ```
    SCRIPT_NAME=/tools/journal-club
    FLASK_ENV=production
    ```

### 4. Add config.yaml secrets
On Render dashboard, add **Environment Variable**:
```
CONFIG_YAML_B64=(base64-encoded config.yaml)
```

Or create `config.yaml` in repo root with:
```yaml
huji_email: "your-email@huji.ac.il"
huji_password: "your-password"
output_dir: "/tmp/journals"
chrome_profile: ""
chrome_path: ""
resend_api_key: "re_..."
resend_from: "Journal Club <noreply@labor-ai.org>"
email_to_1: "recipient@example.com"
admin_password: "changeme"
```

### 5. Install Gunicorn (for Render)
```bash
pip install gunicorn
pip freeze > requirements.txt
git add requirements.txt
git commit -m "add gunicorn to requirements"
git push
```

### 6. Connect to labor-ai.org
- Render gives you a URL like `journal-club-abc123.onrender.com`
- Go to labor-ai.org DNS settings
- Add reverse proxy rule:
  - Path: `/tools/journal-club`
  - Forward to: `https://journal-club-abc123.onrender.com`

(Or use Vercel's rewrite in `next.config.ts`)

---

## Local Testing Before Deploy

```bash
export SCRIPT_NAME=/tools/journal-club
export FLASK_ENV=production
gunicorn wsgi:app
```

Then visit: `http://localhost:8000/tools/journal-club`

---

## Adding to labor-ai.org (Next.js)

In `next.config.ts`, add rewrite:

```typescript
async rewrites() {
  return {
    beforeFiles: [
      {
        source: '/tools/journal-club/:path*',
        destination: 'https://journal-club-abc123.onrender.com/tools/journal-club/:path*',
      }
    ]
  }
}
```

Replace `journal-club-abc123.onrender.com` with your actual Render URL.

---

## Troubleshooting

- **PDFs not downloading:** Check that Chromium is available on Render (may need `apt-get` buildpack)
- **403 Elsevier errors:** Ensure HUJI creds are correct in config.yaml
- **Email not sending:** Verify `resend_from` is a verified sender in Resend dashboard
- **Logs:** `render.com` → Dashboard → Logs tab

---

## Environment Variables Summary

| Variable | Purpose | Example |
|----------|---------|---------|
| `SCRIPT_NAME` | Reverse proxy path | `/tools/journal-club` |
| `FLASK_ENV` | Production mode | `production` |
| `HUJI_EMAIL` | HUJI login email | `user@huji.ac.il` |
| `HUJI_PASSWORD` | HUJI login password | `password123` |
| `RESEND_API_KEY` | Email service | `re_...` |
| `RESEND_FROM` | Email sender address | `Journal Club <noreply@labor-ai.org>` |
| `ADMIN_PASSWORD` | Admin panel password | `changeme` |

---

## Colleagues: How to Access

1. Go to **labor-ai.org**
2. Click **📚 Journal Club** button in top navigation
3. Log in (if first time: enter HUJI email/password once)
4. Start adding journals!

Everything syncs across devices — add on desktop, check on iPad.
