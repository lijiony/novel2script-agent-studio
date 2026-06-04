from app.domain.schemas import RunStatus
from app.services.run_store import RunStore


def test_create_run_writes_manifest_and_input(tmp_path):
    store = RunStore(tmp_path)
    manifest = store.create_run("hello")
    assert manifest.status == RunStatus.queued
    assert store.read_input(manifest.run_id) == "hello"
    assert (tmp_path / manifest.run_id / "manifest.json").exists()


def test_artifact_whitelist(tmp_path):
    store = RunStore(tmp_path)
    manifest = store.create_run("hello")
    try:
        store.artifact_path(manifest.run_id, "../secret.txt")
    except ValueError as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("Path traversal artifact should fail")
