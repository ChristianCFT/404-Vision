# 404-Vision
# Participação da SECOMP - UNIFEI
#
# Atalho para subir o sistema completo (backend + painel) a partir da raiz:
#
#     python main.py
#
# Depois, abra http://localhost:8000 no navegador.
import os
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(RAIZ, "backend")
sys.path.insert(0, BACKEND)

from backend.app import CENAS, FEED_DIR, app, detector, iniciar_aquecimento  # noqa: E402
from backend.dataset import resumo  # noqa: E402

if __name__ == "__main__":
    porta = int(os.getenv("PORT", "8000"))
    base = resumo()

    print(f"[404-Vision] base: {base['imagens']} imagem(ns), "
          f"{base['rotuladas']} rotulada(s) em {base['labels_csv']}")
    print(f"[404-Vision] feed da câmera: {len(CENAS)} cena(s) em {FEED_DIR}")
    if not CENAS:
        print("[404-Vision] AVISO: nenhuma imagem encontrada. "
              "Confira a pasta data/images ou a variável AC_FEED_DIR.")

    # Sobe a thread que calcula as detecções do YOLO em segundo plano.
    # (O painel já responde antes de ela terminar, usando a contagem da base.)
    iniciar_aquecimento()

    print(f"[404-Vision] painel em http://localhost:{porta}")
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=porta)
