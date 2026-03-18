#!/usr/bin/env python3
"""
E2E test client: sends an evaluation request to the green agent and
prints the results.

The green agent will:
1. Send the problem to the purple agent
2. Receive a patch back
3. Evaluate the patch using Docker
4. Return structured results

Usage:
    uv run python test_e2e_client.py \
        --green-url http://127.0.0.1:9009 \
        --purple-url http://127.0.0.1:9010
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import httpx
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.types import Message, Part, Role, TextPart, DataPart

from uuid import uuid4


def create_message(text: str) -> Message:
    return Message(
        kind="message",
        role=Role.user,
        parts=[Part(TextPart(kind="text", text=text))],
        message_id=uuid4().hex,
    )


def merge_parts(parts: list[Part]) -> str:
    chunks = []
    for part in parts:
        if isinstance(part.root, TextPart):
            chunks.append(part.root.text)
        elif isinstance(part.root, DataPart):
            chunks.append(json.dumps(part.root.data, indent=2))
    return "\n".join(chunks)


async def run_e2e(green_url: str, purple_url: str, max_instances: int = 1) -> bool:
    # Build the eval request payload
    eval_request = {
        "participants": {},
        "config": {
            "max_instances": max_instances,
        },
    }
    if purple_url:
        eval_request["participants"]["coding_agent"] = purple_url

    print(f"Eval request:\n{json.dumps(eval_request, indent=2)}\n")

    async with httpx.AsyncClient(timeout=1800) as httpx_client:
        # Resolve green agent card
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=green_url)
        agent_card = await resolver.get_agent_card()
        print(f"Green agent: {agent_card.name} v{agent_card.version}")
        print(f"Skills: {[s.name for s in agent_card.skills]}\n")

        # Create client and send request
        config = ClientConfig(httpx_client=httpx_client, streaming=False)
        factory = ClientFactory(config)
        client = factory.create(agent_card)

        msg = create_message(json.dumps(eval_request))

        print("Sending request to green agent... (this may take a while if Docker eval runs)")
        print("-" * 60)

        final_response = ""
        structured_data = None

        async for event in client.send_message(msg):
            match event:
                case Message() as m:
                    text = merge_parts(m.parts)
                    print(f"[Message] {text}")
                    final_response += text

                case (task, update):
                    state = task.status.state.value
                    status_msg = ""
                    if task.status.message:
                        status_msg = merge_parts(task.status.message.parts)

                    if update:
                        print(f"[{state}] {status_msg}")
                    else:
                        # Final task state
                        print(f"\n[Final state: {state}]")
                        if status_msg:
                            print(f"  Status: {status_msg}")

                        if task.artifacts:
                            for artifact in task.artifacts:
                                print(f"\n  Artifact: {artifact.name or 'unnamed'}")
                                for part in artifact.parts:
                                    if isinstance(part.root, TextPart):
                                        final_response += part.root.text
                                        print(f"  {part.root.text}")
                                    elif isinstance(part.root, DataPart):
                                        structured_data = part.root.data
                                        print(f"  Data: {json.dumps(part.root.data, indent=4)}")

        print("-" * 60)

        # Check results
        if structured_data:
            accuracy = structured_data.get("accuracy", 0)
            passed = structured_data.get("passed", 0)
            total = structured_data.get("total", 0)
            results = structured_data.get("results", [])

            print(f"\nAccuracy: {accuracy:.1%} ({passed}/{total})")
            for r in results:
                status = "PASS" if r["passed"] else "FAIL"
                err = f" — {r['error']}" if r.get("error") else ""
                print(f"  [{status}] {r['instance_id']}{err}")

            if passed == total and total > 0:
                print("\n✓ All instances passed!")
                return True
            else:
                print(f"\n✗ {total - passed} instance(s) failed")
                return False
        else:
            print("\nNo structured results received from green agent.")
            print(f"Raw response: {final_response[:500]}")
            return False


def main():
    parser = argparse.ArgumentParser(description="E2E test client for SWE-bench green agent")
    parser.add_argument("--green-url", default="http://127.0.0.1:9011")
    parser.add_argument("--purple-url", default="")
    parser.add_argument("--max-instances", type=int, default=1)
    args = parser.parse_args()

    success = asyncio.run(run_e2e(args.green_url, args.purple_url, args.max_instances))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
