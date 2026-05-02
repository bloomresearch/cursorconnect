import asyncio
from cursorconnect._bridge.manager import BridgeManager
import os
import tempfile
import json
import logging

logging.basicConfig(level=logging.DEBUG)

# Create a mock bridge script to just echo back success for testing without actual @cursor/sdk
MOCK_BRIDGE = """
const readline = require("readline");
const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
rl.on("line", (line) => {
    if (!line.trim()) return;
    const req = JSON.parse(line);
    if (req.action === "Agent.create") {
        console.log(JSON.stringify({ id: req.id, type: "success", data: { agentId: "mock_agent_1" } }));
    } else if (req.action === "run.stream") {
        console.log(JSON.stringify({ id: req.id, type: "yield", data: { update: "delta1" } }));
        console.log(JSON.stringify({ id: req.id, type: "success", data: null }));
    } else {
        console.log(JSON.stringify({ id: req.id, type: "error", error: "Mock Unknown action" }));
    }
});
"""

async def test():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".js", mode="w") as f:
        f.write(MOCK_BRIDGE)
        f.flush()
        bridge_path = f.name
        
    manager = BridgeManager(bridge_path=bridge_path)
    
    try:
        manager.start()
        print("Started mock bridge")
        
        # Test 1: Agent.create
        res = await manager.send_request("Agent.create", args=[{}])
        print(f"Agent.create result: {res}")
        assert res["agentId"] == "mock_agent_1", "Agent ID mismatch"
        
        # Test 2: run.stream
        updates = []
        async for update in manager.stream_request("run.stream"):
            updates.append(update)
            
        print(f"run.stream result: {updates}")
        assert len(updates) == 1
        assert updates[0]["update"] == "delta1"
        
        print("ALL TESTS PASSED")
    finally:
        manager.close()
        os.unlink(bridge_path)

if __name__ == "__main__":
    asyncio.run(test())
