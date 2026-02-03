import os
from dotenv import load_dotenv

# 1. Load variables from .env file
load_dotenv()

# 2. Get the API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# 3. Validation Check (Stops the script immediately if key is missing)
if not OPENAI_API_KEY:
    print("❌ CRITICAL ERROR: API Key missing.")
    print("   -> Please create a '.env' file with OPENAI_API_KEY=sk-...")
    raise ValueError("OPENAI_API_KEY not found in environment variables.")

# 4. Optional: Centralized Model Name (easier to upgrade later)
SOC2_MODEL = "gpt-4-turbo"