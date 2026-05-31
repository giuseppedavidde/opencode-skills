#!/usr/bin/env python3
"""
dispatch.py — Calcola chunk e genera prompt per parallel dispatch.
Dati item count, chunk_size, e parallel_limit, stima agenti, batches, wall time.
"""

import json
import math
import argparse


def calculate_chunks(items_count: int, chunk_size: int) -> int:
    """Number of chunks given items and chunk size."""
    return math.ceil(items_count / chunk_size)


def calculate_batches(agents: int, parallel_limit: int) -> int:
    """Number of parallel batches needed."""
    return math.ceil(agents / parallel_limit)


def estimate_time(agents: int, chunk_size: int, time_per_item: float,
                  parallel_limit: int, merge_overhead_s: float = 2.0) -> dict:
    """
    Estimate wall time for parallel dispatch.

    Args:
        agents: Number of agent chunks
        chunk_size: Items per chunk
        time_per_item: Seconds per item (average)
        parallel_limit: Max parallel agents
        merge_overhead_s: Seconds for merge phase

    Returns dict with timing breakdown.
    """
    batches = calculate_batches(agents, parallel_limit)
    time_per_chunk = chunk_size * time_per_item
    parallel_time = batches * time_per_chunk
    total_time = parallel_time + merge_overhead_s
    sequential_time = agents * chunk_size * time_per_item

    return {
        "agents": agents,
        "batches": batches,
        "time_per_chunk_s": round(time_per_chunk, 1),
        "parallel_wall_s": round(parallel_time, 1),
        "merge_overhead_s": merge_overhead_s,
        "total_parallel_s": round(total_time, 1),
        "sequential_s": round(sequential_time, 1),
        "speedup": round(sequential_time / total_time, 1) if total_time > 0 else 0
    }


def generate_task_prompt(skill_name: str, items: list, merge_keys: list | None = None,
                         extra_context: str = "") -> str:
    """Generate a task tool prompt for a chunk."""
    item_list = ", ".join(items) if isinstance(items[0], str) else json.dumps(items)
    keys = merge_keys or ["score"]

    prompt = f"""Run {skill_name} on these items: {item_list}.

Return a JSON array of results. Each result object MUST include these keys: {json.dumps(keys)}.
Output ONLY valid JSON — no explanation, no markdown fences, no preamble.

{extra_context}"""

    return prompt.strip()


def generate_agent_mention(chunk_num: int, total_chunks: int, skill_name: str,
                           items: list, output_path: str,
                           merge_keys: list | None = None) -> str:
    """Generate an @agent mention string for a chunk."""
    item_list = ", ".join(items) if isinstance(items[0], str) else json.dumps(items)
    keys = merge_keys or ["score"]

    prompt = f"""Run {skill_name} on these items: {item_list}.

Return a JSON array of results. Each result object MUST include these keys: {json.dumps(keys)}.
Write the JSON array to {output_path}.
Output ONLY valid JSON — no explanation, no markdown fences, no preamble."""

    return f"@agent Chunk {chunk_num} of {total_chunks}: {prompt}"


def format_items(items: list, split_by: str = "ticker") -> list:
    """Format items list for display."""
    if split_by == "market":
        return [f"--universe {item}" for item in items]
    return items


def suggest_chunk_size(split_by: str, total_items: int = None) -> int:
    """Suggest optimal chunk size based on split type."""
    defaults = {
        "ticker": 15,
        "market": 1,
        "file": 20,
        "chapter": 1,
        "query": 1,
    }
    default = defaults.get(split_by, 10)
    if total_items and total_items < default * 2:
        return max(1, total_items // 2)  # At least 2 chunks
    return default


def main():
    parser = argparse.ArgumentParser(description="Calculate dispatch parameters")
    parser.add_argument("--items-count", type=int, required=True, help="Total items to process")
    parser.add_argument("--chunk-size", type=int, help="Items per chunk (auto if omitted)")
    parser.add_argument("--parallel-limit", type=int, default=8, help="Max parallel agents")
    parser.add_argument("--time-per-item", type=float, default=2.0, help="Seconds per item")
    parser.add_argument("--split-by", default="ticker",
                        choices=["ticker", "market", "file", "chapter", "query"])
    parser.add_argument("--skill-name", help="Skill name for prompt generation")
    parser.add_argument("--items", nargs="*", help="Sample items for prompt generation")
    parser.add_argument("--generate", choices=["task", "agent", "none"], default="none",
                        help="Generate prompt for first chunk")
    args = parser.parse_args()

    if not args.chunk_size:
        args.chunk_size = suggest_chunk_size(args.split_by, args.items_count)

    agents = calculate_chunks(args.items_count, args.chunk_size)
    timing = estimate_time(agents, args.chunk_size, args.time_per_item, args.parallel_limit)

    print(f"Dispatch Plan")
    print(f"{'='*60}")
    print(f"  Items:        {args.items_count}")
    print(f"  Split by:     {args.split_by}")
    print(f"  Chunk size:   {args.chunk_size}")
    print(f"  Agents:       {timing['agents']}")
    print(f"  Batches:      {timing['batches']} (parallel_limit={args.parallel_limit})")
    print(f"  Time/chunk:   {timing['time_per_chunk_s']}s")
    print(f"  Parallel:     {timing['parallel_wall_s']}s")
    print(f"  Merge:        {timing['merge_overhead_s']}s")
    print(f"  Total:        {timing['total_parallel_s']}s")
    print(f"  Sequential:   {timing['sequential_s']}s")
    print(f"  Speedup:      {timing['speedup']}x")
    print()

    # Generate prompt for first chunk
    if args.generate != "none" and args.items and args.skill_name:
        chunk_items = format_items(args.items[:args.chunk_size], args.split_by)
        merge_keys = ["score"]

        if args.generate == "task":
            print("Task Prompt (for first chunk):")
            print("-" * 60)
            print(generate_task_prompt(args.skill_name, chunk_items, merge_keys))
        elif args.generate == "agent":
            print("Agent Mention (for first chunk):")
            print("-" * 60)
            print(generate_agent_mention(
                1, agents, args.skill_name, chunk_items,
                f"/tmp/orch_chunk_1.json", merge_keys
            ))

    # Summary for all chunks
    if args.items and args.generate != "none":
        print()
        print("All Chunks Summary:")
        print("-" * 60)
        formatted = format_items(args.items, args.split_by)
        for i in range(agents):
            start = i * args.chunk_size
            end = min(start + args.chunk_size, len(formatted))
            chunk = formatted[start:end]
            print(f"  Chunk {i+1}: {', '.join(str(x) for x in chunk)}")


if __name__ == "__main__":
    main()
