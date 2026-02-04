"""
Configuration module for sanitazer scripts.

This module uses the centralized env_loader utility to load environment variables.
"""

import os
import sys

# Ensure parent directory is in path for imports
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from utils.env_loader import load_env, get_api_key

# Load environment variables from .env file
load_env()

# Get the OpenAI API Key (with validation)
OPENAI_API_KEY = get_api_key("OPENAI_API_KEY")

# Centralized Model Name (easier to upgrade later)
SOC2_MODEL = "gpt-4-turbo"