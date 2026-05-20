import re, json, time
from backend.config import settings
from typing import Optional
from loguru import logger

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

GROQ_MODEL     = "llama-3.1-8b-instant"
OCR_CONF_SEUIL = 60.0
CLASSIF_SEUIL  = 0.85

DOC_TYPES = ["AD","SB","AMM","CMM","IPC","MEL","Work Order","Jobcard",
             "Defect Report","CRS","COA","Specs","Certificate","ATL","RCT"]
CATEGORIES = ["Check A","Check C","Check D","AD","SB","ATL","Specs",
              "Structural Repair","Weight & Balance","STC","Engine","Other"]


class LLMAgent:
    name = "LLMAgent"

    def __init__(self):
        self._client = None
        api_key = settings.groq_api_key
        if not api_key:
            logger.warning(f"[{self.name}] GROQ_API_KEY manquant")
            return
        if not GROQ_AVAILABLE:
            logger.warning(f"[{self.name}] groq non installe")
            return
        try:
            self._client = Groq(api_key=api_key)
            logger.info(f"[{self.name}] Groq connecte â€” {GROQ_MODEL}")
        except Exception as e:
            logger.error(f"[{self.name}] Init erreur : {e}")

    @property
    def disponible(self):
        return self._client is not None

    def _call(self, system, user, max_tokens=512):
        if not self.disponible:
            return None
        for i in range(2):
            try:
                t0 = time.perf_counter()
                r = self._client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[{"role":"system","content":system},
                              {"role":"user","content":user}],
                    max_tokens=max_tokens, temperature=0.0,
                )
                ms = (time.perf_counter()-t0)*1000
                txt = r.choices[0].message.content.strip()
                logger.debug(f"[{self.name}] LLM {ms:.0f}ms")
                return txt
            except Exception as e:
                logger.warning(f"[{self.name}] Tentative {i+1}/2 : {e}")
                if i==0: time.sleep(1)
        return None

    # 1. CORRECTEUR OCR
    def corriger_ocr(self, texte_brut, confidence, filename=""):
        if confidence >= OCR_CONF_SEUIL or not texte_brut.strip():
            return {"texte_corrige":texte_brut,"llm_utilise":False,
                    "amelioration":f"OCR ok ({confidence:.0f}%)"}
        if not self.disponible:
            return {"texte_corrige":texte_brut,"llm_utilise":False,
                    "amelioration":"LLM indisponible"}
        sys = ("Tu es expert en documents aeronautiques MRO.\n"
               "Corrige UNIQUEMENT les erreurs OCR (0/O, 1/l, espaces).\n"
               "Retourne uniquement le texte corrige, sans explication.")
        usr = f"Fichier : {filename}\nConfiance : {confidence:.1f}%\n\n{texte_brut[:1500]}\n\nCORRIGE :"
        r = self._call(sys, usr, 800)
        if not r:
            return {"texte_corrige":texte_brut,"llm_utilise":False,"amelioration":"LLM sans reponse"}
        # Rejeter si Groq répond avec une phrase d'erreur au lieu de corriger
        mots_erreur = ["je n'ai pas", "je ne peux pas", "désolé", "impossible", "accès"]
        if any(m in r.lower() for m in mots_erreur) or len(r) < 20:
            return {"texte_corrige":texte_brut,"llm_utilise":False,"amelioration":"LLM réponse invalide"}
        logger.info(f"[{self.name}] OCR corrigé ({confidence:.0f}%) — {filename}")
        return {"texte_corrige":r,"llm_utilise":True,
                "amelioration":f"OCR {confidence:.0f}% -> LLM"}

    # 2. EXTRACTEUR NER
    def extraire_entites(self, texte, entites_existantes, filename=""):
        cibles = ["aircraft_registration","es_reference","ata_chapter","part_number"]
        manquantes = [k for k in cibles if not entites_existantes.get(k)]
        if not manquantes or not self.disponible:
            return {**entites_existantes, "llm_ner_utilise":False}
        sys = ("Expert MRO NouvelAir Tunisie.\n"
               "Flotte : TS-INP (MSN 2158), TS-INQ (MSN 3012).\n"
               "ES references : ES###### (ex ES001778).\n"
               "Reponds UNIQUEMENT en JSON valide, null si introuvable.")
        usr = (f"Fichier : {filename}\n"
               f"Deja extraits : {json.dumps(entites_existantes)}\n"
               f"A trouver : {manquantes}\n\n"
               f"TEXTE :\n{texte[:2000]}\n\nJSON :")
        r = self._call(sys, usr, 256)
        if not r:
            return {**entites_existantes, "llm_ner_utilise":False}
        try:
            m = re.search(r'\{.*\}', r, re.DOTALL)
            if not m: raise ValueError("no json")
            nouvelles = json.loads(m.group())
            for k,v in nouvelles.items():
                if v and not entites_existantes.get(k):
                    entites_existantes[k] = v
            entites_existantes["llm_ner_utilise"] = True
            logger.info(f"[{self.name}] NER complete â€” {manquantes}")
            return entites_existantes
        except Exception as e:
            logger.warning(f"[{self.name}] NER parse error : {e}")
            return {**entites_existantes, "llm_ner_utilise":False}

    # 3. CLASSIFICATEUR LLM
    def classifier_document(self, texte, filename, file_path,
                            tfidf_type, tfidf_confidence, ner_type=None):
        conflit_ner = ner_type and ner_type != tfidf_type
        conflit_fn  = self._conflit_filename(filename, tfidf_type)
        if not (tfidf_confidence < CLASSIF_SEUIL or conflit_ner or conflit_fn):
            return {"doc_type":tfidf_type,"confidence":tfidf_confidence,
                    "llm_utilise":False,"raison":f"TF-IDF ok ({tfidf_confidence:.0%})",
                    "needs_review":False}
        if not self.disponible:
            return {"doc_type":tfidf_type,"confidence":tfidf_confidence,
                    "llm_utilise":False,"raison":"LLM indisponible",
                    "needs_review":tfidf_confidence < CLASSIF_SEUIL}
        raisons = []
        if tfidf_confidence < CLASSIF_SEUIL: raisons.append(f"confiance {tfidf_confidence:.0%}")
        if conflit_ner: raisons.append(f"conflit NER {ner_type} != {tfidf_type}")
        if conflit_fn:  raisons.append("conflit filename")
        sys = (f"Expert MRO NouvelAir. Types: {', '.join(DOC_TYPES)}\n"
               f"Categories: {', '.join(CATEGORIES)}\n"
               f"REGLE : WORK ORDER ou ES###### => type Work Order meme si AD/SB mentionne.\n"
               f"JSON uniquement: {{\"doc_type\":\"...\",\"category\":\"...\","
               f"\"confidence\":0.XX,\"raison\":\"...\"}}")
        usr = (f"Fichier: {filename}\nChemin: {file_path}\n"
               f"TF-IDF: {tfidf_type} ({tfidf_confidence:.0%})\n"
               f"NER: {ner_type or 'non extrait'}\n"
               f"Doute: {' + '.join(raisons)}\n\n"
               f"TEXTE:\n{texte[:2000]}\n\nClassifie:")
        r = self._call(sys, usr, 256)
        if not r:
            return {"doc_type":tfidf_type,"confidence":tfidf_confidence,
                    "llm_utilise":False,"raison":"LLM sans reponse","needs_review":True}
        try:
            m = re.search(r'\{.*\}', r, re.DOTALL)
            if not m: raise ValueError("no json")
            p = json.loads(m.group())
            dt   = p.get("doc_type", tfidf_type)
            cat  = p.get("category","Other")
            conf = float(p.get("confidence",0.80))
            if dt != tfidf_type: conf = min(conf, 0.88)
            logger.info(f"[{self.name}] Classif: {dt} ({conf:.0%}) â€” {filename}")
            return {"doc_type":dt,"category":cat,"confidence":round(conf,4),
                    "llm_utilise":True,"raison":p.get("raison","LLM"),
                    "needs_review": dt != tfidf_type}
        except Exception as e:
            logger.warning(f"[{self.name}] Classif parse error : {e}")
            return {"doc_type":tfidf_type,"confidence":tfidf_confidence,
                    "llm_utilise":False,"raison":"parse error","needs_review":True}

    def _conflit_filename(self, filename, doc_type):
        fn = filename.upper()
        if doc_type in ("AD","SB") and any(x in fn for x in ["ES0","ES1","ES2","WO-"]):
            return True
        return False

    # 4. RAG
    def repondre_question(self, question, documents_contexte, aircraft_filter=None):
        if not self.disponible or not documents_contexte:
            return {"reponse":"LLM indisponible.","sources":[],"llm_utilise":False}
        ctx, sources = "", []
        for i,doc in enumerate(documents_contexte[:5],1):
            fn = doc.get("filename","?")
            ctx += f"\n--- Doc {i}: {fn} ({doc.get('doc_type','?')} | {doc.get('aircraft_registration','?')}) ---\n"
            ctx += (doc.get("ocr_text") or "")[:400] + "\n"
            sources.append(fn)
        sys = ("Assistant expert MRO NouvelAir. Reponds en francais, concis,\n"
               "en te basant UNIQUEMENT sur les documents fournis.")
        f   = f"Filtre: {aircraft_filter}\n\n" if aircraft_filter else ""
        usr = f"{f}DOCUMENTS:\n{ctx}\n\nQUESTION: {question}\n\nREPONSE:"
        r = self._call(sys, usr, 512)
        if not r:
            return {"reponse":"Pas de reponse.","sources":sources,"llm_utilise":False}
        logger.info(f"[{self.name}] RAG â€” {question[:60]}")
        return {"reponse":r,"sources":sources,"llm_utilise":True}
