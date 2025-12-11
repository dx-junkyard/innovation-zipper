#!/bin/bash

# Service Catalog Reset Script
# This script calls the API to reset the service catalog (MySQL and Qdrant).

API_URL="http://localhost:8087/api/v1/service-catalog/reset"

echo "Resetting Service Catalog..."
response=$(curl -s -X DELETE "$API_URL")

echo "Response:"
echo "$response"

if [[ "$response" == *"success"* ]]; then
    echo "[✓] Service Catalog reset successfully."
else
    echo "[✗] Failed to reset Service Catalog."
    exit 1
fi
