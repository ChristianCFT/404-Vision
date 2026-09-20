"""Mede a qualidade da contagem do YOLO contra a base rotulada (`data/labels.csv`).

É aqui que o dataset "fecha o ciclo" com o código: em vez de olhar uma foto e
achar que está contando pouco, este script roda o detector nas imagens e compara
com a contagem real, imagem por imagem.

Uso:

    python tools/avaliar.py                 # 20 imagens espalhadas (rápido)
    python tools/avaliar.py --todas         # a base inteira
    python tools/avaliar.py -n 40 --csv resultado.csv
    python tools/avaliar.py --antigo        # configuração antiga, para comparar

Qualquer variável de ambiente do detector vale aqui também:

    AC_YOLO_CONF=0.10 AC_YOLO_LADRILHOS_X=4 python tools/avaliar.py -n 12

Métricas:
    MAE    erro médio absoluto, em pessoas (quanto menor, melhor)
    Viés   erro médio com sinal: negativo = está contando MENOS gente do que tem
    MAPE   erro percentual médio (ignora as salas vazias)
    ±10%   fração das cenas em que a contagem ficou a 10% da real
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, ".."))
sys.path.insert(0, os.path.join(RAIZ, "backend"))


def main() -> int:
    p = argparse.ArgumentParser(description="Avalia a contagem do YOLO contra o labels.csv")
    p.add_argument("-n", "--quantidade", type=int, default=20,
                   help="quantas imagens avaliar (espalhadas por ocupação). Padrão: 20")
    p.add_argument("--todas", action="store_true", help="usa a base inteira")
    p.add_argument("--csv", help="salva o resultado imagem a imagem neste arquivo")
    p.add_argument("--antigo", action="store_true",
                   help="força a configuração antiga (yolov8n, 640, conf .35, sem ladrilhos)")
    p.add_argument("--sem-cache", action="store_true",
                   help="ignora data/deteccoes.json e roda o YOLO de novo (lento)")
    p.add_argument("--so-cache", action="store_true",
                   help="avalia só as cenas que já estão no cache (instantâneo)")
    args = p.parse_args()

    if args.antigo:  # precisa vir ANTES de importar o detector (lê o ambiente no import)
        os.environ.update({
            "AC_YOLO_MODELO": "yolov8n.pt", "AC_YOLO_IMGSZ": "640",
            "AC_YOLO_CONF": "0.35", "AC_YOLO_LADRILHOS": "0",
        })

    import cache_deteccoes as cache
    from dataset import amostra, contagem_real, listar_cenas, resumo
    from detector import detector

    # Com o cache pronto (tools/precalcular.py) a avaliação é instantânea.
    salvas = {} if (args.sem_cache or args.antigo) else cache.carregar(detector)

    base = resumo()
    if not base["rotuladas"]:
        print(f"Nenhuma imagem rotulada. Confira {base['dir_imagens']} e {base['labels_csv']}.")
        return 1

    if args.todas:
        cenas = [(c, contagem_real(c)) for c in listar_cenas(so_rotuladas=True)]
    else:
        cenas = amostra(args.quantidade)

    if args.so_cache:
        cenas = [(c, r) for c, r in cenas if os.path.basename(c) in salvas]
        if not cenas:
            print("Nenhuma cena no cache. Rode antes: python tools/precalcular.py")
            return 1

    print(f"Base: {base['rotuladas']} imagens rotuladas | avaliando {len(cenas)}")
    print(f"Detector: {detector.modelo_nome} imgsz={detector.imgsz} conf={detector.confianca} "
          f"ladrilhos={detector.colunas}x{detector.linhas}\n")
    print(f"{'imagem':<14}{'real':>6}{'yolo':>6}{'erro':>7}{'seg':>7}")
    print("-" * 40)

    linhas = []
    t_total = time.time()
    for caminho, real in cenas:
        t0 = time.time()
        item = salvas.get(os.path.basename(caminho))
        d = cache.de_dicionario(item) if item else detector.detectar(caminho)
        dt = time.time() - t0
        if d.origem != "yolo":
            print("\nYOLO indisponível (caiu para a contagem anotada) — "
                  "instale o ultralytics para avaliar de verdade.")
            return 1
        erro = d.pessoas - real
        linhas.append({"imagem": os.path.basename(caminho), "real": real,
                       "yolo": d.pessoas, "erro": erro, "segundos": round(dt, 2)})
        print(f"{os.path.basename(caminho):<14}{real:>6}{d.pessoas:>6}{erro:>+7}{dt:>7.1f}")

    n = len(linhas)
    mae = sum(abs(l["erro"]) for l in linhas) / n
    vies = sum(l["erro"] for l in linhas) / n
    com_gente = [l for l in linhas if l["real"] > 0]
    mape = (sum(abs(l["erro"]) / l["real"] for l in com_gente) / len(com_gente) * 100
            if com_gente else 0.0)
    dentro = sum(1 for l in com_gente if abs(l["erro"]) <= 0.1 * l["real"])
    tempo_medio = sum(l["segundos"] for l in linhas) / n

    print("-" * 40)
    print(f"MAE .............. {mae:.1f} pessoas")
    print(f"Viés ............. {vies:+.1f} pessoas ({'conta menos' if vies < 0 else 'conta mais'} que o real)")
    print(f"MAPE ............. {mape:.1f}%")
    print(f"Dentro de ±10% ... {dentro}/{len(com_gente)} cenas")
    print(f"Tempo por imagem . {tempo_medio:.1f}s (total {time.time() - t_total:.0f}s)")

    # erro por faixa de ocupação: é onde dá para ver que o erro deixou de ser
    # um viés só para baixo e virou dispersão em torno do valor certo
    faixas = [(0, 0, "sala vazia"), (1, 15, "1 a 15"), (16, 30, "16 a 30"),
              (31, 45, "31 a 45"), (46, 10_000, "46 ou mais")]
    print(f"\n{'faixa':<12}{'cenas':>6}{'MAE':>7}{'viés':>8}")
    for lo, hi, nome in faixas:
        sub = [l for l in linhas if lo <= l["real"] <= hi]
        if not sub:
            continue
        e = [l["erro"] for l in sub]
        print(f"{nome:<12}{len(sub):>6}{sum(abs(x) for x in e) / len(e):>7.1f}"
              f"{sum(e) / len(e):>+8.1f}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["imagem", "real", "yolo", "erro", "segundos"])
            w.writeheader()
            w.writerows(linhas)
        print(f"\nDetalhe salvo em {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
