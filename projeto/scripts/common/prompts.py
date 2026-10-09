"""
Prompts padronizados e versionados usados em todas as chamadas de LLM do experimento.

IMPORTANTE (validade do experimento): o prompt usado na coleta final deve ser EXATAMENTE
este (ou uma versão nova, com o número de versão incrementado e registrada no artigo em
"Ameaças à Validade"). Não editar o texto de um prompt no meio de uma coleta sem recomeçar
a coleta daquela abordagem — isso introduziria uma variável de confusão entre amostras.
"""

PROMPT_VERSION = "v1.0"

# ----------------------------------------------------------------------------------------
# Abordagem B — LLM como detector (lê o código e aponta vulnerabilidades), RQ1/RQ2
# ----------------------------------------------------------------------------------------

DETECTOR_SYSTEM_PROMPT = f"""Você é um analista de segurança de aplicações (AppSec) revisando \
código-fonte em busca de vulnerabilidades de segurança. Você NÃO tem acesso a ferramentas \
externas — analise apenas o código fornecido, como faria em uma revisão manual de código.

Responda SOMENTE com um objeto JSON válido (sem markdown, sem texto antes ou depois), no \
formato exato:

{{
  "is_vulnerable": true | false,
  "cwe_id": "CWE-XXX" | null,
  "vulnerable_lines": [int, ...],
  "confidence": 0.0-1.0,
  "justification": "explicação curta (1-3 frases) do raciocínio"
}}

Regras:
- "is_vulnerable" deve refletir se existe PELO MENOS UMA vulnerabilidade de segurança \
explorável no trecho (não apenas má prática de estilo/qualidade de código).
- "cwe_id" é a categoria CWE mais específica e apropriada; use null se is_vulnerable=false \
ou se não for possível classificar com confiança.
- "vulnerable_lines" são os números de linha (1-indexados, conforme fornecidos no trecho) \
mais diretamente responsáveis pela vulnerabilidade; lista vazia se is_vulnerable=false.
- "confidence" é sua probabilidade calibrada de que o veredito "is_vulnerable" está correto.
- Analise apenas o trecho fornecido; não invente contexto externo ao arquivo.
# prompt_version: {PROMPT_VERSION}
"""

DETECTOR_USER_PROMPT_TEMPLATE = """Analise o seguinte arquivo ({language}, caminho: {file_path}) \
em busca de vulnerabilidades de segurança:

```{language}
{code}
```
"""


def build_detector_user_prompt(language: str, file_path: str, code: str) -> str:
    # Adiciona números de linha para que o LLM referencie linhas corretamente.
    numbered = "\n".join(f"{i+1}: {line}" for i, line in enumerate(code.splitlines()))
    return DETECTOR_USER_PROMPT_TEMPLATE.format(language=language, file_path=file_path, code=numbered)


# ----------------------------------------------------------------------------------------
# Abordagem C.1 — Triagem com Jev (TypeSafe AI): classificar achado do SAST como TP/FP
# ----------------------------------------------------------------------------------------

TRIAGE_JEV_SYSTEM_PROMPT = f"""Você está triando um achado de uma ferramenta SAST (análise \
estática). Dado o trecho de código e a descrição do achado, decida se é um verdadeiro \
positivo (vulnerabilidade real) ou falso positivo (alerta incorreto/não explorável).

Responda SOMENTE com JSON no formato:
{{"verdict": "true_positive" | "false_positive", "confidence": 0.0-1.0}}
# prompt_version: {PROMPT_VERSION}
"""

TRIAGE_USER_PROMPT_TEMPLATE = """Achado da ferramenta {tool} (regra: {rule_id}, CWE: {cwe_id}):
"{message}"

Linhas {line_start}-{line_end} do arquivo ({language}):
```{language}
{code_snippet}
```

Este achado é um verdadeiro positivo ou falso positivo?
"""


def build_triage_user_prompt(
    tool: str, rule_id: str, cwe_id: str, message: str, line_start: int, line_end: int,
    language: str, code_snippet: str,
) -> str:
    return TRIAGE_USER_PROMPT_TEMPLATE.format(
        tool=tool, rule_id=rule_id, cwe_id=cwe_id, message=message,
        line_start=line_start, line_end=line_end, language=language, code_snippet=code_snippet,
    )


# ----------------------------------------------------------------------------------------
# Abordagem C.2 — jury-as-a-judge (painel Claude + Gemini) sobre o mesmo achado do SAST
# ----------------------------------------------------------------------------------------
# Reusa o mesmo par (system, user) da triagem do Jev para manter o julgamento comparável
# entre os três "juízes" (Jev, Claude, Gemini); a agregação (voto majoritário / média de
# confiança) é feita em scripts/05_run_triage.py, não no prompt.

JURY_SYSTEM_PROMPT = TRIAGE_JEV_SYSTEM_PROMPT
build_jury_user_prompt = build_triage_user_prompt
