from pathlib import Path
import os
from dotenv import load_dotenv

# Load current .env if it exists
env_path = Path(".env")
if env_path.exists():
    load_dotenv(env_path)

# Add missing environment variables
env_vars = {}

print("Please enter values for required environment variables. Press Enter to skip optional ones.")

# OpenAI (Required)
env_vars["OPENAI_API_KEY"] = input("Enter OPENAI_API_KEY (required): ").strip()
env_vars["OPENAI_MODEL"] = input("Enter OPENAI_MODEL (default: gpt-3.5-turbo): ").strip() or "gpt-3.5-turbo"

# Redis (Required)
env_vars["REDIS_URL"] = input("Enter REDIS_URL (default: redis://localhost:6379): ").strip() or "redis://localhost:6379"

# Optional providers
print("\nOptional providers:")
env_vars["DEEPGRAM_AUTH_TOKEN"] = input("Enter DEEPGRAM_AUTH_TOKEN (optional): ").strip()
env_vars["ELEVENLABS_API_KEY"] = input("Enter ELEVENLABS_API_KEY (optional): ").strip()

# Write to .env file
with open(".env", "w") as f:
    for key, value in env_vars.items():
        if value:  # Only write non-empty values
            f.write(f"{key}={value}\n")

print("\nEnvironment variables have been saved to .env file")