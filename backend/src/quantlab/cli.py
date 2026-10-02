"""Operational commands.

    quantlab migrate                      # Alembic upgrade + LangGraph checkpoint tables
    quantlab import-manifest PATH.json    # import output of scripts/validate-dataset.mjs

`migrate` is the only command that changes the schema. In Docker Compose and on
ECS it runs as a one-off task before the API and worker start, so services never
race to migrate.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ALEMBIC_INI = Path(
    os.environ.get("ALEMBIC_INI", Path(__file__).resolve().parents[2] / "alembic.ini")
)


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    from quantlab.workflow.runner import setup_checkpointer

    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    setup_checkpointer()
    print("migrations applied; LangGraph checkpoint tables ready")


def import_manifest_cmd(path: str) -> int:
    from quantlab.datasets import DatasetImportError, DuplicateDatasetError, import_manifest
    from quantlab.db import transaction
    from quantlab.storage import get_storage

    try:
        with transaction() as s:
            ds = import_manifest(s, get_storage(), Path(path))
            print(
                f"imported dataset {ds.id}: {ds.name} v{ds.version} ({ds.row_count} rows, "
                f"{ds.start_date}..{ds.end_date}, sha256 {ds.content_sha256[:12]})"
            )
    except DuplicateDatasetError as exc:
        print(f"already imported: dataset {exc.existing_id} ({exc.existing_label}); nothing to do")
    except (OSError, ValueError, KeyError) as exc:
        if not isinstance(exc, DatasetImportError):
            print(f"import failed: cannot read manifest {path}: {exc!r}", file=sys.stderr)
            return 1
        print(f"import failed: {exc}", file=sys.stderr)
        if exc.report:
            for e in exc.report.errors:
                print(f"  row {e.row} {e.column or ''}: {e.message}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="quantlab")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    imp = sub.add_parser("import-manifest")
    imp.add_argument("manifest")
    args = parser.parse_args()
    if args.cmd == "migrate":
        migrate()
    elif args.cmd == "import-manifest":
        sys.exit(import_manifest_cmd(args.manifest))


if __name__ == "__main__":
    main()
