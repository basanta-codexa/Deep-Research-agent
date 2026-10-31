import ollama

response = ollama.chat(model = "qwen3.5:4b",
            messages = [
                {"role": "system", "content": "A shirt costs 800 rupees after a 20% discount. What was the original price?"}
            ],
            think=True
)

print(response.message.content)
print(response.eval_count, " tokens generated")
print(response.total_duration / 1e9, "seconds total")