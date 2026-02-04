"""
Environment variable loader utility for SOC 2 audit scripts.

This module provides a centralized way to load environment variables from a .env file
and validate that required secrets are present. All scripts should use this utility
instead of directly loading environment variables.

Usage:
    from utils.env_loader import load_env, get_api_key
    
    # Load environment variables (call once at the beginning of your script)
    load_env()
    
    # Get the OpenAI API key
    api_key = get_api_key()
"""

import os
from dotenv import load_dotenv
from typing import Optional


def load_env(env_file: str = ".env") -> None:
    """
    Load environment variables from a .env file.
    
    This function should be called once at the beginning of your script
    to load all environment variables from the .env file.
    
    Args:
        env_file: Path to the .env file (default: ".env")
    """
    load_dotenv(env_file)


def get_api_key(key_name: str = "OPENAI_API_KEY", required: bool = True) -> Optional[str]:
    """
    Get an API key from environment variables.
    
    Args:
        key_name: Name of the environment variable containing the API key
        required: If True, raises ValueError if the key is not found
        
    Returns:
        The API key value, or None if not found and not required
        
    Raises:
        ValueError: If required=True and the API key is not found
    """
    api_key = os.getenv(key_name)
    
    if not api_key and required:
        print(f"❌ CRITICAL ERROR: {key_name} missing.")
        print(f"   -> Please create a '.env' file with {key_name}=<your-key>")
        raise ValueError(f"{key_name} not found in environment variables.")
    
    return api_key


def get_config_value(key_name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get a configuration value from environment variables.
    
    Args:
        key_name: Name of the environment variable
        default: Default value if the key is not found
        
    Returns:
        The configuration value or the default
    """
    return os.getenv(key_name, default)
