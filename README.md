# 404-Vision

Sistema inteligente para gerenciamento de ambientes de sala de aula, utilizando visão computacional para identificar a quantidade de pessoas no ambiente e auxiliar na estimativa da temperatura e no controle do ar-condicionado.

## 📌 Sobre o projeto

O 404-Vision foi desenvolvido com o objetivo de criar um sistema capaz de analisar imagens de salas de aula e identificar a quantidade de pessoas presentes no ambiente.

A partir da quantidade de pessoas detectadas e de informações climáticas externas obtidas por uma API, o sistema poderá estimar a temperatura interna da sala e determinar se o ar-condicionado deve ser ligado, desligado, aumentado ou diminuido.

## 📦 Dependências

- ultralytics
- opencv-python
- numpy
- pandas
- requests

## ⚙️ Funcionamento

O sistema recebe uma imagem da sala de aula. A detecção é realizada utilizando o modelo de inteligência artificial YOLO, que identifica e contabiliza a quantidade de pessoas presentes na imagem.

Essa quantidade será utilizada como uma das informações para a estimativa da temperatura interna, juntamente com a temperatura externa obtida através da API Open-Meteo.

A partir dessas informações, será realizado um cálculo para obter uma estimativa da temperatura da sala, que poderá ser utilizada para determinar o funcionamento do ar-condicionado.

## Instruções básicas de execução

