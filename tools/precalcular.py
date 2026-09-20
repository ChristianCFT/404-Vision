"""Roda o YOLO uma vez em cada imagem da base e guarda o resultado em cache.

Depois disso o painel fica instantâneo: o backend lê `data/deteccoes.json` em
vez de chamar a rede neural a cada troca de cena.

    python tools/precalcular.py            # só o que ainda falta
    python tools/precalcular.py --refazer  # recalcula tudo
    python tools/precalcular.py -n 12      # só uma amostra (teste rápido)

Pode ser interrompido com Ctrl+C: o que já foi calculado fica salvo.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, ".."))
sys.path.insert(0, os.path.join(RAIZ, "backend"))


def main() -> int:
    p = argparse.ArgumentParser(description="Pré-calcula as detecções da base")
    p.add_argument("-n", "--quantidade", type=int, help="usa só uma amostra de N imagens")
    p.add_argument("--refazer", action="store_true", help="ignora o que já está no cache")
    args = p.parse_args()

    import cache_deteccoes as cache
    from dataset import amostra, contagem_real, listar_cenas
    from detector import detector

    cenas = ([c for c, _ in amostra(args.quantidade)] if args.quantidade
             else listar_cenas())
    if not cenas:
        print("Nenhuma imagem encontrada na base.")
        return 1

    itens = {} if args.refazer else cache.carregar(detector)
    pendentes = [c for c in cenas if os.path.basename(c) not in itens]
    print(f"{len(cenas)} cena(s) | {len(pendentes)} a calcular")
    if not pendentes:
        print("Cache já está completo.")
        return 0

    t0 = time.time()
    try:
        for i, caminho in enumerate(pendentes, 1):
            d = detector.detectar(caminho)
            if d.origem != "yolo":
                print("\nYOLO indisponível — instale o ultralytics "
                      "(pip install -r backend/requirements.txt).")
                return 1
            itens[os.path.basename(caminho)] = cache.para_dicionario(d)
            real = contagem_real(caminho)
            erro = f"{d.pessoas - real:+d}" if real is not None else "?"
            decorrido = time.time() - t0
            falta = decorrido / i * (len(pendentes) - i)
            print(f"[{i}/{len(pendentes)}] {os.path.basename(caminho):<14} "
                  f"yolo={d.pessoas:<3} real={real if real is not None else '?':<3} "
                  f"erro={erro:<4} restam ~{falta / 60:.0f} min")
            if i % 10 == 0:
                cache.salvar(detector, itens)   # salva de tempos em tempos
    except KeyboardInterrupt:
        print("\nInterrompido — salvando o que já foi calculado…")

    cache.salvar(detector, itens)
    print(f"\n{len(itens)} detecção(ões) no cache ({cache.CAMINHO})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
