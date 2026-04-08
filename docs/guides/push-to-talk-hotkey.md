# Push-to-Talk Hotkey

A standalone daemon that gives you a global push-to-talk hotkey for VoiceMode's Whisper STT — without audio ducking.

## How it works

- **Hold `cmd` for 0.3 seconds** → recording starts (Tink sound)
- **Release `cmd`** → recording stops (Pop sound), audio is transcribed via Whisper and injected into the active window

The hold delay prevents accidental triggers when using normal `cmd+X` shortcuts.

Recording uses `sounddevice` (pure Python) rather than ffmpeg. This is important: when the daemon runs via launchd, a subprocess like ffmpeg does not inherit macOS TCC microphone permission — only the Python process itself does. Using `sounddevice` ensures the mic permission granted to Python applies directly.

Key detection uses a raw `CGEventTap` (via pyobjc) rather than pynput. On macOS, pynput fires duplicate events for modifier keys (e.g. pressing left-cmd generates both `cmd_l` and `cmd` events), causing double transcription. CGEventTap fires exactly once per physical key event.

## Prerequisites

- VoiceMode's Whisper service running on port 2022 (`voicemode service start whisper`)
- Python 3.10+
- Python packages: `sounddevice`, `numpy`, `httpx`, `pyobjc-framework-Quartz`

```bash
pip install sounddevice numpy httpx pyobjc-framework-Quartz
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
        <string>/path/to/python3</string>
        <string>/path/to/voicemode-swap/scripts/voicemode_hotkey.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/Users/YOU/.claude/plugins/claude-stt/voicemode_hotkey.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOU/.claude/plugins/claude-stt/voicemode_hotkey.log</string>
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

## macOS Permissions

Two permissions are required:

**Accessibility** — for global key detection and text injection via AppleScript:

**System Settings → Privacy & Security → Accessibility** → add your terminal app and enable it.

**Microphone** — for audio capture via sounddevice. Run the script once directly from Terminal:

```bash
python3 scripts/voicemode_hotkey.py
```

macOS will prompt for microphone access. Grant it. This permission is tied to the Python binary, so it applies when launchd runs the same Python binary.

> **Important:** Do not grant mic permission only to Terminal.app and expect it to work under launchd — launchd spawns Python directly without Terminal as a parent, so Terminal's TCC grant does not apply.

## Configuration

Edit the constants at the top of `scripts/voicemode_hotkey.py`:

| Variable | Default | Description |
|---|---|---|
| `WHISPER_URL` | `http://localhost:2022/v1/audio/transcriptions` | Whisper STT endpoint |
| `HOLD_DELAY` | `0.3` | Seconds to hold cmd before recording starts |
| `AUDIO_DEVICE_INDEX` | `2` | sounddevice input device index (run `python3 -c "import sounddevice as sd; print(sd.query_devices())"` to list) |
| `SAMPLE_RATE` | `16000` | Recording sample rate in Hz |
| `SOUND_START` | Tink.aiff | Sound played when recording starts |
| `SOUND_END` | Pop.aiff | Sound played when recording stops |

## Logs

Logs are written to `~/.claude/plugins/claude-stt/voicemode_hotkey.log` by default.

```bash
tail -f ~/.claude/plugins/claude-stt/voicemode_hotkey.log
```
