import asyncio
import cv2
import numpy as np
import sounddevice as sd
import os
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

from google import genai
from google.genai.types import (
    Blob,
    LiveConnectConfig,
    Tool,
    FunctionDeclaration,
    Schema,
)

# Importing tools from tools.py
from tools import do_math, safe_exec, do_web_search

# ── Configuration ───────────────────────────────────────────────────────────────

load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# Using the latest model supporting Live and Multimodal Tools
MODEL = "models/gemini-3.1-flash-live-preview"

INPUT_DEVICE  = None # Default mic
OUTPUT_DEVICE = None # Default speakers

SYSTEM_PROMPT = """
You are an Autonomous Analytical Agent. Your task is to solve user problems using the available tools.

REASONING PROCESS:
1. If the user asks for data you don't know -> use `web_search`.
2. You will receive raw text from the search engine. Your task is to ANALYZE it.
3. If there are numbers and data in the text -> use `execute_python` to clean them (e.g., using Regex) and prepare for analysis.
4. ALWAYS consider: "Is this data worth showing on a chart?". If yes, write Python code in `execute_python` that uses matplotlib and plt.show().
5. If the user shows you something on the camera (e.g., a chart in a newspaper) -> use `analyze_screen` to focus your attention on visual details.

RULES:
- Be proactive. If you see an opportunity to create a chart or perform calculations – do it without being asked.
- Respond naturally in English.
- Inform the user about what you are doing (e.g., "I'm fetching the data and preparing a visualization...").
""".strip()

# ── Tool Definitions for Gemini ──────────────────────────────────────

TOOLS = [
    Tool(function_declarations=[
        FunctionDeclaration(
            name="web_search",
            description="Fetches raw text data from the internet. Use this when you need facts, numbers, or current news.",
            parameters=Schema(
                type="OBJECT",
                properties={
                    "query": Schema(type="STRING", description="Search engine query"),
                },
                required=["query"],
            ),
        ),
        FunctionDeclaration(
            name="math_solve",
            description="Advanced symbolic calculations (derivatives, integrals, equations).",
            parameters=Schema(
                type="OBJECT",
                properties={
                    "expression": Schema(type="STRING", description="Expression e.g., 'x**2 + sin(x)'"),
                    "operation": Schema(
                        type="STRING",
                        enum=["diff", "integrate", "solve", "simplify", "limit"],
                        description="Type of mathematical operation",
                    ),
                },
                required=["expression", "operation"],
            ),
        ),
        FunctionDeclaration(
            name="execute_python",
            description="Execute Python code. Use this for: extracting data from text (regex), statistics, and generating CHARTS (matplotlib).",
            parameters=Schema(
                type="OBJECT",
                properties={
                    "code": Schema(type="STRING", description="Python code to run in the sandbox"),
                },
                required=["code"],
            ),
        ),
        FunctionDeclaration(
            name="analyze_screen",
            description="Focuses the agent's 'eyes' on the camera feed. Use when there is a chart, table, or text to analyze in front of the camera.",
            parameters=Schema(
                type="OBJECT",
                properties={
                    "focus": Schema(type="STRING", description="What to focus on, e.g., 'price table'"),
                },
                required=["focus"],
            ),
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

def capture_frame():
    global camera
    if camera:
        ret, frame = camera.read()
        if ret:
            _, buf = cv2.imencode(".jpg", frame)
            return buf.tobytes()
    return None

def audio_callback(indata, frames, time, status):
    if loop: loop.call_soon_threadsafe(audio_queue.put_nowait, indata.copy())

async def send_audio(session):
    while True:
        chunk = await audio_queue.get()
        await session.send_realtime_input(audio=Blob(data=chunk.tobytes(), mime_type="audio/pcm;rate=16000"))

async def send_video(session):
    while True:
        frame = capture_frame()
        if frame:
            await session.send_realtime_input(video=Blob(data=frame, mime_type="image/jpeg"))
        await asyncio.sleep(1.0) # 1 FPS is enough for tool analysis

def play_audio(audio_array):
    # Resampling from 24kHz (Gemini) to 48kHz
    audio_48 = np.interp(np.linspace(0, len(audio_array), int(len(audio_array)*2)), 
                         np.arange(len(audio_array)), audio_array).astype(np.int16)
    sd.play(audio_48, samplerate=48000)
    sd.wait()

# ── Tool Dispatcher ───────────────────────────────────────────────────────────

async def dispatch_tool(name: str, args: dict) -> str:
    print(f"🔧 [AGENT REASONING] Calling: {name} with args {args}")
    try:
        if name == "web_search": return await do_web_search(args["query"])
        if name == "math_solve": return do_math(args["expression"], args["operation"])
        if name == "execute_python": return safe_exec(args["code"])
        if name == "analyze_screen": return f"Currently analyzing: {args.get('focus')}. Image received."
        return "Error: Unknown tool."
    except Exception as e:
        return f"Tool execution error: {e}"

async def receive_responses(session):
    audio_buffer = []
    while True:
        async for message in session.receive():
            # Handle function calls
            if message.tool_call:
                responses = []
                for fc in message.tool_call.function_calls:
                    result = await dispatch_tool(fc.name, dict(fc.args))
                    responses.append({"id": fc.id, "name": fc.name, "response": {"result": result}})
                await session.send_tool_response(function_responses=responses)
                continue

            if not message.server_content: continue

            # Transcription and Audio
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
    client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1alpha'})

    config = LiveConnectConfig(
        response_modalities=["AUDIO"],
        tools=TOOLS,
        system_instruction=SYSTEM_PROMPT,
    )

    async with client.aio.live.connect(model=MODEL, config=config) as session:
        print("🚀 Live Agent Ready. You can start speaking (English)!")
        with sd.InputStream(samplerate=16000, channels=1, dtype="int16", callback=audio_callback):
            await asyncio.gather(send_audio(session), send_video(session), receive_responses(session))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if camera: camera.release()