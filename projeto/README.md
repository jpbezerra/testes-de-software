# Avaliação de LLMs na Detecção de Vulnerabilidades — Pipeline de Experimento

Scripts e artefatos de pesquisa do projeto de Fundamentos de Testes de Software (2026.2):
**"Avaliação de Modelos de Linguagem (LLMs) na Detecção de Vulnerabilidades de Segurança em
Código-Fonte: um Estudo Comparativo com Ferramentas de Análise Estática (SAST)"**.

Este diretório implementa as quatro abordagens descritas em `Metodologia`/`Experimentos` do
artigo (`Artigo - Testes de Software.md`):

- **Abordagem A** — SAST tradicional (Semgrep, CodeQL) sobre o benchmark.
- **Abordagem B** — LLM como detector de código (Claude e Gemini), full-text reading.
- **Abordagem C** — Triagem de achados do SAST usando **Jev** (TypeSafe AI) e
  **jury-as-a-judge** (painel Claude + Gemini).
- **Abordagem D** — Teste ativo/dinâmico (RQ4) contra aplicações **propositalmente vulneráveis**
  (OWASP Juice Shop, PyGoat, VAmPI, NodeGoat), em rede Docker isolada sem acesso externo.

## ⚠️ Restrição ética/legal (leia antes de rodar qualquer coisa de `active_attack/`)

Os scripts em `active_attack/` **só podem ser apontados para os containers definidos em
`active_attack/docker-compose.yml`**, executados localmente, em rede Docker isolada
(`internal: true`, sem rota para a internet). **Nunca** aponte o agente de ataque para um
domínio, IP ou sistema de terceiros. Isso é ilegal no Brasil (Lei 12.737/2012)
independentemente da intenção de divulgação responsável. Os scripts incluem uma allowlist de
hosts (`active_attack/common/target_guard.py`) que bloqueia qualquer alvo fora dos containers
conhecidos — não remova essa checagem.

## Estrutura

```
projeto/
├── .env.example              # variáveis de ambiente (chaves de API) — copie para .env
├── requirements.txt
├── data/
│   ├── repopairbench/        # dataset Python reconstruído (git-ignored, baixado pelo script 01)
│   ├── jsts_sample/          # amostra curada JS/TS via CVEfixes (git-ignored)
│   └── samples/              # amostras estratificadas para piloto/execução completa
├── scripts/
│   ├── common/                 # config, schema de dados, clientes de LLM, prompts
│   ├── 01_fetch_dataset.py      # baixa/reconstrói RepoPairBench + builda amostra JS/TS
│   ├── 02_sample_dataset.py     # amostragem estratificada por CWE (piloto ~20-30, completo ~200-300)
│   ├── 03_run_sast.py           # roda Semgrep (+ CodeQL opcional) — Abordagem A
│   ├── 04_run_llm_detectors.py  # roda Claude + Gemini como detectores — Abordagem B
│   ├── 05_run_triage.py         # roda Jev + jury-as-a-judge sobre achados do SAST — Abordagem C
│   ├── 06_consolidate.py        # junta tudo num dataset único com o gabarito
│   └── 07_compute_metrics.py    # precisão/recall/F1/FPR, custo/tempo, teste de McNemar
├── active_attack/             # Abordagem D (RQ4) — ver aviso acima
│   ├── setup_targets.sh         # clona NodeGoat/PyGoat/VAmPI (sem imagem oficial no Docker Hub)
│   ├── docker-compose.yml       # Juice Shop (pull), PyGoat/VAmPI/NodeGoat (build) em rede isolada
│   ├── common/target_guard.py   # allowlist de hosts — nunca remover
│   └── agent_harness.py         # agente de ataque (Condição 1: guiada / Condição 2: autônoma)
├── results/                    # saídas (CSV/JSON) de cada etapa — versionar no repositório
└── logs/                       # logs de execução
```

## Setup

```bash
cd projeto
python -m venv .venv
. .venv/Scripts/activate        # Windows (cmd/PowerShell: .venv\Scripts\Activate.ps1)
pip install -r requirements.txt
copy .env.example .env           # depois edite .env com as chaves de API do time
```

### Chaves necessárias (ver `.env.example`)

- `ANTHROPIC_API_KEY` — console.anthropic.com (API, **não** é a mesma coisa que Claude Pro/claude.ai).
- `GOOGLE_API_KEY` — Google AI Studio (aistudio.google.com) (**não** é a mesma coisa que Gemini
  app/Gemini Advanced).
- `OPENROUTER_API_KEY` — openrouter.ai, usado para acessar o **Jev** (`typesafe/jev-latest`).
- Semgrep é instalado via `pip` (já no `requirements.txt`).
- **CodeQL CLI** (opcional, só se `--tools codeql` for usado em `03_run_sast.py`): baixe em
  https://github.com/github/codeql-action/releases (ou siga
  https://docs.github.com/en/code-security/codeql-cli/getting-started-with-the-codeql-cli/setting-up-the-codeql-cli)
  e garanta que o binário `codeql` esteja no PATH. Os query packs são baixados
  automaticamente na primeira análise (`--download`).

## Ordem de execução (piloto)

```bash
python scripts/01_fetch_dataset.py          # baixa RepoPairBench + monta amostra JS/TS
python scripts/02_sample_dataset.py --n 25  # amostra piloto estratificada por CWE
python scripts/03_run_sast.py --input data/samples/pilot.jsonl
python scripts/04_run_llm_detectors.py --input data/samples/pilot.jsonl
python scripts/05_run_triage.py --sast-results results/sast_findings.jsonl
python scripts/06_consolidate.py
python scripts/07_compute_metrics.py
```

Depois de validar o piloto (ver se os prompts/parsers estão funcionando e os resultados fazem
sentido), repita com `--n 200` (ou o N final definido pela equipe) para a coleta completa.

A Abordagem D (`active_attack/`) é tratada como um módulo separado e mais arriscado — ver o
`README` dentro da própria pasta antes de rodar.

## Convenções de dados

Todos os scripts trocam dados em **JSON Lines** (`.jsonl`), um objeto por linha, com os campos
mínimos definidos em `scripts/common/schema.py`. Isso facilita versionar no git (diffs linha a
linha) e processar incrementalmente.
