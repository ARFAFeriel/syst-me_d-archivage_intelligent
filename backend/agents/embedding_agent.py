"""
Agent Embedding
Génère des vecteurs 384d avec sentence-transformers/all-MiniLM-L6-v2
Stockés dans PostgreSQL via pgvector pour recherche sémantique
"""
from loguru import logger
from typing import Optional
import numpy as np


class EmbeddingAgent:
    """
    Agent Embedding — sentence-transformers MiniLM-L6-v2.
    Génère des vecteurs 384 dimensions à partir du texte OCR + métadonnées.
    """

    def __init__(self):
        self.name = "Embedding Agent"
        self._model = None
        self.dim = 384
        logger.info(f"[{self.name}] Initialisé — chargement lazy (premier appel)")
        # Pas de préchargement au démarrage

    def _get_model(self):
        """Lazy load du modèle sentence-transformers."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                from backend.config import settings
                logger.info(f"[{self.name}] Chargement modèle {settings.embedding_model}...")
                self._model = SentenceTransformer(settings.embedding_model)
                logger.info(f"[{self.name}] Modèle chargé ({self.dim}d)")
            except Exception as e:
                logger.error(f"[{self.name}] Impossible de charger le modèle: {e}")
                self._model = False
        return self._model if self._model else None

    def _build_embedding_text(
        self,
        ocr_text: str,
        filename: str,
        doc_type: str = "",
        category: str = "",
        aircraft: str = "",
        es_ref: str = "",
        ata: str = "",
        sb_ad: str = "",
        semantic_prefix: str = "",   # ← PROFIL : préfixe sémantique du profil
    ) -> str:
        """
        Construit le texte à encoder.
        Combine métadonnées structurées + début du texte OCR.
        Les métadonnées sont répétées pour leur donner plus de poids.

        semantic_prefix : vient du ProcessingProfile — guide la sémantique de l'embedding.
        Ex : "Job Card maintenance task: " oriente le vecteur vers le domaine MRO tâche.
        Ex : "Service bulletin airworthiness: " oriente vers conformité réglementaire.
        Technique issue des "instruction embeddings" (Instructor, E5).
        """
        parts = []

        # Préfixe sémantique du profil (si fourni) — placé EN TÊTE pour maximum d'influence
        if semantic_prefix:
            parts.append(semantic_prefix.strip())

        # Métadonnées structurées (haute importance — répétées 2x)
        meta_parts = []
        if aircraft:
            meta_parts.append(f"aircraft {aircraft}")
        if doc_type:
            meta_parts.append(f"type {doc_type}")
        if category:
            meta_parts.append(f"category {category}")
        if es_ref:
            meta_parts.append(f"reference {es_ref}")
        if ata:
            meta_parts.append(f"ata {ata}")
        if sb_ad:
            meta_parts.append(f"service bulletin airworthiness directive {sb_ad}")
        if filename:
            parts.append(f"filename {filename}")

        if meta_parts:
            meta_str = " ".join(meta_parts)
            parts.append(meta_str)
            parts.append(meta_str)  # Répéter pour augmenter le poids

        # Texte OCR (premiers 512 tokens environ = ~400 mots)
        if ocr_text:
            text_preview = ocr_text[:2000].replace("\n", " ").strip()
            parts.append(text_preview)

        return " ".join(parts)[:4000]

    async def embed_document(
        self,
        text: str = "",
        filename: str = "",
        ner_result=None,
        doc_type: str = "",
        category: str = "",
        aircraft: str = "",
        es_ref: str = "",
        ata: str = "",
        sb_ad: str = "",
        semantic_prefix: str = "",   # ← PROFIL : préfixe sémantique du ProcessingProfile
        # Alias rétrocompat (ancienne signature)
        ocr_text: str = "",
    ) -> Optional[list[float]]:
        """
        Génère l'embedding d'un document.
        Retourne une liste de 384 floats, ou None si erreur.

        semantic_prefix : transmis par pipeline.py depuis profile.embedding.semantic_prefix.
        Exemples réels NouvelAir :
          "Job Card maintenance task: "        → pour ES001778 (Check A TS-INP)
          "Work order maintenance: "           → pour ES001392 (Check C TS-INQ)
          "Service bulletin airworthiness: "   → pour SB A320-27-1208
          "Aircraft delivery document: "       → pour les 1758 docs Old doc
        """
        model = self._get_model()
        if model is None:
            logger.warning(f"[{self.name}] Modèle non disponible, embedding ignoré")
            return None

        # Fusionner les deux noms de paramètre (rétrocompat)
        raw_text = text or ocr_text

        # Extraire les champs NER si fournis
        if ner_result is not None:
            aircraft  = aircraft  or getattr(ner_result, "aircraft_registration", "") or ""
            es_ref    = es_ref    or getattr(ner_result, "es_reference", "")           or ""
            ata       = ata       or getattr(ner_result, "ata_chapter", "")            or ""
            sb_ad     = sb_ad     or getattr(ner_result, "sb_ad_reference", "")        or ""

        input_text = self._build_embedding_text(
            raw_text, filename, doc_type, category,
            aircraft, es_ref, ata, sb_ad,
            semantic_prefix=semantic_prefix,   # ← PROFIL
        )

        try:
            vector = model.encode(input_text, normalize_embeddings=True)
            logger.debug(f"[{self.name}] Embedding généré: {filename} ({self.dim}d)")
            return vector.tolist()
        except Exception as e:
            logger.error(f"[{self.name}] Erreur embedding {filename}: {e}")
            return None

    async def embed_query(self, query: str) -> Optional[list[float]]:
        """Encode une requête de recherche."""
        model = self._get_model()
        if model is None:
            return None
        try:
            vector = model.encode(query.strip(), normalize_embeddings=True)
            return vector.tolist()
        except Exception as e:
            logger.error(f"[{self.name}] Erreur embedding requête: {e}")
            return None

    async def embed_batch(self, texts: list[str]) -> list[Optional[list[float]]]:
        """Encode un lot de textes (plus efficace que un par un)."""
        model = self._get_model()
        if model is None:
            return [None] * len(texts)
        try:
            vectors = model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
            return [v.tolist() for v in vectors]
        except Exception as e:
            logger.error(f"[{self.name}] Erreur batch embedding: {e}")
            return [None] * len(texts)

    def cosine_similarity(self, v1: list[float], v2: list[float]) -> float:
        """Calcule la similarité cosinus entre deux vecteurs."""
        a = np.array(v1)
        b = np.array(v2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))