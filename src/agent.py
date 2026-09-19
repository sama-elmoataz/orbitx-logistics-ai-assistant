from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from src.llm import create_llm
from src.memory import ConversationMemory
from src.tools import TOOLS


SYSTEM_PROMPT = """
You are OrbitAssist, the customer support assistant for OrbitX Logistics.

Help customers with shipping services, policies, shipment tracking,
delivery quotes, insurance, packaging, returns, claims, and delivery issues.

Use search_knowledge_base for questions about OrbitX policies,
services, shipping rules, packaging, insurance, returns, failed
deliveries, damaged shipments, lost shipments, and general company information.

Use track_shipment when the customer asks about a specific shipment,
its status, location, expected delivery, or tracking details.

Use estimate_delivery_quote when the customer asks for a shipping price
or wants to estimate the cost of sending a package.

For a delivery quote, you need:
- origin
- destination
- package weight
- service type

If insurance is requested, you also need the declared value.

Ask for missing information when necessary.

Never invent tracking information, prices, policies, or delivery dates.

Use the conversation history to understand follow-up questions.

Keep answers clear, friendly, and concise.
"""


class OrbitAssistAgent:

    def __init__(self):

        self.llm = create_llm()

        self.tools = TOOLS

        self.llm_with_tools = self.llm.bind_tools(
            self.tools
        )

        self.tool_map = {
            tool.name: tool
            for tool in self.tools
        }

        self.memory = ConversationMemory()

        self.max_iterations = 5


    def build_messages(
        self,
        user_input: str,
    ):

        messages = [
            SystemMessage(
                content=SYSTEM_PROMPT
            )
        ]

        for message in self.memory.get_history():

            if message["role"] == "user":

                messages.append(
                    HumanMessage(
                        content=message["content"]
                    )
                )

            elif message["role"] == "assistant":

                messages.append(
                    AIMessage(
                        content=message["content"]
                    )
                )

        messages.append(
            HumanMessage(
                content=user_input
            )
        )

        return messages


    def run_tool(
        self,
        tool_name: str,
        tool_args: dict,
    ):

        tool = self.tool_map.get(
            tool_name
        )

        if tool is None:
            return f"Tool {tool_name} was not found."

        try:
            return tool.invoke(
                tool_args
            )

        except Exception as error:
            return (
                f"Tool {tool_name} failed: "
                f"{str(error)}"
            )


    def chat(
        self,
        user_input: str,
    ):

        user_input = user_input.strip()

        if not user_input:
            return "Please enter a message."

        messages = self.build_messages(
            user_input
        )

        for _ in range(
            self.max_iterations
        ):

            response = self.llm_with_tools.invoke(
                messages
            )

            messages.append(
                response
            )

            if not response.tool_calls:

                answer = response.content

                if not isinstance(
                    answer,
                    str,
                ):
                    answer = str(
                        answer
                    )

                self.memory.add_user_message(
                    user_input
                )

                self.memory.add_assistant_message(
                    answer
                )

                return answer

            for tool_call in response.tool_calls:

                tool_name = tool_call["name"]

                tool_args = tool_call.get(
                    "args",
                    {},
                )

                tool_result = self.run_tool(
                    tool_name,
                    tool_args,
                )

                messages.append(
                    ToolMessage(
                        content=str(
                            tool_result
                        ),
                        tool_call_id=tool_call["id"],
                    )
                )

        return (
            "I couldn't complete the request. "
            "Please try again."
        )


def main():

    agent = OrbitAssistAgent()

    print("\nOrbitAssist")
    print("Type 'exit' to stop.\n")

    while True:

        user_input = input(
            "You: "
        ).strip()

        if user_input.lower() in [
            "exit",
            "quit",
        ]:
            print("OrbitAssist: Goodbye!")
            break

        response = agent.chat(
            user_input
        )

        print(
            f"\nOrbitAssist: {response}\n"
        )


if __name__ == "__main__":
    main()