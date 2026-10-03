import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq

from betito_bot.agents.tool_agent import DEFAULT_MODEL

load_dotenv()


def build_client() -> ChatGroq:
    """Chat model de LangChain para Groq; cada agente fija su modelo al invocarlo."""
    return ChatGroq(
        api_key=os.environ.get("API_KEY_GROQ"),
        model=os.getenv("LLM_MODEL", DEFAULT_MODEL),
    )
