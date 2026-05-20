import json, spacy
from collections import defaultdict

with open('data/ner_eval_data.json', encoding='utf-8') as f:
    eval_data = json.load(f)

nlp = spacy.load('models/ner_nouvelair_best')
labels = ['AIRCRAFT_REG','ES_REF','ATA_CHAPTER','PART_NUMBER','SERIAL_NUMBER','DOC_REF','DATE_AVIO','AIRLINE']
tp = defaultdict(int); fp = defaultdict(int); fn = defaultdict(int)

for ex in eval_data:
    gold = set((s,e,l) for s,e,l in ex['entities'])
    doc  = nlp(ex['text'])
    pred = set((ent.start_char, ent.end_char, ent.label_) for ent in doc.ents)
    for ent in pred:
        (tp if ent in gold else fp)[ent[2]] += 1
    for ent in gold:
        if ent not in pred: fn[ent[2]] += 1

sep = '-'*65
print('\n' + sep)
print('Label                    Prec   Recall       F1    TP    FP    FN')
print(sep)
f1s = []
for l in labels:
    p  = tp[l]/(tp[l]+fp[l]) if tp[l]+fp[l] else 0
    r  = tp[l]/(tp[l]+fn[l]) if tp[l]+fn[l] else 0
    f1 = 2*p*r/(p+r) if p+r else 0
    f1s.append(f1)
    print(f'{l:<20s} {p:8.3f} {r:8.3f} {f1:8.3f} {tp[l]:5d} {fp[l]:5d} {fn[l]:5d}')
print(sep)
print(f'Macro F1             {sum(f1s)/len(f1s):>30.3f}')
