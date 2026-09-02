import os
import sys

# Garante que o pacote em src/ seja importável nos testes,
# sem precisar instalar o projeto ou alterar o PYTHONPATH manualmente.
SRC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)
