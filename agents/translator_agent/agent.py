import os
import re

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

PORT = int(os.getenv("AGENT_PORT", "9004"))

# ------------------------------------------------------------------
# Fixed PT -> EN dictionary
# ------------------------------------------------------------------

_DICTIONARY = {
    "ola": "hello",
    "olá": "hello",
    "bom": "good",
    "dia": "day",
    "boa": "good",
    "tarde": "afternoon",
    "noite": "night",
    "obrigado": "thank you",
    "obrigada": "thank you",
    "sim": "yes",
    "nao": "no",
    "não": "no",
    "agente": "agent",
    "controle": "control",
    "plano": "plane",
    "teste": "test",
    "mundo": "world",
    "por": "for",
    "favor": "favor",
    "eu": "I",
    "sou": "am",
    "um": "a",
    "uma": "a",
}


def translate(text: str) -> str:
    tokens = re.findall(
        r"[\wÀ-ÿ]+|[^\w\s]",
        text,
        flags=re.UNICODE,
    )

    translated = []

    for token in tokens:
        translated.append(
            _DICTIONARY.get(
                token.lower(),
                token,
            )
        )

    return " ".join(translated)


# ------------------------------------------------------------------
# Executor
# ------------------------------------------------------------------

class TranslatorExecutor(AgentExecutor):

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

        translated = translate(text)

        await event_queue.enqueue_event(
            new_agent_text_message(translated)
        )

    async def cancel(self, context, event_queue):
        raise Exception("Cancel not supported")


# ------------------------------------------------------------------
# Skill
# ------------------------------------------------------------------

translator_skill = AgentSkill(
    id="translate_pt_en",
    name="Translate PT->EN",
    description=(
        "Naive Portuguese-to-English translator using a fixed "
        "word-by-word dictionary."
    ),
    tags=[
        "translation",
        "portuguese",
        "english",
        "testing",
    ],
    examples=[
        "olá mundo",
        "bom dia",
        "eu sou um agente",
        "obrigado",
    ],
)


# ------------------------------------------------------------------
# Agent Card
# ------------------------------------------------------------------

agent_card = AgentCard(
    name="Translator Agent",
    description=(
        "Fictitious test agent that performs naive word-for-word "
        "Portuguese-to-English translation using a fixed dictionary."
    ),
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
    skills=[translator_skill],
)


# ------------------------------------------------------------------
# Server
# ------------------------------------------------------------------

request_handler = DefaultRequestHandler(
    agent_executor=TranslatorExecutor(),
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