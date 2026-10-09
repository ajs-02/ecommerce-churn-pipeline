"""Acquisition acceptance tests through the real command-line boundary."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "olist_valid"
EXPECTED = json.loads((FIXTURE.parent / "olist_expected.json").read_text())


def run_cli(data, mode="existing", env=None):
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/download_data.py"),
            "--mode",
            mode,
            "--data-dir",
            str(data),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_existing_cli_writes_manifest_and_rerun_preserves_contents(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(FIXTURE, data)
    first = run_cli(data)
    assert first.returncode == 0, first.stderr
    manifest = json.loads((data / "dataset_manifest.json").read_text())
    assert len(manifest["files"]) == 9
    assert manifest["source"]["mode"] == "existing"
    for expected in EXPECTED:
        assert manifest["files"][expected["name"]]["sha256"] == expected["sha256"]
    before = {p.name: p.read_bytes() for p in data.iterdir()}
    second = run_cli(data)
    assert second.returncode == 0, second.stderr
    assert "Validated 9 files" in second.stdout
    assert "dataset_manifest.json" in second.stdout
    assert {p.name: p.read_bytes() for p in data.iterdir()} == before


def mock_kaggle(tmp_path, archive, *, fail=False):
    """Replace only the external Kaggle executable; real ZIP/filesystem are used."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    script = bin_dir / "fake_kaggle.py"
    script.write_text("""import os, pathlib, shutil, sys
args = sys.argv[1:]
assert args[:4] == ["datasets", "download", "-d", "olist/brazilian-ecommerce"]
assert "--force" in args and "--quiet" in args
if os.environ.get("FAKE_KAGGLE_FAIL"):
    print("credential-secret https://user:credential-secret@example.invalid", file=sys.stderr)
    sys.exit(1)
shutil.copyfile(os.environ["FAKE_KAGGLE_ARCHIVE"], pathlib.Path(args[args.index("-p")+1]) / "brazilian-ecommerce.zip")
""")
    if os.name == "nt":
        (bin_dir / "kaggle.cmd").write_text(f'@"{sys.executable}" "{script}" %*\n')
    else:
        executable = bin_dir / "kaggle"
        executable.write_text(f"#!{sys.executable}\n" + script.read_text())
        executable.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["FAKE_KAGGLE_ARCHIVE"] = str(archive)
    if fail:
        env["FAKE_KAGGLE_FAIL"] = "1"
    return env


def make_archive(path, source=FIXTURE):
    import zipfile

    with zipfile.ZipFile(path, "w") as archive:
        for csv in sorted(source.glob("*.csv")):
            archive.write(csv, csv.name)
    return path


def test_download_cli_publishes_validated_archive_and_repeats_identically(tmp_path):
    archive = make_archive(tmp_path / "valid.zip")
    env = mock_kaggle(tmp_path, archive)
    data = tmp_path / "downloaded"
    first = run_cli(data, "download", env)
    assert first.returncode == 0, first.stderr
    manifest = json.loads((data / "dataset_manifest.json").read_text())
    assert manifest["source"]["dataset"] == "olist/brazilian-ecommerce"
    assert manifest["source"]["mode"] == "download"
    for expected in EXPECTED:
        assert manifest["files"][expected["name"]]["sha256"] == expected["sha256"]
    before = {p.name: p.read_bytes() for p in data.iterdir()}
    second = run_cli(data, "download", env)
    assert second.returncode == 0, second.stderr
    assert before == {p.name: p.read_bytes() for p in data.iterdir()}


import pytest


@pytest.mark.parametrize(
    "member",
    [
        "../escaped.csv",
        "/escaped.csv",
        "C:/escaped.csv",
        "C:escaped.csv",
        "..\\escaped.csv",
        "\\\\server\\share\\escaped.csv",
        "nested/file.csv",
        "olist_orders_dataset.csv",
    ],
)
def test_unsafe_or_duplicate_archive_member_preserves_previous_dataset(
    tmp_path, member
):
    import zipfile

    data = tmp_path / "data"
    shutil.copytree(FIXTURE, data)
    assert run_cli(data).returncode == 0
    before = {p.name: p.read_bytes() for p in data.iterdir()}
    archive = make_archive(tmp_path / "unsafe.zip")
    with zipfile.ZipFile(archive, "a") as stream:
        stream.writestr(member, "secret-content")
    result = run_cli(data, "download", mock_kaggle(tmp_path, archive))
    assert result.returncode == 1
    assert "unsafe or duplicate archive member" in result.stderr
    assert "secret-content" not in result.stderr
    assert before == {p.name: p.read_bytes() for p in data.iterdir()}
    assert not (tmp_path / "escaped.csv").exists()
    assert not list(tmp_path.glob(".olist-acquire-*"))


def test_download_preserves_unrelated_local_files_by_refusing_replacement(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(FIXTURE, data)
    (data / "notes.txt").write_text("unrelated work")
    before = {p.name: p.read_bytes() for p in data.iterdir()}
    archive = make_archive(tmp_path / "valid.zip")
    result = run_cli(data, "download", mock_kaggle(tmp_path, archive))
    assert result.returncode == 1
    assert "unrelated files" in result.stderr
    assert before == {p.name: p.read_bytes() for p in data.iterdir()}


@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "truncated_csv",
        "truncated_zip",
        "download",
        "schema",
        "key",
        "money",
        "symlink",
    ],
)
def test_failed_candidate_never_replaces_previous_valid_dataset(tmp_path, failure):
    import stat
    import zipfile

    data = tmp_path / "data"
    shutil.copytree(FIXTURE, data)
    assert run_cli(data).returncode == 0
    before = {p.name: p.read_bytes() for p in data.iterdir()}
    candidate = tmp_path / "candidate"
    shutil.copytree(FIXTURE, candidate)
    path = candidate / "olist_orders_dataset.csv"
    if failure == "missing":
        path.unlink()
    elif failure == "truncated_csv":
        path.write_text(path.read_text()[:-10])
    elif failure == "schema":
        path.write_text(path.read_text().replace("order_status", "secret_header"))
    elif failure == "key":
        path.write_text(path.read_text().replace("c" * 32, "credential-secret"))
    elif failure == "money":
        path = candidate / "olist_order_items_dataset.csv"
        path.write_text(path.read_text().replace("10.00", "NaN"))
    archive = make_archive(tmp_path / "candidate.zip", candidate)
    if failure == "truncated_zip":
        archive.write_bytes(archive.read_bytes()[:40])
    elif failure == "symlink":
        archive.unlink()
        with zipfile.ZipFile(archive, "w") as stream:
            entry = zipfile.ZipInfo("olist_orders_dataset.csv")
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            stream.writestr(entry, "../outside")
    result = run_cli(
        data, "download", mock_kaggle(tmp_path, archive, fail=failure == "download")
    )
    assert result.returncode == 1
    assert result.stderr.strip()
    assert "credential-secret" not in result.stdout + result.stderr
    assert "secret_header" not in result.stdout + result.stderr
    assert before == {p.name: p.read_bytes() for p in data.iterdir()}
    assert not list(tmp_path.glob(".olist-acquire-*"))


def test_cli_help_and_argument_errors_are_truthful():
    help_result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/download_data.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "existing,download" in help_result.stdout
    invalid = subprocess.run(
        [sys.executable, str(ROOT / "scripts/download_data.py")],
        capture_output=True,
        text=True,
    )
    assert invalid.returncode == 2


def test_existing_invalid_dataset_keeps_previous_manifest(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(FIXTURE, data)
    assert run_cli(data).returncode == 0
    manifest = (data / "dataset_manifest.json").read_bytes()
    (data / "olist_sellers_dataset.csv").unlink()
    result = run_cli(data)
    assert result.returncode == 1
    assert "olist_sellers_dataset.csv" in result.stderr
    assert (data / "dataset_manifest.json").read_bytes() == manifest


@pytest.mark.parametrize("rollback_fails", [False, True])
def test_publication_failure_restores_or_retains_previous_dataset(
    tmp_path, rollback_fails
):
    data = tmp_path / "data"
    shutil.copytree(FIXTURE, data)
    assert run_cli(data).returncode == 0
    before = {p.name: p.read_bytes() for p in data.iterdir()}
    archive = make_archive(tmp_path / "valid.zip")
    env = mock_kaggle(tmp_path, archive)
    injection = tmp_path / "fault"
    injection.mkdir()
    (injection / "sitecustomize.py").write_text("""import os
from pathlib import Path
original = os.rename
def rename(source, target, *args, **kwargs):
    name = Path(source).name
    if name == "candidate" or (os.environ.get("FAIL_RESTORE") and name.startswith(".olist-previous-")):
        raise PermissionError("injected rename failure")
    return original(source, target, *args, **kwargs)
os.rename = rename
""")
    env["PYTHONPATH"] = str(injection)
    if rollback_fails:
        env["FAIL_RESTORE"] = "1"
    result = run_cli(data, "download", env)
    assert result.returncode == 1
    if rollback_fails:
        backups = list(tmp_path.glob(".olist-previous-*"))
        assert len(backups) == 1
        assert before == {p.name: p.read_bytes() for p in backups[0].iterdir()}
        assert str(backups[0]) in result.stderr
        assert "retained" in result.stderr
    else:
        assert before == {p.name: p.read_bytes() for p in data.iterdir()}
        assert "restored" in result.stderr
