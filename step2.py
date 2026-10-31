import ollama

def add(a : int, b : int) -> int:
    return a + b


tools = [
    {
        "type": "function",
        "function": {
            "name": "add",
            "description": "add two numbers(integer) and return their sum",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "integer", "description": "The first number"},
                    "b": {"type": "integer", "description": "The second number"}
                },
                "required": ["a", "b"]
            }
        }
    }
]


messages = [{"role": "user", "content": "what is 4821 + 7392 ?"}]

response = ollama.chat(
    model="qwen3.5:4b",
    messages=messages,
    tools=tools,
    think=False
)

messages.append(response.message)

if response.message.tool_calls:
    for call in response.message.tool_calls:
        result = add(**call.function.arguments)
        print("Ran tool:", call.function.name, "-->", result)
        messages.append(
            {"role" : "tool", "tool_name" : call.function.name, "content" : str(result)}
        )
    final = ollama.chat(model = "qwen3.5:4b", messages=messages, tools=tools, think=False)
    print("Final answer: ", final.message.content)
else:
    print(response.message.content)