import os
import requests
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

api_key = os.getenv("OPENROUTER_API_KEY")
model = os.getenv("EMBEDDING_MODEL")

response = requests.post(
    f"https://openrouter.ai/api/v1/embeddings",
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    },
    # json={"model": model, "input": ["Michigan State University", "Machine Learning",""]},
    # HTTP status: 400
    # API error: {'message': '[\n  {\n    "origin": "string",\n    "code": "too_small",\n    "minimum": 1,\n    "inclusive": true,\n    "path": [\n      "input",\n      2\n    ],\n    "message": "Too small: expected string to have >=1 characters"\n  }\n]', 'code': 400}
    json={"model": model, "input": ["Michigan State University", "Machine Learning","  "]},
    timeout=30,
)

result = response.json()
print("HTTP status:", response.status_code)

if "error" in result:
    print("API error:", result["error"])
else:
    vector = result["data"][0]["embedding"]
    print("Vector length:", len(vector))
    print("First 5 numbers:", vector[:5])
    print("All zeros?", all(v == 0 for v in vector))