from flashrank import Ranker, RerankRequest

from src.config import RERANK_TOP_N


def create_reranker():

    ranker = Ranker()

    return ranker


def rerank_documents(query, documents, ranker):

    passages = []

    for index, document in enumerate(documents):

        passages.append({
            "id": str(index),
            "text": document.page_content,
        })

    rerank_request = RerankRequest(
        query=query,
        passages=passages,
    )

    results = ranker.rerank(rerank_request)

    top_results = results[:RERANK_TOP_N]

    reranked_documents = []

    for result in top_results:

        index = int(result["id"])

        document = documents[index]

        document.metadata["rerank_score"] = result["score"]

        reranked_documents.append(document)

    return reranked_documents


def main():

    print("Reranker module loaded successfully.")


if __name__ == "__main__":
    main()