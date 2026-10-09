#!/usr/bin/env python
"""
Calcula as métricas de avaliação definidas em Metodologia > Métricas de Avaliação:

  - Precisão, Recall, F1-score, FPR (taxa de falsos positivos) por detector.
  - Custo total estimado e latência média por detector (quando aplicável).
  - Teste de McNemar entre pares de detectores (comparação pareada de classificadores
    sobre as MESMAS amostras — ex.: Claude vs. Semgrep, RQ1; Claude vs. Gemini, RQ2;
    Semgrep bruto vs. Semgrep+Jev, RQ3).

Lê results/consolidated.csv (gerado pelo script 06) e escreve:
  - results/metrics_by_detector.csv
  - results/mcnemar_pairwise.csv

Uso:
    python scripts/07_compute_metrics.py
    python scripts/07_compute_metrics.py --mcnemar-pairs semgrep:claude claude:gemini semgrep:jev
"""
from __future__ import annotations

import argparse
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.stats.contingency_tables import mcnemar

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.config import RESULTS_DIR  # noqa: E402


def compute_classification_metrics(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (approach, detector), group in df.groupby(["approach", "detector"]):
        y_true = group["is_vulnerable"].astype(bool)
        y_pred = group["predicted_vulnerable"].astype(bool)

        tp = int(((y_pred) & (y_true)).sum())
        fp = int(((y_pred) & (~y_true)).sum())
        tn = int(((~y_pred) & (~y_true)).sum())
        fn = int(((~y_pred) & (y_true)).sum())

        precision = tp / (tp + fp) if (tp + fp) else float("nan")
        recall = tp / (tp + fn) if (tp + fn) else float("nan")
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision == precision and recall == recall and (precision + recall) > 0
            else float("nan")
        )
        fpr = fp / (fp + tn) if (fp + tn) else float("nan")

        rows.append({
            "approach": approach,
            "detector": detector,
            "n": len(group),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": round(precision, 4) if precision == precision else None,
            "recall": round(recall, 4) if recall == recall else None,
            "f1": round(f1, 4) if f1 == f1 else None,
            "fpr": round(fpr, 4) if fpr == fpr else None,
            "latencia_media_s": round(group["latency_seconds"].dropna().mean(), 3)
                if "latency_seconds" in group and group["latency_seconds"].notna().any() else None,
            "custo_total_usd": round(group["estimated_cost_usd"].dropna().sum(), 4)
                if "estimated_cost_usd" in group and group["estimated_cost_usd"].notna().any() else None,
            "erros": int(group["error"].notna().sum()) if "error" in group else 0,
        })
    return pd.DataFrame(rows).sort_values(["approach", "detector"])


def run_mcnemar(df: pd.DataFrame, detector_a: str, detector_b: str) -> dict | None:
    """Teste de McNemar pareado: compara acerto/erro de dois detectores NAS MESMAS
    amostras (apenas amostras avaliadas por ambos entram no teste)."""
    a = df[df["detector"] == detector_a][["sample_id", "correct"]].rename(columns={"correct": "correct_a"})
    b = df[df["detector"] == detector_b][["sample_id", "correct"]].rename(columns={"correct": "correct_b"})
    merged = a.merge(b, on="sample_id", how="inner")
    if merged.empty:
        print(f"[aviso] Sem amostras em comum entre '{detector_a}' e '{detector_b}' — pulando McNemar.")
        return None

    # Tabela de contingência 2x2: [ambos certos, só A certo; só B certo, ambos errados]
    both_correct = int(((merged.correct_a) & (merged.correct_b)).sum())
    only_a = int(((merged.correct_a) & (~merged.correct_b)).sum())
    only_b = int(((~merged.correct_a) & (merged.correct_b)).sum())
    both_wrong = int(((~merged.correct_a) & (~merged.correct_b)).sum())

    table = np.array([[both_correct, only_a], [only_b, both_wrong]])
    # exact=True é recomendado para N pequeno (típico de piloto ~25-30 amostras);
    # para N grande, considerar exact=False (usa correção de continuidade qui-quadrado).
    result = mcnemar(table, exact=(len(merged) < 50), correction=True)
    return {
        "detector_a": detector_a, "detector_b": detector_b, "n_pareado": len(merged),
        "ambos_certos": both_correct, "so_a_certo": only_a, "so_b_certo": only_b,
        "ambos_errados": both_wrong,
        "estatistica": round(float(result.statistic), 4),
        "p_valor": round(float(result.pvalue), 4),
        "significativo_p<0.05": bool(result.pvalue < 0.05),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mcnemar-pairs", nargs="*", default=None,
        help="pares 'detectorA:detectorB' a comparar; se omitido, compara todos os pares disponíveis.",
    )
    args = parser.parse_args()

    consolidated_path = RESULTS_DIR / "consolidated.csv"
    if not consolidated_path.exists():
        print(f"[erro] {consolidated_path} não existe. Rode scripts/06_consolidate.py antes.")
        return
    df = pd.read_csv(consolidated_path)
    df["correct"] = df["correct"].astype(bool)

    metrics_df = compute_classification_metrics(df)
    metrics_path = RESULTS_DIR / "metrics_by_detector.csv"
    metrics_df.to_csv(metrics_path, index=False)
    print(f"[ok] métricas por detector -> {metrics_path}\n")
    print(metrics_df.to_string(index=False))

    detectors = sorted(df["detector"].unique())
    if args.mcnemar_pairs:
        pairs = [tuple(p.split(":")) for p in args.mcnemar_pairs]
    else:
        pairs = list(combinations(detectors, 2))

    mcnemar_rows = [r for r in (run_mcnemar(df, a, b) for a, b in pairs) if r is not None]
    if mcnemar_rows:
        mcnemar_df = pd.DataFrame(mcnemar_rows)
        mcnemar_path = RESULTS_DIR / "mcnemar_pairwise.csv"
        mcnemar_df.to_csv(mcnemar_path, index=False)
        print(f"\n[ok] McNemar pareado -> {mcnemar_path}\n")
        print(mcnemar_df.to_string(index=False))


if __name__ == "__main__":
    main()
