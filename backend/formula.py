"""Núcleo da fórmula de demanda de climatização.

Sem dependências externas: pode ser usado direto (import) ou via API (app.py).

    Ti = Te + N * K
    O  = min(N / N_MAX, 1)
    D  = (Ti - T_CONFORTO) * (1 + ALFA * O)
    AC = T_CONFORTO - D / 3   (limitado a 3°C abaixo do conforto; D <= 0 => desligado)

Ajustes desta versão (contexto 404-Vision / Itajubá):
    - temperatura de conforto padrão .... 23 °C
    - lotação máxima da sala ............. 80 lugares
    - K padrão .......................... 0.05 °C por pessoa
"""
import math
from dataclasses import dataclass

ALFA = 0.5              # reforço da ocupação sobre a demanda
DEMANDA_POR_GRAU = 3    # a cada 3 pontos de demanda, o AC desce 1°C
QUEDA_MAXIMA = 3        # o setpoint nunca fica mais de 3°C abaixo do conforto
LIMIAR_ALTA = 4.5       # demanda a partir da qual a climatização é "alta"

# Limites aceitos nas entradas (evitam valores absurdos vindos de fora)
LIMITES = {
    "temp_externa": (-50.0, 60.0),
    "pessoas": (0, 100_000),
    "t_conforto": (16.0, 30.0),
    "k": (0.0, 1.0),
    "n_max": (1, 100_000),
}


@dataclass(frozen=True)
class Parametros:
    t_conforto: float = 23.0   # temperatura de conforto (°C)
    k: float = 0.05            # °C que cada pessoa esquenta a sala
    n_max: int = 80            # lotação máxima da sala


@dataclass(frozen=True)
class Resultado:
    temp_interna_estimada: float
    ocupacao: float
    demanda: float
    ac_ligado: bool
    setpoint: int | None       # None quando o AC deve ficar desligado


class ValidacaoErro(ValueError):
    """Erro de validação. `erros` mapeia campo -> mensagem."""

    def __init__(self, erros: dict):
        super().__init__("entrada inválida")
        self.erros = erros


def _numero(valor):
    """Retorna float se `valor` for um número finito (bool não vale), senão None."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return float(valor) if math.isfinite(valor) else None


def _inteiro(valor):
    """Retorna int se `valor` for inteiro (aceita 70.0), senão None."""
    n = _numero(valor)
    return int(n) if n is not None and n.is_integer() else None


def _checa(erros, campo, valor, convertido):
    if convertido is None:
        erros[campo] = "deve ser um número" if campo not in ("pessoas", "n_max") else "deve ser um número inteiro"
        return None
    lo, hi = LIMITES[campo]
    if not lo <= convertido <= hi:
        erros[campo] = f"deve estar entre {lo} e {hi}"
        return None
    return convertido


def validar(temp_externa, pessoas, parametros: Parametros):
    """Valida entradas e parâmetros. Devolve (te, n, Parametros) já convertidos."""
    erros: dict = {}
    te = _checa(erros, "temp_externa", temp_externa, _numero(temp_externa))
    n = _checa(erros, "pessoas", pessoas, _inteiro(pessoas))
    tc = _checa(erros, "t_conforto", parametros.t_conforto, _numero(parametros.t_conforto))
    k = _checa(erros, "k", parametros.k, _numero(parametros.k))
    nm = _checa(erros, "n_max", parametros.n_max, _inteiro(parametros.n_max))
    if erros:
        raise ValidacaoErro(erros)
    return te, n, Parametros(t_conforto=tc, k=k, n_max=nm)


def calcular(temp_externa, pessoas, parametros: Parametros = Parametros()) -> Resultado:
    """Calcula demanda e temperatura do AC. Levanta ValidacaoErro se algo for inválido."""
    te, n, p = validar(temp_externa, pessoas, parametros)

    ti = te + n * p.k
    ocupacao = min(n / p.n_max, 1.0)
    demanda = (ti - p.t_conforto) * (1 + ALFA * ocupacao)

    if demanda <= 0:
        ligado, setpoint = False, None
    else:
        bruto = p.t_conforto - demanda / DEMANDA_POR_GRAU
        limitado = max(p.t_conforto - QUEDA_MAXIMA, min(p.t_conforto, bruto))
        ligado, setpoint = True, math.floor(limitado + 0.5)  # arredonda meio para cima

    return Resultado(
        temp_interna_estimada=round(ti, 2),
        ocupacao=round(ocupacao, 2),
        demanda=round(demanda, 2),
        ac_ligado=ligado,
        setpoint=setpoint,
    )


def classificar_demanda(resultado: Resultado, pessoas: int) -> tuple[str, str]:
    """Traduz o Resultado para o nível ('low'|'medium'|'high') e a recomendação
    que o front-end exibe. Mantém a mesma linguagem do painel.

    Regra de produto: sala vazia não é climatizada (a câmera existe justamente
    para não resfriar ambiente sem gente), mesmo que a temperatura peça."""
    if pessoas == 0:
        return "low", "Desligar aparelhos ociosos"
    if not resultado.ac_ligado:
        return "low", "Reduzir climatização"
    if resultado.demanda >= LIMIAR_ALTA:
        return "high", "Aumentar climatização"
    return "medium", "Manter climatização"
