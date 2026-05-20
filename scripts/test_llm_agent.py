import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from dotenv import load_dotenv; load_dotenv()
except: pass

from backend.agents.llm_agent import LLMAgent

def sep(t): print(f"\n{'='*50}\n  {t}\n{'='*50}")

agent = LLMAgent()

sep("1. Connexion Groq")
if agent.disponible:
    print("  OK Groq connecte â€” llama-3.1-8b-instant")
else:
    print("  ERREUR â€” verifier GROQ_API_KEY dans .env")
    sys.exit(1)

sep("2. Correcteur OCR (58%)")
r = agent.corriger_ocr("W0RK 0RDER ES00l778\nA/C TS-lNP\nATA 32", 58.0, "ES001778.pdf")
print(f"  llm_utilise : {r['llm_utilise']}")
print(f"  amelioration: {r['amelioration']}")
if r["llm_utilise"]: print(f"  resultat: {r['texte_corrige'][:150]}")

sep("3. Extracteur NER")
r = agent.extraire_entites(
    "WORK ORDER ES001392\nAircraft TS-INQ MSN 3012\nATA 27 FLIGHT CONTROLS\nPN 821-2100-6",
    {}, "ES001392.pdf")
print(f"  llm_ner_utilise: {r.get('llm_ner_utilise')}")
for k in ["aircraft_registration","es_reference","ata_chapter","part_number"]:
    v = r.get(k)
    print(f"  {'OK' if v else '--'} {k}: {v}")

sep("4. Classificateur LLM (Work Order classifie AD)")
r = agent.classifier_document(
    "WORK ORDER ES152410\nRef AD 2023-0142\nActions: inspect per AD",
    "TS-INQ_AD_ES152410.pdf", "C:/Archive/AD/",
    "AD", 0.72, "Work Order")
print(f"  TF-IDF : AD (72%)")
print(f"  LLM    : {r['doc_type']} ({r['confidence']:.0%})")
print(f"  raison : {r['raison']}")

sep("5. RAG")
docs = [{"filename":"ES001778_WO.pdf","doc_type":"Work Order",
         "aircraft_registration":"TS-INP",
         "ocr_text":"Work Order ES001778. ATA 32 Landing Gear. Limit 5000 FH."}]
r = agent.repondre_question("Quelle est la limite FH pour TS-INP ?", docs, "TS-INP")
print(f"  llm_utilise: {r['llm_utilise']}")
print(f"  reponse: {r['reponse']}")

print("\n" + "="*50)
print("  TESTS TERMINES")
print("="*50)
