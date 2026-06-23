# Global Rules

## Python Virtual Environment Mandatory
CRITICAL: Before ANY Python operation (install, run, test), load @skills/python-venv. You MUST use a virtual environment. Never `pip install` on the system Python.

## Python Development Standards
CRITICAL: Whenever working with Python, you MUST load and strictly adhere to the instructions defined in @skills/python-pydantic.

This includes:
- Mandatory use of Pydantic for data models.
- Extensive use of type hinting.
- Ensuring all code is PEP 8 compliant and pythonic.
- Verifying all Python code with `pylint` before proposing it to the user.

## Graphify Knowledge Graph
CRITICAL: Whenever you need to understand a codebase, project architecture, or file relationships, load the @skills/graphify skill and use `/graphify .` to build a knowledge graph. This turns any folder into a queryable graph with community detection, god nodes, and surprising connections.

## Headroom Compression — MANDATORY
CRITICAL: You MUST use headroom to compress content and minimize token usage at ALL times:

1. **Compress large tool outputs** — After any tool returns >2000 chars of output, compress it with `headroom_compress` BEFORE reasoning over it. Use `headroom_retrieve` with the hash if you later need the full original.

2. **Compress before grep/read results** — Large file reads, search results, logs, JSON outputs must be compressed first.

3. **Use `headroom_stats` periodically** — Check savings at the end of session or after heavy tool usage.

4. **Always prefer compression over truncation** — Never truncate with head/tail when you can compress and retrieve on demand.
