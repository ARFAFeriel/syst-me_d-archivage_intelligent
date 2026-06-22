import asyncio, sys
sys.path.insert(0, ".")
async def run():
    from backend.services.search_service import SearchService
    from backend.schemas.search import SearchRequest
    from backend.database import AsyncSessionLocal
    svc = SearchService()
    async with AsyncSessionLocal() as db:
        req = SearchRequest(query="certificats ATA 26 protection incendie TS-INQ", use_semantic=True, use_fts=True, limit=5, offset=0)
        resp = await svc.search(db, req)
        docs = resp.results if hasattr(resp, "results") else (resp.get("results", []) if isinstance(resp, dict) else [])
        print(f"Type resp: {type(resp)}")
        print(f"Nb docs: {len(docs)}")
        for i, d in enumerate(docs[:3]):
            print(f"\n--- Doc {i+1} ---")
            if hasattr(d, "__dict__"):
                for k, v in d.__dict__.items():
                    if not k.startswith("_"):
                        print(f"  {k}: {v}")
            else:
                print(d)
asyncio.run(run())
