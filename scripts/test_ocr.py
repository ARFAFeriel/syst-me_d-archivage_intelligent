import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from backend.agents.ocr_agent import OCRAgent

async def test():
    agent = OCRAgent()
    path = r"\\?\C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft\TS-INP\Check C\ES001392\JobCard\698.pdf"
    print(f"Test : {path}")
    result = await agent.process(path)
    print(f"Conf        : {result.confidence:.1f}%")
    print(f"Engine      : {result.engine}")
    print(f"needs_review: {result.needs_review}")
    print(f"Texte       : {result.text[:400]}")

asyncio.run(test())