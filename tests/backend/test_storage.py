"""Storage boundary tests. S3 is exercised through real boto3 calls against
moto's in-process S3 mock, so no AWS account or network is needed."""

import boto3
import pytest
from moto import mock_aws

from quantlab.config import Settings
from quantlab.storage import LocalStorage, S3Storage, StorageError, build_storage


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


def test_local_roundtrip_and_key_safety(tmp_path):
    st = LocalStorage(tmp_path)
    st.put_bytes("datasets/a.csv", b"x", "text/csv")
    assert st.get_bytes("datasets/a.csv") == b"x" and st.exists("datasets/a.csv")
    assert not st.exists("datasets/missing.csv")
    with pytest.raises(StorageError):
        st.get_bytes("datasets/missing.csv")
    for bad in ("../escape", "/abs/path", "a/../../b"):
        with pytest.raises(StorageError):
            st.put_bytes(bad, b"x", "text/plain")


def test_s3_roundtrip_with_prefix_and_encryption(aws_env):
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="ql-test")
        st = S3Storage("ql-test", "quantlab/", client=client)
        st.put_bytes("datasets/abc.csv", b"date,open\n", "text/csv")
        head = client.head_object(Bucket="ql-test", Key="quantlab/datasets/abc.csv")
        assert head["ContentType"] == "text/csv"
        assert head["ServerSideEncryption"] == "AES256"
        assert st.get_bytes("datasets/abc.csv") == b"date,open\n"
        assert st.exists("datasets/abc.csv") and not st.exists("datasets/nope.csv")
        with pytest.raises(StorageError, match="not found"):
            st.get_bytes("datasets/nope.csv")


def test_s3_missing_bucket_raises_storage_error(aws_env):
    with mock_aws():
        st = S3Storage("does-not-exist", client=boto3.client("s3", region_name="us-east-1"))
        with pytest.raises(StorageError, match="upload failed"):
            st.put_bytes("k", b"x", "text/plain")


def test_build_storage_selects_backend(aws_env, tmp_path):
    assert isinstance(build_storage(Settings(local_storage_dir=str(tmp_path))), LocalStorage)
    with mock_aws():
        st = build_storage(Settings(storage_backend="s3", s3_bucket="b"))
        assert isinstance(st, S3Storage)
    with pytest.raises(StorageError, match="S3_BUCKET"):
        build_storage(Settings(storage_backend="s3", s3_bucket=""))
