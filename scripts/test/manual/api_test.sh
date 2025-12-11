curl http://localhost:8086/api/v1/user-message \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "message": "週末はコーヒーを淹れて、その香りをたのしみながら読書をします。あなたは週末何をしますか？"
  }'
