"""Ponte entre a base de imagens (`data/`) e o resto do sistema.

A base tem duas partes:

    data/images/imgNN.jpg   as fotos da sala (1920x1080, câmera de teto)
    data/labels.csv         a contagem real de cada foto: image_file_name,count

Este módulo é o único lugar que sabe onde essas coisas ficam. Todos os outros
usam as funções daqui:

    caminho_base()            -> .../data
    contagem_real("img01.jpg")-> 53   (ou None se a foto não estiver rotulada)
    listar_cenas()            -> caminhos das imagens, em ordem de ocupação
    amostra(n)                -> n cenas espalhadas do vazio ao lotado (para a demo)

Nada aqui depende de Flask, YOLO ou internet: dá para importar no Jupyter, num
script de avaliação ou num teste.
"""
from __future__ import annotations

import csv
import os
import re
from functools import lru_cache

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, ".."))

# Dá para apontar para outra base com variáveis de ambiente.
DATA_DIR = os.path.abspath(os.getenv("AC_DATA_DIR", os.path.join(RAIZ, "data")))
IMAGENS_DIR = os.path.abspath(os.getenv("AC_IMAGENS_DIR", os.path.join(DATA_DIR, "images")))
LABELS_CSV = os.path.abspath(os.getenv("AC_LABELS_CSV", os.path.join(DATA_DIR, "labels.csv")))

EXTENSOES = (".jpg", ".jpeg", ".png")

# nome no estilo antigo das cenas de demonstração: "sala_16p.jpg" -> 16
_PADRAO_NOME = re.compile(r"_(\d+)\s*p", re.IGNORECASE)


def caminho_base() -> str:
    return DATA_DIR


def caminho_imagens() -> str:
    return IMAGENS_DIR


@lru_cache(maxsize=1)
def rotulos() -> dict[str, int]:
    """Lê `labels.csv` uma única vez: {"img01.jpg": 53, ...}.

    Tolerante: aceita CRLF, espaços sobrando, cabeçalho ausente e linhas
    quebradas (uma linha ruim não derruba a base inteira).
    """
    tabela: dict[str, int] = {}
    if not os.path.exists(LABELS_CSV):
        print(f"[dataset] labels.csv não encontrado em {LABELS_CSV}")
        return tabela

    with open(LABELS_CSV, newline="", encoding="utf-8-sig") as f:
        for linha in csv.reader(f):
            if len(linha) < 2:
                continue
            nome, valor = linha[0].strip(), linha[1].strip()
            if not nome or nome.lower() in ("image_file_name", "image", "arquivo"):
                continue  # cabeçalho
            try:
                tabela[nome.lower()] = int(float(valor))
            except ValueError:
                print(f"[dataset] linha ignorada em labels.csv: {linha!r}")
    return tabela


def contagem_real(caminho_ou_nome: str) -> int | None:
    """Contagem anotada da imagem, ou None se ela não estiver na base.

    Aceita caminho completo ou só o nome do arquivo. Se não achar no CSV, ainda
    tenta o padrão antigo do nome ("sala_16p.jpg"), para as cenas de demo.
    """
    nome = os.path.basename(caminho_ou_nome).strip().lower()
    if nome in rotulos():
        return rotulos()[nome]
    m = _PADRAO_NOME.search(nome)
    return int(m.group(1)) if m else None


def listar_cenas(diretorio: str | None = None, so_rotuladas: bool = False) -> list[str]:
    """Imagens da base, ordenadas pela ocupação anotada (vazio -> lotado).

    As sem rótulo vão para o fim, em ordem alfabética — assim o feed da "câmera"
    sempre começa com a sala vazia e enche aos poucos, o que fica bom na demo.
    """
    pasta = diretorio or IMAGENS_DIR
    if not os.path.isdir(pasta):
        return []
    arquivos = [
        os.path.join(pasta, n)
        for n in os.listdir(pasta)
        if n.lower().endswith(EXTENSOES)
    ]
    if so_rotuladas:
        arquivos = [c for c in arquivos if contagem_real(c) is not None]
    arquivos.sort(key=lambda c: (contagem_real(c) is None, contagem_real(c) or 0, os.path.basename(c)))
    return arquivos


def amostra(quantidade: int = 9, diretorio: str | None = None) -> list[tuple[str, int]]:
    """`quantidade` cenas bem distribuídas entre a mais vazia e a mais cheia.

    Serve para o modo demonstração do painel: em vez de 119 fotos quase iguais,
    mostra uma rampa de ocupação. Devolve [(caminho, contagem), ...].
    """
    cenas = [(c, contagem_real(c)) for c in listar_cenas(diretorio, so_rotuladas=True)]
    if not cenas or quantidade <= 0:
        return []
    if quantidade >= len(cenas):
        return cenas
    # pega índices igualmente espaçados na lista já ordenada por ocupação
    passo = (len(cenas) - 1) / (quantidade - 1) if quantidade > 1 else 0
    escolhidos = {round(i * passo) for i in range(quantidade)}
    return [cenas[i] for i in sorted(escolhidos)]


def resumo() -> dict:
    """Números da base, usados em /saude e nos scripts."""
    cenas = listar_cenas()
    rotuladas = [c for c in cenas if contagem_real(c) is not None]
    contagens = [contagem_real(c) for c in rotuladas]
    return {
        "dir_imagens": IMAGENS_DIR,
        "labels_csv": LABELS_CSV,
        "imagens": len(cenas),
        "rotuladas": len(rotuladas),
        "sem_rotulo": len(cenas) - len(rotuladas),
        "rotulos_sem_imagem": sorted(
            set(rotulos()) - {os.path.basename(c).lower() for c in cenas}
        ),
        "min": min(contagens) if contagens else None,
        "max": max(contagens) if contagens else None,
        "media": round(sum(contagens) / len(contagens), 1) if contagens else None,
    }


if __name__ == "__main__":  # python dataset.py -> confere se a base está ligada
    r = resumo()
    print(f"imagens .......... {r['imagens']} em {r['dir_imagens']}")
    print(f"rotuladas ........ {r['rotuladas']} (sem rótulo: {r['sem_rotulo']})")
    print(f"ocupação ......... de {r['min']} a {r['max']} pessoas (média {r['media']})")
    if r["rotulos_sem_imagem"]:
        print(f"rótulos sem foto . {len(r['rotulos_sem_imagem'])}: {r['rotulos_sem_imagem'][:6]}...")
    print("amostra p/ demo .. " + ", ".join(
        f"{os.path.basename(c)}={n}" for c, n in amostra(9)
    ))
