import os
import logging
from cursorconnect import CursorClient, CursorAPIError

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ==============================================================================
# Test Application
# ==============================================================================

if __name__ == "__main__":
    # Ensure you export your API key before running: 
    # export CURSOR_API_KEY="your-api-key"
    API_KEY = os.getenv("CURSOR_API_KEY")
    
    if not API_KEY:
        logging.error("Please set the CURSOR_API_KEY environment variable.")
        exit(1)

    logging.info("Initializing CursorClient...")
    client = CursorClient(api_key=API_KEY)

    try:
        # 1. Retrieve API Key Info
        me_info = client.get_me()
        logging.info(f"Authenticated as: {me_info.get('userEmail')} (Key: {me_info.get('apiKeyName')})")

        # 2. List available models
        models = client.list_models()
        logging.info(f"Available models: {models}")
        
        # Pick the first model, fallback to 'composer-2'
        model_id = models[0] if models else "composer-2"

        # 3. Create a test Agent
        repo_url = "https://github.com/cursor-sh/demo-repo" # Replace with your real repo URL
        prompt = "Create a hello_world.py script that prints 'Hello from Cursor Cloud Agent!'"
        
        logging.info(f"Creating agent to execute: '{prompt}' on {repo_url} ...")
        agent = client.agents.create(
            prompt_text=prompt,
            repo_url=repo_url,
            model_id=model_id,
            autoCreatePR=False
        )
        
        logging.info(f"Agent created successfully: {agent}")
        logging.info(f"Initial Run ID: {agent.latest_run_id}")

        # 4. Stream the initial run (SSE)
        # Getting the run object to monitor its state
        run = agent.runs.get(agent.latest_run_id)
        logging.info(f"Streaming updates for Run {run.id}...")
        
        for event in run.stream():
            event_type = event.get('event')
            data = event.get('data', {})
            
            if event_type == "status":
                logging.info(f"[STATUS] {data.get('status')}")
            elif event_type == "assistant":
                text = data.get("text", "")
                if text:
                    print(text, end="", flush=True)
            elif event_type == "result":
                print() # newline after stream ends
                logging.info(f"[RESULT] Run finished with status: {data.get('status')}")
            elif event_type == "error":
                logging.error(f"[ERROR] {data.get('message')}")
        
        # 5. Check for artifacts
        logging.info("Checking for artifacts...")
        artifacts = agent.artifacts.list()
        if not artifacts:
            logging.info("No artifacts found.")
        else:
            for art in artifacts:
                logging.info(f"Artifact found: {art.path} ({art.size_bytes} bytes)")
                dl_url = art.get_download_url()
                logging.info(f"Download URL (valid for 15m): {dl_url}")
                
        # 6. Cleanup
        logging.info("Cleaning up... Deleting the agent permanently.")
        agent.delete()
        logging.info("Agent deleted. Test finished successfully!")

    except CursorAPIError as e:
        logging.error(f"Cursor API returned an error: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
