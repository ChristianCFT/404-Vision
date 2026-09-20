"""Temperatura externa em tempo real via API Open-Meteo.

Coordenadas padrão: Itajubá - MG (sede da UNIFEI / SECOMP).
Endpoint usado (o mesmo passado no enunciado, acrescido de `current` e `timezone`):

    https://api.open-meteo.com/v1/forecast?latitude=-22.4122&longitude=-45.4563
        &current=temperature_2m,apparent_temperature
        &hourly=temperature_2m,apparent_temperature

Estratégia:
    - guarda a última leitura por alguns minutos (cache) para não bombardear a API;
    - se a API falhar (sem internet, timeout, etc.), devolve o último valor conhecido
      ou um padrão, marcando a origem como "fallback". O sistema nunca trava por isso.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

import requests

# --- configuração (Itajubá - MG) ---
LATITUDE = -22.4122
LONGITUDE = -45.4563
CIDADE = "Itajubá - MG"
FUSO = "America/Sao_Paulo"

URL = "https://api.open-meteo.com/v1/forecast"
TEMPO_CACHE_S = 600      # 10 min: a temperatura externa não muda a cada segundo
TIMEOUT_S = 8
TEMP_FALLBACK = 24.0     # usado só se a API nunca respondeu


@dataclass
class Clima:
    temperatura: float          # temperature_2m (°C) — o "Te" da fórmula
    sensacao: float | None      # apparent_temperature (°C)
    horario: str                # horário da medição (ISO) ou "-"
    cidade: str
    origem: str                 # "open-meteo" | "cache" | "fallback"


class ProvedorClima:
    """Busca a temperatura externa e mantém um cache simples em memória."""

    def __init__(self, latitude: float = LATITUDE, longitude: float = LONGITUDE,
        cidade: str = CIDADE, fuso: str = FUSO):
        self.latitude = latitude
        self.longitude = longitude
        self.cidade = cidade
        self.fuso = fuso
        self._cache: Clima | None = None
        self._buscado_em = 0.0

    def _consultar_api(self) -> Clima:
        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "current": "temperature_2m,apparent_temperature",
            "hourly": "temperature_2m,apparent_temperature",
            "timezone": self.fuso,
            "forecast_days": 1,
        }
        resp = requests.get(URL, params=params, timeout=TIMEOUT_S)
        resp.raise_for_status()
        dados = resp.json()

        # 1ª opção: bloco "current" (valor instantâneo)
        atual = dados.get("current") or {}
        temp = atual.get("temperature_2m")
        sensacao = atual.get("apparent_temperature")
        horario = atual.get("time", "-")

        # 2ª opção: se "current" não veio, pega a hora atual dentro de "hourly"
        if temp is None:
            temp, sensacao, horario = self._da_hora_atual(dados)

        if temp is None:
            raise ValueError("resposta da Open-Meteo sem temperatura")

        return Clima(
            temperatura=round(float(temp), 1),
            sensacao=round(float(sensacao), 1) if sensacao is not None else None,
            horario=horario,
            cidade=self.cidade,
            origem="open-meteo",
        )

    @staticmethod
    def _da_hora_atual(dados: dict):
        """Escolhe, dentro do bloco `hourly`, a linha da hora mais próxima de agora."""
        horaria = dados.get("hourly") or {}
        tempos = horaria.get("time") or []
        temps = horaria.get("temperature_2m") or []
        sens = horaria.get("apparent_temperature") or []
        if not tempos or not temps:
            return None, None, "-"
        agora = datetime.now().strftime("%Y-%m-%dT%H:00")
        try:
            i = tempos.index(agora)
        except ValueError:
            i = len(temps) - 1  # cai no último ponto disponível
        s = sens[i] if i < len(sens) else None
        return temps[i], s, tempos[i]

    def obter(self, forcar: bool = False) -> Clima:
        """Devolve a temperatura externa, usando cache quando ainda estiver fresco."""
        agora = time.monotonic()
        cache_valido = self._cache and (agora - self._buscado_em) < TEMPO_CACHE_S
        if cache_valido and not forcar:
            return Clima(**{**self._cache.__dict__, "origem": "cache"})

        try:
            clima = self._consultar_api()
            self._cache = clima
            self._buscado_em = agora
            return clima
        except Exception as e:  # rede caiu, timeout, JSON estranho...
            print(f"[clima] falha ao consultar Open-Meteo: {e}")
            if self._cache:  # devolve a última leitura boa, marcada como fallback
                return Clima(**{**self._cache.__dict__, "origem": "fallback"})
            return Clima(
                temperatura=TEMP_FALLBACK, sensacao=None, horario="-",
                cidade=self.cidade, origem="fallback",
            )


# instância pronta para uso (Itajubá)
provedor = ProvedorClima()


if __name__ == "__main__":  # teste rápido: python clima.py
    c = provedor.obter(forcar=True)
    print(f"{c.cidade}: {c.temperatura} °C (sensação {c.sensacao} °C) "
          f"[{c.origem}] às {c.horario}")
