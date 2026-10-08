import asyncio
from pathlib import Path
import _bootstrap  # noqa: F401
from app.services.rag import get_rag_service

async def main():
    rag = get_rag_service()
    for path in sorted(Path('data/sample_docs').glob('*')):
        if path.suffix.lower() in {'.md','.txt','.pdf','.docx'}:
            result = await rag.ingest_file(path, title=path.stem, source_uri=str(path))
            print(path.name, result)

if __name__ == '__main__':
    asyncio.run(main())
