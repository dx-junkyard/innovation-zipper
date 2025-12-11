from qdrant_client import QdrantClient
client = QdrantClient(host="localhost", port=6333)
print(client.query_points.__doc__)
