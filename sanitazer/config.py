"""
Configuration module for sanitazer scripts.

This module uses the centralized env_loader utility to load environment variables.
"""

import sys
import os

# Add parent directory to path to access utils module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.env_loader import load_env, get_api_key

# Load environment variables from .env file
load_env()

# Get the OpenAI API Key (with validation)
OPENAI_API_KEY = get_api_key("OPENAI_API_KEY")

# Centralized Model Name (easier to upgrade later)
SOC2_MODEL = "gpt-4-turbo"