import os

from dotenv import load_dotenv


load_dotenv()


EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

DATABASE_PATH = "data/orbitx_shipments.db"

LLM_MODEL = os.getenv("LLM_MODEL")

OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY"
)

ORS_API_KEY = os.getenv(
    "ORS_API_KEY"
)


CHUNK_SIZE = 800

CHUNK_OVERLAP = 150

RETRIEVAL_K = 10

RERANK_TOP_N = 4


PDF_PATH = (
    "data/"
    "orbitx_company_information.pdf"
)

VECTORSTORE_PATH = "data/vectorstore"