# APS — Testes Automatizados, Adequação e Análise de Mutação

Suíte de testes automatizados (pytest) e análise de mutação (mutmut) para o
`Scholarship Eligibility Evaluator`, na versão Python.

Tecnologias escolhidas:

* **Linguagem:** Python 3.11
* **Framework de teste:** pytest
* **Ferramenta de mutação:** mutmut (v3.7)

(justificativa completa no relatório, `docs/RELATORIO.md` / `docs/RELATORIO.pdf`)

## Estrutura de diretórios

```
aps-scholarship-eligibility/
├── src/
│   └── scholarship_eligibility_evaluator.py   # sistema-base (não alterado na lógica)
├── tests/
│   └── test_scholarship_eligibility_evaluator.py
├── conftest.py                                # coloca src/ no sys.path para os testes
├── pyproject.toml                             # config do pytest e do mutmut
├── requirements.txt
├── mutation_reports/
│   ├── initial/                                # saída da 1ª rodada do mutmut (score inicial)
│   ├── final/                                   # saída da 2ª rodada, após corrigir as lacunas
│   └── manual_equivalent_mutant/                # evidência do mutante equivalente analisado manualmente
└── docs/
    ├── RELATORIO.md                            # relatório (fonte)
    └── RELATORIO.pdf                           # relatório (PDF, mesmo conteúdo)
```

## Pré-requisitos

* Python 3.10+
* pip

## Instalação

A partir da pasta `aps-scholarship-eligibility/`:

```bash
pip install -r requirements.txt
```

## Como executar os testes

Comando principal:

```bash
pytest
```

Saída esperada: **29 testes, todos passando** (`29 passed`).

Para ver os testes individualmente (verboso):

```bash
pytest -v
```

> O arquivo `conftest.py` na raiz do projeto adiciona `src/` ao `sys.path`
> automaticamente — não é necessário instalar o pacote nem configurar
> `PYTHONPATH` manualmente.

## Como executar a análise de mutação

O mutmut já está configurado via `pyproject.toml` (seção `[tool.mutmut]`):
`source_paths = ["src"]` e a suíte de testes em `tests/`.

Executar a análise de mutação (isso mutará `src/scholarship_eligibility_evaluator.py`
e rodará a suíte pytest contra cada mutante):

```bash
mutmut run
```

Ver o placar resumido:

```bash
mutmut results
```

Ver todos os mutantes, incluindo os mortos:

```bash
mutmut results --all true
```

Ver o diff de um mutante específico (sobrevivente ou não):

```bash
mutmut show <nome_do_mutante>
# ex.: mutmut show scholarship_eligibility_evaluator.x__validate_inputs__mutmut_7
```

Exportar um resumo (score) em JSON:

```bash
mutmut export-cicd-stats
# grava mutants/mutmut-cicd-stats.json
```

> Observação: esta versão do mutmut (3.x) não possui um comando de relatório
> HTML embutido (`mutmut html` não existe mais); por isso os relatórios desta
> entrega estão em texto/JSON, salvos em `mutation_reports/` (ver seção
> abaixo), conforme permitido pelo enunciado ("HTML, texto ou equivalente").

### Nenhuma configuração adicional é necessária

O `pyproject.toml` já traz tudo que o mutmut precisa (`source_paths`,
`also_copy` para incluir `conftest.py`/`tests/` na cópia mutada, e
`pytest_add_cli_args_test_selection`). O `mutmut run` cria uma pasta
`mutants/` (ignorada no `.gitignore`) com uma cópia do projeto por mutante —
pode ser apagada e regenerada a qualquer momento com `mutmut run` novamente.

## Relatórios de mutação entregues

* `mutation_reports/initial/` — rodada inicial da suíte (antes de examinar os
  sobreviventes): score, lista completa de mutantes e diffs dos 2 sobreviventes.
* `mutation_reports/final/` — rodada final, após as correções motivadas pela
  análise de mutação: score final e lista completa.
* `mutation_reports/manual_equivalent_mutant/` — diff do mutante equivalente
  identificado manualmente (`frozen=True` → `frozen=False`, que o mutmut não
  gera por padrão porque só muta código dentro de corpos de função) e a
  evidência de que a suíte final não o mata (nem deveria, ver `docs/RELATORIO.md`).

Os detalhes de cada mutante analisado, a justificativa do mutante equivalente
e a discussão de adequação estão em `docs/RELATORIO.md` (também disponível em
PDF, `docs/RELATORIO.pdf`, com o mesmo conteúdo).
