"""Cache em disco das detecções do YOLO (`data/deteccoes.json`).

Por que existe: rodar o YOLO em resolução alta + ladrilhos custa alguns segundos
por imagem. O painel atualiza a cada 2 s e troca de cena a cada 5 s — sem cache,
a primeira exibição de cada cena trava a requisição.

Como funciona: as detecções já calculadas ficam num JSON, indexadas pelo nome do
arquivo. O cache guarda junto a "assinatura" da configuração do detector
(modelo, imgsz, conf, ladrilhos). Se você mudar qualquer parâmetro, a assinatura
muda e o cache antigo é ignorado — nunca mostra número calculado com outra
configuração.

    python tools/precalcular.py     # preenche o cache da base inteira
"""
from __future__ import annotations

import json
import os
import threading

from dataset import DATA_DIR

CAMINHO = os.path.abspath(os.getenv("AC_CACHE_DETECCOES", os.path.join(DATA_DIR, "deteccoes.json")))
_trava = threading.Lock()


def assinatura(detector) -> str:
    """Identifica a configuração do detector; muda quando um parâmetro muda."""
    return "|".join(str(x) for x in (
        detector.modelo_nome, detector.imgsz, detector.confianca, detector.iou_nms,
        detector.colunas, detector.linhas, detector.sobreposicao,
        detector.margem_borda, detector.iou_fusao, detector.contencao_fusao,
        detector.tta,
    ))


def carregar(detector) -> dict[str, dict]:
    """Detecções salvas que valem para a configuração atual ({nome: {...}})."""
    if not os.path.exists(CAMINHO):
        return {}
    try:
        with open(CAMINHO, encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError) as e:
        print(f"[cache] arquivo ilegível ({e}); começando do zero.")
        return {}

    if dados.get("assinatura") != assinatura(detector):
        print("[cache] configuração do detector mudou; o cache antigo será ignorado.")
        return {}
    itens = dados.get("imagens", {})
    print(f"[cache] {len(itens)} detecção(ões) reaproveitada(s) de {CAMINHO}")
    return itens


def salvar(detector, itens: dict[str, dict]) -> None:
    """Grava o cache inteiro (escrita atômica: grava .tmp e renomeia)."""
    with _trava:
        os.makedirs(os.path.dirname(CAMINHO), exist_ok=True)
        temporario = CAMINHO + ".tmp"
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump({"assinatura": assinatura(detector), "imagens": itens},
                      f, ensure_ascii=False)
        os.replace(temporario, CAMINHO)


def para_dicionario(deteccao) -> dict:
    # guarda também as confianças: permite reavaliar outro corte de confiança
    # depois, sem rodar o YOLO de novo.
    return {"pessoas": deteccao.pessoas, "caixas": deteccao.caixas,
            "origem": deteccao.origem, "confiancas": deteccao.confiancas}


def de_dicionario(item: dict):
    from detector import Deteccao
    return Deteccao(pessoas=int(item.get("pessoas", 0)),
                    caixas=list(item.get("caixas", [])),
                    origem=item.get("origem", "yolo"),
                    confiancas=list(item.get("confiancas", [])))
