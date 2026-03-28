import asyncio
import os
import json
from dotenv import load_dotenv

from google import genai
from google.genai.types import (
    Blob,
    LiveConnectConfig,
    Tool,
    FunctionDeclaration,
    Schema,
)

# Fix imports when used from main backend context
try:
    from backend.services.agent_tools import do_math, safe_exec, do_web_search
except ImportError:
    from services.agent_tools import do_math, safe_exec, do_web_search

load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = "models/gemini-3.1-flash-live-preview"

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
            description="Focuses the agent's 'eyes' on the video feed. Use when there is a chart, table, or text to analyze in the visual data.",
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


class AgentService:
    def __init__(self):
        self.api_key = GEMINI_API_KEY
        if not self.api_key:
            print("Warning: GEMINI_API_KEY not found in environment!")
        self.client = genai.Client(api_key=self.api_key, http_options={'api_version': 'v1alpha'})
        self.session = None
        self.session_context = None
        self.out_queue = asyncio.Queue()
        self.sender_task = None

    async def start_session(self):
        """Initializes the connection with Gemini Live API."""
        config = LiveConnectConfig(
            response_modalities=["AUDIO"],
            tools=TOOLS,
            system_instruction=SYSTEM_PROMPT,
        )
        self.session_context = self.client.aio.live.connect(model=MODEL, config=config)
        self.session = await self.session_context.__aenter__()
        
        self.sender_task = asyncio.create_task(self._send_loop())
        print("🚀 Agent Session Ready.")

    async def close_session(self):
        """Closes the connection with Gemini Live API."""
        if self.sender_task:
            self.sender_task.cancel()
        if self.session_context:
            await self.session_context.__aexit__(None, None, None)
            self.session = None
            self.session_context = None
            print("🛑 Agent Session Closed.")

    async def send_audio_chunk(self, audio_bytes: bytes, sample_rate: int = 16000):
        """Queues raw PCM audio bytes for the agent."""
        if not self.session:
            return
        mime_type = f"audio/pcm;rate={sample_rate}"
        self.out_queue.put_nowait({"type": "audio", "data": audio_bytes, "mime": mime_type})

    async def send_video_frame(self, frame_bytes: bytes, mime_type: str = "image/jpeg"):
        """Queues video frames for the agent."""
        if not self.session:
            return
        self.out_queue.put_nowait({"type": "video", "data": frame_bytes, "mime": mime_type})

    async def _send_loop(self):
        """Background task that reads from the queue and sends to Gemini, automatically batching audio."""
        try:
            while True:
                item = await self.out_queue.get()
                
                if item["type"] == "audio":
                    buffer = bytearray(item["data"])
                    mime = item["mime"]
                    
                    video_item = None
                    try:
                        # Batch all pending audio in the queue
                        while True:
                            nxt = self.out_queue.get_nowait()
                            if nxt["type"] == "audio":
                                buffer.extend(nxt["data"])
                            else:
                                video_item = nxt
                                break
                    except asyncio.QueueEmpty:
                        pass
                    
                    await self.session.send_realtime_input(audio=Blob(data=bytes(buffer), mime_type=mime))
                    
                    if video_item:
                        await self.session.send_realtime_input(video=Blob(data=video_item["data"], mime_type=video_item["mime"]))
                        
                elif item["type"] == "video":
                    await self.session.send_realtime_input(video=Blob(data=item["data"], mime_type=item["mime"]))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Agent send error: {e}")

    async def receive_responses(self):
        """
        An async generator that yields audio chunks returned by Gemini.
        It inherently handles executing tool calls and returning their results.
        Returns bytes (PCM 24000Hz by default for Gemini Voice).
        """
        if not self.session:
            return

        async for message in self.session.receive():
            if message.tool_call:
                responses = []
                for fc in message.tool_call.function_calls:
                    result = await self._dispatch_tool(fc.name, dict(fc.args))
                    responses.append({"id": fc.id, "name": fc.name, "response": {"result": result}})
                await self.session.send_tool_response(function_responses=responses)
                continue

            if message.server_content and message.server_content.model_turn:
                for part in message.server_content.model_turn.parts:
                    if part.text:
                        print(f"🤖 Agent [TEXT]: {part.text}")
                    if part.inline_data:
                        print(f"🤖 Agent [AUDIO]: Receiving voice response chunk ({len(part.inline_data.data)} bytes)...")
                        # Yield raw audio data bytes
                        yield part.inline_data.data

            if message.server_content and message.server_content.turn_complete:
                print(f"🤖 Agent: [Zakończył mówić / Turn Complete]")

    async def _dispatch_tool(self, name: str, args: dict) -> str:
        """Internal tool dispatcher."""
        print(f"🔧 [AGENT REASONING] Calling: {name} with args {args}")
        try:
            if name == "web_search": 
                return await do_web_search(args.get("query", ""))
            if name == "math_solve": 
                return do_math(args.get("expression", ""), args.get("operation", ""))
            if name == "execute_python": 
                return safe_exec(args.get("code", ""))
            if name == "analyze_screen": 
                return f"Currently analyzing: {args.get('focus')}. Data processed."
            return "Error: Unknown tool."
        except Exception as e:
            return f"Tool execution error: {e}"
