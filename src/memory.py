from typing import Dict, List


class ConversationMemory:

    def __init__(self):

        self.messages: List[Dict[str, str]] = []


    def add_message(
        self,
        role: str,
        content: str,
    ):

        self.messages.append(
            {
                "role": role,
                "content": content,
            }
        )


    def add_user_message(
        self,
        content: str,
    ):

        self.add_message(
            role="user",
            content=content,
        )


    def add_assistant_message(
        self,
        content: str,
    ):

        self.add_message(
            role="assistant",
            content=content,
        )


    def get_history(
        self,
    ) -> List[Dict[str, str]]:

        return self.messages


    def clear(self):

        self.messages = []


    def __len__(self):

        return len(self.messages)


def main():

    memory = ConversationMemory()

    memory.add_user_message(
        "My name is Sama."
    )

    memory.add_assistant_message(
        "Nice to meet you, Sama!"
    )

    memory.add_user_message(
        "Can you track my shipment?"
    )

    memory.add_assistant_message(
        "Sure. Please send me your OrbitX tracking ID."
    )

    print("\nConversation History:\n")

    for message in memory.get_history():

        print(
            f"{message['role']}: "
            f"{message['content']}"
        )

    print(
        f"\nTotal messages: {len(memory)}"
    )


if __name__ == "__main__":
    main()