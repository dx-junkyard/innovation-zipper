
import sys
import os

# Add the project root to sys.path to allow imports
sys.path.append(os.getcwd())

try:
    from config import (
        MODEL_FAST,
        MODEL_SMART,
        MODEL_CAPTURE_FILTERING,
        MODEL_HOT_CACHE,
        MODEL_INTENT_ROUTING,
        MODEL_INTEREST_EXPLORATION,
        MODEL_SITUATION_ANALYSIS,
        MODEL_HYPOTHESIS_GENERATION,
        MODEL_STRUCTURAL_ANALYSIS,
        MODEL_INNOVATION_SYNTHESIS,
        MODEL_GAP_ANALYSIS,
        MODEL_REPORT_GENERATION,
        MODEL_RESPONSE_PLANNING
    )
    print("All configuration constants imported successfully.")
except ImportError as e:
    print(f"ImportError: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
