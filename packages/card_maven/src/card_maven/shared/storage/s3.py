"""S3 adapter. Works with AWS S3 and S3-compatible stores (SeaweedFS locally)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from card_maven.shared.errors import DependencyUnavailableError
from card_maven.shared.storage.port import ObjectInfo, PresignedUpload

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

    from card_maven.shared.config import Settings

_MISSING = {"404", "NoSuchKey", "NotFound"}


def _client(settings: Settings, endpoint_url: str | None) -> S3Client:
    # Static keys are for local S3-compatible stores only; on AWS they are unset
    # and boto3's default credential chain (IAM role via IRSA) is used.
    key_id = settings.s3_access_key_id
    secret = settings.s3_secret_access_key
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=settings.s3_region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if endpoint_url else "auto"},
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=3,
            read_timeout=10,
        ),
        aws_access_key_id=key_id.get_secret_value() if key_id else None,
        aws_secret_access_key=secret.get_secret_value() if secret else None,
    )


class S3ObjectStore:
    def __init__(
        self, bucket: str, client: S3Client, *, presign_client: S3Client | None = None
    ) -> None:
        self.bucket = bucket
        self._client = client
        # Presigned URLs embed the host they were signed for. Locally, the API
        # reaches storage at an internal hostname but the browser needs a public
        # one, so presigning can use a differently configured client.
        self._presign = presign_client or client

    @classmethod
    def from_settings(cls, settings: Settings) -> S3ObjectStore:
        client = _client(settings, settings.s3_endpoint_url)
        public = settings.s3_public_endpoint_url
        presign = (
            _client(settings, public) if public and public != settings.s3_endpoint_url else None
        )
        return cls(settings.s3_bucket, client, presign_client=presign)

    def presign_upload(
        self, key: str, *, content_type: str, max_bytes: int, expires_in: int
    ) -> PresignedUpload:
        post = self._presign.generate_presigned_post(
            Bucket=self.bucket,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, max_bytes],
            ],
            ExpiresIn=expires_in,
        )
        return PresignedUpload(url=post["url"], fields=dict(post["fields"]))

    def head(self, key: str) -> ObjectInfo | None:
        try:
            response = self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if str(exc.response.get("Error", {}).get("Code")) in _MISSING:
                return None
            raise DependencyUnavailableError("object storage request failed") from exc
        except BotoCoreError as exc:
            raise DependencyUnavailableError("object storage is unreachable") from exc
        return ObjectInfo(
            size=int(response["ContentLength"]), content_type=response.get("ContentType")
        )

    def iter_bytes(self, key: str, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        try:
            body = self._client.get_object(Bucket=self.bucket, Key=key)["Body"]
        except (ClientError, BotoCoreError) as exc:
            raise DependencyUnavailableError("object storage read failed") from exc
        try:
            yield from body.iter_chunks(chunk_size)
        finally:
            body.close()

    def presign_download(self, key: str, *, expires_in: int) -> str:
        url: str = self._presign.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_in
        )
        return url

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError) as exc:
            raise DependencyUnavailableError("object storage delete failed") from exc

    def ensure_bucket(self, *, cors_origins: list[str]) -> bool:
        """Create the bucket if needed and allow browser uploads from ``cors_origins``.

        For local and test environments; on AWS, Terraform owns the bucket.
        Returns ``True`` if the bucket was created.
        """
        created = False
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self.bucket)
            created = True
        self._client.put_bucket_cors(
            Bucket=self.bucket,
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedOrigins": cors_origins,
                        "AllowedMethods": ["GET", "POST", "PUT"],
                        "AllowedHeaders": ["*"],
                        "ExposeHeaders": ["ETag"],
                        "MaxAgeSeconds": 600,
                    }
                ]
            },
        )
        return created
