"""Interactive terminal chat with Sokokali (no server needed).

Run from the ``backend`` directory:  python -m app.cli
"""

import asyncio
import logging

from app.core.config import get_settings
from app.core.container import build_container
from app.schemas.chat import ChatRequest


async def _run() -> None:
    logging.disable(logging.CRITICAL)
    container = build_container(get_settings())
    engine = f"Claude {container.llm.model}" if container.llm else "rule-based engine (no LLM configured)"
    print("=" * 50)
    print("SOKOKALI AI SYSTEM STARTED (simulated sports and forex data)")
    print(f"Conversation engine: {engine}")
    print("Type 'fixtures', 'demo' for a sample prediction, 'forex' for signals, or 'exit' to quit.")
    print("=" * 50)
    while True:
        try:
            message = input("Viewer: ").strip()
        except (EOFError, KeyboardInterrupt):
            message = "exit"
        if not message:
            continue
        if message.lower() == "exit":
            print("Sokokali: Kwaheri! See you next time!")
            await container.aclose()
            return
        if message.lower() == "demo":
            message = "Arsenal vs Chelsea, who will win?"
        if len(message) > container.settings.chat_max_message_length:
            print("Sokokali: That message is too long, try a shorter one.")
            continue
        response = await container.chat.handle(ChatRequest(message=message, viewer_id="cli"))
        print(f"Sokokali [{response.engine}]: {response.reply}")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
