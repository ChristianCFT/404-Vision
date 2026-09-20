"""Gera a lista `demoFrames` do painel a partir da base rotulada.

O modo demonstração do frontend mostra uma rampa de ocupação (sala vazia ->
lotada) com fotos reais de `data/images` e a contagem de `data/labels.csv`.
Este script escolhe as cenas e imprime o trecho pronto para colar em
`frontend/config.js`:

    python tools/cenas_demo.py            # 9 cenas (padrão)
    python tools/cenas_demo.py -n 12
    python tools/cenas_demo.py --escrever # já troca o trecho no config.js
"""
from __future__ import annotations

import argparse
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, ".."))
sys.path.insert(0, os.path.join(RAIZ, "backend"))

CONFIG_JS = os.path.join(RAIZ, "frontend", "config.js")


def main() -> int:
    p = argparse.ArgumentParser(description="Gera demoFrames a partir da base")
    p.add_argument("-n", "--quantidade", type=int, default=9)
    p.add_argument("--escrever", action="store_true",
                   help="substitui o bloco demoFrames direto no frontend/config.js")
    args = p.parse_args()

    from dataset import amostra

    cenas = amostra(args.quantidade)
    if not cenas:
        print("Base vazia ou sem rótulos — confira data/images e data/labels.csv.")
        return 1

    itens = ",\n".join(
        f"    {{ file: '/data/images/{os.path.basename(c)}', count: {n} }}"
        for c, n in cenas
    )
    bloco = f"demoFrames: [\n{itens}\n  ]"

    if not args.escrever:
        print("Cole no lugar do bloco demoFrames em frontend/config.js:\n")
        print("  " + bloco)
        return 0

    with open(CONFIG_JS, encoding="utf-8") as f:
        texto = f.read()
    novo, trocas = re.subn(r"demoFrames:\s*\[.*?\n\s*\]", bloco, texto, count=1, flags=re.S)
    if not trocas:
        print("Não achei o bloco demoFrames em frontend/config.js — cole à mão.")
        return 1
    with open(CONFIG_JS, "w", encoding="utf-8") as f:
        f.write(novo)
    print(f"{len(cenas)} cena(s) escritas em {CONFIG_JS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
