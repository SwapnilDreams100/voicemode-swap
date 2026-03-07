# Push-to-Talk Hotkey

A standalone daemon that gives you a global push-to-talk hotkey for VoiceMode's Whisper STT — without audio ducking.

## How it works

- **Hold `cmd` for 1 second** → recording starts (Tink sound)
- **Release `cmd`** → recording stops (Pop sound), audio is transcribed via Whisper and injected into the active window

The 1-second hold delay prevents accidental triggers when using normal `cmd+X` shortcuts.

Recording uses `ffmpeg` rather than PortAudio/sounddevice, which avoids macOS audio ducking when the daemon is idle.

## Prerequisites

- VoiceMode's Whisper service running on port 2022 (`voicemode service start whisper`)
- Python 3.10+
- ffmpeg (`brew install ffmpeg`)
- Python packages: `pynput`, `httpx`, `scipy`, `numpy`

```bash
pip install pynput httpx scipy numpy
```

## Running manually

```bash
python3 scripts/voicemode_hotkey.py
```

## Auto-start on login (macOS)

Create a LaunchAgent plist at `~/Library/LaunchAgents/com.voicemode.hotkey.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.voicemode.hotkey</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/voicemode-swap/scripts/voicemode_hotkey.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/tmp/voicemode_hotkey.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/voicemode_hotkey.log</string>
</dict>
</plist>
```

Then load it:

```bash
launchctl load ~/Library/LaunchAgents/com.voicemode.hotkey.plist
```

To unload:

```bash
launchctl unload ~/Library/LaunchAgents/com.voicemode.hotkey.plist
```

## macOS Accessibility Permission

macOS requires Accessibility permission for global hotkey detection. Go to:

**System Settings → Privacy & Security → Accessibility**

Add your terminal app and enable it.

## Configuration

Edit the constants at the top of `scripts/voicemode_hotkey.py`:

| Variable | Default | Description |
|---|---|---|
| `WHISPER_URL` | `http://localhost:2022/v1/audio/transcriptions` | Whisper STT endpoint |
| `HOLD_DELAY` | `1.0` | Seconds to hold cmd before recording starts |
| `AUDIO_DEVICE` | `None` | Audio input device (None = system default) |
| `SOUND_START` | Tink.aiff | Sound played when recording starts |
| `SOUND_END` | Pop.aiff | Sound played when recording stops |

## Logs

Logs are written to `~/.claude/plugins/claude-stt/voicemode_hotkey.log` by default.

```bash
tail -f ~/.claude/plugins/claude-stt/voicemode_hotkey.log
```
