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
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

import requests
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.config import DATA_DIR, PRIORITY_CWES  # noqa: E402
from common.schema import CodeSample, write_jsonl  # noqa: E402

DREA_REPO_URL = "https://github.com/huhusmang/DREA.git"
REPOPAIRBENCH_DIR = DATA_DIR / "repopairbench"
JSTS_DIR = DATA_DIR / "jsts_sample"

# Zenodo record 13118970 = CVEfixes v1.0.8 (publicado em 28/07/2024), confirmado via
# https://zenodo.org/records/13118970 — arquivo único de 12.7 GB. Se uma versão mais
# recente existir no momento da coleta, ajuste CVEFIXES_RECORD_ID/CVEFIXES_FILENAME
# (basta abrir https://zenodo.org/records/13118970 e seguir para "Versions" -> a mais
# nova, copiando o novo record id e nome de arquivo).
CVEFIXES_RECORD_ID = "13118970"
CVEFIXES_FILENAME = "CVEfixes_v1.0.8.zip"
CVEFIXES_DOWNLOAD_URL = f"https://zenodo.org/records/{CVEFIXES_RECORD_ID}/files/{CVEFIXES_FILENAME}?download=1"
CVEFIXES_LANGUAGES = ("JavaScript", "TypeScript")


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

    # Diretório onde clone_repos.sh materializa os repositórios-fonte. O script oficial do
    # DREA clona cada repo referenciado pelo nome "<owner>__<repo>" dentro de data/repos/
    # (convenção comum nesse tipo de dataset de mineração de repositórios). Se a versão do
    # DREA usada tiver uma convenção diferente, o fallback de busca recursiva abaixo ainda
    # encontra o repositório pelo nome.
    repos_root_candidates = [
        drea_clone / "data" / "repos",
        drea_clone / "data" / "repositories",
        drea_clone / "data",
    ]

    def _find_repo_dir(repo_full_name: str) -> Path | None:
        repo_short = repo_full_name.split("/")[-1]
        candidates = [repo_full_name.replace("/", "__"), repo_full_name.replace("/", "_"), repo_short]
        for root in repos_root_candidates:
            if not root.exists():
                continue
            for name in candidates:
                direct = root / name
                if (direct / ".git").exists():
                    return direct
            # Busca recursiva (até profundidade razoável) por uma pasta .git cujo nome bate.
            for git_dir in root.glob("**/.git"):
                if git_dir.parent.name in (repo_short, repo_full_name.replace("/", "__")):
                    return git_dir.parent
        return None

    def _git_show(repo_dir: Path, commit: str, path: str) -> str | None:
        try:
            proc = subprocess.run(
                ["git", "show", f"{commit}:{path}"], cwd=repo_dir,
                capture_output=True, text=True, timeout=30,
            )
            return proc.stdout if proc.returncode == 0 else None
        except (subprocess.TimeoutExpired, OSError):
            return None

    def _diff_lines(repo_dir: Path, commit_before: str, commit_after: str, path: str) -> list[int]:
        """Linhas do arquivo NO COMMIT VULNERÁVEL que foram alteradas pelo commit de
        correção — aproximação razoável de 'vulnerable_lines' quando o dataset de origem
        não as fornecer explicitamente."""
        try:
            proc = subprocess.run(
                ["git", "diff", "-U0", commit_before, commit_after, "--", path],
                cwd=repo_dir, capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                return []
            lines = []
            for hunk_line in proc.stdout.splitlines():
                if hunk_line.startswith("@@"):
                    # formato: @@ -start,count +start,count @@
                    minus_part = hunk_line.split(" ")[1]  # "-start,count"
                    start = int(minus_part.split(",")[0].lstrip("-"))
                    count = int(minus_part.split(",")[1]) if "," in minus_part else 1
                    lines.extend(range(start, start + max(count, 1)))
            return lines
        except (subprocess.TimeoutExpired, OSError, IndexError, ValueError):
            return []

    # Converte o manifest/jsonl original em CodeSample padronizado, já com o código extraído.
    samples: list[CodeSample] = []
    missing_repo_dirs: set[str] = set()
    with open(jsonl_path, "r", encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    for i, entry in enumerate(tqdm(entries, desc="Extraindo código do RepoPairBench")):
        repo = entry.get("repo", entry.get("repository", ""))
        commit_vuln = entry.get("vulnerable_commit", entry.get("commit_before", ""))
        commit_fixed = entry.get("fixed_commit", entry.get("commit_after"))
        file_path = entry.get("file_path", entry.get("path", ""))

        repo_dir = _find_repo_dir(repo) if repo else None
        code, vulnerable_lines, notes = "", [], ""

        if repo_dir is None:
            missing_repo_dirs.add(repo)
            notes = "repo não encontrado no checkout local após clone_repos.sh"
        else:
            shown = _git_show(repo_dir, commit_vuln, file_path)
            if shown is None:
                notes = f"git show falhou para {commit_vuln}:{file_path}"
            else:
                code = shown
                if commit_fixed:
                    vulnerable_lines = _diff_lines(repo_dir, commit_vuln, commit_fixed, file_path)

        samples.append(
            CodeSample(
                sample_id=f"rpb-{i:04d}",
                source_benchmark="repopairbench",
                language="python",
                repo=repo,
                commit_vulnerable=commit_vuln,
                commit_fixed=commit_fixed,
                file_path=file_path,
                code=code,
                is_vulnerable=True,
                cwe_id=entry.get("cwe_id", entry.get("cwe")),
                cve_id=entry.get("cve_id", entry.get("cve")),
                vulnerable_lines=vulnerable_lines,
                notes=notes,
            )
        )

    out_path = REPOPAIRBENCH_DIR / "samples.jsonl"
    write_jsonl(out_path, (s.to_dict() for s in samples))
    n_with_code = sum(1 for s in samples if s.code)
    print(f"[ok] {len(samples)} amostras do RepoPairBench escritas em {out_path}")
    print(f"      ({n_with_code}/{len(samples)} com código extraído com sucesso)")
    if missing_repo_dirs:
        print(
            f"[aviso] {len(missing_repo_dirs)} repositório(s) não encontrados no checkout local "
            f"(provavelmente clone_repos.sh falhou para eles, ex. repo removido/renomeado): "
            f"{sorted(missing_repo_dirs)[:10]}{'...' if len(missing_repo_dirs) > 10 else ''}\n"
            "         Essas amostras ficaram com 'code' vazio e devem ser descartadas na "
            "etapa de amostragem (script 02) ou re-investigadas manualmente."
        )


def _download_with_progress(url: str, dest: Path) -> None:
    if dest.exists():
        print(f"[skip] {dest} já existe, não vou baixar de novo (delete o arquivo para forçar).")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_dest = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        with open(tmp_dest, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc=f"Baixando {dest.name}"
        ) as bar:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                bar.update(len(chunk))
    tmp_dest.rename(dest)


def _locate_cvefixes_db(extract_dir: Path) -> Path | None:
    """O ZIP do CVEfixes contém um dump relacional; versões do dataset já publicaram isso
    tanto como um .sql (dump textual) quanto como um .db SQLite pronto (gerado pelo
    próprio pipeline `create_db.py` do projeto). Procuramos primeiro por um .db pronto; se
    só existir um .sql, materializamos um SQLite a partir dele."""
    db_candidates = list(extract_dir.glob("**/*.db"))
    if db_candidates:
        return db_candidates[0]

    sql_candidates = list(extract_dir.glob("**/*.sql"))
    if sql_candidates:
        sql_path = sql_candidates[0]
        db_path = sql_path.with_suffix(".db")
        print(f"Encontrei dump SQL ({sql_path.name}) sem .db pronto — materializando SQLite em {db_path}...")
        conn = sqlite3.connect(db_path)
        try:
            with open(sql_path, "r", encoding="utf-8", errors="replace") as f:
                conn.executescript(f.read())
            conn.commit()
        finally:
            conn.close()
        return db_path

    return None


# Nomes de tabela/coluna conforme o schema documentado do CVEfixes (paper PROMISE'21 +
# README do repositório secureIT-project/CVEfixes): a tabela `file_change` guarda o
# conteúdo antes/depois de cada arquivo alterado por um commit de correção, com uma coluna
# `programming_language` (derivada da extensão); `fixes` liga um `cve_id` a um `hash`
# (commit) via `repository`; `cwe_classification` liga `cve_id` a `cwe_id`.
# CONFIRME este schema contra o arquivo `Data/create_db.sql` do repositório ao rodar —
# dumps de versões diferentes podem ter pequenas variações de nome de coluna.
CVEFIXES_QUERY = """
SELECT
    fc.file_change_id   AS file_change_id,
    fc.filename          AS file_path,
    fc.programming_language AS language,
    fc.code_before        AS code_before,
    fc.code_after         AS code_after,
    f.hash                AS commit_vulnerable,
    f.repo_url            AS repo,
    cl.cve_id              AS cve_id,
    cw.cwe_id               AS cwe_id
FROM file_change fc
JOIN fixes f ON fc.hash = f.hash
JOIN cve cl ON f.cve_id = cl.cve_id
LEFT JOIN cwe_classification cw ON cl.cve_id = cw.cve_id
WHERE fc.programming_language IN ({langs})
"""


def fetch_jsts_sample() -> None:
    """Baixa o dump oficial do CVEfixes (Zenodo, record {record}, {fname}), extrai o
    banco relacional, filtra commits em JavaScript/TypeScript (opcionalmente restritos às
    CWEs prioritárias do estudo) e converte cada linha para o schema CodeSample.

    Aviso de tamanho: o download tem ~12.7 GB compactado. Rode isso com conexão estável e
    espaço em disco de sobra (o ZIP + a extração podem passar de 30 GB temporariamente).
    """.format(record=CVEFIXES_RECORD_ID, fname=CVEFIXES_FILENAME)
    JSTS_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = JSTS_DIR / CVEFIXES_FILENAME
    extract_dir = JSTS_DIR / "_cvefixes_extracted"

    print(f"Baixando CVEfixes de {CVEFIXES_DOWNLOAD_URL} ...")
    try:
        _download_with_progress(CVEFIXES_DOWNLOAD_URL, zip_path)
    except requests.RequestException as exc:
        print(
            f"[erro] Falha ao baixar o CVEfixes automaticamente ({exc}).\n"
            f"Baixe manualmente em https://zenodo.org/records/{CVEFIXES_RECORD_ID} e coloque "
            f"o arquivo em {zip_path}, depois rode este script de novo (ele detecta o arquivo "
            "já baixado e pula o download)."
        )
        return

    if not extract_dir.exists():
        print(f"Extraindo {zip_path.name} (pode levar alguns minutos)...")
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
    else:
        print(f"[skip] {extract_dir} já existe, não vou re-extrair.")

    db_path = _locate_cvefixes_db(extract_dir)
    if db_path is None:
        print(
            f"[erro] Não encontrei nenhum .db ou .sql dentro de {extract_dir} após extrair. "
            "A estrutura do release pode ter mudado — confira manualmente o conteúdo do ZIP "
            "e ajuste _locate_cvefixes_db() / CVEFIXES_QUERY (nomes de tabela/coluna) "
            "conforme o schema real encontrado."
        )
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    langs_sql = ", ".join(f"'{lang}'" for lang in CVEFIXES_LANGUAGES)
    try:
        cursor = conn.execute(CVEFIXES_QUERY.format(langs=langs_sql))
        rows = cursor.fetchall()
    except sqlite3.OperationalError as exc:
        print(
            f"[erro] A consulta SQL falhou contra o schema deste dump: {exc}\n"
            "Isso geralmente significa que os nomes de tabela/coluna em CVEFIXES_QUERY "
            f"(no topo de {Path(__file__).name}) não batem com esta versão do CVEfixes. "
            f"Abra {db_path} com `sqlite3 {db_path} '.schema'` (ou um visualizador de SQLite) "
            "para ver os nomes reais e ajustar a query."
        )
        conn.close()
        return
    conn.close()

    priority_cwe_set = set(PRIORITY_CWES)
    samples: list[CodeSample] = []
    for i, row in enumerate(rows):
        cwe_id = row["cwe_id"]
        if priority_cwe_set and cwe_id and cwe_id not in priority_cwe_set:
            continue  # mantém a amostra focada nas CWEs priorizadas pelo estudo
        language = "typescript" if str(row["language"]).lower() == "typescript" else "javascript"
        samples.append(
            CodeSample(
                sample_id=f"jsts-{i:04d}",
                source_benchmark="cvefixes_jsts",
                language=language,
                repo=row["repo"] or "",
                commit_vulnerable=row["commit_vulnerable"] or "",
                commit_fixed=None,  # CVEfixes já guarda before/after no próprio file_change
                file_path=row["file_path"] or "",
                code=row["code_before"] or "",
                is_vulnerable=True,
                cwe_id=cwe_id,
                cve_id=row["cve_id"],
                notes="code_after disponível na linha original do CVEfixes, se precisar do par corrigido",
            )
        )

    out_path = JSTS_DIR / "samples.jsonl"
    write_jsonl(out_path, (s.to_dict() for s in samples))
    print(f"[ok] {len(samples)} amostras JS/TS (CWEs prioritárias) escritas em {out_path}")
    if not samples:
        print(
            "[aviso] Nenhuma amostra sobrou após o filtro de CWE prioritária. Considere "
            "ampliar common.config.PRIORITY_CWES ou remover o filtro (defina "
            "priority_cwe_set vazio) para usar todas as CWEs disponíveis em JS/TS."
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
