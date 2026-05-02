import os
import asyncio
import logging
from dotenv import load_dotenv
from cursorconnect._bridge.manager import BridgeManager

logging.basicConfig(level=logging.INFO)

async def test_local_bridge():
    print("Loading API key from .env...")
    load_dotenv()
    api_key = os.environ.get("CURSOR_API_KEY")
    if not api_key:
        print("ERROR: CURSOR_API_KEY not found in .env")
        return

    print("\n1. Initializing Local Bridge Manager...")
    # Pointing to the internal bridge.js file
    bridge_path = os.path.join(os.path.dirname(__file__), "cursorconnect", "_bridge", "bridge.js")
    manager = BridgeManager(bridge_path=bridge_path)
    
    print("\n2. Spawning Node.js subprocess and creating local Agent...")
    try:
        # Note: We pass api_key in the options dict inside the args array
        # This mirrors how the TypeScript Agent.create() expects it
        result = await manager.send_request(
            action="Agent.create",
            args=[{
                "apiKey": api_key,
                "prompt": "Respond with exactly 'Hello from the Local Node Bridge!'. Do not use any tools.",
                "model": {"id": "claude-sonnet-4-6"}
            }]
        )
        agent_id = result.get("agentId")
        print(f"-> Local Agent created successfully! Internal ID: {agent_id}")
    except Exception as e:
        print(f"Error: Failed to create local agent: {e}")
        manager.close()
        return

    print("\n3. Sending a message and starting a stream...")
    try:
        # Send the message, passing streamEvents=True so bridge.js converts them to SSE-like yields
        run_res = await manager.send_request(
            action="agent.send",
            target=agent_id,
            args=["Please go ahead and output the greeting.", {"streamEvents": True}]
        )
        run_id = run_res.get("runId")
        print(f"-> Run started successfully! Internal Run ID: {run_id}")
        
        print("\n4. Streaming response from Node.js process:")
        print("-" * 40)
        
        async for update in manager.stream_request("run.stream", target=run_id):
            print(update)
        
        print("\n" + "-" * 40)
        
        print("\n5. Waiting for terminal status...")
        final_result = await manager.send_request("run.wait", target=run_id)
        status = final_result.get("status") if isinstance(final_result, dict) else final_result
        print(f"Run completed with status: {status}")
        
    except Exception as e:
        print(f"Error: Stream or wait failed: {e}")

    print("\n6. Cleaning up...")
    try:
        await manager.send_request("agent.close", target=agent_id)
    except Exception as e:
        print(f"Warning on close: {e}")
        
    manager.close()
    print("Local Bridge test complete!")

if __name__ == "__main__":
    asyncio.run(test_local_bridge())
