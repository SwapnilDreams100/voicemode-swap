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
brew install uv
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

Hold `cmd` anywhere (browser, Slack, editor, terminal), speak, release — your words are typed into the active window.

### How it works

`scripts/voicemode_hotkey.py` listens globally for `cmd` hold using a raw CGEventTap, records via `sounddevice` (pure Python) using a hardcoded mic device index so your headphones stay as system default for calls, sends the WAV to Whisper, then pastes the transcript.

> **Why sounddevice, not ffmpeg?** When launchd spawns the daemon, ffmpeg runs as a subprocess without inheriting macOS TCC microphone permission. sounddevice records directly in Python, so the mic permission granted to the Python binary applies. Using ffmpeg here results in silent recordings.

> **Why CGEventTap, not pynput?** On macOS, pynput fires duplicate events for modifier keys (pressing left-cmd generates both `Key.cmd_l` and `Key.cmd`), causing double transcription. CGEventTap fires exactly once per physical key event.

### Install dependencies

```bash
pip install sounddevice numpy httpx pyobjc-framework-Quartz
```

### Configure the input device

The daemon hardcodes a specific sounddevice input index so it always uses the built-in mic — your earphones/headphones remain the system default for everything else.

List your devices:

```python
python3 -c "import sounddevice as sd; [print(i, d['name']) for i, d in enumerate(sd.query_devices()) if d['max_input_channels'] > 0]"
```

Example output:
```
0 JBL Endurance Race 2
2 MacBook Pro Microphone
4 ZoomAudioDevice
```

Set `AUDIO_DEVICE_INDEX` near the top of `scripts/voicemode_hotkey.py` to match your built-in mic:

```python
AUDIO_DEVICE_INDEX = 2  # MacBook Pro Microphone
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

Hold `cmd`, speak, release. You should see:

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

### Blank audio / `[BLANK_AUDIO]` every time

The most common cause when running via launchd: the Python process does not have microphone TCC permission.

Run the script **directly from Terminal** once to trigger the macOS mic permission prompt:

```bash
python3 ~/.claude/plugins/claude-stt/voicemode_hotkey.py
```

Grant access when prompted. Then confirm it appears in **System Settings → Privacy & Security → Microphone**. After granting, restart the daemon via launchd.

> Do not rely on Terminal.app's mic permission — launchd spawns Python directly, so only the Python binary's own TCC grant applies.

### "Audio too short, skipping." every time

The recording is ending before enough audio is captured. Try holding `cmd` longer before speaking, or lower `HOLD_DELAY` in the script.

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

```python
python3 -c "import sounddevice as sd; [print(i, d['name']) for i, d in enumerate(sd.query_devices()) if d['max_input_channels'] > 0]"
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
