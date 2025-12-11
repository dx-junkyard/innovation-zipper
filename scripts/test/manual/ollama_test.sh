curl http://localhost:11434/api/generate \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "model": "schroneko/llama-3.1-swallow-8b-instruct-v0.1:latest",
    "prompt": "日本の歴史を縄文時代から簡単におしえてください",
    "stream": false
  }'
