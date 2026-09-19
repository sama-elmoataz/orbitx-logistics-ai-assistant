from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

from src.config import (
    EMBEDDING_MODEL,
    RETRIEVAL_K,
    VECTORSTORE_PATH,
)


def load_vectorstore():

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL
    )

    vectorstore = FAISS.load_local(
        VECTORSTORE_PATH,
        embeddings,
        allow_dangerous_deserialization=True,
    )

    return vectorstore


def retrieve_documents(query):

    vectorstore = load_vectorstore()

    documents = vectorstore.similarity_search(
        query,
        k=RETRIEVAL_K,
    )

    return documents


def main():

    query = "What happens if a delivery attempt fails?"

    documents = retrieve_documents(query)

    for index, document in enumerate(
        documents,
        start=1,
    ):
        print(f"\nDocument {index}")
        print(document.page_content)


if __name__ == "__main__":
    main()