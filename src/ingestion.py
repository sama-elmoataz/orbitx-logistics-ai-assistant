from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBEDDING_MODEL,
    PDF_PATH,
    VECTORSTORE_PATH,
)


def load_documents():

    loader = PyPDFLoader(PDF_PATH)

    documents = loader.load()

    return documents


def split_documents(documents):

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    chunks = text_splitter.split_documents(
        documents
    )

    return chunks


def create_vectorstore(chunks):

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL
    )

    vectorstore = FAISS.from_documents(
        chunks,
        embeddings,
    )

    vectorstore.save_local(
        VECTORSTORE_PATH
    )

    return vectorstore


def main():

    documents = load_documents()

    chunks = split_documents(
        documents
    )

    create_vectorstore(
        chunks
    )

    print(
        f"Loaded {len(documents)} pages."
    )

    print(
        f"Created {len(chunks)} chunks."
    )

    print(
        "Vector store created successfully."
    )


if __name__ == "__main__":
    main()