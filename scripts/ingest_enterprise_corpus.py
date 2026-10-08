import asyncio
from pathlib import Path

import _bootstrap  # noqa: F401
from app.db import engine
from app.services.rag import get_rag_service


TENANT_ID = "00000000-0000-0000-0000-000000000001"
ADMIN_ID = "00000000-0000-0000-0000-000000000011"


async def main():
    root = Path("data/enterprise_docs")
    files = sorted(path for path in root.rglob("*.md") if path.name != "README.md")
    rag = get_rag_service()
    indexed = skipped = chunks = 0
    for index, path in enumerate(files, 1):
        relative = path.relative_to(root).as_posix()
        result = await rag.ingest_file(
            path, title=f"{path.parent.name}_{path.stem}", source_uri=f"enterprise://{relative}",
            tenant_id=TENANT_ID, owner_user_id=ADMIN_ID, visibility="TENANT",
        )
        if result.get("skipped"):
            skipped += 1
        else:
            indexed += 1
            chunks += int(result.get("chunks", 0))
        print(f"[{index}/{len(files)}] {relative} {'skipped' if result.get('skipped') else 'indexed'}")
    await engine.dispose()
    print(f"enterprise_corpus indexed={indexed} skipped={skipped} new_chunks={chunks} total_files={len(files)}")


if __name__ == "__main__":
    asyncio.run(main())
