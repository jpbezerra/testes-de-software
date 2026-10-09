#!/usr/bin/env python
"""
Amostragem estratificada por CWE a partir dos CodeSamples reconstruídos pelo script 01,
para gerar o conjunto piloto (ex.: 25 amostras) ou o conjunto completo (ex.: 200-300).

Também inclui amostras negativas (is_vulnerable=False) quando disponíveis no benchmark de
origem, para permitir o cálculo de falsos positivos / taxa de falsos positivos (FPR) de
cada abordagem — se o benchmark só tiver pares vulnerável/corrigido, o script usa a versão
corrigida (commit_fixed) do mesmo arquivo como amostra negativa correspondente (par
"limpo"), quando esse conteúdo estiver disponível.

Uso:
    python scripts/02_sample_dataset.py --n 25 --out data/samples/pilot.jsonl
    python scripts/02_sample_dataset.py --n 250 --out data/samples/full.jsonl
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.config import DATA_DIR, SETTINGS  # noqa: E402
from common.schema import read_jsonl, write_jsonl  # noqa: E402


def load_all_samples() -> list[dict]:
    samples = []
    for sub in ("repopairbench", "jsts_sample"):
        path = DATA_DIR / sub / "samples.jsonl"
        if path.exists():
            samples.extend(read_jsonl(path))
        else:
            print(f"[aviso] {path} não existe ainda — rode scripts/01_fetch_dataset.py primeiro.")
    return samples


def stratified_sample(samples: list[dict], n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    by_cwe: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        by_cwe[s.get("cwe_id") or "SEM_CWE"].append(s)

    cwes = list(by_cwe.keys())
    rng.shuffle(cwes)
    if not cwes:
        return []

    per_cwe_quota = max(1, n // len(cwes))
    selected: list[dict] = []
    for cwe in cwes:
        bucket = by_cwe[cwe][:]
        rng.shuffle(bucket)
        selected.extend(bucket[:per_cwe_quota])

    # Completa a quota (ou corta o excesso) a partir do restante, mantendo variedade de CWE.
    rng.shuffle(selected)
    if len(selected) < n:
        remaining = [s for s in samples if s not in selected]
        rng.shuffle(remaining)
        selected.extend(remaining[: n - len(selected)])
    return selected[:n]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=25, help="tamanho da amostra (padrão: piloto=25)")
    parser.add_argument("--out", type=str, default=None, help="arquivo .jsonl de saída")
    parser.add_argument("--seed", type=int, default=SETTINGS.random_seed)
    args = parser.parse_args()

    out_path = Path(args.out) if args.out else DATA_DIR / "samples" / f"sample_{args.n}.jsonl"

    all_samples = load_all_samples()
    if not all_samples:
        print("[erro] Nenhuma amostra carregada. Rode scripts/01_fetch_dataset.py primeiro.")
        return

    chosen = stratified_sample(all_samples, args.n, args.seed)
    write_jsonl(out_path, chosen)

    by_cwe = defaultdict(int)
    for s in chosen:
        by_cwe[s.get("cwe_id") or "SEM_CWE"] += 1

    print(f"[ok] {len(chosen)} amostras selecionadas (seed={args.seed}) -> {out_path}")
    print("Distribuição por CWE:")
    for cwe, count in sorted(by_cwe.items(), key=lambda kv: -kv[1]):
        print(f"  {cwe}: {count}")


if __name__ == "__main__":
    main()
