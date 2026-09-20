"""Ajusta a correção linear da contagem usando a base rotulada.

Mesmo bem configurado, o YOLO erra de um jeito que tem padrão nesta sala: conta
um pouco **a mais** quando há 20-45 pessoas e um pouco **a menos** quando passa
de 45. Um ajuste linear (`pessoas = A · detectado + B`) corrige boa parte disso
sem treinar modelo nenhum.

O ajuste é feito em cima do cache (`data/deteccoes.json`), então é instantâneo —
não roda o YOLO de novo. Rode antes `python tools/precalcular.py`.

    python tools/calibrar.py            # ajusta, valida e mostra o que pôr no .env

Como a validação é feita: metade das cenas (alternadas, para manter a mistura de
ocupações) ajusta os coeficientes, a outra metade só serve para medir. O número
que importa é o da metade de teste — o ajuste nunca a viu.

⚠️ Os coeficientes valem para ESTA câmera e ESTE enquadramento. Trocou a sala ou
o ângulo, rotule algumas fotos novas e rode de novo.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, ".."))
sys.path.insert(0, os.path.join(RAIZ, "backend"))


def ajustar(pares: list[tuple[int, int]]) -> tuple[float, float]:
    """Mínimos quadrados de `real = A · detectado + B`."""
    n = len(pares)
    sx = sum(d for _, d in pares)
    sy = sum(r for r, _ in pares)
    sxx = sum(d * d for _, d in pares)
    sxy = sum(r * d for r, d in pares)
    denominador = n * sxx - sx * sx
    if denominador == 0:                 # todas as detecções iguais: não dá para ajustar
        return 1.0, 0.0
    a = (n * sxy - sx * sy) / denominador
    return a, (sy - a * sx) / n


def mae(pares, corrigir=lambda d: d) -> float:
    return sum(abs(corrigir(d) - r) for r, d in pares) / len(pares)


def main() -> int:
    p = argparse.ArgumentParser(description="Ajusta a calibração da contagem")
    p.add_argument("--minimo", type=int, default=20,
                   help="mínimo de cenas no cache para tentar ajustar (padrão: 20)")
    args = p.parse_args()

    import cache_deteccoes as cache
    from dataset import contagem_real
    from detector import detector

    itens = cache.carregar(detector)
    if not itens:
        print("Cache vazio ou de outra configuração. Rode antes:\n"
              "    python tools/precalcular.py")
        return 1

    pares = sorted(
        (contagem_real(nome), v["pessoas"])
        for nome, v in itens.items() if contagem_real(nome) is not None
    )
    if len(pares) < args.minimo:
        print(f"Só {len(pares)} cena(s) no cache; precisa de ao menos {args.minimo}. "
              "Rode mais um pouco de tools/precalcular.py.")
        return 1

    treino, teste = pares[0::2], pares[1::2]
    a, b = ajustar(treino)
    corrigir = lambda d: max(0, round(a * d + b))  # noqa: E731

    print(f"Cenas usadas: {len(pares)} ({len(treino)} para ajustar, {len(teste)} para testar)\n")
    print(f"Ajuste encontrado:  pessoas = {a:.3f} · detectado + {b:.2f}\n")
    print(f"{'':<12}{'MAE sem':>10}{'MAE com':>10}")
    print(f"{'ajuste':<12}{mae(treino):>10.1f}{mae(treino, corrigir):>10.1f}")
    print(f"{'teste':<12}{mae(teste):>10.1f}{mae(teste, corrigir):>10.1f}   <- o que vale")

    if mae(teste, corrigir) >= mae(teste):
        print("\nO ajuste NÃO melhorou nos dados de teste — deixe a calibração desligada.")
        return 0

    print("\nPara ativar, ponha isto no backend/.env:\n")
    print(f"    AC_CALIBRACAO_A={a:.3f}")
    print(f"    AC_CALIBRACAO_B={b:.2f}")
    print("\n(para desligar depois: A=1 e B=0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
