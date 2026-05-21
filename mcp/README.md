***REMOVED*** Structural Isomorphism — MCP Server

An [MCP](https://modelcontextprotocol.io) server that exposes the
**Structural Isomorphism** cross-domain engine as agent-callable tools.

It lets Claude (or any MCP-aware agent) ask *"what known phenomenon in
another field shares the same deep structure as my problem?"* — e.g. a bank
run is structurally a positive-feedback cascade, the same shape seen in
epidemics, traffic jams, and forest fires.

The server is a thin MCP wrapper over the deployed backend at
`https://beta.structural.bytedance.city`. It runs over **stdio** transport.

***REMOVED******REMOVED*** Tools

| Tool | What it does | Speed |
|------|--------------|-------|
| `search_isomorphism(query, top_k=8)` | Search for phenomena that share a deep structural pattern with `query`. Returns a ranked list (id/name/domain/description/score/relevance/cross_domain). | fast (<1s) |
| `get_phenomenon(phenomenon_id)` | Fetch full detail of one phenomenon plus its similar / same-structure neighbours. | fast |
| `analyze_isomorphism(question, phenomenon_id, lang="zh")` | Generate a deep 9-section cross-domain transfer report mapping a known phenomenon's structure onto the user's problem. | **slow, 3-4 min** |
| `find_isomorphism(question, lang="zh")` | One-shot: search for the best analogue, then run the full analysis on it. | **slow, 3-4 min** |

The 9 report sections: `shared_structure`, `your_problem_breakdown`,
`target_domain_intro`, `structural_mapping`, `borrowable_insights`,
`how_to_combine`, `research_directions`, `risks_and_limits`, `action_plan`.

Every tool returns a structured dict. On success `{"ok": true, ...}`; on
failure `{"ok": false, "error": "<kind>", "message": "..."}` — kinds include
`timeout`, `unreachable`, `http_error`, `not_found`, `bad_request`,
`empty_report`, `out_of_scope`. No raw exceptions ever surface to the agent.

***REMOVED******REMOVED*** Install

```bash
***REMOVED*** from the repo root, into the project venv
.venv/bin/pip install -r mcp/requirements.txt
```

Dependencies: `mcp` (official Python SDK) + `httpx`.

***REMOVED******REMOVED*** Configuration

The backend base URL is read from the `STRUCTURAL_API_BASE` environment
variable. Default: `https://beta.structural.bytedance.city`. Point it at a
local backend (`http://localhost:8000`) for development.

***REMOVED******REMOVED*** Use in Claude Code

Register the server (run once):

```bash
claude mcp add structural-isomorphism \
  -e STRUCTURAL_API_BASE=https://beta.structural.bytedance.city \
  -- /Users/dadamini/Projects/structural-isomorphism/.venv/bin/python \
     /Users/dadamini/Projects/structural-isomorphism/mcp/server.py
```

Then in a Claude Code session the four tools are available as
`mcp__structural-isomorphism__search_isomorphism`, etc.

***REMOVED******REMOVED*** Use in Claude Desktop

Add this to `claude_desktop_config.json` (macOS path:
`~/Library/Application Support/Claude/claude_desktop_config.json`) and
restart Claude Desktop. See `claude_desktop_config.example.json`:

```json
{
  "mcpServers": {
    "structural-isomorphism": {
      "command": "/Users/dadamini/Projects/structural-isomorphism/.venv/bin/python",
      "args": ["/Users/dadamini/Projects/structural-isomorphism/mcp/server.py"],
      "env": { "STRUCTURAL_API_BASE": "https://beta.structural.bytedance.city" }
    }
  }
}
```

> Use an **absolute** path to the venv `python` — the SDK launches the
> server as a subprocess and does not inherit your shell's `PATH`.

***REMOVED******REMOVED*** Testing

```bash
.venv/bin/python -m pytest mcp/test_server.py -q
```

23 unit tests, all mocked — no network. They cover HTTP success, 404,
timeout, unreachable, SSE multi-event assembly, partial reports, cached
inline reports, and empty results.

***REMOVED******REMOVED*** Notes

- `analyze_isomorphism` / `find_isomorphism` are intentionally slow (the
  report is LLM-generated). The HTTP timeout is 360s. Agents should call
  `search_isomorphism` for quick lookups and reserve analyze for when the
  user explicitly wants a deep report.
- Vector search is language-neutral; queries can be Chinese or English.
