# Universal Dictation Setup (macOS)

A guide to setting up voicemode-swap as a system-wide dictation tool on macOS. Hold `cmd` for 1 second anywhere — terminal, browser, editor, Slack — speak, release, and your words are typed into the active window.

This combines two components:

- **Whisper service** — local speech-to-text running at `localhost:2022`
- **Hotkey daemon** (`voicemode_hotkey.py`) — listens for `cmd` hold, records via ffmpeg, transcribes via Whisper, injects text

## Prerequisites

- macOS (Apple Silicon or Intel)
- [Homebrew](https://brew.sh)
- Python 3.10+

## Step 1: Install system dependencies

```bash
brew install ffmpeg uv
```

Verify ffmpeg is at `/opt/homebrew/bin/ffmpeg`:

```bash
which ffmpeg
# /opt/homebrew/bin/ffmpeg
```

## Step 2: Clone and install voicemode-swap

```bash
git clone https://github.com/mbailey/voicemode /Users/your-name/voicemode-swap
cd voicemode-swap
uv tool install -e .
```

Verify:

```bash
voicemode --version
```

## Step 3: Install the Whisper service

```bash
voicemode service install whisper
```

This downloads the `base` model (~150MB) and builds `whisper-server` with CoreML + Metal support for Apple Silicon.

Start it and confirm it's healthy:

```bash
voicemode service start whisper
voicemode service status whisper
```

You should see:

```
✅ Whisper is running locally
   Port: 2022
   Model: ggml-base.bin
   Core ML: ✓ Enabled & Active
   GPU: Metal
```

## Step 4: Enable Whisper to auto-start at login

```bash
voicemode service enable whisper
```

This creates a launchd agent at `~/Library/LaunchAgents/com.voicemode.whisper.plist`.

**Important:** The plist must include `/opt/homebrew/bin` in the PATH so that `whisper-server` can find `ffmpeg` when it runs as a background service (it won't inherit your shell's PATH). Verify it's there:

```bash
grep -A5 "PATH" ~/Library/LaunchAgents/com.voicemode.whisper.plist
```

You should see `/opt/homebrew/bin` in the PATH string. If not, edit it in:

```bash
open ~/Library/LaunchAgents/com.voicemode.whisper.plist
```

## Step 5: Set up the hotkey daemon

The daemon lives at `scripts/voicemode_hotkey.py`. Install its Python dependencies:

```bash
pip install pynput httpx
```

**Critical:** The script calls `ffmpeg` by full path (`/opt/homebrew/bin/ffmpeg`). If you're starting fresh from this repo, verify line ~73 in `scripts/voicemode_hotkey.py` uses the full path:

```python
"/opt/homebrew/bin/ffmpeg", "-y",
```

Not just `"ffmpeg"` — this causes a `FileNotFoundError` when the daemon runs outside a login shell (e.g. launched at startup via launchd).

Copy the script to a permanent location (or leave it in the repo):

```bash
mkdir -p ~/.claude/plugins/claude-stt
cp scripts/voicemode_hotkey.py ~/.claude/plugins/claude-stt/voicemode_hotkey.py
```

## Step 6: Grant Accessibility permission

The daemon needs macOS Accessibility access to inject keystrokes globally.

Go to: **System Settings → Privacy & Security → Accessibility**

Add your terminal app (Terminal, iTerm2, Warp, etc.) and enable it.

## Step 7: Auto-start the hotkey daemon at login

Create a launchd plist:

```bash
cat > ~/Library/LaunchAgents/com.voicemode.hotkey.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voicemode.hotkey</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/YOUR_USERNAME/.claude/plugins/claude-stt/voicemode_hotkey.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/.claude/plugins/claude-stt/voicemode_hotkey.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/.claude/plugins/claude-stt/voicemode_hotkey.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF
```

Replace `YOUR_USERNAME` with your actual username (`echo $USER`).

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.voicemode.hotkey.plist
```

## Step 8: Pin the input device

The daemon uses ffmpeg's avfoundation to record. By default it would use whatever your system default input is — which macOS often resets to a Bluetooth headset after a reboot, breaking dictation while leaving your calls/music unaffected.

The fix is to hardcode a specific device in the script so the daemon always uses the built-in mic, independent of your system default. Your earphones/headphones remain the default for everything else.

First, list your avfoundation audio devices:

```bash
ffmpeg -f avfoundation -list_devices true -i "" 2>&1 | grep -A20 "AVFoundation audio"
```

Find your built-in mic (e.g. `[2] MacBook Pro Microphone`) and set `AUDIO_DEVICE_INDEX` near the top of `scripts/voicemode_hotkey.py`:

```python
AUDIO_DEVICE_INDEX = "2"  # MacBook Pro Microphone
```

Do **not** change your system default input — that would affect calls, video, etc.

## Verify everything works

```bash
# Whisper healthy?
curl http://localhost:2022/health
# {"status":"ok"}

# Daemon running?
pgrep -la python | grep voicemode_hotkey

# Watch the daemon log live
tail -f ~/.claude/plugins/claude-stt/voicemode_hotkey.log
```

Then hold `cmd` for 1 second, speak, release. You should see in the log:

```
🎤 Recording started...
⏹️  Recording stopped, transcribing...
📝 Transcribed: your words here
✅ Text injected.
```

## Troubleshooting

### "FileNotFoundError: ffmpeg" in the log

The daemon can't find `ffmpeg` because it's running without Homebrew in PATH.

Fix: make sure `scripts/voicemode_hotkey.py` uses the full path `/opt/homebrew/bin/ffmpeg` (not just `ffmpeg`), and that the launchd plist has `/opt/homebrew/bin` in its `EnvironmentVariables > PATH`.

### "Audio too short, skipping." every time

ffmpeg failed silently (likely the same PATH issue above — it crashed before writing any audio).

### Whisper returns `{"error":"FFmpeg conversion failed."}`

The whisper-server process can't find ffmpeg. Check the plist PATH includes `/opt/homebrew/bin`:

```bash
grep -A5 PATH ~/Library/LaunchAgents/com.voicemode.whisper.plist
```

Restart the service after fixing:

```bash
launchctl unload ~/Library/LaunchAgents/com.voicemode.whisper.plist
launchctl load ~/Library/LaunchAgents/com.voicemode.whisper.plist
```

### Text is transcribed but nothing is typed

Accessibility permission is missing. Go to **System Settings → Privacy & Security → Accessibility** and add your terminal.

### Wrong microphone / no audio captured

If the daemon records but transcription returns empty or gibberish, it may be reading from the wrong device. Check `AUDIO_DEVICE_INDEX` in `voicemode_hotkey.py` — run the device list command to confirm the index is still correct:

```bash
ffmpeg -f avfoundation -list_devices true -i "" 2>&1 | grep -A20 "AVFoundation audio"
```

Device indices can shift when you plug/unplug USB audio devices. Update `AUDIO_DEVICE_INDEX` if needed and restart the daemon.

### Check service status at any time

```bash
voicemode service status whisper
voicemode service status kokoro    # if using local TTS
pgrep -la python | grep hotkey
tail -20 ~/.claude/plugins/claude-stt/voicemode_hotkey.log
```
