import asyncio
import cv2
import numpy as np
import sounddevice as sd
import os
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from PIL import Image
import io

from google import genai
from google.genai.types import (
    Blob,
    LiveConnectConfig,
    Tool,
    FunctionDeclaration,
    Schema,
)

# Import tools from tools.py
from tools import do_math, safe_exec, do_web_search, do_extract_plots, do_digitize_plot

# ── Configuration ───────────────────────────────────────────────────────────────

load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = "models/gemini-3.1-flash-live-preview"

SYSTEM_PROMPT = """
You are a High-Precision Data Science Agent. 

CRITICAL PROTOCOL FOR PLOT VERIFICATION:
1. **NEVER ESTIMATE NUMBERS BY EYE**: Your visual stream is low-fidelity. You are PROHIBITED from guessing data points or percentages (e.g., "roughly 3.4%") from the image frame.
2. **PLOT EXTRACTION** If image contains multiple plots you can use "do_extract_plots" to extract images of plots on slide
3. **MANDATORY DIGITIZATION**: If a user asks to check, verify, or analyze a chart/plot, your FIRST action must be calling 'digitize_plot'.
4. **RESEARCH**: Use 'web_search' to find official, current statistics from reputable sources (e.g., GUS, World Bank).
5. **SCIENTIFIC COMPARISON**: Use 'execute_python' to:
    - Load the CSV data obtained from 'digitize_plot'.
    - Use the official data from 'web_search'.
    - Calculate the mathematical delta (variance).
    - Generate a comparison chart showing BOTH datasets.

FAILURE CONDITION: If you write Python code containing "estimated_data = [...]" based on your vision, you have failed the task. You must only use data returned by tools.
""".strip()

# ── Tool Definitions ──────────────────────────────────────────────────────────

TOOLS = [
    Tool(function_declarations=[
        FunctionDeclaration(
            name="web_search",
            description="Fetch facts/news from the internet.",
            parameters=Schema(type="OBJECT", properties={"query": Schema(type="STRING")}, required=["query"]),
        ),
        FunctionDeclaration(
            name="math_solve",
            description="Symbolic math (diff, integrate, solve).",
            parameters=Schema(
                type="OBJECT",
                properties={
                    "expression": Schema(type="STRING"),
                    "operation": Schema(type="STRING", enum=["diff", "integrate", "solve", "simplify", "limit"]),
                },
                required=["expression", "operation"],
            ),
        ),
        FunctionDeclaration(
            name="execute_python",
            description="Run Python code for data analysis and plotting (matplotlib).",
            parameters=Schema(type="OBJECT", properties={"code": Schema(type="STRING")}, required=["code"]),
        ),
        FunctionDeclaration(
            name="extract_plots",
            description="Isolates and saves plots from the image for visual review.",
            parameters=Schema(type="OBJECT", properties={"reason": Schema(type="STRING")}),
        ),
        FunctionDeclaration(
            name="digitize_plot",
            description="Converts a visual chart into raw numbers. Use this when you need to perform calculations or comparisons with the chart data.",
            parameters=Schema(type="OBJECT", properties={"reason": Schema(type="STRING")}),
        ),
    ])
]

# ── Audio/Video Logic ────────────────────────────────────────────────

audio_queue = asyncio.Queue()
loop = None
camera = None
executor = ThreadPoolExecutor(max_workers=1)

def get_camera():
    cap = cv2.VideoCapture(0)
    return cap if cap.isOpened() else None

def capture_frame(as_jpeg=True):
    global camera
    if camera:
        ret, frame = camera.read()
        if ret:
            if as_jpeg:
                _, buf = cv2.imencode(".jpg", frame)
                return buf.tobytes()
            return frame
    return None

def audio_callback(indata, frames, time, status):
    if loop: loop.call_soon_threadsafe(audio_queue.put_nowait, indata.copy())

async def send_audio(session):
    while True:
        chunk = await audio_queue.get()
        await session.send_realtime_input(audio=Blob(data=chunk.tobytes(), mime_type="audio/pcm;rate=16000"))

async def send_video(session):
    while True:
        frame_bytes = capture_frame(as_jpeg=True)
        if frame_bytes:
            await session.send_realtime_input(video=Blob(data=frame_bytes, mime_type="image/jpeg"))
        await asyncio.sleep(0.7) # Approx 1.5 FPS

def play_audio(audio_array):
    audio_48 = np.interp(np.linspace(0, len(audio_array), int(len(audio_array)*2)), 
                         np.arange(len(audio_array)), audio_array).astype(np.int16)
    sd.play(audio_48, samplerate=48000)
    sd.wait()

# ── Tool Dispatcher ───────────────────────────────────────────────────────────

async def dispatch_tool(name: str, args: dict) -> str:
    print(f"🔧 [TOOL CALL] {name} ({args})")
    try:
        if name == "web_search": return await do_web_search(args["query"])
        if name == "math_solve": return do_math(args["expression"], args["operation"])
        if name == "execute_python": return safe_exec(args["code"])
        if name == "digitize_plot":
            raw_frame = capture_frame(as_jpeg=True)
            if raw_frame:
                return do_digitize_plot(raw_frame, GEMINI_API_KEY)
            return "Error: Camera not available."
        if name == "extract_plots":
            raw_frame = capture_frame(as_jpeg=True)
            if raw_frame:
                return do_extract_plots(raw_frame)
            return "Error: Camera not available."
                
        return "Unknown tool."
    except Exception as e:
        return f"Error executing tool: {e}"

async def receive_responses(session):
    audio_buffer = []
    while True:
        async for message in session.receive():
            if message.tool_call:
                responses = []
                for fc in message.tool_call.function_calls:
                    result = await dispatch_tool(fc.name, dict(fc.args))
                    responses.append({"id": fc.id, "name": fc.name, "response": {"result": result}})
                await session.send_tool_response(function_responses=responses)
                continue

            if not message.server_content: continue
            turn = message.server_content.model_turn
            if turn:
                for part in turn.parts:
                    if part.text: print(f"🤖: {part.text}")
                    if part.inline_data:
                        audio_buffer.append(np.frombuffer(part.inline_data.data, dtype=np.int16))

            if message.server_content.turn_complete:
                if audio_buffer:
                    full_audio = np.concatenate(audio_buffer)
                    await loop.run_in_executor(executor, play_audio, full_audio)
                audio_buffer = []

# ── MAIN ──────────────────────────────────────────────────────────────────────

async def main():
    global loop, camera
    loop = asyncio.get_running_loop()
    camera = get_camera()
    if not camera:
        print("❌ Error: No camera found.")
        return
    
    client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1alpha'})
    config = LiveConnectConfig(
        response_modalities=["AUDIO"],
        tools=TOOLS,
        system_instruction=SYSTEM_PROMPT,
    )

    async with client.aio.live.connect(model=MODEL, config=config) as session:
        print("🚀 Agent Online. Ask me to analyze plots or do math!")
        with sd.InputStream(samplerate=16000, channels=1, dtype="int16", callback=audio_callback):
            await asyncio.gather(send_audio(session), send_video(session), receive_responses(session))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if camera: camera.release()