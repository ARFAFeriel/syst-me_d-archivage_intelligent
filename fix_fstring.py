f = open('backend/agents/classifier_agent.py', encoding='utf-8').read()
old = """logger.info(f'[Classifier] LLM fallback : {llm['doc_type']} ({llm['confidence']:.0%})')"""
new = """logger.info("[Classifier] LLM fallback : " + llm['doc_type'] + f" ({llm['confidence']:.0%})")"""
if old in f:
    open('backend/agents/classifier_agent.py','w',encoding='utf-8').write(f.replace(old,new))
    print('OK fixe')
else:
    print('Chaine non trouvee — affichage contexte:')
    idx = f.find('LLM fallback')
    print(repr(f[idx:idx+120]))
