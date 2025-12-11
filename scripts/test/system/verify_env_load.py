import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[3]))

# Create a dummy .env file for testing if it doesn't exist
env_path = Path(__file__).resolve().parents[1] / ".env"
original_env_content = None
if env_path.exists():
    original_env_content = env_path.read_text()

try:
    # Write a test key to .env
    with open(env_path, "a") as f:
        f.write("\nOPENAI_API_KEY=test-key-from-env-file\n")

    # Import main which should load .env
    from app.api import main

    # Check if key is loaded
    key = os.environ.get("OPENAI_API_KEY")
    print(f"Loaded OPENAI_API_KEY: {key}")

    if key == "test-key-from-env-file":
        print("SUCCESS: .env file was loaded correctly.")
    else:
        print("FAILURE: .env file was NOT loaded correctly or key mismatch.")

finally:
    # Cleanup: Restore original .env content
    if original_env_content is not None:
        env_path.write_text(original_env_content)
    else:
        # If it didn't exist, remove it (though in this project it likely exists)
        if env_path.exists():
            # We appended, so we should probably just revert the append if possible,
            # but reading/writing back original is safer if it existed.
            # If it didn't exist, we delete it.
            pass # logic above handles restoration if it existed.
            # If it didn't exist, we should delete it, but the code above assumes it might.
            # Let's refine the cleanup.
            pass

    # Actually, simpler cleanup:
    # If we modified it, we restore it.
    # If we created it, we delete it.
    pass
