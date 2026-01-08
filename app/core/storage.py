import boto3
from botocore.client import Config
from config import settings
import logging
import os

logger = logging.getLogger(__name__)

class StorageClient:
    def __init__(self):
        # 1. 内部操作用クライアント (Dockerネットワーク内の通信用: http://minio:9000)
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION_NAME,
            config=Config(signature_version="s3v4"),
            use_ssl=settings.S3_USE_SSL
        )

        # 2. [追加] 署名生成専用クライアント (ブラウザ用URL: http://localhost:9000)
        # これを使わないと、Hostヘッダーの不一致で署名エラーになります
        self.signer_client = boto3.client(
            "s3",
            endpoint_url=settings.S3_PUBLIC_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION_NAME,
            config=Config(signature_version="s3v4"),
            use_ssl=settings.S3_USE_SSL
        )

        self.bucket_name = settings.S3_BUCKET_NAME
        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except Exception:
            try:
                self.s3_client.create_bucket(Bucket=self.bucket_name)
                logger.info(f"Created bucket: {self.bucket_name}")
            except Exception as e:
                logger.error(f"Failed to create bucket {self.bucket_name}: {e}")
                # In production, we might want to raise, but for now log error.

    def upload_file(self, file_obj, object_name: str, content_type: str = "application/pdf"):
        try:
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                object_name,
                ExtraArgs={"ContentType": content_type}
            )
            logger.info(f"Uploaded {object_name} to {self.bucket_name}")
            return True
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            raise e

    def generate_presigned_url(self, object_name: str, expiration: int = 300) -> str:
        try:
            # 修正: self.signer_client を使用してURLを生成する
            url = self.signer_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": object_name},
                ExpiresIn=expiration
            )
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            return ""

    def download_file(self, object_name: str, destination_path: str):
        try:
            self.s3_client.download_file(self.bucket_name, object_name, destination_path)
            logger.info(f"Downloaded {object_name} to {destination_path}")
            return True
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise e

storage = StorageClient()
