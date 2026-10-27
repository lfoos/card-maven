"""S3 adapter tests. Run against moto by default; set CARD_MAVEN_TEST_S3_ENDPOINT
(e.g. http://localhost:8333 with `make up`) to also run against real SeaweedFS."""

import os
import uuid
from collections.abc import Iterator

import boto3
import pytest
import requests
from moto import mock_aws

from card_maven.shared.config import Settings
from card_maven.shared.errors import DependencyUnavailableError
from card_maven.shared.storage.s3 import S3ObjectStore

REAL_ENDPOINT = os.environ.get("CARD_MAVEN_TEST_S3_ENDPOINT")


def _settings(bucket: str | None = None, **overrides: object) -> Settings:
    bucket = bucket or f"test-{uuid.uuid4().hex[:12]}"
    return Settings(_env_file=None, s3_bucket=bucket, **overrides)  # type: ignore[call-arg]


@pytest.fixture(params=["moto", "seaweedfs"])
def store(request: pytest.FixtureRequest) -> Iterator[S3ObjectStore]:
    if request.param == "moto":
        with mock_aws():
            store = S3ObjectStore.from_settings(_settings(s3_endpoint_url=None))
            store.ensure_bucket(cors_origins=["http://localhost:5173"])
            yield store
    else:
        if not REAL_ENDPOINT:
            pytest.skip(
                "set CARD_MAVEN_TEST_S3_ENDPOINT to test against a real S3-compatible store"
            )
        # One shared bucket: each SeaweedFS bucket reserves volumes, so a bucket
        # per test would exhaust a small local server.
        store = S3ObjectStore.from_settings(
            _settings("card-maven-test", s3_endpoint_url=REAL_ENDPOINT)
        )
        store.ensure_bucket(cors_origins=["http://localhost:5173"])
        yield store


def http() -> requests.Session:
    session = requests.Session()
    session.trust_env = False  # local endpoints must not go through a proxy
    return session


def post(
    store: S3ObjectStore,
    key: str,
    data: bytes,
    *,
    content_type: str = "image/jpeg",
    max_bytes: int = 1000,
    tamper: dict[str, str] | None = None,
) -> requests.Response:
    upload = store.presign_upload(
        key, content_type=content_type, max_bytes=max_bytes, expires_in=300
    )
    fields = {**upload.fields, **(tamper or {})}
    return http().post(
        upload.url,
        data=fields,
        files={"file": ("f", data, fields.get("Content-Type", content_type))},
    )


def test_presigned_post_round_trip(store: S3ObjectStore) -> None:
    key = f"users/u/{uuid.uuid4()}"
    assert post(store, key, b"\xff\xd8\xff" + b"x" * 10).status_code in (200, 204)
    info = store.head(key)
    assert info is not None
    assert (info.size, info.content_type) == (13, "image/jpeg")
    assert b"".join(store.iter_bytes(key, chunk_size=4)) == b"\xff\xd8\xff" + b"x" * 10
    assert (
        http().get(store.presign_download(key, expires_in=60)).content.startswith(b"\xff\xd8\xff")
    )
    store.delete(key)
    assert store.head(key) is None
    store.delete(key)  # deleting a missing key is fine


def test_policy_is_enforced_by_storage(store: S3ObjectStore) -> None:
    if store.bucket != "card-maven-test":
        pytest.skip("moto does not enforce POST policy conditions; covered against SeaweedFS")
    key = f"users/u/{uuid.uuid4()}"
    assert post(store, key, b"x" * 2000).status_code == 400  # too large
    assert post(store, key, b"<script>", tamper={"Content-Type": "text/html"}).status_code == 403
    assert post(store, key, b"x", tamper={"key": "users/someone-else/evil"}).status_code == 403
    assert store.head(key) is None
    assert store.head("users/someone-else/evil") is None


def test_ensure_bucket_is_idempotent(store: S3ObjectStore) -> None:
    store.ensure_bucket(cors_origins=["http://localhost:5173"])
    assert store.ensure_bucket(cors_origins=["http://localhost:5173"]) is False


def test_public_endpoint_used_for_presigning() -> None:
    with mock_aws():
        store = S3ObjectStore.from_settings(
            _settings(
                s3_endpoint_url="http://seaweedfs:8333",
                s3_public_endpoint_url="http://localhost:8333",
            )
        )
        assert store.presign_download("k", expires_in=60).startswith("http://localhost:8333/")
        assert store.presign_upload(
            "k", content_type="image/png", max_bytes=1, expires_in=60
        ).url.startswith("http://localhost:8333/")


def test_unreachable_storage_is_a_dependency_error() -> None:
    store = S3ObjectStore(
        "bucket",
        boto3.client(
            "s3",
            endpoint_url="http://127.0.0.1:1",
            region_name="us-east-1",
            aws_access_key_id="x",
            aws_secret_access_key="y",
            config=boto3.session.Config(connect_timeout=1, retries={"max_attempts": 1}),
        ),
    )
    with pytest.raises(DependencyUnavailableError):
        store.head("k")
    with pytest.raises(DependencyUnavailableError):
        store.delete("k")
    with pytest.raises(DependencyUnavailableError):
        list(store.iter_bytes("k"))


def test_server_errors_other_than_missing_are_dependency_errors() -> None:
    with mock_aws():
        store = S3ObjectStore.from_settings(_settings(s3_endpoint_url=None))  # bucket never created
        with pytest.raises(DependencyUnavailableError):
            store.head("k")
