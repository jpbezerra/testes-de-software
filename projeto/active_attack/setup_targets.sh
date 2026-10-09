#!/usr/bin/env bash
# Clona os repositórios oficiais das aplicações vulneráveis usadas na Abordagem D (RQ4),
# para que o docker-compose.yml possa buildá-las a partir do Dockerfile de cada projeto
# em vez de depender de um nome de imagem adivinhado no Docker Hub (namespaces de
# terceiros no Docker Hub podem estar desatualizados, não-oficiais, ou nem existir mais).
#
# Exceção: o OWASP Juice Shop TEM uma imagem oficial confirmada (bkimminich/juice-shop),
# publicada pelo próprio mantenedor do projeto (ver https://help.owasp-juice.shop/part1/running.html)
# — por isso ele é só "pull", não precisa ser clonado/buildado.
#
# Uso:
#   bash setup_targets.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENDOR_DIR="$SCRIPT_DIR/_vendor"
mkdir -p "$VENDOR_DIR"

clone_or_update() {
    local url="$1" dir="$2"
    if [ -d "$dir/.git" ]; then
        echo "[skip] $dir já existe, não vou re-clonar (delete a pasta para forçar)."
    else
        echo "Clonando $url -> $dir"
        git clone --depth 1 "$url" "$dir"
    fi
}

clone_or_update "https://github.com/OWASP/NodeGoat.git" "$VENDOR_DIR/nodegoat"
clone_or_update "https://github.com/adeyosemanputra/pygoat.git" "$VENDOR_DIR/pygoat"
clone_or_update "https://github.com/erev0s/VAmPI.git" "$VENDOR_DIR/vampi"

echo ""
echo "[ok] Repositórios clonados em $VENDOR_DIR."
echo "Confirme antes de buildar (as instruções/variáveis de ambiente de cada projeto podem"
echo "ter mudado desde que este script foi escrito):"
echo "  - $VENDOR_DIR/nodegoat/README.md   (docker-compose build / docker-compose up)"
echo "  - $VENDOR_DIR/pygoat/Dockerfile    (porta exposta e comando de start)"
echo "  - $VENDOR_DIR/vampi/Dockerfile e docker-compose.yml (variável de ambiente que ativa"
echo "    o modo vulnerável — no README do projeto, procure por 'vulnerable' no arquivo"
echo "    .env ou docker-compose.yml dele; esse projeto's próprio compose expõe a porta 5000)."
echo ""
echo "Depois de confirmar, rode: docker compose up -d --build"
