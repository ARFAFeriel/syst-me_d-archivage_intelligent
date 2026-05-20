"""
fix_organised_duplicates.py
============================
Supprime les fichiers en double dans ORGANISED/ en gardant la meilleure copie.

Stratégie de sélection :
  - Si les copies sont dans des dossiers d'immatriculation différents,
    on garde celle dont le nom de dossier correspond à la registration dans le nom du fichier.
  - Sinon, on garde la première trouvée (ordre alphabétique du chemin).

Usage :
    py fix_organised_duplicates.py --dry-run        # aperçu sans rien supprimer
    py fix_organised_duplicates.py --delete         # suppression réelle
"""

import os
import sys
import argparse
from pathlib import Path
from collections import defaultdict

ORGANISED_PATH = r"C:\Users\ferie\Desktop\stage nvl\AviationArchive\ORGANISED"

VALID_REGISTRATIONS = {"TS-INP", "TS-INQ", "TS-INO", "TS-ING", "TS-INT", "EE"}


def best_copy(paths: list[Path]) -> Path:
    """
    Choisit la meilleure copie parmi plusieurs fichiers portant le même nom.
    Préfère le fichier dont le dossier parent correspond à la registration du nom.
    Ex: TS-INQ_SPECS_2011.pdf → préfère le chemin contenant 'TS-INQ'
    """
    filename = paths[0].name
    # Extraire la registration depuis le nom de fichier (ex: TS-INQ)
    reg_in_name = None
    for reg in VALID_REGISTRATIONS:
        if filename.startswith(reg + "_"):
            reg_in_name = reg
            break

    if reg_in_name:
        # Chercher un chemin dont un dossier parent correspond
        for p in paths:
            parts = [part.upper() for part in p.parts]
            if reg_in_name.upper() in parts:
                return p

    # Fallback : chemin le plus court (moins de sous-dossiers = mieux organisé)
    return min(paths, key=lambda p: len(p.parts))


def find_duplicates(organised_path: str) -> dict[str, list[Path]]:
    """Retourne un dict nom_fichier → liste de chemins complets."""
    root = Path(organised_path)
    by_name: dict[str, list[Path]] = defaultdict(list)

    for pdf in sorted(root.rglob("*.pdf")):
        by_name[pdf.name].append(pdf)

    return {k: v for k, v in by_name.items() if len(v) > 1}


def main():
    parser = argparse.ArgumentParser(description="Purge des doublons dans ORGANISED/")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Affiche les actions sans rien supprimer (défaut)")
    parser.add_argument("--delete",  action="store_true",
                        help="Supprime réellement les doublons")
    args = parser.parse_args()

    do_delete = args.delete
    mode = "SUPPRESSION RÉELLE" if do_delete else "DRY-RUN (aperçu)"

    print(f"\n{'═'*60}")
    print(f"  Purge doublons ORGANISED/ — {mode}")
    print(f"{'═'*60}")
    print(f"  Dossier : {ORGANISED_PATH}\n")

    duplicates = find_duplicates(ORGANISED_PATH)

    if not duplicates:
        print("✓ Aucun doublon trouvé !")
        return

    total_to_delete = 0
    total_size_mb   = 0.0
    kept_list       = []
    deleted_list    = []

    for name, paths in sorted(duplicates.items()):
        keeper = best_copy(paths)
        to_delete = [p for p in paths if p != keeper]

        kept_list.append((name, keeper))
        for p in to_delete:
            size_kb = p.stat().st_size / 1024
            total_size_mb += size_kb / 1024
            total_to_delete += 1
            deleted_list.append((name, p, size_kb))

    # Affichage résumé
    print(f"  Fichiers avec doublons : {len(duplicates)}")
    print(f"  Copies à supprimer     : {total_to_delete}")
    print(f"  Espace récupéré estimé : {total_size_mb:.1f} MB\n")

    print(f"{'─'*60}")
    print(f"  Détail (20 premiers) :")
    print(f"{'─'*60}")
    for name, p, size_kb in deleted_list[:20]:
        action = "SUPPRIMER" if do_delete else "À supprimer"
        print(f"  [{action}] {name}")
        print(f"    chemin : ...{str(p).split('ORGANISED')[-1]}")
        print(f"    taille : {size_kb:.0f} KB")

    if len(deleted_list) > 20:
        print(f"  ... et {len(deleted_list) - 20} autres\n")

    if not do_delete:
        print(f"\n{'═'*60}")
        print(f"  Mode DRY-RUN : aucun fichier supprimé.")
        print(f"  Relancez avec --delete pour appliquer les suppressions.")
        print(f"{'═'*60}\n")
        return

    # Suppression réelle
    print(f"\n{'─'*60}")
    print(f"  Suppression en cours...")
    print(f"{'─'*60}")

    deleted_ok  = 0
    deleted_err = 0

    for name, p, size_kb in deleted_list:
        try:
            os.remove(p)
            print(f"  ✓ Supprimé : {p.name} ({size_kb:.0f} KB)")
            deleted_ok += 1
        except Exception as e:
            print(f"  ✗ Erreur   : {p.name} → {e}")
            deleted_err += 1

    print(f"\n{'═'*60}")
    print(f"  Résultat")
    print(f"{'═'*60}")
    print(f"  Supprimés avec succès : {deleted_ok}")
    print(f"  Erreurs               : {deleted_err}")
    print(f"  Espace récupéré       : {total_size_mb:.1f} MB")

    # Vérification finale
    remaining = find_duplicates(ORGANISED_PATH)
    print(f"  Doublons restants     : {len(remaining)}")
    print(f"{'═'*60}\n")
    print("  ✓ Fait. Relancez le pipeline pour les documents manquants.")


if __name__ == "__main__":
    main()