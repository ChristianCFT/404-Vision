"""Contagem de pessoas na imagem da sala.

Por que a versão anterior contava menos gente do que tem na sala
-----------------------------------------------------------------
As fotos da base são de uma câmera de teto, 1920x1080, com ~50 alunos sentados.
Quem está no fundo aparece com 40-60 px de altura e metade do corpo escondida
pela carteira e pelo colega da frente. A configuração antiga era o pior caso
possível para isso:

  * `yolov8n` (o menor modelo) — pouca capacidade para objeto pequeno;
  * `imgsz=640` (padrão do Ultralytics) — a imagem era **reduzida 3x** antes de
    entrar na rede, então o aluno do fundo virava uma mancha de ~20 px;
  * `conf=0.35` — corte alto, e detecção de pessoa parcialmente oculta costuma
    sair com confiança baixa (0.15-0.3).

O que esta versão faz
---------------------
1. **Modelo maior** (`yolo11m` por padrão, ainda roda em CPU).
2. **Resolução alta** (`imgsz=1280`): o aluno do fundo chega à rede com o dobro
   de pixels.
3. **Confiança menor** (`0.15`) e `max_det` alto: deixa passar a detecção fraca
   de quem está meio escondido.
4. **Inferência em ladrilhos** (estilo SAHI): além da imagem inteira, a foto é
   dividida numa grade com sobreposição e cada pedaço é analisado em tamanho
   cheio. Um aluno de 50 px na foto original vira um "objeto grande" dentro do
   seu ladrilho. É o ganho maior em sala cheia.
5. **Fusão das detecções**: tudo é juntado e passa por um NMS próprio que
   também remove caixa contida em outra (o mesmo aluno visto pela foto inteira e
   pelo ladrilho), e descarta o corpo cortado na borda de ladrilho interno.

Tudo é configurável por variável de ambiente (veja `.env.example`), e o modo
antigo continua acessível: `AC_YOLO_LADRILHOS=0` desliga os ladrilhos.

Se o `ultralytics` não estiver instalado, o sistema **não quebra**: cai para a
contagem anotada da base (`data/labels.csv`), marcada como origem "anotacao".
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dataset import contagem_real

# caixa relativa à imagem (0..1), no formato que o front-end espera
Caixa = dict  # {"x": float, "y": float, "w": float, "h": float}


@dataclass
class Deteccao:
    pessoas: int
    caixas: list[Caixa] = field(default_factory=list)
    origem: str = "yolo"          # "yolo" | "anotacao"
    confiancas: list[float] = field(default_factory=list)


def contagem_do_nome(caminho: str) -> int | None:
    """Contagem anotada da imagem (labels.csv, ou o padrão "sala_16p.jpg").

    Mantido com este nome porque o app.py já importava daqui.
    """
    return contagem_real(caminho)


def _env_float(nome: str, padrao: float) -> float:
    try:
        return float(os.getenv(nome, padrao))
    except (TypeError, ValueError):
        return padrao


def _env_int(nome: str, padrao: int) -> int:
    try:
        return int(float(os.getenv(nome, padrao)))
    except (TypeError, ValueError):
        return padrao


# ------------------------------------------------------------ fusão de caixas ---
def _iou_e_contencao(a, b) -> tuple[float, float]:
    """(IoU, interseção/área da menor) entre duas caixas xyxy."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0, 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    uniao = area_a + area_b - inter
    menor = min(area_a, area_b)
    return (inter / uniao if uniao > 0 else 0.0,
            inter / menor if menor > 0 else 0.0)


def fundir(caixas: list[tuple], iou_max: float, contencao_max: float) -> list[tuple]:
    """NMS guloso com duas regras, pensado para sala cheia.

    Cada caixa é (x1, y1, x2, y2, conf). Percorre da mais confiante para a menos
    e descarta a candidata quando ela:
      * cobre demais uma já aceita (IoU > `iou_max`), ou
      * está praticamente dentro de uma já aceita (interseção/menor área >
        `contencao_max`) — o caso de o mesmo aluno ser visto pela foto inteira e
        pelo ladrilho, com caixas de tamanhos bem diferentes.

    `iou_max` é propositalmente alto (0.55+): em sala cheia duas pessoas
    diferentes se sobrepõem bastante, e um NMS agressivo apaga gente de verdade.
    """
    aceitas: list[tuple] = []
    for cand in sorted(caixas, key=lambda c: c[4], reverse=True):
        duplicada = False
        for ok in aceitas:
            iou, contencao = _iou_e_contencao(cand, ok)
            if iou > iou_max or contencao > contencao_max:
                duplicada = True
                break
        if not duplicada:
            aceitas.append(cand)
    return aceitas


def grade_ladrilhos(largura: int, altura: int, colunas: int, linhas: int,
                    sobreposicao: float) -> list[tuple[int, int, int, int]]:
    """Recortes (x1, y1, x2, y2) de uma grade com sobreposição entre vizinhos.

    A sobreposição (fração do ladrilho) evita que alguém fique cortado ao meio
    na divisa e não seja contado por ninguém.
    """
    if colunas < 1 or linhas < 1:
        return []
    passo_x = largura / colunas
    passo_y = altura / linhas
    margem_x = passo_x * sobreposicao
    margem_y = passo_y * sobreposicao
    recortes = []
    for i in range(colunas):
        for j in range(linhas):
            x1 = int(max(0, i * passo_x - margem_x))
            y1 = int(max(0, j * passo_y - margem_y))
            x2 = int(min(largura, (i + 1) * passo_x + margem_x))
            y2 = int(min(altura, (j + 1) * passo_y + margem_y))
            if x2 - x1 > 32 and y2 - y1 > 32:
                recortes.append((x1, y1, x2, y2))
    return recortes


class DetectorPessoas:
    """YOLO com carregamento preguiçoso, ladrilhos e fallback transparente."""

    def __init__(self, modelo: str | None = None, confianca: float | None = None):
        # --- modelo ---
        self.modelo_nome = modelo or os.getenv("AC_YOLO_MODELO", "yolo11m.pt")
        self.confianca = confianca if confianca is not None else _env_float("AC_YOLO_CONF", 0.05)
        self.imgsz = _env_int("AC_YOLO_IMGSZ", 1280)
        self.iou_nms = _env_float("AC_YOLO_IOU", 0.6)       # NMS interno do YOLO
        self.max_det = _env_int("AC_YOLO_MAX_DET", 600)
        self.tta = _env_int("AC_YOLO_TTA", 0) == 1          # augment=True (mais lento)

        # --- ladrilhos ---
        self.colunas = _env_int("AC_YOLO_LADRILHOS_X", 3)
        self.linhas = _env_int("AC_YOLO_LADRILHOS_Y", 2)
        if _env_int("AC_YOLO_LADRILHOS", 1) == 0:           # desliga tudo
            self.colunas = self.linhas = 1
        self.sobreposicao = _env_float("AC_YOLO_SOBREPOSICAO", 0.2)
        self.margem_borda = _env_int("AC_YOLO_MARGEM_BORDA", -1)  # px; -1 = regra desligada

        # --- fusão ---
        self.iou_fusao = _env_float("AC_YOLO_IOU_FUSAO", 0.55)
        self.contencao_fusao = _env_float("AC_YOLO_CONTENCAO", 0.7)
        self.area_min = _env_float("AC_YOLO_AREA_MIN", 0.00015)  # 0,015% da imagem
        self.area_max = _env_float("AC_YOLO_AREA_MAX", 0.35)

        self._modelo = None
        self._tentou_carregar = False
        self.disponivel = False       # vira True depois que os pesos carregam

    @property
    def instalado(self) -> bool:
        """Se o ultralytics está instalado (sem precisar carregar os pesos)."""
        import importlib.util
        return importlib.util.find_spec("ultralytics") is not None

    # ------------------------------------------------------------------ YOLO ---
    def _carregar(self):
        """Carrega o modelo uma única vez. Se falhar, marca YOLO como indisponível."""
        if self._tentou_carregar:
            return self._modelo
        self._tentou_carregar = True
        try:
            from ultralytics import YOLO  # import pesado: só aqui
            self._modelo = YOLO(self.modelo_nome)
            self.disponivel = True
            print(f"[detector] YOLO carregado: {self.modelo_nome} "
                  f"(imgsz={self.imgsz}, conf={self.confianca}, "
                  f"ladrilhos={self.colunas}x{self.linhas})")
        except Exception as e:
            self._modelo = None
            self.disponivel = False
            print(f"[detector] YOLO indisponível ({e}). Usando contagem anotada.")
        return self._modelo

    def _prever(self, imagem, recorte=None) -> list[tuple]:
        """Roda o YOLO num array (imagem inteira ou ladrilho).

        Devolve caixas em pixels da imagem ORIGINAL: (x1, y1, x2, y2, conf).
        """
        resultado = self._modelo.predict(
            imagem,
            conf=self.confianca,
            iou=self.iou_nms,
            imgsz=self.imgsz,
            classes=[0],          # só "person" (COCO)
            max_det=self.max_det,
            augment=self.tta,
            verbose=False,
        )[0]

        if resultado.boxes is None or len(resultado.boxes) == 0:
            return []

        dx, dy = (recorte[0], recorte[1]) if recorte else (0, 0)
        caixas = []
        xyxy = resultado.boxes.xyxy.tolist()
        confs = resultado.boxes.conf.tolist()
        for (x1, y1, x2, y2), c in zip(xyxy, confs):
            caixas.append((x1 + dx, y1 + dy, x2 + dx, y2 + dy, float(c)))
        return caixas

    def _descartar_cortadas(self, caixas, recorte, largura, altura) -> list[tuple]:
        """Tira detecções encostadas na divisa interna do ladrilho.

        Quem está na divisa aparece pela metade neste ladrilho, mas inteiro no
        vizinho (por causa da sobreposição). Ficar com as duas metades inflaria
        a contagem; então mantemos só a versão inteira.
        """
        if self.margem_borda < 0:      # AC_YOLO_MARGEM_BORDA=-1 desliga a regra
            return caixas
        x1r, y1r, x2r, y2r = recorte
        m = self.margem_borda
        mantidas = []
        for (x1, y1, x2, y2, c) in caixas:
            encosta_esq = x1 <= x1r + m and x1r > 0
            encosta_dir = x2 >= x2r - m and x2r < largura
            encosta_topo = y1 <= y1r + m and y1r > 0
            encosta_base = y2 >= y2r - m and y2r < altura
            if encosta_esq or encosta_dir or encosta_topo or encosta_base:
                continue
            mantidas.append((x1, y1, x2, y2, c))
        return mantidas

    def _detectar_yolo(self, caminho: str) -> Deteccao | None:
        modelo = self._carregar()
        if modelo is None:
            return None
        try:
            import cv2

            imagem = cv2.imread(caminho)
            if imagem is None:
                print(f"[detector] não consegui abrir a imagem: {caminho}")
                return None
            altura, largura = imagem.shape[:2]

            # 1) passada na imagem inteira (pega quem está perto da câmera)
            todas = self._prever(imagem)

            # 2) passada ladrilho a ladrilho (pega quem está no fundo da sala)
            recortes = grade_ladrilhos(largura, altura, self.colunas, self.linhas,
                                       self.sobreposicao)
            if len(recortes) > 1:
                for recorte in recortes:
                    x1, y1, x2, y2 = recorte
                    parciais = self._prever(imagem[y1:y2, x1:x2], recorte)
                    todas += self._descartar_cortadas(parciais, recorte, largura, altura)

            # 3) fusão + filtro de tamanho
            area_imagem = float(largura * altura)
            todas = [
                c for c in todas
                if self.area_min <= ((c[2] - c[0]) * (c[3] - c[1]) / area_imagem) <= self.area_max
            ]
            finais = fundir(todas, self.iou_fusao, self.contencao_fusao)

            caixas = [
                {"x": round(x1 / largura, 4), "y": round(y1 / altura, 4),
                 "w": round((x2 - x1) / largura, 4), "h": round((y2 - y1) / altura, 4)}
                for (x1, y1, x2, y2, _) in finais
            ]
            return Deteccao(
                pessoas=len(caixas),
                caixas=caixas,
                origem="yolo",
                confiancas=[round(c[4], 3) for c in finais],
            )
        except Exception as e:
            print(f"[detector] erro no YOLO ({e}); caindo para anotação.")
            return None

    # -------------------------------------------------------------- fallback ---
    @staticmethod
    def _detectar_anotacao(caminho: str) -> Deteccao:
        n = contagem_real(caminho)
        return Deteccao(pessoas=n if n is not None else 0, caixas=[], origem="anotacao")

    # ---------------------------------------------------------- API pública ---
    def detectar(self, caminho: str) -> Deteccao:
        """Conta as pessoas na imagem `caminho`, escolhendo YOLO ou anotação."""
        return self._detectar_yolo(caminho) or self._detectar_anotacao(caminho)


# instância padrão
detector = DetectorPessoas()


if __name__ == "__main__":  # teste rápido: python detector.py <imagem>
    import sys
    import time

    from dataset import listar_cenas

    alvos = sys.argv[1:] or listar_cenas()[-1:]  # sem argumento: a cena mais cheia
    for alvo in alvos:
        t0 = time.time()
        d = detector.detectar(alvo)
        real = contagem_real(alvo)
        extra = f" | anotado: {real} (erro {d.pessoas - real:+d})" if real is not None else ""
        print(f"{os.path.basename(alvo)}: {d.pessoas} pessoa(s) [{d.origem}] "
              f"em {time.time() - t0:.1f}s{extra}")
