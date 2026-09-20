# 404-Vision

Sistema inteligente para gerenciamento de ambientes de sala de aula, utilizando visão computacional para identificar a quantidade de pessoas no ambiente e auxiliar na estimativa da temperatura e no controle do ar-condicionado.

## 📌 Sobre o projeto

O 404-Vision foi desenvolvido com o objetivo de criar um sistema capaz de analisar imagens de salas de aula e identificar a quantidade de pessoas presentes no ambiente.

A partir da quantidade de pessoas detectadas e de informações climáticas externas obtidas por uma API, o sistema poderá estimar a temperatura interna da sala e determinar se o ar-condicionado deve ser ligado ou desligado.

## Dependências

ultralytics
opencv-python
numpy
pandas
requests

O fluxo principal do sistema é:

```text
Imagem da sala
      ↓
Detecção de pessoas (YOLO)
      ↓
Quantidade de pessoas
      ↓
Temperatura externa (Open-Meteo)
      ↓
Estimativa da temperatura interna
      ↓
Decisão sobre o ar-condicionado
      ↓
Resultado apresentado no Frontend