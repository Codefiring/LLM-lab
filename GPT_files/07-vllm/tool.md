curl -s http://127.0.0.1:8000/v1/responses \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3",
    "input": "列出当前目录文件",
    "tools": [
      {
        "type": "function",
        "name": "shell",
        "description": "Run a shell command",
        "parameters": {
          "type": "object",
          "properties": {
            "cmd": { "type": "string" }
          },
          "required": ["cmd"]
        }
      }
    ],
    "tool_choice": "auto"
  }' | jq