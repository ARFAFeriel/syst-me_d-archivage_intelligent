import spacy
nlp = spacy.load('models/ner_nouvelair_best')

tests = [
    'Work Order ES001778 pour aeronef TS-INQ ATA 32-40',
    'AD 2023-12-04 applicable au MSN 2158 P/N 1234567',
    'SB 737-28-1234 emis le 15 JAN 2023 pour TS-INP',
]
for t in tests:
    doc = nlp(t)
    print(f'\nTexte : {t}')
    for ent in doc.ents:
        print(f'  [{ent.label_}] {ent.text}')
