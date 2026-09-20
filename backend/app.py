"""Back-end do 404-Vision — integra câmera (YOLO), clima (Open-Meteo) e fórmula.

Sobe um único servidor Flask que:
  - serve o painel (frontend/) na raiz  -> abra http://localhost:8000
  - usa a base `data/images` como "feed" da câmera, ciclando pelas cenas
  - conta as pessoas de cada cena com o YOLO (detector.py)
  - compara com a contagem anotada em `data/labels.csv` (transparência: o painel
    e a API mostram o valor real e o erro da detecção)
  - busca a temperatura externa de Itajubá na API Open-Meteo (com cache)
  - aplica a fórmula de climatização e decide os ares-condicionados

O YOLO em resolução alta leva alguns segundos por imagem, então as detecções são
calculadas **em segundo plano** e guardadas em `data/deteccoes.json`. Enquanto
uma cena ainda não foi processada, a API responde com a contagem anotada da base
e avisa isso no campo `deteccao.origem` — o painel nunca fica travado.

Endpoints:
    GET  /                  -> painel (index.html)
    GET  /api/status        -> estado atual (JSON consumido pelo frontend)
    GET  /api/frame         -> imagem atual da câmera
    GET  /api/cenas         -> lista das cenas da base com a contagem anotada
    GET  /data/images/<f>   -> uma imagem da base (usada pelo modo demonstração)
    GET  /saude             -> diagnóstico (base, YOLO, cache)
    GET  /config            -> parâmetros padrão em uso
    POST /calcular          -> calcula demanda para entradas arbitrárias
"""
import os
import threading
import time
from dataclasses import asdict
from datetime import datetime

from flask import Flask, jsonify, request, send_file, send_from_directory

import cache_deteccoes as cache
import dataset
from clima import provedor as clima
from detector import Deteccao, contagem_do_nome, detector  # noqa: F401 (reexport)
from formula import Parametros, ValidacaoErro, calcular, classificar_demanda

# ------------------------------------------------------------------ config ---
AQUI = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(AQUI, "..", "frontend"))

# O feed da câmera é a base de imagens do projeto (antes apontava para uma pasta
# de demonstração que nem existe no repositório — era por isso que o painel
# aparecia sem imagem e com 0 pessoas).
FEED_DIR = os.path.abspath(os.getenv("AC_FEED_DIR", dataset.caminho_imagens()))
CICLO_S = float(os.getenv("AC_CICLO_S", "5"))       # segundos por cena
NUM_ACS = int(os.getenv("AC_NUM_APARELHOS", "4"))
SALA = os.getenv("AC_SALA", "Sala B-03")
CAMERA = os.getenv("AC_CAMERA", "Câmera 1")
PRECALCULAR = os.getenv("AC_PRECALCULAR", "1") == "1"  # thread de aquecimento
# Zona morta contra detecção fantasma: uma única caixa solta numa sala vazia é
# quase sempre ruído (mochila, cadeira), e ligar o ar por causa dela quebra a
# regra de produto "sala vazia não é climatizada". Coloque 1 para desligar.
PESSOAS_MINIMAS = int(os.getenv("AC_PESSOAS_MINIMAS", "2"))
# Calibração opcional da contagem: pessoas = A * detectado + B.
# Padrão (1, 0) = desligada. Ajuste os valores com tools/calibrar.py — ela
# corrige o excesso em sala média e a falta em sala cheia, mas vale só para
# ESTA câmera/sala: mudou o ângulo, refaça o ajuste.
CALIBRACAO_A = float(os.getenv("AC_CALIBRACAO_A", "1"))
CALIBRACAO_B = float(os.getenv("AC_CALIBRACAO_B", "0"))

INICIO = time.monotonic()
_ultimo: dict = {}                       # último estado, usado por /api/frame


def parametros_do_ambiente() -> Parametros:
    """Lê os padrões de variáveis de ambiente (AC_T_CONFORTO, AC_K, AC_N_MAX)."""
    base = Parametros()
    return Parametros(
        t_conforto=float(os.getenv("AC_T_CONFORTO", base.t_conforto)),
        k=float(os.getenv("AC_K", base.k)),
        n_max=int(os.getenv("AC_N_MAX", base.n_max)),
    )


def carregar_cenas() -> list[str]:
    """Cenas do feed, em ordem crescente de ocupação (a base sabe a ordem)."""
    return dataset.listar_cenas(FEED_DIR)


CENAS = carregar_cenas()


# --------------------------------------------------------- cache de detecção ---
class CacheDeteccoes:
    """Guarda as detecções em memória + disco e as calcula em segundo plano.

    `obter` nunca bloqueia: devolve a detecção pronta ou None. Quem chama decide
    o que fazer enquanto o YOLO não termina (aqui: usa a contagem anotada).
    """

    def __init__(self):
        self.itens: dict[str, dict] = cache.carregar(detector)
        self.trava = threading.Lock()
        self.calculando: str | None = None
        self.novos_desde_salvar = 0

    def obter(self, caminho: str):
        item = self.itens.get(os.path.basename(caminho))
        return cache.de_dicionario(item) if item else None

    def calcular(self, caminho: str):
        """Roda o YOLO (bloqueante) e guarda o resultado."""
        nome = os.path.basename(caminho)
        d = detector.detectar(caminho)
        if d.origem != "yolo":       # sem ultralytics: não vale a pena cachear
            return d
        with self.trava:
            self.itens[nome] = cache.para_dicionario(d)
            self.novos_desde_salvar += 1
            if self.novos_desde_salvar >= 5:
                cache.salvar(detector, self.itens)
                self.novos_desde_salvar = 0
        return d

    def aquecer(self, cenas: list[str]):
        """Thread de fundo: calcula as cenas que ainda faltam, uma a uma."""
        faltando = [c for c in cenas if os.path.basename(c) not in self.itens]
        if not faltando:
            print("[cache] todas as cenas já têm detecção salva.")
            return
        print(f"[cache] calculando {len(faltando)} cena(s) em segundo plano "
              f"(o painel já funciona; use tools/precalcular.py para adiantar)")
        for caminho in faltando:
            try:
                self.calculando = os.path.basename(caminho)
                self.calcular(caminho)
            except Exception as e:                      # nunca derruba o servidor
                print(f"[cache] falha em {os.path.basename(caminho)}: {e}")
            finally:
                self.calculando = None
        with self.trava:
            cache.salvar(detector, self.itens)
            self.novos_desde_salvar = 0
        print("[cache] pré-cálculo concluído.")

    def prontas(self) -> int:
        return len(self.itens)


deteccoes = CacheDeteccoes()


def iniciar_aquecimento():
    """Sobe a thread de pré-cálculo (só uma vez, e só se houver cenas)."""
    if not PRECALCULAR or not CENAS:
        return
    t = threading.Thread(target=deteccoes.aquecer, args=(CENAS,),
                         name="precalculo-yolo", daemon=True)
    t.start()


# -------------------------------------------------------------- feed/câmera ---
def cena_atual() -> str | None:
    """Escolhe a cena pelo tempo decorrido, em vaivém (0 -> fim -> 0)."""
    if not CENAS:
        return None
    if len(CENAS) == 1:
        return CENAS[0]
    passos = int((time.monotonic() - INICIO) / CICLO_S)
    periodo = len(CENAS) - 1
    pos = passos % (2 * periodo)
    idx = pos if pos <= periodo else 2 * periodo - pos
    return CENAS[idx]


def calibrar(n: int) -> int:
    """Aplica a correção linear na contagem bruta.

    Sala vazia continua vazia: o intercepto B é positivo e arredondaria 0 para
    1, ligando o ar num ambiente sem ninguém — exatamente o que a regra de
    produto proíbe. A correção só vale quando já há alguém detectado.
    """
    if n <= 0 or (CALIBRACAO_A == 1 and CALIBRACAO_B == 0):
        return n
    return max(0, round(CALIBRACAO_A * n + CALIBRACAO_B))


def aplicar_zona_morta(d: Deteccao) -> Deteccao:
    """Trata contagem abaixo de PESSOAS_MINIMAS como sala vazia."""
    if 0 < d.pessoas < PESSOAS_MINIMAS:
        return Deteccao(pessoas=0, caixas=[], origem=f"{d.origem} (abaixo do mínimo)")
    return d


def detectar_cena(caminho: str) -> Deteccao:
    """Detecção da cena: do cache, ou a contagem anotada enquanto o YOLO não vem."""
    pronta = deteccoes.obter(caminho)
    if pronta is not None:
        return aplicar_zona_morta(pronta)
    if not PRECALCULAR:              # sem thread de fundo: calcula na hora
        return aplicar_zona_morta(deteccoes.calcular(caminho))
    n = dataset.contagem_real(caminho)
    return Deteccao(pessoas=n or 0, caixas=[], origem="anotacao (YOLO em fila)")


def montar_ares(nivel: str, setpoint):
    """Decide quantos aparelhos ligar conforme a demanda; todos no mesmo setpoint."""
    ligar = {"low": 0, "medium": 2, "high": NUM_ACS}.get(nivel, 0)
    ares = []
    for i in range(NUM_ACS):
        ligado = i < ligar
        ares.append({
            "id": f"A{i + 1}",
            "on": ligado,
            "setpoint": setpoint if ligado else None,
            "mode": "Refrigerando" if ligado else "Desligado",
        })
    return ares


def montar_status(params: Parametros) -> dict:
    """Roda o pipeline completo (câmera -> clima -> fórmula) e devolve o JSON do painel."""
    cena = cena_atual()
    deteccao = detectar_cena(cena) if cena else None
    bruto = deteccao.pessoas if deteccao else 0
    pessoas = calibrar(bruto)
    caixas = deteccao.caixas if deteccao else []
    origem_det = deteccao.origem if deteccao else "indisponível"

    tempo = clima.obter()
    resultado = calcular(tempo.temperatura, pessoas, params)
    nivel, recomendacao = classificar_demanda(resultado, pessoas)
    ares = montar_ares(nivel, resultado.setpoint)

    nome_cena = os.path.basename(cena) if cena else None
    real = dataset.contagem_real(cena) if cena else None

    status = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "room": SALA,
        "camera": CAMERA,
        "capacity": params.n_max,
        "people": pessoas,
        "outdoor_temp": tempo.temperatura,
        "k": params.k,
        "estimated_temp": resultado.temp_interna_estimada,
        "demand": nivel,
        "recommendation": recomendacao,
        "acs": ares,
        "detections": caixas,
        # o nome da cena vai na URL: evita cache do navegador e garante que a
        # imagem mostrada é a mesma que gerou este JSON
        "frame_url": f"/api/frame?cena={nome_cena}" if nome_cena else "/api/frame",
        # extras (transparência — o frontend ignora o que não usa)
        "clima": {
            "cidade": tempo.cidade,
            "sensacao": tempo.sensacao,
            "origem": tempo.origem,
            "horario": tempo.horario,
        },
        "deteccao": {
            "origem": origem_det,
            "ocupacao": resultado.ocupacao,
            "demanda": resultado.demanda,
            "cena": nome_cena,
            "bruto": bruto,                                   # antes da calibração
            "anotado": real,                                  # verdade da base
            "erro": (pessoas - real) if real is not None else None,
            "cenas_prontas": deteccoes.prontas(),
            "cenas_total": len(CENAS),
        },
    }
    _ultimo["frame_path"] = cena
    _ultimo["status"] = status
    return status


# --------------------------------------------------------------------- app ---
def criar_app(padrao: Parametros | None = None) -> Flask:
    app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
    app.json.ensure_ascii = False
    padrao = padrao or parametros_do_ambiente()
    origem_permitida = os.getenv("AC_CORS_ORIGIN", "*")

    @app.after_request
    def cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = origem_permitida
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return resp

    # ---- painel ----
    @app.get("/")
    def index():
        return send_file(os.path.join(FRONTEND_DIR, "index.html"))

    # ---- API consumida pelo painel (modo "Backend") ----
    @app.get("/api/status")
    def api_status():
        return jsonify(montar_status(padrao))

    @app.get("/api/frame")
    def api_frame():
        pedida = request.args.get("cena")
        caminho = None
        if pedida:  # só aceita nome de arquivo dentro do feed (evita path traversal)
            candidato = os.path.join(FEED_DIR, os.path.basename(pedida))
            if os.path.exists(candidato):
                caminho = candidato
        caminho = caminho or _ultimo.get("frame_path") or cena_atual()
        if not caminho or not os.path.exists(caminho):
            return jsonify(erro="nenhuma cena disponível"), 404
        return send_file(caminho, max_age=0)

    # ---- base de imagens ----
    @app.get("/api/cenas")
    def api_cenas():
        """Cenas da base com a contagem anotada (o modo demonstração usa isto)."""
        cenas = [
            {
                "arquivo": os.path.basename(c),
                "url": f"/data/images/{os.path.basename(c)}",
                "anotado": dataset.contagem_real(c),
                "detectado": (d.pessoas if (d := deteccoes.obter(c)) else None),
            }
            for c in CENAS
        ]
        return jsonify(total=len(cenas), cenas=cenas)

    @app.get("/data/images/<path:arquivo>")
    def imagem_da_base(arquivo):
        return send_from_directory(dataset.caminho_imagens(), arquivo, max_age=3600)

    # ---- utilitários / diagnóstico ----
    @app.get("/saude")
    def saude():
        base = dataset.resumo()
        return jsonify(
            status="ok",
            cenas=len(CENAS),
            feed_dir=FEED_DIR,
            yolo=detector.instalado,
            yolo_carregado=detector.disponivel,
            modelo=detector.modelo_nome,
            deteccoes_prontas=deteccoes.prontas(),
            calculando=deteccoes.calculando,
            base={"imagens": base["imagens"], "rotuladas": base["rotuladas"],
                  "labels_csv": base["labels_csv"]},
        )

    @app.get("/config")
    def config():
        return jsonify(asdict(padrao))

    @app.post("/calcular")
    def rota_calcular():
        corpo = request.get_json(silent=True)
        if not isinstance(corpo, dict):
            return jsonify(erro="corpo deve ser um JSON objeto"), 400

        faltando = {c: "campo obrigatório" for c in ("temp_externa", "pessoas") if c not in corpo}
        if faltando:
            return jsonify(erro="entrada inválida", detalhes=faltando), 400

        params = Parametros(
            t_conforto=corpo.get("t_conforto", padrao.t_conforto),
            k=corpo.get("k", padrao.k),
            n_max=corpo.get("n_max", padrao.n_max),
        )
        try:
            r = calcular(corpo["temp_externa"], corpo["pessoas"], params)
        except ValidacaoErro as e:
            return jsonify(erro="entrada inválida", detalhes=e.erros), 400

        nivel, rec = classificar_demanda(r, int(corpo["pessoas"]))
        return jsonify(
            entrada={"temp_externa": corpo["temp_externa"], "pessoas": corpo["pessoas"]},
            parametros={"t_conforto": params.t_conforto, "k": params.k, "n_max": params.n_max},
            resultado={
                "temp_interna_estimada": r.temp_interna_estimada,
                "ocupacao": r.ocupacao,
                "demanda": r.demanda,
            },
            ac={"ligado": r.ac_ligado, "setpoint": r.setpoint},
            demanda={"nivel": nivel, "recomendacao": rec},
        )

    @app.errorhandler(404)
    def nao_encontrado(_):
        return jsonify(erro="rota não encontrada"), 404

    @app.errorhandler(405)
    def metodo_invalido(_):
        return jsonify(erro="método não permitido"), 405

    return app


app = criar_app()

if __name__ == "__main__":
    print(f"[404-Vision] {len(CENAS)} cena(s) em {FEED_DIR}")
    print(f"[404-Vision] painel em http://localhost:{os.getenv('PORT', '8000')}")
    iniciar_aquecimento()
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))
