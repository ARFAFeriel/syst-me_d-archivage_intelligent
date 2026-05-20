import sys
sys.path.insert(0, 'backend/agents')
sys.path.insert(0, 'agents')
sys.path.insert(0, '.')

# Charger v7 directement depuis le fichier
import importlib.util, pathlib

spec = importlib.util.spec_from_file_location(
    'ner_agent_v7',
    next(pathlib.Path('.').rglob('ner_agent_v7.py'), None)
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

tests = [
    'Work Order ES001778 pour aeronef TS-INQ ATA 32-40',
    'AD 2023-12-04 applicable au MSN 2158 P/N 1234567',
    'SB 737-28-1234 emis le 15 JAN 2023 pour TS-INP',
]
for t in tests:
    print(f'\nTexte : {t}')
    ents = m.extract_entities(t)
    for k, v in ents.items():
        if v: print(f'  [{k}] {v}')
