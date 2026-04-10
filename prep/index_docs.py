"""
Offline preparation script.

Run once (or whenever your Apple support docs change) to:
1. Submit PDFs to PageIndex and get document tree structures
2. Store the trees in MongoDB for use by the context_retrieval node

Usage:
    python -m prep.index_docs --pdf path/to/apple-support.pdf --doc-id apple-support

Set PAGEINDEX_API_KEY and MONGODB_URI in your environment or .env file.
"""
import asyncio
import argparse
import os
import time
import requests
import motor.motor_asyncio
from pageindex import PageIndexClient
import pageindex.utils as utils


PAGEINDEX_API_KEY = os.environ["PAGEINDEX_API_KEY"]
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")


async def store_tree(doc_id: str, tree: list):
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
    db = client.support_bot
    await db.document_trees.replace_one(
        {"doc_id": doc_id},
        {"doc_id": doc_id, "tree": tree},
        upsert=True,
    )
    print(f"Stored tree for '{doc_id}' in MongoDB.")
    client.close()


def submit_and_wait(pdf_path: str) -> list:
    pi_client = PageIndexClient(api_key=PAGEINDEX_API_KEY)

    result = pi_client.submit_document(pdf_path)
    pi_doc_id = result["doc_id"]
    print(f"Submitted to PageIndex: {pi_doc_id}")

    # Poll until ready
    for attempt in range(30):
        if pi_client.is_retrieval_ready(pi_doc_id):
            tree = pi_client.get_tree(pi_doc_id, node_summary=True)["result"]
            print(f"Tree ready: {len(tree)} top-level nodes")
            return tree
        print(f"  Waiting for PageIndex to process... (attempt {attempt + 1}/30)")
        time.sleep(10)

    raise TimeoutError("PageIndex did not finish processing within 5 minutes")


async def main(pdf_path: str, doc_id: str):
    print(f"Indexing '{pdf_path}' as doc_id='{doc_id}'")
    tree = submit_and_wait(pdf_path)

    print("\nTree structure:")
    utils.print_tree(tree)

    await store_tree(doc_id, tree)
    print("\nDone. Document is ready for retrieval.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True, help="Path to the PDF to index")
    parser.add_argument("--doc-id", required=True, help="Identifier for this document")
    args = parser.parse_args()

    asyncio.run(main(args.pdf, args.doc_id))
