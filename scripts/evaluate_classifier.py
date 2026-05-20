"""
evaluate_classifier.py
Évaluation du modèle de classification — Système d'archivage intelligent NouvelAir
"""

import sys
import warnings
warnings.filterwarnings("ignore")

import psycopg2
import psycopg2.extras
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import (
    classification_report, confusion_matrix,
    accuracy_score, f1_score, precision_score, recall_score
)
from collections import Counter
import json
from datetime import datetime

DB_CONFIG = {
    "host": "localhost", "port": 5434,
    "dbname": "nouv_db", "user": "postgres", "password": "Nouv26",
}

NORM = {
    "WORK_ORDER": "Work Order", "JOBCARD": "Jobcard",
    "DEFECT_REPORT": "Defect Report", "SPECS": "Specs",
    "CERTIFICATE": "Certificate", "AD": "AD", "SB": "SB",
    "AMM": "AMM", "CMM": "CMM", "IPC": "IPC",
    "ATL": "ATL", "NCR": "NCR", "RCT": "RCT",
}

def norm_type(x):
    s = str(x).strip().upper().replace(" ", "_").replace("-", "_")
    return NORM.get(s, x)

RULES = {
    "AD":            {"kw": ["airworthiness directive", " ad ", "directive", "easa ad", "faa ad", "mandatory action"], "fn": ["a3", "ad-"]},
    "SB":            {"kw": ["service bulletin", " sb ", "modification", "retrofit"], "fn": ["sb-", "a3"]},
    "AMM":           {"kw": ["aircraft maintenance manual", "amm", "maintenance manual", "procedure"], "fn": ["amm"]},
    "CMM":           {"kw": ["component maintenance manual", "cmm", "overhaul", "bench test"], "fn": ["cmm"]},
    "IPC":           {"kw": ["illustrated parts", "ipc", "parts catalog", "figure", "item number"], "fn": ["ipc"]},
    "Specs":         {"kw": ["specifications", "specs", "technical specification", "general information", "msn"], "fn": ["specs", "msn"]},
    "Certificate":   {"kw": ["certificate", "certificat", "form 1", "crs", "release to service", "approval"], "fn": ["cert", "form1", "crs"]},
    "RCT":           {"kw": ["rct", "release certificate", "return to service"], "fn": ["rct"]},
    "Work Order":    {"kw": ["work order", "wo ", "task card", "maintenance task"], "fn": ["wo-", "workorder"]},
    "Jobcard":       {"kw": ["job card", "jobcard", "job sheet", "task number"], "fn": []},
    "Defect Report": {"kw": ["defect report", "defect", "fault", "snag", "mel"], "fn": ["defect", "dr-"]},
    "NCR":           {"kw": ["non conformance", "ncr", "non-conformance", "quality report"], "fn": ["ncr"]},
    "ATL":           {"kw": ["technical log", "atl", "flight log", "sector", "departure", "arrival"], "fn": ["tl"]},
}

def classify_document(filename, content):
    fn = (filename or "").lower()
    ct = (content  or "")[:2000].lower()
    scores = {cls: 0.0 for cls in RULES}
    for cls, r in RULES.items():
        for kw in r["kw"]:
            if kw in ct: scores[cls] += 1.0
            if kw in fn: scores[cls] += 0.5
        for fp in r["fn"]:
            if fp in fn: scores[cls] += 2.0
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "Unknown"

NV_BLUE="#1a56db"; NV_PURPLE="#7c3aed"; NV_GREEN="#059669"
NV_ORANGE="#d97706"; NV_RED="#dc2626"
BG="#0f172a"; CARD="#1e293b"; TX="#e2e8f0"; TX2="#94a3b8"

def setup_style():
    plt.rcParams.update({
        "figure.facecolor": BG, "axes.facecolor": CARD, "axes.edgecolor": "#334155",
        "axes.labelcolor": TX, "xtick.color": TX2, "ytick.color": TX2, "text.color": TX,
        "grid.color": "#1e293b", "grid.linestyle": "--", "grid.linewidth": 0.5,
        "font.family": "DejaVu Sans", "font.size": 10,
    })

def main():
    print("\n" + "="*60)
    print("  EVALUATION DU MODELE DE CLASSIFICATION -- NouvelAir MRO")
    print("="*60 + "\n")

    print("Connexion a nouv_db (port 5434)...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur  = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        print("   OK Connecte\n")
    except Exception as e:
        print(f"   ERREUR : {e}"); sys.exit(1)

    print("Chargement des documents...")
    cur.execute("""
        SELECT id, filename, doc_type, ocr_confidence,
               COALESCE(ocr_text, '') AS raw_text, aircraft_registration
        FROM documents WHERE doc_type IS NOT NULL ORDER BY id
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("   Aucun document trouve"); sys.exit(1)

    df = pd.DataFrame(rows, columns=["id","filename","doc_type","ocr_confidence","raw_text","aircraft"])
    total = len(df)
    print(f"   {total} documents charges\n")

    df["doc_type"] = df["doc_type"].apply(norm_type)

    print("Re-classification...")
    df["predicted"] = df.apply(lambda r: classify_document(r["filename"], r["raw_text"]), axis=1)
    print("   Termine\n")

    y_true = df["doc_type"].tolist()
    y_pred = df["predicted"].tolist()

    acc  = accuracy_score(y_true, y_pred)
    f1_w = f1_score(y_true, y_pred, average="weighted", zero_division=0)
    prec = precision_score(y_true, y_pred, average="weighted", zero_division=0)
    rec  = recall_score(y_true, y_pred, average="weighted", zero_division=0)
    unk_pct = (df["predicted"] == "Unknown").sum() / total * 100

    print("="*55)
    print("  METRIQUES GLOBALES")
    print("="*55)
    print(f"  Accuracy            : {acc*100:.1f}%")
    print(f"  F1-score (weighted) : {f1_w*100:.1f}%")
    print(f"  Precision weighted  : {prec*100:.1f}%")
    print(f"  Rappel weighted     : {rec*100:.1f}%")
    print(f"  Docs Unknown        : {unk_pct:.1f}%")
    print(f"  Total evalue        : {total}")
    print("="*55 + "\n")

    labels = sorted(set(y_true + y_pred) - {"Unknown"})
    report = classification_report(y_true, y_pred, labels=labels, zero_division=0, output_dict=True)

    print(f"  {'Classe':<18} {'P':>6} {'R':>6} {'F1':>6} {'Support':>8}")
    print("  " + "-"*50)
    for cls in labels:
        if cls in report:
            m = report[cls]
            print(f"  {cls:<18} {m['precision']*100:>5.1f}% {m['recall']*100:>5.1f}% "
                  f"{m['f1-score']*100:>5.1f}% {int(m['support']):>8}")
    print()

    dist_true = Counter(y_true)
    dist_pred = Counter(y_pred)

    print("Generation des graphiques...")
    setup_style()
    fig = plt.figure(figsize=(22, 26), facecolor=BG)
    fig.suptitle(
        "Evaluation du Modele de Classification -- NouvelAir MRO\n"
        f"Systeme d'archivage intelligent  {total} documents  {datetime.now().strftime('%d/%m/%Y')}",
        fontsize=15, fontweight="bold", color=TX, y=0.98
    )

    # KPI cards
    kpi_ax = fig.add_axes([0.04, 0.88, 0.92, 0.07])
    kpi_ax.set_xlim(0,1); kpi_ax.set_ylim(0,1); kpi_ax.axis("off")
    kpis = [(f"{acc*100:.1f}%","Accuracy"),(f"{f1_w*100:.1f}%","F1-Score"),
            (f"{prec*100:.1f}%","Precision"),(f"{rec*100:.1f}%","Rappel"),
            (f"{total}","Documents"),(f"{len(labels)}","Classes")]
    for i,((val,lbl),col) in enumerate(zip(kpis,[NV_BLUE,NV_PURPLE,NV_GREEN,NV_ORANGE,TX2,TX2])):
        x=0.02+i*0.163
        kpi_ax.add_patch(plt.Rectangle((x,0.05),0.15,0.9,color=CARD,linewidth=2,edgecolor=col,transform=kpi_ax.transData))
        kpi_ax.text(x+0.075,0.6,val,ha="center",va="center",fontsize=18,fontweight="bold",color=col)
        kpi_ax.text(x+0.075,0.22,lbl,ha="center",va="center",fontsize=8,color=TX2)

    # Matrice de confusion
    ax_cm = fig.add_axes([0.05,0.52,0.55,0.33])
    cm = confusion_matrix(y_true,y_pred,labels=labels)
    rs = cm.sum(axis=1,keepdims=True); rs[rs==0]=1
    sns.heatmap(cm/rs*100,annot=True,fmt=".0f",cmap="Blues",
                xticklabels=labels,yticklabels=labels,
                linewidths=0.3,linecolor="#0f172a",
                cbar_kws={"shrink":0.7,"label":"% par classe reelle"},
                ax=ax_cm,annot_kws={"size":8})
    ax_cm.set_title("Matrice de Confusion (normalisee %)",fontsize=11,fontweight="bold",color=TX,pad=10)
    ax_cm.set_xlabel("Classe Predite",color=TX2,fontsize=9)
    ax_cm.set_ylabel("Classe Reelle",color=TX2,fontsize=9)
    ax_cm.tick_params(axis="x",rotation=45,labelsize=8)
    ax_cm.tick_params(axis="y",rotation=0,labelsize=8)

    # F1 par classe
    ax_f1 = fig.add_axes([0.65,0.52,0.32,0.33])
    f1_vals = sorted([(c,report[c]["f1-score"]*100) for c in labels if c in report],key=lambda x:x[1],reverse=True)
    cls_names=[x[0] for x in f1_vals]; f1_scores=[x[1] for x in f1_vals]
    ax_f1.barh(range(len(cls_names)),f1_scores,
               color=[NV_GREEN if v>=80 else(NV_ORANGE if v>=60 else NV_RED) for v in f1_scores],
               edgecolor="none",height=0.65)
    ax_f1.set_yticks(range(len(cls_names))); ax_f1.set_yticklabels(cls_names,fontsize=8)
    ax_f1.set_xlim(0,110); ax_f1.set_xlabel("F1-Score (%)",color=TX2,fontsize=9)
    ax_f1.set_title("F1-Score par Classe",fontsize=11,fontweight="bold",color=TX,pad=10)
    ax_f1.axvline(80,color=TX2,linestyle="--",linewidth=0.8,alpha=0.5,label="Seuil 80%")
    for i,val in enumerate(f1_scores): ax_f1.text(val+1,i,f"{val:.1f}%",va="center",fontsize=7,color=TX)
    ax_f1.legend(fontsize=7,loc="lower right")

    # Distribution
    ax_dist = fig.add_axes([0.05,0.26,0.55,0.22])
    dist_df = pd.DataFrame([{"type":k,"reel":dist_true.get(k,0),"predit":dist_pred.get(k,0)} for k in labels]).sort_values("reel",ascending=False)
    x=np.arange(len(dist_df))
    ax_dist.bar(x-0.2,dist_df["reel"],width=0.4,label="Reel",color=NV_BLUE,alpha=0.9)
    ax_dist.bar(x+0.2,dist_df["predit"],width=0.4,label="Predit",color=NV_PURPLE,alpha=0.9)
    ax_dist.set_xticks(x); ax_dist.set_xticklabels(dist_df["type"],rotation=35,ha="right",fontsize=8)
    ax_dist.set_ylabel("Nombre de documents",color=TX2,fontsize=9)
    ax_dist.set_title("Distribution Reelle vs Predite",fontsize=11,fontweight="bold",color=TX,pad=10)
    ax_dist.legend(fontsize=9); ax_dist.grid(axis="y",alpha=0.3)

    # Precision vs Rappel
    ax_pr = fig.add_axes([0.65,0.26,0.32,0.22])
    pv=[report[c]["precision"]*100 if c in report else 0 for c in cls_names]
    rv=[report[c]["recall"]*100 if c in report else 0 for c in cls_names]
    yi=np.arange(len(cls_names))
    ax_pr.scatter(pv,yi,color=NV_BLUE,s=60,zorder=3,label="Precision")
    ax_pr.scatter(rv,yi,color=NV_ORANGE,s=60,zorder=3,label="Rappel")
    for i in range(len(cls_names)):
        ax_pr.hlines(i,min(pv[i],rv[i]),max(pv[i],rv[i]),colors=TX2,linewidth=0.8,alpha=0.5)
    ax_pr.set_yticks(yi); ax_pr.set_yticklabels(cls_names,fontsize=8)
    ax_pr.set_xlim(0,110); ax_pr.set_xlabel("Score (%)",color=TX2,fontsize=9)
    ax_pr.set_title("Precision vs Rappel",fontsize=11,fontweight="bold",color=TX,pad=10)
    ax_pr.legend(fontsize=8,loc="lower right"); ax_pr.grid(axis="x",alpha=0.3)

    # OCR confidence
    ax_conf = fig.add_axes([0.05,0.06,0.55,0.17])
    bins_b=[0,30,50,70,85,95,100]; lbls_b=["0-30%","30-50%","50-70%","70-85%","85-95%","95-100%"]
    df["conf_bin"]=pd.cut(df["ocr_confidence"].fillna(0),bins=bins_b,labels=lbls_b,include_lowest=True)
    df["correct"]=(df["doc_type"]==df["predicted"]).astype(int)
    cstats=df.groupby("conf_bin",observed=True)["correct"].agg(["mean","count"]).reset_index()
    bar_c=ax_conf.bar(range(len(cstats)),cstats["mean"]*100,
                      color=[NV_GREEN if v>=0.8 else(NV_ORANGE if v>=0.6 else NV_RED) for v in cstats["mean"]],
                      edgecolor="none",width=0.6)
    ax_conf.set_xticks(range(len(cstats)))
    ax_conf.set_xticklabels([f"{r['conf_bin']}\n(n={int(r['count'])})" for _,r in cstats.iterrows()],fontsize=8)
    ax_conf.set_ylabel("Taux correct (%)",color=TX2,fontsize=9); ax_conf.set_ylim(0,110)
    ax_conf.set_title("Taux de Bonne Classification par Tranche de Confiance OCR",fontsize=11,fontweight="bold",color=TX,pad=10)
    for i,val in enumerate(cstats["mean"]*100): ax_conf.text(i,val+1.5,f"{val:.0f}%",ha="center",fontsize=8,color=TX)
    ax_conf.axhline(80,color=TX2,linestyle="--",linewidth=0.8,alpha=0.5); ax_conf.grid(axis="y",alpha=0.3)

    # Top confusions
    ax_err = fig.add_axes([0.65,0.06,0.32,0.17])
    errors=df[df["doc_type"]!=df["predicted"]][["doc_type","predicted"]].copy()
    errors["pair"]=errors["doc_type"]+" -> "+errors["predicted"]
    top_errors=errors["pair"].value_counts().head(8)
    if len(top_errors):
        ax_err.barh(range(len(top_errors)),top_errors.values,color=NV_RED,alpha=0.8,edgecolor="none",height=0.6)
        ax_err.set_yticks(range(len(top_errors))); ax_err.set_yticklabels(top_errors.index,fontsize=7)
        ax_err.set_xlabel("Occurrences",color=TX2,fontsize=9)
        ax_err.set_title("Top Confusions (Reel -> Predit)",fontsize=11,fontweight="bold",color=TX,pad=10)
        ax_err.grid(axis="x",alpha=0.3)
    else:
        ax_err.text(0.5,0.5,"Aucune erreur",ha="center",va="center",fontsize=12,color=NV_GREEN,transform=ax_err.transAxes)
        ax_err.axis("off")

    out_path = "scripts/evaluation_classification.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close()
    print(f"   Graphique sauvegarde : {out_path}\n")

    json_path = "scripts/evaluation_classification.json"
    report_data = {
        "date": datetime.now().isoformat(),
        "total_documents": total,
        "metrics": {
            "accuracy": round(acc*100,2), "f1_weighted": round(f1_w*100,2),
            "precision_weighted": round(prec*100,2), "recall_weighted": round(rec*100,2),
            "unknown_pct": round(unk_pct,2),
        },
        "per_class": {
            cls: {"precision":round(report[cls]["precision"]*100,1),
                  "recall":round(report[cls]["recall"]*100,1),
                  "f1":round(report[cls]["f1-score"]*100,1),
                  "support":int(report[cls]["support"])}
            for cls in labels if cls in report
        },
    }
    with open(json_path,"w",encoding="utf-8") as f:
        json.dump(report_data,f,indent=2,ensure_ascii=False)
    print(f"   Rapport JSON : {json_path}\n")

    print("="*55)
    print("  EVALUATION TERMINEE")
    print(f"  Accuracy : {acc*100:.1f}%  |  F1 : {f1_w*100:.1f}%")
    print("="*55 + "\n")

if __name__ == "__main__":
    main()
