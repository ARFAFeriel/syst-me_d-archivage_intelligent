# watcher.py
import time
import asyncio
import sys
import httpx
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.core.pipeline import PipelineOrchestrator
from backend.database import AsyncSessionLocal

class ArchiveWatcher(FileSystemEventHandler):

    def __init__(self):
        self.processing = set()
        self.orchestrator = PipelineOrchestrator()
        # ✅ Boucle persistante — ne se ferme jamais
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def on_created(self, event):
        if event.is_directory:
            return
        if not event.src_path.endswith('.pdf'):
            return
        self.handle_new_file(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        if not event.dest_path.endswith('.pdf'):
            return
        self.handle_new_file(event.dest_path)

    def handle_new_file(self, file_path: str):
        if not self.wait_for_file(file_path):
            print(f"❌ Fichier inaccessible : {file_path}")
            return

        if file_path in self.processing:
            return
        self.processing.add(file_path)

        print(f"\n{'='*50}")
        print(f"🆕 Nouveau document détecté !")
        print(f"   Fichier : {Path(file_path).name}")
        print(f"   Dossier : {Path(file_path).parent.name}")
        print(f"{'='*50}")

        # ✅ Utiliser la boucle persistante
        self.loop.run_until_complete(self.process_async(file_path))
        self.processing.discard(file_path)

    async def process_async(self, file_path: str):
        try:
            with open(file_path, 'rb') as f:
                file_content = f.read()

            filename = Path(file_path).name
            print(f"   Lancement du pipeline...")

            async with AsyncSessionLocal() as db:
                result = await self.orchestrator.process_document(
                    db=db,
                    file_content=file_content,
                    filename=filename,
                    original_path=file_path,
                    file_size_kb=len(file_content) / 1024
                )

                if result.status.value == "duplicate":
                    print(f"   ⏭️  Doublon — ignoré")
                else:
                    print(f"   ✅ Archivé ! ID: {result.document_id}")
                    await self.notify_frontend(
                        result.document_id,
                        filename,
                        result.status.value
                    )

        except Exception as e:
            print(f"   ❌ Erreur : {e}")

    async def notify_frontend(self, doc_id, filename, status):
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    "http://localhost:8000/api/notify",
                    json={
                        "document_id": doc_id,
                        "filename": filename,
                        "status": status
                    },
                    timeout=3.0
                )
            print(f"   📡 Frontend notifié !")
        except Exception as e:
            print(f"   ⚠️  Notification échouée : {e}")

    def wait_for_file(self, file_path, timeout=30):
        start = time.time()
        last_size = -1
        while time.time() - start < timeout:
            try:
                current_size = Path(file_path).stat().st_size
                if current_size == last_size and current_size > 0:
                    return True
                last_size = current_size
                time.sleep(1)
            except FileNotFoundError:
                time.sleep(1)
        return False


def start_watcher(archive_root: str):
    path = Path(archive_root)
    if not path.exists():
        print(f"❌ Dossier introuvable : {archive_root}")
        return

    event_handler = ArchiveWatcher()
    observer = Observer()
    observer.schedule(event_handler, str(path), recursive=True)
    observer.start()

    print("="*50)
    print("  🔍 WATCHER ACTIF — Surveillance en temps réel")
    print("="*50)
    print(f"  Dossier : {archive_root}")
    print(f"  Mode    : Récursif + Async Pipeline")
    print(f"  Arrêt   : Ctrl+C")
    print("="*50)

    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        observer.stop()
        print("\n🛑 Watcher arrêté proprement.")
    observer.join()


if __name__ == "__main__":
    start_watcher(
        r"C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft"
    )