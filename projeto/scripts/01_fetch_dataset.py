#!/usr/bin/env python
"""
Baixa/reconstrói os dois benchmarks usados no experimento:

1. RepoPairBench (Python) — clona o artefato público do artigo DREA (Sun & Meng, 2026) e
   reconstrói o dataset de pares vulnerável/corrigido a partir de
   `data/repopairbench_100.jsonl` + `data/scripts/clone_repos.sh`.
   Repositório: https://github.com/huhusmang/DREA

2. Amostra curada JS/TS via CVEfixes — CVEfixes é um dataset de commits de correção de
   vulnerabilidades (multi-linguagem) construído a partir do NVD. Este script faz o
   download do dump oficial e filtra apenas commits em JavaScript/TypeScript.
   Repositório: https://github.com/secureIT-project/CVEfixes

Uso:
    python scripts/01_fetch_dataset.py --only repopairbench
    python scripts/01_fetch_dataset.py --only jsts
    python scripts/01_fetch_dataset.py              # ambos

Saída:
    data/repopairbench/samples.jsonl   (schema: common.schema.CodeSample)
    data/jsts_sample/samples.jsonl     (schema: common.schema.CodeSample)
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.config import DATA_DIR  # noqa: E402
from common.schema import CodeSample, write_jsonl  # noqa: E402

DREA_REPO_URL = "https://github.com/huhusmang/DREA.git"
REPOPAIRBENCH_DIR = DATA_DIR / "repopairbench"
JSTS_DIR = DATA_DIR / "jsts_sample"


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"$ {' '.join(cmd)}" + (f"  (cwd={cwd})" if cwd else ""))
    subprocess.run(cmd, cwd=cwd, check=True)


def fetch_repopairbench() -> None:
    """Clona o repositório DREA (contém o RepoPairBench) e roda o script de
    reconstrução oficial do dataset (clone dos repositórios-fonte + checkout dos
    commits vulnerável/corrigido)."""
    REPOPAIRBENCH_DIR.mkdir(parents=True, exist_ok=True)
    drea_clone = REPOPAIRBENCH_DIR / "_drea_src"

    if not drea_clone.exists():
        _run(["git", "clone", "--depth", "1", DREA_REPO_URL, str(drea_clone)])
    else:
        print(f"[skip] {drea_clone} já existe, não vou re-clonar (delete a pasta para forçar).")

    manifest_path = drea_clone / "data" / "repopairbench_100_manifest.json"
    jsonl_path = drea_clone / "data" / "repopairbench_100.jsonl"
    clone_script = drea_clone / "data" / "scripts" / "clone_repos.sh"

    if not jsonl_path.exists():
        raise FileNotFoundError(
            f"Não encontrei {jsonl_path} — a estrutura do repositório DREA pode ter mudado. "
            "Confira manualmente em https://github.com/huhusmang/DREA/tree/main/data"
        )

    # Reconstrói os repositórios-fonte (clona cada repo referenciado e faz checkout dos
    # commits vulnerável/corrigido). Este passo pode demorar bastante (são ~100 repositórios).
    if clone_script.exists():
        print("Rodando o script oficial de reconstrução do dataset (pode levar minutos)...")
        _run(["bash", str(clone_script)], cwd=drea_clone / "data")
    else:
        print(
            f"[aviso] {clone_script} não encontrado — pulei a reconstrução automática dos "
            "repositórios. Verifique manualmente o DATASET.md do DREA para o procedimento "
            "atualizado antes de prosseguir."
        )

    # Converte o manifest/jsonl original em CodeSample padronizado.
    samples: list[CodeSample] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            # Os nomes de campo exatos do RepoPairBench devem ser confirmados ao abrir o
            # arquivo (estrutura pode variar); os campos abaixo são os mais prováveis
            # segundo a documentação do DREA — AJUSTE conforme necessário ao rodar.
            samples.append(
                CodeSample(
                    sample_id=f"rpb-{i:04d}",
                    source_benchmark="repopairbench",
                    language="python",
                    repo=entry.get("repo", entry.get("repository", "")),
                    commit_vulnerable=entry.get("vulnerable_commit", entry.get("commit_before", "")),
                    commit_fixed=entry.get("fixed_commit", entry.get("commit_after")),
                    file_path=entry.get("file_path", entry.get("path", "")),
                    code="",  # preenchido depois a partir do repositório clonado (ver TODO abaixo)
                    is_vulnerable=True,
                    cwe_id=entry.get("cwe_id", entry.get("cwe")),
                    cve_id=entry.get("cve_id", entry.get("cve")),
                    notes="code vazio — ver TODO em 01_fetch_dataset.py: extrair do checkout local",
                )
            )

    out_path = REPOPAIRBENCH_DIR / "samples.jsonl"
    write_jsonl(out_path, (s.to_dict() for s in samples))
    print(f"[ok] {len(samples)} amostras do RepoPairBench escritas em {out_path}")
    print(
        "[TODO equipe] O campo 'code' ficou vazio: depois que clone_repos.sh reconstruir os "
        "repositórios em _drea_src/data/repos/<algo>, escreva um passo que leia o conteúdo de "
        "cada 'file_path' no commit 'commit_vulnerable' (via `git show <sha>:<path>`) e "
        "preencha 'code' e 'vulnerable_lines'. A estrutura exata de onde os repos são "
        "clonados depende da versão do clone_repos.sh — confira no terminal ao rodar."
    )


def fetch_jsts_sample() -> None:
    """Esqueleto para a amostra complementar JS/TS via CVEfixes.

    CVEfixes publica um dump em SQLite (CVEfixes.db) via Zenodo, além do código-fonte do
    gerador em https://github.com/secureIT-project/CVEfixes. Como o dump é grande (GBs) e
    o link de download exato muda por versão, este passo é deixado como TODO explícito
    para a equipe (decisão: baixar o dump completo é caro; melhor seria baixar só a
    tabela de commits/CWEs filtrados em JS/TS, se o Zenodo permitir range request, ou usar
    o script `create_db.py` do próprio projeto para gerar apenas o subconjunto JS/TS).
    """
    JSTS_DIR.mkdir(parents=True, exist_ok=True)
    print(
        "[TODO equipe] Download do CVEfixes ainda não implementado automaticamente.\n"
        "Passos manuais sugeridos:\n"
        "  1. Acessar https://github.com/secureIT-project/CVEfixes e localizar o link atual\n"
        "     do dump no Zenodo (procurar por 'CVEfixes.db' ou 'CVEfixes_v1.0.7.tar.gz').\n"
        "  2. Baixar o .db e colocar em data/jsts_sample/CVEfixes.db (git-ignored).\n"
        "  3. Rodar uma consulta SQL filtrando commits com programming_language IN "
        "('JavaScript','TypeScript') e CWE em common.config.PRIORITY_CWES.\n"
        "  4. Converter cada linha para o schema CodeSample (source_benchmark='cvefixes_jsts') "
        "e salvar em data/jsts_sample/samples.jsonl — mesmo formato do RepoPairBench.\n"
        "Deixe este script fazer esse ETL quando o link/esquema do dump estiver confirmado."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=["repopairbench", "jsts"], default=None)
    args = parser.parse_args()

    if args.only in (None, "repopairbench"):
        fetch_repopairbench()
    if args.only in (None, "jsts"):
        fetch_jsts_sample()


if __name__ == "__main__":
    main()
