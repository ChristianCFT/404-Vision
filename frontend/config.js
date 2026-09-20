// Configuração do frontend do 404 Vision.
// Edite aqui, sem precisar mexer no app.js.
window.VISION_CONFIG = {
  // 'demo' usa fotos da base de dados (funciona sem backend).
  // 'api' busca os dados no backend Python. Também dá para trocar pelo botão
  // do topo ou pela URL: index.html?mode=api
  mode: 'demo',

  // Endereço do backend. Se o FastAPI/Flask servir este frontend, use ''.
  apiBase: 'http://localhost:8000',
  statusPath: '/api/status',   // JSON com os dados (veja o README)
  framePath: '/api/frame',     // usado só se o JSON não trouxer "frame_url"
  pollMs: 2000,                // de quanto em quanto tempo consulta o backend

  // Valores padrão quando o backend não envia.
  room: 'Sala B-03',
  camera: 'Câmera 1',
  capacity: 70,

  // Faixa do termômetro visual (°C).
  thermalMin: 22,
  thermalMax: 34,

  // Regras da classificação (só usadas se o backend não enviar "demand").
  // Com a estimativa em °C: abaixo de medium = baixa, a partir de high = alta.
  thresholds: { medium: 26, high: 27 },

  // Quantos pontos o gráfico de histórico guarda.
  historySize: 40,

  // Ares da sala no modo demonstração.
  demoAcs: ['A1', 'A2', 'A3', 'A4'],

  // Cenas do modo demonstração (fotos reais + contagem anotada na base).
  demoFrames: [
    { file: 'assets/demo/sala_00p.jpg', count: 0 },
    { file: 'assets/demo/sala_05p.jpg', count: 5 },
    { file: 'assets/demo/sala_16p.jpg', count: 16 },
    { file: 'assets/demo/sala_24p.jpg', count: 24 },
    { file: 'assets/demo/sala_32p.jpg', count: 32 },
    { file: 'assets/demo/sala_40p.jpg', count: 40 },
    { file: 'assets/demo/sala_48p.jpg', count: 48 },
    { file: 'assets/demo/sala_56p.jpg', count: 56 },
    { file: 'assets/demo/sala_62p.jpg', count: 62 }
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
