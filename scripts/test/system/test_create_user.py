import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.api.main import app

class TestCreateUser(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("app.api.main.DBClient")
    def test_create_user(self, mock_db_client):
        mock_repo = MagicMock()
        mock_repo.create_user.return_value = "test-user-id"
        mock_db_client.return_value = mock_repo

        response = self.client.post("/api/v1/users", json={"line_user_id": "line-123"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"user_id": "test-user-id"})
        mock_repo.create_user.assert_called_with(line_user_id="line-123")

if __name__ == '__main__':
    unittest.main()
