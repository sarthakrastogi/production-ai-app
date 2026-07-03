import json
import asyncio
import pybreaker
import motor.motor_asyncio
from langchain_google_genai import ChatGoogleGenerativeAI

from app.graph.state import SupportBotState
from app.observability.logging import get_logger
from app.resilience.breakers import pageindex_breaker
from app.config import settings

_mongo_client = None

def get_mongo():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGODB_URI)
    return _mongo_client.support_bot


_tree_search_llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash", temperature=0)

_TREE_SEARCH_PROMPT = """
You are given a question and a tree structure of an Apple support document.
Each node has a node_id, title, and summary.
Find all nodes likely to contain the answer.

Question: {query}

Document tree:
{tree_json}

Reply ONLY with JSON: {{"node_list": ["node_id_1", "node_id_2"]}}
"""


def _build_node_map(tree: list, node_map: dict | None = None) -> dict:
    if node_map is None:
        node_map = {}
    for node in tree:
        node_map[node["node_id"]] = node
        if "nodes" in node:
            _build_node_map(node["nodes"], node_map)
    return node_map


def _strip_text(tree: list) -> list:
    """Remove text content from tree for the search prompt (reduce tokens)."""
    result = []
    for node in tree:
        n = {k: v for k, v in node.items() if k not in ("text",)}
        if "nodes" in node:
            n["nodes"] = _strip_text(node["nodes"])
        result.append(n)
    return result


async def _search_tree(tree: list, query: str) -> list[dict]:
    stripped = _strip_text(tree)
    prompt = _TREE_SEARCH_PROMPT.format(
        query=query,
        tree_json=json.dumps(stripped, indent=2),
    )
    result = await _tree_search_llm.ainvoke(prompt)
    node_ids = json.loads(result.content)["node_list"]
    node_map = _build_node_map(tree)
    return [node_map[nid] for nid in node_ids if nid in node_map]


async def context_retrieval_node(state: SupportBotState) -> dict:
    log = get_logger(state["request_id"], node="context_retrieval")

    try:
        with pageindex_breaker:
            db = get_mongo()
            doc = await db.document_trees.find_one({"doc_id": "apple-support"})
            if not doc:
                log.warning("no_document_tree_found")
                return {"retrieved_context": []}

            relevant_nodes = await _search_tree(doc["tree"], state["scrubbed_query"])
            context = [node.get("text", "") for node in relevant_nodes if node.get("text")]

            log.info("retrieval_complete", num_nodes=len(relevant_nodes))
            return {"retrieved_context": context}

    except pybreaker.CircuitBreakerError:
        log.warning("pageindex_circuit_open")
        return {"retrieved_context": []}
    except Exception as exc:
        log.warning("retrieval_failed", error=str(exc))
        return {"retrieved_context": []}
