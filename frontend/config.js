// Configuração do frontend do 404 Vision.
// Edite aqui, sem precisar mexer no app.js.
window.VISION_CONFIG = {
  // 'api' busca os dados no backend Python (padrão, já integrado).
  // 'demo' usa fotos da base sem backend. Dá para trocar pelo botão do topo
  // ou pela URL: index.html?mode=demo
  mode: 'api',

  // Vazio = mesma origem: o próprio backend Flask serve este painel.
  // (Se abrir o frontend separado do backend, use 'http://localhost:8000'.)
  apiBase: '',
  statusPath: '/api/status',   // JSON com os dados (veja o README)
  framePath: '/api/frame',     // usado só se o JSON não trouxer "frame_url"
  pollMs: 2000,                // de quanto em quanto tempo consulta o backend

  // Valores padrão quando o backend não envia.
  room: 'Sala B-03',
  camera: 'Câmera 1',
  capacity: 80,

  // Faixa do termômetro visual (°C). Mínimo baixo cobre as manhãs de Itajubá.
  thermalMin: 14,
  thermalMax: 34,

  // Regras da classificação (só usadas se o backend não enviar "demand";
  // no modo api quem manda o nível é o backend, a partir da fórmula).
  thresholds: { medium: 24, high: 27 },

  // Quantos pontos o gráfico de histórico guarda.
  historySize: 40,

  // Ares da sala no modo demonstração.
  demoAcs: ['A1', 'A2', 'A3', 'A4'],

  // Cenas do modo demonstração: fotos REAIS de data/images com a contagem
  // anotada em data/labels.csv (uma rampa do vazio ao lotado).
  // O backend serve essa pasta em /data/images — por isso os caminhos absolutos.
  // Para regerar esta lista com outras fotos:  python tools/cenas_demo.py
  demoFrames: [
    { file: '/data/images/img105.jpg', count: 0 },
    { file: '/data/images/img63.jpg', count: 14 },
    { file: '/data/images/img54.jpg', count: 23 },
    { file: '/data/images/img127.jpg', count: 29 },
    { file: '/data/images/img28.jpg', count: 31 },
    { file: '/data/images/img47.jpg', count: 42 },
    { file: '/data/images/img59.jpg', count: 50 },
    { file: '/data/images/img45.jpg', count: 52 },
    { file: '/data/images/img02.jpg', count: 57 }
  ],
  demoCycleMs: 5000,

  // Modo WebCam: a detecção roda no próprio navegador (TensorFlow.js + COCO-SSD).
  // Precisa de internet na primeira vez para baixar o modelo (~10 MB).
  webcam: {
    tfUrl: 'https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4.22.0/dist/tf.min.js',
    modelUrl: 'https://cdn.jsdelivr.net/npm/@tensorflow-models/coco-ssd@2.2.3/dist/coco-ssd.min.js',
    modelBase: 'lite_mobilenet_v2', // 'lite_mobilenet_v2' (rápido) | 'mobilenet_v2' (mais preciso, mais pesado)
    minScore: 0.55,   // confiança mínima inicial (o modelo não aceita menos que 0.5)
    smoothing: 7,     // nº de leituras usadas na mediana, evita a contagem "piscar"
    capacity: 10,     // lugares da "sala" no teste (notebook costuma ver poucas pessoas)
    outdoor: 25,      // temperatura externa inicial (°C)
    k: 0.4,           // fator K inicial, maior que o da demo para reagir a poucas pessoas
    mirror: true      // imagem espelhada, como uma câmera frontal
  }
};
