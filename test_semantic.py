import asyncio
from backend.services.search_service import SearchService
from backend.schemas.search import SearchRequest
from backend.database import AsyncSessionLocal

async def test():
    service = SearchService()
    async with AsyncSessionLocal() as db:
        request = SearchRequest(
            query="certificat ES006819 ATA 21 TS-INQ",
            limit=10,
            use_semantic=True,
            use_fts=False
        )
        response = await service.search(db, request)
        print("Nombre de résultats:", len(response.results))
        for r in response.results[:5]:
            print(r.document.id, r.document.filename, r.score, r.semantic_score)

asyncio.run(test())