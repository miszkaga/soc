"""
Configuration module for SOC 2 audit scripts.

This module uses the centralized env_loader utility to load environment variables.
"""

from utils.env_loader import load_env, get_api_key

# Load environment variables from .env file
load_env()

# Get the OpenAI API Key (with validation)
OPENAI_API_KEY = get_api_key("OPENAI_API_KEY")

# Centralized Model Name (easier to upgrade later)
SOC2_MODEL = "gpt-4-turbo"