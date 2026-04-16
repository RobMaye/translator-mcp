# translator-mcp

An MCP (Model Context Protocol) server for the [NCATS Biomedical Data Translator](https://ui.transltr.io). Enables LLMs to query a federated biomedical knowledge graph — connecting genes, diseases, drugs, pathways, and phenotypes across hundreds of data sources.

No API key required. The Translator is fully open access.

## Quick Start

```bash
pip install translator-mcp
translator-mcp
```

Or add to your MCP config:
```json
{
  "mcpServers": {
    "translator": {
      "command": "translator-mcp"
    }
  }
}
```

## Example Queries

Once connected, ask your LLM things like:
- "What drugs might affect gene X?"
- "What diseases are associated with BRCA1?"
- "Find chemicals that positively regulate a given gene"
- "What biological pathways does TP53 participate in?"

## License

MIT
