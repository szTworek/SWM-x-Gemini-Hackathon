import asyncio
import os
import re
import uuid
from typing import Callable, Optional
from dotenv import load_dotenv

from google import genai
from google.genai.types import (
    Blob,
    LiveConnectConfig,
    Tool,
    FunctionDeclaration,
    Schema,
    ContextWindowCompressionConfig,
    SlidingWindow,
)

# Fix imports when used from main backend context
try:
    from backend.services.agent_tools import do_math, safe_exec, do_web_search, do_send_chat
except ImportError:
    from services.agent_tools import do_math, safe_exec, do_web_search, do_send_chat

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
        FunctionDeclaration(
            name="send_chat_message",
            description="Sends a text message to the Google Meet chat so all participants can read it. Use this to share results, summaries, links or any important information with the participants directly in the chat.",
            parameters=Schema(
                type="OBJECT",
                properties={
                    "message": Schema(type="STRING", description="The message text to send to the meeting chat (max 490 characters)"),
                },
                required=["message"],
            ),
        ),
        FunctionDeclaration(
            name="read_chat",
            description="Reads the most recent chat messages from the meeting. Use this to catch up on what participants wrote in the chat, or when asked about the chat history.",
            parameters=Schema(
                type="OBJECT",
                properties={
                    "limit": Schema(type="INTEGER", description="Number of recent messages to fetch (1-50, default 10)"),
                },
                required=[],
            ),
        ),
    ])
]


class AgentService:
    def __init__(self, tool_event_callback: Optional[Callable] = None, chat_callback: Optional[Callable] = None, get_chat_messages_callback: Optional[Callable] = None):
        self.api_key = GEMINI_API_KEY
        if not self.api_key:
            print("Warning: GEMINI_API_KEY not found in environment!")
        self.client = genai.Client(api_key=self.api_key, http_options={'api_version': 'v1alpha'})
        self.session = None
        self.session_context = None
        self.out_queue = asyncio.Queue()
        self.sender_task = None
        # Optional async callback: (tool_id: str, tool_name: str, log: str) -> None
        self.tool_event_callback = tool_event_callback
        # Optional async callback for sending to Meet chat:
        #   - Plain text: (message: str, is_text: bool) -> None
        #   - Chart PNG:  (plot_b64: str) -> None  (is_text defaults to False)
        self.chat_callback = chat_callback
        # Optional async callback: (limit: int) -> list[dict]
        self.get_chat_messages_callback = get_chat_messages_callback

    async def start_session(self):
        """Initializes the connection with Gemini Live API."""
        config = LiveConnectConfig(
            response_modalities=["AUDIO"],
            tools=TOOLS,
            system_instruction=SYSTEM_PROMPT,
            # Context window compression eliminates the 2-min (audio+video) / 15-min (audio-only)
            # session limits by using a sliding window that discards old tokens automatically.
            context_window_compression=ContextWindowCompressionConfig(
                sliding_window=SlidingWindow(),
            ),
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
            try:
                await self.session_context.__aexit__(None, None, None)
            except Exception:
                pass
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
        """Background task: batches queued audio/video and sends to Gemini every 500ms."""
        try:
            while True:
                item = await self.out_queue.get()

                if item["type"] == "audio":
                    buffer = bytearray(item["data"])
                    mime = item["mime"]
                    video_item = None

                    # Batch all pending audio into one payload (reduces API calls to ~2/sec).
                    # The 500ms sleep also ensures the internal websocket can handle server pings.
                    await asyncio.sleep(0.5)

                    try:
                        while True:
                            nxt = self.out_queue.get_nowait()
                            if nxt["type"] == "audio":
                                buffer.extend(nxt["data"])
                            else:
                                video_item = nxt
                                break
                    except asyncio.QueueEmpty:
                        pass

                    # Cap at ~4 seconds of audio to avoid sending sudden large bursts
                    MAX_AUDIO_BYTES = 128_000
                    if len(buffer) > MAX_AUDIO_BYTES:
                        buffer = buffer[-MAX_AUDIO_BYTES:]

                    print(f"[AGENT SENDER] Sending bundled payload -> Audio: {len(buffer)} bytes | Video: {'Yes' if video_item else 'No'}")
                    await self.session.send_realtime_input(audio=Blob(data=bytes(buffer), mime_type=mime))

                    if video_item:
                        await self.session.send_realtime_input(video=Blob(data=video_item["data"], mime_type=video_item["mime"]))

                elif item["type"] == "video":
                    await self.session.send_realtime_input(video=Blob(data=item["data"], mime_type=item["mime"]))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[AGENT SENDER] Error: {e}")

    async def receive_responses(self):
        """
        Async generator — yields raw PCM audio bytes from Gemini responses.
        Handles tool calls without blocking the receive loop (important for ping handling).
        """
        if not self.session:
            return

        async def _handle_tool_call(tool_call):
            responses = []
            for fc in tool_call.function_calls:
                # Unique ID per tool invocation so the UI can track each run separately
                tool_run_id = str(uuid.uuid4())[:8]
                args_preview = ", ".join(f"{k}={repr(v)[:60]}" for k, v in dict(fc.args).items())
                start_log = f"▶ Wywołano z: {args_preview}" if args_preview else "▶ Wywołano"

                if self.tool_event_callback:
                    asyncio.create_task(self.tool_event_callback(tool_run_id, fc.name, start_log))

                result = await self._dispatch_tool(fc.name, dict(fc.args))

                # Trim long results so the UI stays readable
                result_preview = str(result)[:200] + ("..." if len(str(result)) > 200 else "")
                done_log = f"✅ Zakończono. Wynik: {result_preview}"
                if self.tool_event_callback:
                    asyncio.create_task(self.tool_event_callback(tool_run_id, fc.name, done_log))

                responses.append({"id": fc.id, "name": fc.name, "response": {"result": result}})
            try:
                await self.session.send_tool_response(function_responses=responses)
            except Exception as e:
                print(f"[AGENT] Failed to send tool response: {e}")

        try:
            while True:
                # Track whether we received any message in this turn.
                # If session.receive() returns zero messages (StopAsyncIteration immediately),
                # it means the connection is dead — break to avoid a busy spin-loop
                # that would starve the entire asyncio event loop.
                got_message = False

                async for message in self.session.receive():
                    got_message = True

                    if message.tool_call:
                        # Fire-and-forget — never block this loop or server pings will time out
                        asyncio.create_task(_handle_tool_call(message.tool_call))
                        continue

                    if message.server_content and message.server_content.model_turn:
                        for part in message.server_content.model_turn.parts:
                            if part.text:
                                print(f"🤖 Agent [TEXT]: {part.text}")
                            if part.inline_data:
                                yield part.inline_data.data

                    if message.server_content and message.server_content.turn_complete:
                        print("🤖 Agent: [Turn Complete] — waiting for next turn...")

                if not got_message:
                    # session.receive() returned without yielding anything —
                    # this means the WebSocket session has closed on the Gemini side.
                    print("[AGENT RECEIVER] session.receive() returned empty — session closed, stopping receiver.")
                    break

                # Always yield to the event loop between turns.
                # This prevents starvation if receive() returns synchronously.
                await asyncio.sleep(0)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[AGENT RECEIVER] Session ended: {e}")

    async def _dispatch_tool(self, name: str, args: dict) -> str:
        """Internal tool dispatcher."""
        print(f"🔧 [AGENT] Calling tool: {name} with args {args}")
        try:
            if name == "web_search":
                return await do_web_search(args.get("query", ""))
            if name == "math_solve":
                return await asyncio.to_thread(do_math, args.get("expression", ""), args.get("operation", ""))
            if name == "execute_python":
                raw = await asyncio.to_thread(safe_exec, args.get("code", ""))
                # Extract PLOT_B64 marker and call chat_callback from async context
                match = re.search(r'\[PLOT_B64\](.*?)\[/PLOT_B64\]', raw, re.DOTALL)
                if match:
                    plot_b64 = match.group(1).strip()
                    clean_output = re.sub(r'\[PLOT_B64\].*?\[/PLOT_B64\]', '', raw, flags=re.DOTALL).strip()
                    if self.chat_callback:
                        try:
                            await self.chat_callback(plot_b64, is_text=False)
                        except Exception as e:
                            print(f"[AGENT] Chart callback error: {e}")
                    return clean_output + "\n\n✅ Chart generated and sent to Meet chat." if clean_output else "✅ Chart generated and sent to Meet chat."
                return raw
            if name == "analyze_screen":
                return f"Currently analyzing: {args.get('focus')}. Data processed."
            if name == "send_chat_message":
                return await do_send_chat(args.get("message", ""), self.chat_callback)
            if name == "read_chat":
                limit = min(max(int(args.get("limit", 10)), 1), 50)
                if not self.get_chat_messages_callback:
                    return "Error: Chat reading is not configured for this session."
                messages = await self.get_chat_messages_callback(limit)
                if not messages:
                    return "No chat messages found."
                lines = []
                for m in messages:
                    ts = m.get("created_at", "")[:19].replace("T", " ") if m.get("created_at") else ""
                    prefix = f"[{ts}] " if ts else ""
                    lines.append(f"{prefix}{m['sender']}: {m['message']}")
                return f"Last {len(messages)} chat message(s):\n" + "\n".join(lines)
            return "Error: Unknown tool."
        except Exception as e:
            return f"Tool execution error: {e}"
