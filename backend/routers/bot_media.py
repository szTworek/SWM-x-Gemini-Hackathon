import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/bot_media")

# Global dict to hold outbound audio queues for each meeting bot
bot_audio_queues = {}

# Ultra-simple Sandbox HTML served to Recall.ai's headless bot browser
# It connects to the websocket below, receives raw PCM from Gemini, and plays it instantly.
SANDBOX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Voice Agent Sandbox</title>
</head>
<body style="background-color: black; color: white;">
    <h1>Voice Agent Active</h1>
    <p>Meeting ID: {meet_id}</p>
    <script>
        const meetId = "{meet_id}";
        const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = wsProtocol + "//" + window.location.host + "/bot_media/ws/bot-speaker/" + meetId;
        const ws = new WebSocket(wsUrl);

        let audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
        let nextPlayTime = 0;

        ws.binaryType = "arraybuffer";

        ws.onopen = () => console.log("Connected to speaker websocket");
        
        ws.onmessage = async (event) => {
            // Browsers typically require user interaction to play audio,
            // BUT Recall.ai grants automatic audio-play permissions!
            if (audioContext.state === 'suspended') {
                await audioContext.resume();
            }

            // We receive raw 16-bit PCM Mono from Gemini at 24000 Hz
            const pcm16 = new Int16Array(event.data);
            
            // Convert to Float32 for Web Audio API
            const float32 = new Float32Array(pcm16.length);
            for (let i = 0; i < pcm16.length; i++) {
                // Normalize -32768..32767 to -1.0..1.0
                float32[i] = pcm16[i] / 32768.0;
            }

            const audioBuffer = audioContext.createBuffer(1, float32.length, 24000);
            audioBuffer.copyToChannel(float32, 0);

            const source = audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(audioContext.destination);

            let currentTime = audioContext.currentTime;
            
            // Ensure gapless playback by chaining the chunks
            if (currentTime > nextPlayTime) {
                // If we ran out of audio buffer (agent paused), reset the playhead + a tiny buffer
                nextPlayTime = currentTime + 0.1;
            }

            source.start(nextPlayTime);
            nextPlayTime += audioBuffer.duration;
        };

        ws.onclose = () => console.log("WebSocket closed");
        ws.onerror = (e) => console.error("WebSocket Error", e);
    </script>
</body>
</html>
"""

@router.get("/bot_sandbox/{meet_id}")
async def get_sandbox(meet_id: str):
    return HTMLResponse(content=SANDBOX_HTML.replace("{meet_id}", meet_id))

@router.websocket("/ws/bot-speaker/{meet_id}")
async def bot_speaker_websocket(websocket: WebSocket, meet_id: str):
    await websocket.accept()
    print(f"[BOT-MEDIA-WS] Sandbox connected for {meet_id} (Browser ready to play audio!)")

    if meet_id not in bot_audio_queues:
        bot_audio_queues[meet_id] = asyncio.Queue()

    queue = bot_audio_queues[meet_id]

    try:
        while True:
            # Wait for audio chunks arriving from the Gemini Agent responses
            chunk = await queue.get()
            # Send them as raw binary immediately to the webpage
            await websocket.send_bytes(chunk)
    except WebSocketDisconnect:
        print(f"[BOT-MEDIA-WS] Sandbox disconnected for {meet_id}")
    except Exception as e:
        print(f"[BOT-MEDIA-WS] Speaker stream error: {e}")
