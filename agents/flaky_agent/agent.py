import os
import random
import time

import uvicorn

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
)
from a2a.utils import new_agent_text_message

PORT = int(os.getenv("AGENT_PORT", "9005"))

FAILURE_RATE = float(os.getenv("FAILURE_RATE", "0.5"))

MIN_DELAY_MS = int(os.getenv("MIN_DELAY_MS", "0"))
MAX_DELAY_MS = int(os.getenv("MAX_DELAY_MS", "200"))


class FlakyExecutor(AgentExecutor):

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:

        # atraso artificial
        delay_ms = random.randint(MIN_DELAY_MS, MAX_DELAY_MS)
        time.sleep(delay_ms / 1000)

        # falha aleatória
        if random.random() < FAILURE_RATE:
            raise RuntimeError("simulated transient failure")

        message = context.message
        part = message.parts[0]

        if hasattr(part, "text"):
            text = part.text
        elif hasattr(part, "data"):
            text = str(part.data)
        else:
            text = str(part)

        await event_queue.enqueue_event(
            new_agent_text_message(text)
        )

    async def cancel(self, context, event_queue):
        raise Exception("Cancel not supported")


skill = AgentSkill(
    id="unreliable_echo",
    name="Unreliable Echo",
    description=f"Echoes the input but randomly fails about {int(FAILURE_RATE*100)}% of the time.",
    tags=["testing", "retry", "fault-injection"],
    examples=[
        "hello",
        "retry test",
        "this should echo"
    ],
)

agent_card = AgentCard(
    name="Flaky Agent",
    description="Agent used to test retry logic and reactive adaptation.",
    version="1.0.0",
    url=f"http://0.0.0.0:{PORT}",
    default_input_modes=["text"],
    default_output_modes=["text"],
    capabilities=AgentCapabilities(
        streaming=False,
        extended_agent_card=False,
    ),
    supported_interfaces=[
        AgentInterface(
            protocol_binding="JSONRPC",
            transport="HTTP",
            url=f"http://0.0.0.0:{PORT}",
        )
    ],
    skills=[skill],
)

request_handler = DefaultRequestHandler(
    agent_executor=FlakyExecutor(),
    task_store=InMemoryTaskStore(),
)

app = A2AStarletteApplication(
    agent_card=agent_card,
    http_handler=request_handler,
)

if __name__ == "__main__":
    uvicorn.run(
        app.build(),
        host="0.0.0.0",
        port=PORT,
    )