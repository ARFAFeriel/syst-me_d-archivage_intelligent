import pickle
import re

with open(r"backend\models\classifier_model.pkl", "rb") as f:
    data = pickle.load(f)

vectorizer = data["vectorizer"]
model = data["model"]

texte = "Task Card Title Page Number REPLACEMENT OF OZONE FILTER CONVERTER Customer Card Number AC Type AC Reg AMS Rev No Date of Check AMS Task No Reference"

X = vectorizer.transform([texte])
feature_names = vectorizer.get_feature_names_out()

# Les mots du texte qui existent dans le vocabulaire du modele, avec leur score TF-IDF
nz = X.nonzero()[1]
mots_presents = [(feature_names[i], X[0, i]) for i in nz]
mots_presents.sort(key=lambda x: -x[1])

print("=== Mots du document presents dans le vocabulaire TF-IDF (tries par score) ===")
for mot, score in mots_presents[:20]:
    print(f"{mot}: {score:.4f}")

print("\n=== Classes possibles du modele ===")
print(model.classes_ if hasattr(model, "classes_") else "Pas d''attribut classes_ direct (CalibratedClassifierCV)")

print("\n=== Prediction et probabilites ===")
pred = model.predict(X)
print("Prediction:", pred)
if hasattr(model, "predict_proba"):
    proba = model.predict_proba(X)
    for cls, p in zip(model.classes_, proba[0]):
        print(f"{cls}: {p:.4f}")
