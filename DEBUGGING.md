# Debugging Guide — Journal Club PDF Download

## Enable Debug Logging

### Local Development
```bash
DEBUG=1 python app.py
```
This sets log level to DEBUG and prints all messages to console.

### Production (Render)
Set environment variable in Render dashboard:
```
DEBUG=1
```
Then check logs via Render's log viewer. Logs are also written to `journal_club.log` on disk.

## Common Issues & Solutions

### 1. "Chrome not installed" Error
**Issue:** PDF download fails with "Chrome not installed"

**Cause:** Playwright's bundled Chromium was not installed during build

**Solution:**
- Check Render build log — should show `python -m playwright install chromium`
- If missing, manually trigger redeploy:
  ```bash
  git commit --allow-empty -m "trigger rebuild"
  git push
  ```

### 2. "PDF not captured" Error
**Issue:** Browser starts but PDF never gets captured

**Symptoms in logs:**
```
[PDF wait] Waiting 30s...
[PDF wait] Waiting 25s...
[PDF wait] ✗ Timeout after 30s — PDF not captured
```

**Possible causes:**
- Authentication failed (HUJI login issue)
- JavaScript didn't execute (content loading)
- PDF download was blocked
- Response hook never fired

**Debugging:**
1. Enable `DEBUG=1` to see all response hooks
2. Look for `[PDF captured]` or `[PDF response not PDF]` messages
3. Check if `[Download event]` appears
4. Enable headless=False temporarily to see what browser sees:
   ```python
   # In journal_club/browser.py, change:
   headless=True,
   # To:
   headless=False,  # THIS WILL FAIL ON RENDER (no display)
   ```

### 3. Authentication Failures
**Issue:** Gets to article page but can't authenticate

**Check logs for:**
```
[Browser] Launching Playwright bundled Chromium...
[Browser] ✓ Chromium launched successfully
```

Then look for authentication logs (varies by publisher):
- JAMA: Look for form submission logs
- Elsevier: Check for OAuth redirect
- OpenAthens: Check for login form interception

**Solutions:**
- Verify HUJI credentials in `config.yaml`
- Check if HUJI cookies are being sent
- Verify proxy/network access (on Render, may need special config)

### 4. Render Build Failures
**Check build log for:**
```
ERROR: Could not build wheels for playwright
```

**Solution:** Render build needs system dependencies for Chromium
- Playwright should handle this automatically
- If not, add to `build.sh`:
  ```bash
  apt-get update && apt-get install -y libnss3 libxss1 libatk1.0-0
  ```

## Logging Output Interpretation

### Log Levels

| Level | Meaning | When to See |
|-------|---------|-----------|
| **DEBUG** | Detailed info about every step | `DEBUG=1` only |
| **INFO** | Important milestones (PDF captured, saved) | Always |
| **WARNING** | Expected error that was handled | Connection timeouts, fallbacks |
| **ERROR** | Something failed | Auth errors, missing files |

### Example Debug Output

```
2026-04-14 23:14:39 [    INFO] journal_club.app: Journal Club started (debug=True, log_level=DEBUG)
2026-04-14 23:14:40 [   DEBUG] journal_club.browser: [Browser] Profile dir: /tmp/chrome-profile
2026-04-14 23:14:40 [    INFO] journal_club.browser: [Browser] Launching Playwright bundled Chromium...
2026-04-14 23:14:43 [    INFO] journal_club.browser: [Browser] ✓ Chromium launched successfully
2026-04-14 23:14:43 [   DEBUG] journal_club.browser: [Browser] New page created
2026-04-14 23:14:45 [    INFO] journal_club.pdf_capture: [PDF captured] 245,632 bytes from https://example.com/pdf/...
2026-04-14 23:14:45 [    INFO] journal_club.pdf_capture: [PDF save] ✓ Saved downloads/example.pdf (245,632 bytes)
```

## Real-Time Debugging on Render

### View Live Logs
```bash
render logs <service-id>
```

### SSH into Container (if available)
```bash
render ssh <service-id>
# Then check:
ls -la journal_club.log
tail -f journal_club.log
```

### Check Disk Usage
```bash
# On Render container
df -h
# Chromium might use 500MB+
```

## Testing Locally

### Test PDF Capture Directly
```python
from journal_club.download import download_article
from journal_club.config import load_config

cfg = load_config("config.yaml")
try:
    meta, pdf_path = download_article("https://www.nejm.org/doi/10.1056/...", cfg)
    print(f"✓ Success: {pdf_path}")
except Exception as e:
    print(f"✗ Failed: {e}")
```

### Test Browser Launch
```python
from journal_club.browser import launch_browser

with launch_browser("/tmp/test-profile") as (p, browser, context, page):
    page.goto("https://google.com")
    print(page.title())
```

## Performance Notes

- **First PDF download:** Slower (Chromium initializing) — ~8-12s
- **Subsequent downloads:** ~4-6s per PDF
- **Authentication overhead:** +2-3s for HUJI login
- **Render cold start:** First request after deploy may take 30s+

## Getting Help

Include in any issue report:
1. **Log output** (run with `DEBUG=1`)
2. **Article URL** being downloaded
3. **Publisher** (NEJM, Lancet, etc.)
4. **Error message** from logs
5. **Render service logs** (last 100 lines)

Example debug command:
```bash
DEBUG=1 python download.py "https://www.nejm.org/doi/10.1056/NEJMoa2504068" 2>&1 | tee debug-output.txt
```
