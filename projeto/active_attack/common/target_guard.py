"""
Allowlist de alvos para a Abordagem D (RQ4). TODA requisição HTTP feita pelo agente de
ataque passa por `assert_target_allowed()` antes de sair. Isso é uma restrição de
segurança/ética do projeto, não um detalhe de implementação — ver active_attack/README.md
e a nota ética em "Artigo - Testes de Software.md" > Motivação.

NÃO remova, comente ou flexibilize esta checagem para "só testar rápido". Se precisar
adicionar uma aplicação vulnerável nova, adicione o host dela em ALLOWED_HOSTS E no
docker-compose.yml — nunca aponte para um domínio/IP fora deste arquivo.
"""
from __future__ import annotations

from urllib.parse import urlparse

# Hosts correspondentes aos serviços definidos em active_attack/docker-compose.yml.
# "localhost"/"127.0.0.1" são incluídos porque as portas são publicadas no host para
# facilitar debug fora do container do agente; em produção (agente também em container na
# mesma rede Docker), os nomes de serviço (ex. "juice-shop") seriam o caminho normal.
ALLOWED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "juice-shop",
    "pygoat",
    "vampi",
    "nodegoat",
}

ALLOWED_PORTS = {3000, 8000, 5000, 4000}


class ForbiddenTargetError(Exception):
    """Levantado quando o agente tenta requisitar algo fora da allowlist. Isso deve ser
    tratado como um erro fatal de execução — nunca capturado silenciosamente para "tentar
    de outro jeito"."""


def assert_target_allowed(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    port = parsed.port

    if parsed.scheme not in ("http", "https"):
        raise ForbiddenTargetError(f"Esquema não permitido: {url!r}")

    if host not in ALLOWED_HOSTS:
        raise ForbiddenTargetError(
            f"Host '{host}' não está na allowlist de aplicações propositalmente "
            f"vulneráveis (ALLOWED_HOSTS em active_attack/common/target_guard.py). "
            f"URL bloqueada: {url!r}"
        )

    if port is not None and port not in ALLOWED_PORTS:
        raise ForbiddenTargetError(
            f"Porta {port} não está na allowlist ({sorted(ALLOWED_PORTS)}). URL bloqueada: {url!r}"
        )
