import os

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

PORT = int(os.getenv("AGENT_PORT", "9001"))


class EchoExecutor(AgentExecutor):

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:

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


echo_skill = AgentSkill(
    id="echo",
    name="Echo",
    description="Repeats exactly the text it receives.",
    tags=[
        "echo",
        "testing",
        "debug",
    ],
    examples=[
        "Hello",
        "Testing A2A",
        "Any text",
    ],
)

agent_card = AgentCard(
    name="Echo Agent",
    description="Fictitious test agent that echoes back the input text unchanged.",
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
    skills=[echo_skill],
)

request_handler = DefaultRequestHandler(
    agent_executor=EchoExecutor(),
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