"""Validate existing Olist files or acquire a validated dataset from Kaggle."""

import argparse
import json
import hashlib
import shutil
import subprocess
import zipfile
import stat
import os
from pathlib import Path
import sys
import tempfile

from dataset_manifest import DatasetValidationError, SCHEMAS, validate_dataset

DATASET = "olist/brazilian-ecommerce"
MANIFEST = "dataset_manifest.json"


def _write_manifest(directory, manifest):
    contents = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=".manifest-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(contents)
        os.replace(temporary, directory / MANIFEST)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _download(directory):
    if directory.is_symlink():
        raise DatasetValidationError("data directory: symbolic links are not supported")
    directory = directory.resolve()
    if directory.exists():
        allowed = set(SCHEMAS) | {MANIFEST, ".gitkeep"}
        if not directory.is_dir() or any(
            p.name not in allowed or not p.is_file() or p.is_symlink()
            for p in directory.iterdir()
        ):
            raise DatasetValidationError(
                "data directory: refusing replacement of unrelated files"
            )
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".olist-acquire-", dir=directory.parent
    ) as temporary:
        work = Path(temporary)
        subprocess.run(
            [
                shutil.which("kaggle") or "kaggle",
                "datasets",
                "download",
                "-d",
                DATASET,
                "-p",
                str(work),
                "--force",
                "--quiet",
            ],
            check=True,
            capture_output=True,
            timeout=600,
        )
        archive_path = work / "brazilian-ecommerce.zip"
        candidate = work / "candidate"
        candidate.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            seen = set()
            for entry in archive.infolist():
                kind = stat.S_IFMT(entry.external_attr >> 16)
                if (
                    entry.filename not in SCHEMAS
                    or entry.filename in seen
                    or kind not in (0, stat.S_IFREG)
                ):
                    raise DatasetValidationError("unsafe or duplicate archive member")
                seen.add(entry.filename)
            for entry in archive.infolist():
                with archive.open(entry) as source, (candidate / entry.filename).open(
                    "wb"
                ) as target:
                    shutil.copyfileobj(source, target)
        with archive_path.open("rb") as stream:
            archive_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        manifest = validate_dataset(
            candidate,
            source={
                "mode": "download",
                "dataset": DATASET,
                "archive_sha256": archive_hash,
            },
        )
        _write_manifest(candidate, manifest)
        if (directory / ".gitkeep").is_file():
            shutil.copyfile(directory / ".gitkeep", candidate / ".gitkeep")
        # Outside the staging cleanup scope so failed rollback cannot delete prior data.
        backup = Path(tempfile.mkdtemp(prefix=".olist-previous-", dir=directory.parent))
        backup.rmdir()
        had_previous = directory.exists()
        if had_previous:
            directory.rename(backup)
        try:
            candidate.rename(directory)
        except OSError:
            if had_previous:
                try:
                    backup.rename(directory)
                except OSError:
                    raise DatasetValidationError(
                        f"Publication failed; previous dataset retained at {backup}"
                    ) from None
                raise DatasetValidationError(
                    "Publication failed; previous dataset restored"
                ) from None
            raise
        if backup.exists():
            try:
                shutil.rmtree(backup)
            except OSError:
                print(
                    f"Published valid dataset; previous backup retained at {backup}",
                    file=sys.stderr,
                )
        return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=["existing", "download"])
    parser.add_argument(
        "--data-dir", type=Path, default=Path(__file__).resolve().parents[1] / "data"
    )
    args = parser.parse_args()
    try:
        if args.mode == "download":
            manifest = _download(args.data_dir)
        else:
            manifest = validate_dataset(
                args.data_dir, source={"mode": "existing", "dataset": DATASET}
            )
            _write_manifest(args.data_dir, manifest)
    except DatasetValidationError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        print(
            "Dataset acquisition failed; inspect the destination and any retained .olist-previous-* backup.",
            file=sys.stderr,
        )
        return 1
    print(f"Validated 9 files; manifest: {args.data_dir / MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
