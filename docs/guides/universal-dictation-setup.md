# Universal Dictation & Claude Voice Setup (macOS)

This repo provides two complementary voice capabilities that share the same Whisper STT backend:

| | Universal Dictation | Claude Code Voice |
|---|---|---|
| **What it does** | Hold Cmd → speak anywhere → text typed into active window | Full two-way voice conversation with Claude Code |
| **Input (STT)** | Whisper at `localhost:2022` | Whisper at `localhost:2022` |
| **Output (TTS)** | None — dictation only | Kokoro at `localhost:8880` |
| **How** | `voicemode_hotkey.py` daemon | voicemode MCP plugin for Claude Code |

You can set up just dictation, just Claude voice, or both. Whisper is shared between them.

---

## Prerequisites

- macOS (Apple Silicon or Intel)
- [Homebrew](https://brew.sh)
- Python 3.10+

```bash
brew install ffmpeg uv
```

Verify ffmpeg landed at `/opt/homebrew/bin/ffmpeg`:

```bash
which ffmpeg
# /opt/homebrew/bin/ffmpeg
```

---

## Part 1: Clone and install voicemode-swap

```bash
git clone https://github.com/SwapnilDreams100/voicemode-swap ~/voicemode-swap
cd ~/voicemode-swap
uv tool install -e .
voicemode --version
```

---

## Part 2: Whisper STT service (required for both)

### Install

```bash
voicemode service install whisper
```

Downloads the `base` model (~150MB) and builds `whisper-server` with CoreML + Metal for Apple Silicon.

### Start and verify

```bash
voicemode service start whisper
voicemode service status whisper
```

Expected output:

```
✅ Whisper is running locally
   Port: 2022
   Model: ggml-base.bin
   Core ML: ✓ Enabled & Active
   GPU: Metal
```

Test it directly:

```bash
curl http://localhost:2022/health
# {"status":"ok"}
```

### Enable auto-start at login

```bash
voicemode service enable whisper
```

This creates `~/Library/LaunchAgents/com.voicemode.whisper.plist`. Verify `/opt/homebrew/bin` is in the plist PATH (whisper-server calls ffmpeg internally and launchd doesn't inherit your shell PATH):

```bash
grep -A5 PATH ~/Library/LaunchAgents/com.voicemode.whisper.plist
```

If `/opt/homebrew/bin` is missing, open and add it:

```bash
open ~/Library/LaunchAgents/com.voicemode.whisper.plist
```

---

## Part 3: Universal dictation — hotkey daemon

Hold `cmd` for 1 second anywhere (browser, Slack, editor, terminal), speak, release — your words are typed into the active window.

### How it works

`scripts/voicemode_hotkey.py` listens globally for `cmd` hold, records via ffmpeg using a hardcoded mic device (so your headphones stay as system default for calls), sends the WAV to Whisper, then pastes the transcript.

### Install dependencies

```bash
pip install pynput httpx
```

### Configure the input device

The daemon hardcodes a specific avfoundation device so it always uses the built-in mic — your earphones/headphones remain the system default for everything else.

List your devices:

```bash
ffmpeg -f avfoundation -list_devices true -i "" 2>&1 | grep -A20 "AVFoundation audio"
```

Example output:
```
[0] Aggregate Device
[1] JBL Endurance Race 2
[2] MacBook Pro Microphone
[3] ZoomAudioDevice
```

Set `AUDIO_DEVICE_INDEX` near the top of `scripts/voicemode_hotkey.py` to match your built-in mic:

```python
AUDIO_DEVICE_INDEX = "2"  # MacBook Pro Microphone
```

Do **not** change your system default input device — that would affect calls, video meetings, etc.

### Install the script

```bash
mkdir -p ~/.claude/plugins/claude-stt
cp scripts/voicemode_hotkey.py ~/.claude/plugins/claude-stt/voicemode_hotkey.py
```

### Grant Accessibility permission

The daemon needs Accessibility access to inject keystrokes globally.

**System Settings → Privacy & Security → Accessibility** → add your terminal app and enable it.

### Auto-start at login

Use the template from this repo:

```bash
sed "s/YOUR_USERNAME/$USER/g" scripts/launchd/com.voicemode.hotkey.plist \
  > ~/Library/LaunchAgents/com.voicemode.hotkey.plist
```

Then update the python path in the plist to match yours:

```bash
which python3   # e.g. /Users/you/.pyenv/versions/3.11.10/bin/python3
```

Edit `~/Library/LaunchAgents/com.voicemode.hotkey.plist` and set that as the first `<string>` in `ProgramArguments`.

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.voicemode.hotkey.plist
```

### Verify dictation works

Watch the log while you test:

```bash
tail -f ~/.claude/plugins/claude-stt/voicemode_hotkey.log
```

Hold `cmd` for 1 second, speak, release. You should see:

```
🎤 Recording started...
⏹️  Recording stopped, transcribing...
📝 Transcribed: your words here
✅ Text injected.
```

---

## Part 4: Claude Code voice — Kokoro TTS + voicemode MCP plugin

This enables full two-way voice with Claude Code. Claude speaks back using Kokoro TTS; you speak to it using Whisper (same service as Part 2).

### Install Kokoro TTS

```bash
voicemode service install kokoro
voicemode service start kokoro
voicemode service status kokoro
```

Expected:

```
✅ Kokoro is running locally
   Port: 8880
   Version: v0.2.4
```

### Enable Kokoro auto-start at login

```bash
voicemode service enable kokoro
```

This creates `~/Library/LaunchAgents/com.voicemode.kokoro.plist`.

### Install the voicemode MCP plugin for Claude Code

```bash
claude mcp add --scope user voicemode -- uvx --refresh voice-mode
```

Or if running from this local repo:

```bash
claude mcp add --scope user voicemode -- uv run --directory ~/voicemode-swap voicemode
```

### Configure Claude Code permissions

Add to `~/.claude/settings.json` so Claude can use voice tools without prompting every time:

```json
{
  "permissions": {
    "allow": [
      "mcp__voicemode__converse",
      "mcp__voicemode__service"
    ]
  }
}
```

### Verify Claude voice works

In Claude Code, say:

```
converse
```

You'll hear a chime, Claude will greet you, and you can speak back. Kokoro handles Claude's speech; Whisper handles yours.

Check provider discovery to confirm both endpoints are registered:

```bash
voicemode diag registry
```

You should see Kokoro under TTS and Whisper under STT as `✅`.

---

## Full service status check

```bash
voicemode service status whisper    # STT — port 2022
voicemode service status kokoro     # TTS — port 8880
pgrep -la python | grep hotkey      # dictation daemon
tail -5 ~/.claude/plugins/claude-stt/voicemode_hotkey.log
```

---

## Troubleshooting

### "FileNotFoundError: ffmpeg" in hotkey log

The daemon launched without Homebrew in PATH (common with launchd). The script must use the full path `/opt/homebrew/bin/ffmpeg`, not just `ffmpeg`. Check `scripts/voicemode_hotkey.py` line ~75.

### "Audio too short, skipping." every time

ffmpeg crashed silently — almost always the same PATH issue above.

### Whisper returns `{"error":"FFmpeg conversion failed."}`

The whisper-server itself can't find ffmpeg. Check the whisper launchd plist has `/opt/homebrew/bin` in PATH:

```bash
grep -A5 PATH ~/Library/LaunchAgents/com.voicemode.whisper.plist
```

Reload after fixing:

```bash
launchctl unload ~/Library/LaunchAgents/com.voicemode.whisper.plist
launchctl load ~/Library/LaunchAgents/com.voicemode.whisper.plist
```

### Dictation transcribes but nothing is typed

Accessibility permission missing. **System Settings → Privacy & Security → Accessibility** → add your terminal.

### Wrong mic / empty transcriptions

Device indices can shift when you plug/unplug USB or Bluetooth audio. Re-list and update `AUDIO_DEVICE_INDEX`:

```bash
ffmpeg -f avfoundation -list_devices true -i "" 2>&1 | grep -A20 "AVFoundation audio"
```

### Kokoro not speaking / Claude voice silent

```bash
voicemode service status kokoro
curl http://localhost:8880/health
voicemode diag registry
```

If Kokoro is down, restart it:

```bash
voicemode service restart kokoro
```

### Check all logs

```bash
tail -20 ~/.claude/plugins/claude-stt/voicemode_hotkey.log
tail -20 ~/.voicemode/logs/whisper/whisper.err.log
tail -20 ~/.voicemode/logs/kokoro/kokoro.err.log
tail -20 ~/.voicemode/logs/events/voicemode_events_$(date +%Y-%m-%d).jsonl
```
