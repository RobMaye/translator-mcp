"""MCP server for the NCATS Biomedical Data Translator (TRAPI)."""

import sys
import json
import logging
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)

mcp = FastMCP("translator")

# BioThings Explorer — reliable, synchronous TRAPI endpoint
BTE_BASE = "https://bte.transltr.io/v1"

TIMEOUT = 120.0


async def _trapi_query(endpoint: str, query: dict) -> dict[str, Any]:
    """Execute a TRAPI query against the given endpoint."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                endpoint,
                json=query,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            raise ToolError(f"Query timed out after {TIMEOUT}s. The Translator may be under heavy load — try again.")
        except httpx.HTTPStatusError as e:
            raise ToolError(f"Translator returned HTTP {e.response.status_code}. Try a simpler query or try again later.")


def _build_one_hop(
    subject_ids: list[str] | None,
    subject_categories: list[str],
    predicate: str | None,
    object_ids: list[str] | None,
    object_categories: list[str],
) -> dict:
    """Build a one-hop TRAPI query message."""
    n0: dict[str, Any] = {"categories": subject_categories}
    if subject_ids:
        n0["ids"] = subject_ids

    n1: dict[str, Any] = {"categories": object_categories}
    if object_ids:
        n1["ids"] = object_ids

    edge: dict[str, Any] = {"subject": "n0", "object": "n1"}
    if predicate:
        edge["predicates"] = [predicate]

    return {
        "message": {
            "query_graph": {
                "nodes": {"n0": n0, "n1": n1},
                "edges": {"e0": edge},
            }
        }
    }


def _format_results(data: dict, max_results: int = 20) -> str:
    """Format TRAPI response into a readable summary."""
    message = data.get("message", {})
    results = message.get("results", [])
    kg_nodes = message.get("knowledge_graph", {}).get("nodes", {})
    kg_edges = message.get("knowledge_graph", {}).get("edges", {})

    if not results:
        return "No results found."

    lines = [f"Found {len(results)} results. Showing top {min(len(results), max_results)}:\n"]

    for i, result in enumerate(results[:max_results]):
        score = result.get("score", "N/A")
        node_bindings = result.get("node_bindings", {})

        # Resolve node names from knowledge graph
        bound_nodes = {}
        for qnode_key, bindings in node_bindings.items():
            for binding in bindings:
                node_id = binding.get("id", "")
                node_info = kg_nodes.get(node_id, {})
                name = node_info.get("name", node_id)
                categories = node_info.get("categories", [])
                cat_str = categories[0].replace("biolink:", "") if categories else "Unknown"
                bound_nodes[qnode_key] = f"{name} ({cat_str}, {node_id})"

        # Resolve edge info
        edge_bindings = result.get("edge_bindings", {})
        edge_details = []
        for qedge_key, bindings in edge_bindings.items():
            for binding in bindings:
                edge_id = binding.get("id", "")
                edge_info = kg_edges.get(edge_id, {})
                predicate = edge_info.get("predicate", "related_to")
                sources = edge_info.get("sources", [])
                source_names = [s.get("resource_id", "") for s in sources[:3]]
                edge_details.append(f"  Relationship: {predicate}")
                if source_names:
                    edge_details.append(f"  Sources: {', '.join(source_names)}")

        lines.append(f"--- Result {i + 1} (score: {score}) ---")
        for key, desc in bound_nodes.items():
            lines.append(f"  {key}: {desc}")
        lines.extend(edge_details)
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def find_drugs_for_gene(
    gene_curie: str,
    max_results: int = 20,
) -> str:
    """Find drugs or chemicals that affect a specific gene.

    Use this to discover drug repurposing candidates for a gene of interest.
    Returns chemicals/drugs with evidence of affecting the gene, sourced from
    hundreds of biomedical databases.

    Args:
        gene_curie: The gene identifier in CURIE format (e.g. 'NCBIGene:51322' for WAC,
                    'NCBIGene:4233' for MET, 'NCBIGene:7157' for TP53)
        max_results: Maximum number of results to return (1-50)
    """
    query = _build_one_hop(
        subject_ids=None,
        subject_categories=["biolink:SmallMolecule"],
        predicate=None,
        object_ids=[gene_curie],
        object_categories=["biolink:Gene"],
    )
    data = await _trapi_query(f"{BTE_BASE}/query", query)
    return _format_results(data, max_results)


@mcp.tool()
async def find_diseases_for_gene(
    gene_curie: str,
    max_results: int = 20,
) -> str:
    """Find diseases associated with a specific gene.

    Args:
        gene_curie: The gene identifier in CURIE format (e.g. 'NCBIGene:51322' for WAC)
        max_results: Maximum number of results to return (1-50)
    """
    query = _build_one_hop(
        subject_ids=[gene_curie],
        subject_categories=["biolink:Gene"],
        predicate="biolink:gene_associated_with_condition",
        object_ids=None,
        object_categories=["biolink:Disease"],
    )
    data = await _trapi_query(f"{BTE_BASE}/query", query)
    return _format_results(data, max_results)


@mcp.tool()
async def find_drugs_for_disease(
    disease_curie: str,
    max_results: int = 20,
) -> str:
    """Find drugs that may treat a specific disease.

    Args:
        disease_curie: The disease identifier in CURIE format
                       (e.g. 'MONDO:0014458' for DeSanto-Shinawi syndrome,
                       'MONDO:0005148' for type 2 diabetes)
        max_results: Maximum number of results to return (1-50)
    """
    query = _build_one_hop(
        subject_ids=None,
        subject_categories=["biolink:Drug"],
        predicate="biolink:treats",
        object_ids=[disease_curie],
        object_categories=["biolink:Disease"],
    )
    data = await _trapi_query(f"{BTE_BASE}/query", query)
    return _format_results(data, max_results)


@mcp.tool()
async def find_gene_pathways(
    gene_curie: str,
    max_results: int = 20,
) -> str:
    """Find biological pathways and processes a gene participates in.

    Args:
        gene_curie: The gene identifier in CURIE format (e.g. 'NCBIGene:51322' for WAC)
        max_results: Maximum number of results to return (1-50)
    """
    query = _build_one_hop(
        subject_ids=[gene_curie],
        subject_categories=["biolink:Gene"],
        predicate="biolink:participates_in",
        object_ids=None,
        object_categories=["biolink:BiologicalProcess"],
    )
    data = await _trapi_query(f"{BTE_BASE}/query", query)
    return _format_results(data, max_results)


@mcp.tool()
async def find_correlated_genes(
    gene_curie: str,
    max_results: int = 20,
) -> str:
    """Find genes that are correlated with or interact with a specific gene.

    Useful for understanding pathway neighbours and downstream effects.

    Args:
        gene_curie: The gene identifier in CURIE format (e.g. 'NCBIGene:51322' for WAC)
        max_results: Maximum number of results to return (1-50)
    """
    query = _build_one_hop(
        subject_ids=[gene_curie],
        subject_categories=["biolink:Gene"],
        predicate="biolink:correlated_with",
        object_ids=None,
        object_categories=["biolink:Gene"],
    )
    data = await _trapi_query(f"{BTE_BASE}/query", query)
    return _format_results(data, max_results)


@mcp.tool()
async def custom_query(
    subject_category: str,
    predicate: str,
    object_category: str,
    subject_id: str | None = None,
    object_id: str | None = None,
    max_results: int = 20,
) -> str:
    """Run a custom one-hop query against the Translator knowledge graph.

    For advanced queries not covered by the other tools. All values use
    the Biolink Model ontology.

    Common categories: biolink:Gene, biolink:Disease, biolink:Drug,
    biolink:ChemicalEntity, biolink:Pathway, biolink:BiologicalProcess,
    biolink:PhenotypicFeature, biolink:Protein

    Common predicates: biolink:affects, biolink:treats, biolink:causes,
    biolink:correlated_with, biolink:positively_regulates,
    biolink:negatively_regulates, biolink:participates_in,
    biolink:gene_associated_with_condition, biolink:interacts_with

    Common CURIE prefixes: NCBIGene: (genes), MONDO: (diseases),
    CHEBI: (chemicals), HP: (phenotypes), DRUGBANK: (drugs)

    Args:
        subject_category: Biolink category for the subject node
        predicate: Biolink predicate for the relationship
        object_category: Biolink category for the object node
        subject_id: Optional CURIE to pin the subject (e.g. 'NCBIGene:51322')
        object_id: Optional CURIE to pin the object (e.g. 'MONDO:0014458')
        max_results: Maximum number of results to return (1-50)
    """
    query = _build_one_hop(
        subject_ids=[subject_id] if subject_id else None,
        subject_categories=[subject_category],
        predicate=predicate,
        object_ids=[object_id] if object_id else None,
        object_categories=[object_category],
    )
    data = await _trapi_query(f"{BTE_BASE}/query", query)
    return _format_results(data, max_results)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
