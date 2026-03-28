

async def broadcast_tool_log(
        active_connections,
        meet_id: str, tool_id: str, tool_name: str, log_msg: str
):
    if meet_id not in active_connections or not active_connections[meet_id]:
        return

    message = {
        "event": "tool_update",
        "tool_id": tool_id,
        "tool_name": tool_name,
        "log": log_msg
    }

    disconnected_sockets = set()
    for ws in list(active_connections[meet_id]):
        try:
            await ws.send_json(message)
        except Exception as e:
            #print(f"[Runner WS] Błąd wysyłania do klienta: {e}")
            disconnected_sockets.add(ws)

    for dead_ws in disconnected_sockets:
        active_connections[meet_id].discard(dead_ws)