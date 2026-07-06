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

PORT = int(os.getenv("AGENT_PORT", "9003"))


class ReverseTextExecutor(AgentExecutor):

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

        reversed_text = text[::-1]

        await event_queue.enqueue_event(
            new_agent_text_message(reversed_text)
        )

    async def cancel(self, context, event_queue):
        raise Exception("Cancel not supported")


reverse_skill = AgentSkill(
    id="reverse",
    name="Reverse Text",
    description="Returns the input text with its characters in reverse order.",
    tags=[
        "text",
        "reverse",
        "testing",
    ],
    examples=[
        "hello",
        "abcdef",
        "A2A Protocol",
    ],
)

agent_card = AgentCard(
    name="Reverse Text Agent",
    description="Fictitious test agent that reverses the characters of the input text.",
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
    skills=[reverse_skill],
)

request_handler = DefaultRequestHandler(
    agent_executor=ReverseTextExecutor(),
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