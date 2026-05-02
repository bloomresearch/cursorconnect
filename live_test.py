import os
from dotenv import load_dotenv

from cursorconnect import Agent
from cursorconnect.types import AssistantMessage

def run_live_test():
    print("Loading API key from .env...")
    load_dotenv()
    
    api_key = os.environ.get("CURSOR_API_KEY")
    if not api_key:
        print("ERROR: CURSOR_API_KEY not found in .env")
        return

    print("\n1. Creating a live agent...")
    from cursorconnect.types import ModelSelection, CloudOptions
    
    agent = Agent.create(
        api_key=api_key,
        prompt="Respond with exactly 'Hello from the CursorConnect SDK!'. Do not use any tools.",
        name="live-test-agent",
        model=ModelSelection(id="claude-sonnet-4-6"),
        cloud=CloudOptions(repos=[{"url": "https://github.com/cursorconnect/dummy-repo"}])
    )
    print(f"✅ Agent created successfully! ID: {agent.agent_id}")
    
    print("\n2. Streaming the initial run response:")
    print("-" * 40)
    
    run = agent.initial_run
    for event in run.stream():
        if event.type is AssistantMessage:
            for block in event.message.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    print(block["text"], end="", flush=True)
                    
    print("\n" + "-" * 40)
    
    # Wait for the run to formally finish
    result = run.wait()
    print(f"\n3. Run completed with status: {result.status}")
    
    print("\n4. Cleaning up (deleting the agent)...")
    agent.delete()
    print("✅ Cleanup complete. Live test successful!")

if __name__ == "__main__":
    run_live_test()
