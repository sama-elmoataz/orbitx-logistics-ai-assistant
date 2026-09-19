from langchain_openai import ChatOpenAI

from src.config import (
    LLM_MODEL,
    OPENROUTER_API_KEY,
)


def create_llm():

    llm = ChatOpenAI(
        model=LLM_MODEL,
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        temperature=0,
    )

    return llm