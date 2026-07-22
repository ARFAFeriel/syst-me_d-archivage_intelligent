"""
Agent Classifier
TF-IDF + LR — 13 classes de documents aéronautiques
Entraîné sur patterns textuels et métadonnées structurées
"""
import re
import pickle
import os
import numpy as np
from pathlib import Path
from loguru import logger
from backend.schemas.document import ClassifierResult, DocumentTypeEnum


# ── Règles de classification basées sur les patterns ─────────────────────────
# Utilisées comme features + fallback si le modèle ML n'est pas chargé

CLASSIFICATION_RULES = {
    DocumentTypeEnum.WORK_ORDER: {
        "keywords": [
            "work order", "ordre d execution", "ordre d'execution", "execution no",
            "travaux", "maintenance task", "workorder", "task card",
            "wp linked", "wp ref", "opened on", "repetitive w.o",
        ],
        "filename_patterns": [r"ES\d{4,8}", r"WO\d+"],
        "path_patterns": ["workorder", "work order", "wo", "check a", "check c", "check"],
        "weight": 1.3,
    },
    DocumentTypeEnum.JOBCARD: {
        "keywords": ["job card", "jobcard", "task", "skill", "man hours"],
        "filename_patterns": [r"^\d{2,4}\.pdf$"],
        "path_patterns": ["jobcard", "job card"],
        "weight": 1.0,
    },
    DocumentTypeEnum.DEFECT_REPORT: {
        "keywords": ["defect", "anomaly", "finding", "damage", "discrepancy", "defect report"],
        "filename_patterns": [r"^\d{1,3}\.pdf$"],
        "path_patterns": ["defect report", "defect"],
        "weight": 1.0,
    },

    DocumentTypeEnum.AD: {
        "keywords": ["airworthiness directive", "ad", "directive", "easa", "faa", "mandatory"],
        "filename_patterns": [r"A3\d{2}-\d{2}-\d{3,5}", r"AD-\d{4}"],
        "path_patterns": ["ad", "airworthiness"],
        "weight": 1.2,
    },
    DocumentTypeEnum.SB: {
        "keywords": ["service bulletin", "sb", "modification", "retrofit"],
        "filename_patterns": [r"A3\d{2}-\d{2}[A-Z]\d{4}", r"SB-"],
        "path_patterns": ["sb", "service bulletin"],
        "weight": 1.0,
    },
    DocumentTypeEnum.ATL: {
        "keywords": ["technical log", "atl", "flight log", "sector", "departure", "arrival"],
        "filename_patterns": [r"TL\d{2}[A-Z]{3}"],
        "path_patterns": ["atl", "technical log"],
        "weight": 1.0,
    },
    DocumentTypeEnum.AMM: {
        "keywords": ["aircraft maintenance manual", "amm", "procedure", "maintenance manual"],
        "filename_patterns": [r"AMM"],
        "path_patterns": ["amm"],
        "weight": 1.0,
    },
    DocumentTypeEnum.CMM: {
        "keywords": ["component maintenance manual", "cmm", "overhaul", "bench test"],
        "filename_patterns": [r"CMM"],
        "path_patterns": ["cmm"],
        "weight": 1.0,
    },
    DocumentTypeEnum.IPC: {
        "keywords": ["illustrated parts", "ipc", "parts catalog", "figure", "item number"],
        "filename_patterns": [r"IPC"],
        "path_patterns": ["ipc"],
        "weight": 1.0,
    },
    DocumentTypeEnum.SPECS: {
        "keywords": ["specifications", "specs", "technical specification", "general information", "msn"],
        "filename_patterns": [r"Specs", r"MSN.*Specs"],
        "path_patterns": ["specs", "specifications", "status"],
        "weight": 1.0,
    },
    DocumentTypeEnum.CERTIFICATE: {
        "keywords": ["certificate", "certificat", "form 1", "crs", "release to service", "approval"],
        "filename_patterns": [r"cert", r"Form1", r"CRS"],
        "path_patterns": ["certificates", "burn certs", "ht certificates"],
        "weight": 1.0,
    },
    DocumentTypeEnum.RCT: {
        "keywords": ["rct", "release certificate", "return to service"],
        "filename_patterns": [r"RCT"],
        "path_patterns": ["rct"],
        "weight": 1.1,
    },
}


# Un Work Order ou Job Card reste ce qu'il est, même s'il est dans /AD/ ou /SB/
STRUCTURAL_TYPES = {
    DocumentTypeEnum.WORK_ORDER,
    DocumentTypeEnum.JOBCARD,
    DocumentTypeEnum.DEFECT_REPORT,

    DocumentTypeEnum.CERTIFICATE,
    DocumentTypeEnum.RCT,
}

# Category mapping
TYPE_TO_CATEGORY = {
    DocumentTypeEnum.WORK_ORDER: "Check A",
    DocumentTypeEnum.JOBCARD: "Check A",
    DocumentTypeEnum.DEFECT_REPORT: "Check C",
  
    DocumentTypeEnum.AD: "AD",
    DocumentTypeEnum.SB: "SB",
    DocumentTypeEnum.ATL: "ATL",
    DocumentTypeEnum.AMM: "AMM",
    DocumentTypeEnum.CMM: "CMM",
    DocumentTypeEnum.IPC: "IPC",
    DocumentTypeEnum.SPECS: "Specs",
    DocumentTypeEnum.CERTIFICATE: "Certificates",
    DocumentTypeEnum.RCT: "Check A",
}


def _is_work_order_filename(filename: str) -> bool:
    """
    Détecte si le nom de fichier indique structurellement un Work Order.
    ES###### est un identifiant NouvelAir de Work Order — priorité maximale.
    """
    return bool(re.search(r"^ES\d{4,8}(\.pdf)?$", filename, re.IGNORECASE))



# ── Path rules — classification par chemin d'archivage ──────────────────────
import re as _re_path
_PATH_RULES_RAW = [
    (r"[/\\]workorder[/\\]",             "WORK_ORDER"),
    (r"_workorder_",                      "WORK_ORDER"),
    (r"[/\\]jobcard[/\\]",               "JOBCARD"),
    (r"_jobcard_",                        "JOBCARD"),
    (r"[/\\]defect[_\s]?report[/\\]",    "DEFECT_REPORT"),
    (r"_defect[_\s]?report_",            "DEFECT_REPORT"),
    (r"_rct[-_.]",                        "RCT"),
    (r"[/\\]rct[/\\]",                   "RCT"),
    (r"[/\\]old[_\s]?doc[/\\]ad[/\\]",  "AD"),
    (r"[/\\]ad[_\s]?dfps[/\\]",         "AD"),
    (r"[/\\]ads[_\s]?not",              "AD"),
    (r"[/\\]old[_\s]?doc[/\\]sb[/\\]",  "SB"),
    (r"[/\\]sb[_\s]?airbus[/\\]",       "SB"),
    (r"[/\\]atl[/\\]",                   "ATL"),
    
    (r"_rct\.pdf$",                        "RCT"),
    (r"_rct_",                             "RCT"),
    (r"rct-es\d+",                         "RCT"),
    (r"[/\\]ht[_\s]?certificates[/\\]",  "CERTIFICATE"),
    (r"[/\\]occm[/\\]",                  "CERTIFICATE"),
    (r"[/\\]cmm[/\\]",                   "CMM"),
    (r"[/\\]specs[/\\]",                 "SPECS"),
]
_COMPILED_PATH_RULES = [
    (_re_path.compile(p, _re_path.IGNORECASE), t)
    for p, t in _PATH_RULES_RAW
]
class ClassifierAgent:
    """
    Agent Classification de Documents.
    Utilise TF-IDF + LR si le modèle est chargé,
    sinon utilise le système de règles basé sur patterns.
    """

    MODEL_PATH = Path(__file__).parent.parent / "models" / "classifier_model.pkl"

    def __init__(self):
        self.name = "Classifier Agent"
        self._model = None
        self._vectorizer = None
        self._load_model()
        try:
            from backend.agents.llm_agent import LLMAgent
            self._llm = LLMAgent()
        except Exception:
            self._llm = type('FakeLLM', (), {'disponible': False})()
        logger.info(f"[{self.name}] Initialisé")


    def _classify_from_path(self, file_path: str):
        """Classifie depuis le chemin — None si chemin non informatif (uploads)."""
        if not file_path:
            return None
        path_n = file_path.replace("\\", "/").lower()
        non_info = ["/downloads/", "/desktop/", "/documents/", "/temp/", "/tmp/"]
        if any(x in path_n for x in non_info):
            return None
        for pattern, doc_type_str in _COMPILED_PATH_RULES:
            if pattern.search(path_n):
                try:
                    return DocumentTypeEnum[doc_type_str], 1.0
                except KeyError:
                    continue
        return None
    def _load_model(self):
        """Charge le modèle ML si disponible."""
        if self.MODEL_PATH.exists():
            try:
                with open(self.MODEL_PATH, "rb") as f:
                    data = pickle.load(f)
                    self._model = data["model"]
                    self._vectorizer = data["vectorizer"]
                    logger.info(f"[{self.name}] Modèle ML chargé depuis {self.MODEL_PATH}")
            except Exception as e:
                logger.warning(f"[{self.name}] Impossible de charger le modèle ML: {e}")
        else:
            logger.info(f"[{self.name}] Mode règles (modèle ML non trouvé)")

    async def process(
        self,
        text: str,
        filename: str,
        file_path: str = "",
        ner_result=None
    ) -> ClassifierResult:
        """
        Classifie un document.
        Retourne ClassifierResult avec type, catégorie, confiance, scores.
        """
        path_result = self._classify_from_path(file_path)
        if path_result:
            doc_type, conf = path_result
            category = self._infer_category(doc_type, file_path)
            logger.info(f"[{self.name}] Path rule → {doc_type.value} (conf=1.0)")
            return ClassifierResult(predicted_type=doc_type, predicted_category=category, confidence=conf, scores={doc_type.value: conf})
        logger.info(f"[{self.name}] Classification: {filename}")

        # ── FIX 1 : Détection structurelle prioritaire par nom de fichier ─────
        # ES###### est un Work Order NouvelAir — aucune règle ne peut l'écraser.
        if _is_work_order_filename(filename):
            logger.info(
                f"[{self.name}] Nom ES###### détecté → Work Order forcé (filename rule)"
            )
            category = self._infer_category(
                DocumentTypeEnum.WORK_ORDER, file_path, force_type=DocumentTypeEnum.WORK_ORDER
            )
            return ClassifierResult(
                predicted_type=DocumentTypeEnum.WORK_ORDER,
                predicted_category=category,
                confidence=0.97,
                scores={DocumentTypeEnum.WORK_ORDER.value: 0.97}
            )

        # Préparer le texte combiné
        combined_text = self._prepare_text(text, filename, file_path)

        # 1. Essai ML
        if self._model and self._vectorizer:
            try:
                return self._classify_ml(combined_text, filename, file_path)
            except Exception as e:
                logger.warning(f"[{self.name}] ML échoué, fallback règles: {e}")

        # 2. Fallback règles
        result = self._classify_rules(combined_text, filename, file_path, ner_result)

        ner_type = None
        if ner_result and hasattr(ner_result, 'raw_entities'):
            ner_types = (ner_result.raw_entities or {}).get('llm_doc_type', [])
            ner_type = ner_types[0] if ner_types else None

        if self._llm.disponible and (result.confidence < 0.85 or ner_type):
            llm = self._llm.classifier_document(
                texte=combined_text, filename=filename, file_path=file_path,
                tfidf_type=result.predicted_type.value,
                tfidf_confidence=result.confidence,
                ner_type=ner_type
            )
            if llm['llm_utilise']:
                try:
                    result.predicted_type = DocumentTypeEnum(llm['doc_type'])
                except ValueError:
                    pass
                result.confidence = llm['confidence']
                result.predicted_category = self._infer_category(result.predicted_type, file_path)
                logger.info("[Classifier] LLM fallback : " + llm['doc_type'] + f" ({llm['confidence']:.0%})")
        return result

    def _prepare_text(self, text: str, filename: str, file_path: str) -> str:
        """Combine texte OCR + filename + path pour classification."""
        parts = []
        if text:
            parts.append(text[:3000].lower())
        if filename:
            fn = filename.replace("-", " ").replace("_", " ").replace(".", " ").lower()
            parts.append(f"FILENAME {fn}")
        if file_path:
            path_parts = file_path.replace("\\", "/").split("/")
            parts.append(f"PATH {' '.join(path_parts).lower()}")
        return " ".join(parts)

    def _classify_ml(self, text: str, filename: str, file_path: str) -> ClassifierResult:
        """Classification via TF-IDF + LR."""
        X = self._vectorizer.transform([text])
        proba = self._model.predict_proba(X)[0]
        classes = self._model.classes_

        scores = {cls: float(p) for cls, p in zip(classes, proba)}
        best_idx = int(np.argmax(proba))
        predicted = classes[best_idx]
        confidence = float(proba[best_idx])

        try:
            doc_type = DocumentTypeEnum(predicted)
        except ValueError:
            doc_type = DocumentTypeEnum.OTHER

        category = self._infer_category(doc_type, file_path)

        return ClassifierResult(
            predicted_type=doc_type,
            predicted_category=category,
            confidence=round(confidence, 4),
            scores=scores
        )

    def _classify_rules(
        self, text: str, filename: str, file_path: str, ner_result=None
    ) -> ClassifierResult:
        """Classification par règles et patterns."""
        scores: dict[str, float] = {}
        text_lower = text.lower()
        filename_lower = filename.lower()
        path_lower = file_path.lower().replace("\\", "/")

        for doc_type, rules in CLASSIFICATION_RULES.items():
            score = 0.0

            # Keywords dans le texte OCR
            for kw in rules["keywords"]:
                if kw in text_lower:
                    score += 0.15 * rules["weight"]

            # Patterns dans le nom de fichier
            for pattern in rules["filename_patterns"]:
                if re.search(pattern, filename, re.IGNORECASE):
                    score += 0.35 * rules["weight"]

            # Patterns dans le chemin
            for pp in rules["path_patterns"]:
                if pp in path_lower:
                    score += 0.50 * rules["weight"]

            scores[doc_type.value] = min(score, 1.0)

        # Meilleur score
        if scores:
            best_type_str = max(scores, key=scores.get)
            best_score = scores[best_type_str]
            try:
                predicted = DocumentTypeEnum(best_type_str)
            except ValueError:
                predicted = DocumentTypeEnum.OTHER
        else:
            predicted = DocumentTypeEnum.OTHER
            best_score = 0.5

        # ── FIX 2 : NER boost ne peut PAS écraser un type structurel ─────────
        # Ex : un Work Order qui contient une référence AD reste un Work Order.
        if ner_result and predicted not in STRUCTURAL_TYPES:
            if ner_result.sb_ad_reference:
                fname_upper = filename.upper()
                path_upper = path_lower.upper()
                if "AD" in path_upper or "AD" in fname_upper:
                    predicted = DocumentTypeEnum.AD
                    best_score = max(best_score, 0.85)
                elif "SB" in path_upper:
                    predicted = DocumentTypeEnum.SB
                    best_score = max(best_score, 0.80)

        category = self._infer_category(predicted, file_path)

        return ClassifierResult(
            predicted_type=predicted,
            predicted_category=category,
            confidence=round(best_score, 4),
            scores={k: round(v, 4) for k, v in scores.items()}
        )

    def _infer_category(
        self,
        doc_type: DocumentTypeEnum,
        file_path: str,
        force_type: DocumentTypeEnum = None
    ) -> str:
        """
        Infère la catégorie depuis le type et le chemin.

        ── FIX 3 : Les types structurels (Work Order, Job Card, etc.) ne sont
        jamais overridés par le dossier /ad/ ou /sb/ du chemin.
        Le chemin indique le CONTEXTE du document, pas son TYPE.
        Ex : ES152410.pdf dans /AD/ → catégorie = "Check A" (Work Order),
             pas "AD".
        """
        # Le type effectif à utiliser pour l'inférence
        effective_type = force_type or doc_type
        path_lower = file_path.lower().replace("\\", "/")

        # ── Si c'est un type structurel, la catégorie vient du type, pas du chemin
        if effective_type in STRUCTURAL_TYPES:
            # Seul "check a" / "check c" dans le chemin peut affiner la catégorie
            if "check c" in path_lower or "check-c" in path_lower:
                return "Check C"
            if "check a" in path_lower or "check-a" in path_lower:
                return "Check A"
            # Sinon : catégorie standard du type
            return TYPE_TO_CATEGORY.get(effective_type, "Other")

        # ── Pour les autres types : le chemin peut affiner la catégorie ────────
        if "check a" in path_lower or "check-a" in path_lower:
            return "Check A"
        if "check c" in path_lower or "check-c" in path_lower:
            return "Check C"
        if "/atl/" in path_lower:
            return "ATL"
        if "/sb/" in path_lower:
            return "SB"
        if "/ad/" in path_lower:
            return "AD"
        if "specs" in path_lower or "specifications" in path_lower:
            return "Specs"
        if "structural repair" in path_lower:
            return "Structural Repair"
        if "/stc/" in path_lower:
            return "STC"
        if "weight" in path_lower or "balance" in path_lower:
            return "Weight & Balance"

        return TYPE_TO_CATEGORY.get(effective_type, "Other")

    def train(self, training_data: list[dict]):
        """
        Entraîne le modèle TF-IDF + LR sur des données annotées.
        training_data: [{"text": ..., "label": ..., "filename": ..., "path": ...}]
        """
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression

        if len(training_data) < 10:
            logger.warning(f"[{self.name}] Pas assez de données d'entraînement ({len(training_data)})")
            return

        texts = [
            self._prepare_text(d["text"], d.get("filename", ""), d.get("path", ""))
            for d in training_data
        ]
        labels = [d["label"] for d in training_data]

        self._vectorizer = TfidfVectorizer(
            max_features=20000,
            ngram_range=(1, 3),
            min_df=1,
            analyzer="word"
        )
        X = self._vectorizer.fit_transform(texts)

        self._model = LogisticRegression(
            max_iter=1000,
            C=1.0,
            solver="lbfgs",
            class_weight="balanced"
        )
        self._model.fit(X, labels)

        self.MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(self.MODEL_PATH, "wb") as f:
            pickle.dump({"model": self._model, "vectorizer": self._vectorizer}, f)

        logger.info(
            f"[{self.name}] Modèle entraîné sur {len(texts)} documents et sauvegardé"
        )






