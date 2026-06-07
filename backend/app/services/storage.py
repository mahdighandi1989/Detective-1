import logging
from typing import IO, Optional, Union
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

from app.core.config import settings

logger = logging.getLogger(__name__)

class StorageService:
    """
    Service for interacting with S3-compatible object storage (e.g., MinIO or AWS S3).
    """
    def __init__(self):
        # Initialize S3 client for MinIO compatibility.
        # For MinIO, endpoint_url is crucial. For AWS S3, it can often be omitted
        # if using standard AWS regions, but explicit endpoint_url is more robust.
        # Use a custom Config to set signature_version which can be necessary for MinIO.
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.MINIO_ENDPOINT_URL,
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
            config=Config(signature_version="s3v4")
        )
        self.bucket_name = settings.MINIO_BUCKET_NAME
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """Ensures the S3 bucket exists. Creates it if it doesn't."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.debug(f"Bucket '{self.bucket_name}' already exists.")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == '404' or error_code == 'NoSuchBucket':
                # Bucket does not exist, create it
                logger.info(f"Bucket '{self.bucket_name}' not found, attempting to create.")
                try:
                    # AWS S3 requires LocationConstraint for regions other than 'us-east-1'
                    # MinIO does not typically need it.
                    # If using AWS S3 in a specific region, you might need:
                    # CreateBucketConfiguration={'LocationConstraint': settings.AWS_REGION}
                    self.s3_client.create_bucket(Bucket=self.bucket_name)
                    logger.info(f"Bucket '{self.bucket_name}' created successfully.")
                except ClientError as ce:
                    logger.error(f"Error creating bucket '{self.bucket_name}': {ce}")
                    raise
            else:
                logger.error(f"Error checking bucket '{self.bucket_name}': {e}")
                raise

    def upload_file(self, file_content: Union[IO[bytes], bytes], object_name: str, content_type: Optional[str] = None) -> str:
        """
        Uploads a file (from a file-like object or bytes) to the S3 bucket.

        Args:
            file_content: The content of the file to upload (file-like object or bytes).
            object_name: The name of the object (file) in the bucket.
            content_type: Optional MIME type of the content. If not provided, boto3 might infer it.

        Returns:
            The URL or key of the uploaded object.
        """
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type

            if isinstance(file_content, bytes):
                self.s3_client.put_object(Bucket=self.bucket_name, Key=object_name, Body=file_content, **extra_args)
            else: # Assume IO[bytes]
                self.s3_client.upload_fileobj(file_content, self.bucket_name, object_name, ExtraArgs=extra_args)
            
            logger.info(f"File '{object_name}' uploaded successfully to bucket '{self.bucket_name}'.")
            # For MinIO, the endpoint_url + bucket + key often forms the access URL
            # For AWS S3, it's more complex, but the Key is the identifier.
            return f"{settings.MINIO_ENDPOINT_URL}/{self.bucket_name}/{object_name}" if settings.MINIO_ENDPOINT_URL else object_name
        except ClientError as e:
            logger.error(f"Error uploading file '{object_name}': {e}")
            raise

    def download_file(self, object_name: str) -> Optional[bytes]:
        """
        Downloads a file from the S3 bucket.

        Args:
            object_name: The name of the object (file) to download.

        Returns:
            The content of the file as bytes, or None if not found.
        """
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=object_name)
            file_content = response['Body'].read()
            logger.info(f"File '{object_name}' downloaded successfully from bucket '{self.bucket_name}'.")
            return file_content
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == '404' or error_code == 'NoSuchKey':
                logger.warning(f"File '{object_name}' not found in bucket '{self.bucket_name}'.")
                return None
            else:
                logger.error(f"Error downloading file '{object_name}': {e}")
                raise

    def delete_file(self, object_name: str) -> bool:
        """
        Deletes a file from the S3 bucket.

        Args:
            object_name: The name of the object (file) to delete.

        Returns:
            True if the file was deleted successfully, False otherwise.
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=object_name)
            logger.info(f"File '{object_name}' deleted successfully from bucket '{self.bucket_name}'.")
            return True
        except ClientError as e:
            logger.error(f"Error deleting file '{object_name}': {e}")
            return False