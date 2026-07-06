import ast
import json
import operator
import os

import a2a

print(a2a.__file__)
print(a2a.__path__)
import pkgutil

print([m.name for m in pkgutil.iter_modules(a2a.__path__)])

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

PORT = int(os.getenv("AGENT_PORT", "9002"))

# ------------------------------------------------------
# Safe evaluator
# ------------------------------------------------------

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _safe_eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value

    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](
            _safe_eval(node.left),
            _safe_eval(node.right),
        )

    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](
            _safe_eval(node.operand),
        )

    raise ValueError("Unsupported or unsafe expression")


def evaluate(expression: str):
    tree = ast.parse(expression, mode="eval")
    return _safe_eval(tree.body)


# ------------------------------------------------------
# Executor
# ------------------------------------------------------

class CalculatorExecutor(AgentExecutor):

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

        expression = text

        try:
            parsed = json.loads(text)

            if isinstance(parsed, dict):
                expression = parsed.get("expression", text)

        except Exception:
            pass

        try:
            result = evaluate(expression)

            response = {
                "expression": expression,
                "result": result,
            }

            await event_queue.enqueue_event(
                new_agent_text_message(
                    json.dumps(response)
                )
            )

        except Exception as e:

            await event_queue.enqueue_event(
                new_agent_text_message(
                    f"Error: Could not evaluate '{expression}': {e}"
                )
            )

    async def cancel(self, context, event_queue):
        raise Exception("Cancel not supported")


# ------------------------------------------------------
# Agent Card
# ------------------------------------------------------

calculator_skill = AgentSkill(
    id="calculate",
    name="Calculate",
    description="Evaluates arithmetic expressions safely.",
    tags=[
        "calculator",
        "math",
        "arithmetic",
    ],
    examples=[
        "2+2",
        "10*(3-1)",
        '{"expression":"5**4"}',
    ],
)

agent_card = AgentCard(
    name="Calculator Agent",
    description="Evaluates arithmetic expressions (+, -, *, /, **, parentheses).",
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
    skills=[calculator_skill],
)

# ------------------------------------------------------
# Server
# ------------------------------------------------------

request_handler = DefaultRequestHandler(
    agent_executor=CalculatorExecutor(),
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