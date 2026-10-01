import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()


def build_client() -> Groq:
    api_key = os.environ.get("API_KEY_GROQ")
    return Groq(api_key=api_key)
