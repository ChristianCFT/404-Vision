/* 404 Vision — frontend
   Três modos de dados:
   - demo:   fotos reais da base + cálculo local (não precisa de backend)
   - api:    consulta o backend Python (formato em frontend/README.md)
   - webcam: usa a câmera do notebook e conta pessoas no próprio navegador */
(() => {
  'use strict';

  const CFG = window.VISION_CONFIG;
  const $ = (id) => document.getElementById(id);
  const el = {
    frame: $('frame'), img: $('camImg'), canvas: $('boxes'), empty: $('camEmpty'),
    camName: $('camName'), camTime: $('camTime'), camCount: $('camCount'), camCountLabel: $('camCountLabel'),
    tempEst: $('tempEst'), markOut: $('markOut'), markEst: $('markEst'),
    markOutLabel: $('markOutLabel'), markEstLabel: $('markEstLabel'),
    scaleMin: $('scaleMin'), scaleMax: $('scaleMax'), formula: $('formula'),
    verdict: $('verdict'), demandText: $('demandText'), recText: $('recText'),
    ringFg: $('ringFg'), occPct: $('occPct'), occPeople: $('occPeople'), occCap: $('occCap'), occHint: $('occHint'),
    acList: $('acList'), acsCount: $('acsCount'),
    chartArea: $('chartArea'), chartLine: $('chartLine'),
    status: $('status'), statusText: $('statusText'), banner: $('banner'),
    demoBar: $('demoBar'), demoScene: $('demoScene'), demoSceneLabel: $('demoSceneLabel'),
    demoOutdoor: $('demoOutdoor'), demoK: $('demoK'), demoPlay: $('demoPlay'),
    video: $('camVideo'), camAction: $('camAction'), wcLoading: $('wcLoading'), wcLoadingText: $('wcLoadingText'),
    webcamBar: $('webcamBar'), wcDevice: $('wcDevice'), wcDeviceField: $('wcDeviceField'),
    wcOutdoor: $('wcOutdoor'), wcK: $('wcK'), wcCap: $('wcCap'),
    wcScore: $('wcScore'), wcScoreLabel: $('wcScoreLabel'), wcMirror: $('wcMirror'), wcToggle: $('wcToggle')
  };

  const LEVELS = {
    low:    { text: 'Baixa',  rec: 'Reduzir climatização' },
    medium: { text: 'Média',  rec: 'Manter climatização' },
    high:   { text: 'Alta',   rec: 'Aumentar climatização' }
  };

  const state = {
    mode: 'demo',
    history: [],
    timer: null,
    demoIdx: 0,
    demoDir: 1,
    demoAuto: true,
    lastCount: null,
    shownTemp: null,
    dets: []
  };

  /* ---------- utilidades ---------- */
  const nf = (n, d = 1) => Number(n).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const pad = (n) => String(n).padStart(2, '0');
  const clock = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;

  function classify(temp) {
    if (temp >= CFG.thresholds.high) return 'high';
    if (temp >= CFG.thresholds.medium) return 'medium';
    return 'low';
  }

  /* ---------- normaliza o JSON do backend ---------- */
  function normalize(raw) {
    const people = Number(raw.people ?? raw.count ?? 0);
    const outdoor = Number(raw.outdoor_temp ?? raw.outdoor ?? 25);
    const k = Number(raw.k ?? 0.1);
    const est = Number(raw.estimated_temp ?? (outdoor + people * k));
    const demand = LEVELS[raw.demand] ? raw.demand : classify(est);
    return {
      ts: raw.timestamp ? new Date(raw.timestamp) : new Date(),
      room: raw.room ?? CFG.room,
      camera: raw.camera ?? CFG.camera,
      capacity: Number(raw.capacity ?? CFG.capacity) || CFG.capacity,
      people, outdoor, k, est, demand,
      rec: raw.recommendation ?? LEVELS[demand].rec,
      acs: (raw.acs ?? []).map((a) => ({
        id: a.id ?? a.name ?? '?',
        on: Boolean(a.on ?? a.ligado),
        temp: a.setpoint ?? a.temp ?? a.temperature ?? null,
        mode: a.mode ?? null
      })),
      frameUrl: raw.frame_url ?? null,
      detections: Array.isArray(raw.detections) ? raw.detections : []
    };
  }

  /* cor da temperatura = cor do degradê da barra na posição da estimativa */
  const STOPS = [[0, [47, 107, 255]], [0.25, [63, 200, 168]], [0.5, [255, 210, 63]], [1, [229, 50, 45]]];
  function thermalColor(r) {
    r = clamp(r, 0, 1);
    for (let i = 1; i < STOPS.length; i++) {
      if (r <= STOPS[i][0]) {
        const [a, ca] = STOPS[i - 1], [b, cb] = STOPS[i];
        const t = (r - a) / (b - a);
        return `rgb(${ca.map((v, j) => Math.round(v + (cb[j] - v) * t)).join(',')})`;
      }
    }
    return `rgb(${STOPS[STOPS.length - 1][1].join(',')})`;
  }

  /* ---------- renderização ---------- */
  function render(d) {
    document.body.classList.remove('stale');

    // câmera
    el.camName.textContent = `${d.camera} · ${d.room}`;
    el.camTime.textContent = clock(d.ts);
    el.camCount.textContent = d.people;
    el.camCountLabel.textContent = d.people === 1 ? 'pessoa detectada' : 'pessoas detectadas';
    if (state.lastCount !== null && state.lastCount !== d.people) scanOnce();
    state.lastCount = d.people;
    state.dets = d.detections;
    drawBoxes(state.dets);

    // temperatura
    tweenTemp(d.est);
    const span = CFG.thermalMax - CFG.thermalMin;
    el.tempEst.parentElement.style.setProperty('--temp-color', thermalColor((d.est - CFG.thermalMin) / span));
    const pos = (t) => `${clamp((t - CFG.thermalMin) / span, 0, 1) * 100}%`;
    el.markOut.style.left = pos(d.outdoor);
    el.markEst.style.left = pos(d.est);
    el.markOutLabel.textContent = `externa ${nf(d.outdoor)} °C`;
    el.markEstLabel.textContent = `estimada ${nf(d.est)} °C`;
    el.scaleMin.textContent = CFG.thermalMin;
    el.scaleMax.textContent = CFG.thermalMax;
    el.formula.innerHTML =
      `<span>${nf(d.outdoor)}</span> + <span>${d.people}</span> × <span>${nf(d.k, 2)}</span> = <span>${nf(d.est)}</span>` +
      `<em>externa + pessoas × K</em>`;

    // decisão
    el.verdict.dataset.level = d.demand;
    el.demandText.textContent = LEVELS[d.demand].text;
    el.recText.textContent = d.rec;

    // ocupação
    const pct = clamp(d.people / d.capacity, 0, 1) * 100;
    el.ringFg.style.strokeDashoffset = 100 - pct;
    el.occPct.innerHTML = `${Math.round(pct)}<small>%</small>`;
    el.occPeople.textContent = d.people;
    el.occCap.textContent = d.capacity;
    el.occHint.textContent =
      d.people === 0 ? 'Sala vazia' :
      pct < 35 ? 'Poucas pessoas na sala' :
      pct < 70 ? 'Sala com ocupação média' : 'Sala quase cheia';

    // ares
    renderAcs(d.acs);

    // histórico
    state.history.push({ people: d.people, cap: d.capacity, est: d.est });
    if (state.history.length > CFG.historySize) state.history.shift();
    drawChart();
  }

  function renderAcs(acs) {
    const on = acs.filter((a) => a.on).length;
    el.acsCount.textContent = on === 1 ? '1 ligado' : `${on} ligados`;
    el.acList.innerHTML = acs.map((a) => {
      const t = a.on && a.temp != null ? `${Math.round(a.temp)}<small>°C</small>` : '--<small>°C</small>';
      const mode = a.on ? (a.mode || 'Refrigerando') : 'Desligado';
      return `<li class="ac ${a.on ? 'on' : ''}">
        <div class="ac-top">
          <span class="ac-name">${escapeHtml(a.id)}</span>
          <span class="ac-state"><i></i>${a.on ? 'Ligado' : 'Desligado'}</span>
        </div>
        <p class="ac-temp" aria-label="${a.on && a.temp != null ? `${Math.round(a.temp)} graus` : 'sem temperatura'}">${t}</p>
        <p class="ac-mode">${escapeHtml(mode)}</p>
      </li>`;
    }).join('');
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  /* número grande da temperatura anima suavemente até o novo valor */
  function tweenTemp(target) {
    const from = state.shownTemp ?? target;
    state.shownTemp = target;
    if (matchMedia('(prefers-reduced-motion: reduce)').matches || from === target) {
      el.tempEst.textContent = nf(target);
      return;
    }
    const t0 = performance.now(), dur = 700;
    const step = (now) => {
      const p = clamp((now - t0) / dur, 0, 1);
      const e = 1 - Math.pow(1 - p, 3);
      el.tempEst.textContent = nf(from + (target - from) * e);
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  function scanOnce() {
    el.frame.style.setProperty('--frame-w', `${el.frame.clientWidth}px`);
    el.frame.classList.remove('scanning');
    void el.frame.offsetWidth; // reinicia a animação
    el.frame.classList.add('scanning');
  }

  /* ---------- gráfico de histórico ---------- */
  function drawChart() {
    const W = 320, H = 90, pad = 6;
    const h = state.history;
    const n = h.length;
    if (n === 0) return;
    const x = (i) => (n === 1 ? W : (i / (n - 1)) * W);
    const yPeople = (p) => H - pad - clamp(p.people / p.cap, 0, 1) * (H - pad * 2);
    const yTemp = (p) => H - pad - clamp((p.est - CFG.thermalMin) / (CFG.thermalMax - CFG.thermalMin), 0, 1) * (H - pad * 2);

    const pts = n === 1 ? [h[0], h[0]] : h;
    const xi = (i) => (n === 1 ? i * W : x(i));
    let area = `M0 ${H}`;
    let line = '';
    pts.forEach((p, i) => {
      area += ` L${xi(i).toFixed(1)} ${yPeople(p).toFixed(1)}`;
      line += `${i === 0 ? 'M' : 'L'}${xi(i).toFixed(1)} ${yTemp(p).toFixed(1)} `;
    });
    area += ` L${W} ${H} Z`;
    el.chartArea.setAttribute('d', area);
    el.chartLine.setAttribute('d', line.trim());
  }

  /* ---------- caixas de detecção (backend ou webcam) ---------- */
  function rrect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.roundRect ? ctx.roundRect(x, y, w, h, r) : ctx.rect(x, y, w, h);
  }

  function drawBoxes(dets) {
    const c = el.canvas;
    const w = c.clientWidth, h = c.clientHeight;
    const dpr = window.devicePixelRatio || 1;
    if (c.width !== w * dpr || c.height !== h * dpr) { c.width = w * dpr; c.height = h * dpr; }
    const ctx = c.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.lineWidth = 2;
    dets.forEach((b) => {
      const x = b.x * w, y = b.y * h, bw = b.w * w, bh = b.h * h;
      ctx.strokeStyle = '#ffb14a';
      ctx.fillStyle = 'rgba(255, 138, 61, .14)';
      rrect(ctx, x, y, bw, bh, 4);
      ctx.fill();
      ctx.stroke();

      if (b.label) { // etiqueta opcional (usada no modo webcam)
        ctx.font = '600 12px "Instrument Sans", system-ui, sans-serif';
        ctx.textBaseline = 'middle';
        const tw = ctx.measureText(b.label).width + 12;
        const lx = clamp(x, 0, Math.max(0, w - tw));
        const ly = y >= 22 ? y - 20 : y + 3; // sem espaço acima? escreve dentro da caixa
        ctx.fillStyle = 'rgba(21, 19, 46, .8)';
        rrect(ctx, lx, ly, tw, 18, 9);
        ctx.fill();
        ctx.fillStyle = '#fff';
        ctx.fillText(b.label, lx + 6, ly + 9.5);
      }
    });
  }

  /* ---------- imagem da câmera ---------- */
  let frameToken = 0; // ignora respostas de imagens antigas (ex.: depois de trocar de modo)
  function setFrame(url) {
    if (!url) return;
    const token = ++frameToken;
    const pre = new Image();
    pre.onload = () => {
      if (token !== frameToken) return;
      el.img.src = url;
      el.empty.hidden = true;
    };
    pre.onerror = () => {
      if (token !== frameToken) return;
      console.error('[imagem] não carregou:', url);
      if (!el.img.getAttribute('src')) { // só avisa se ainda não há nenhuma imagem na tela
        el.empty.hidden = false;
        el.empty.firstElementChild.textContent = state.mode === 'demo'
          ? `Não encontrei a imagem de demonstração (${url.split('/').pop().split('?')[0]}). Ela vem da base em data/images, servida pelo backend — confira se o "python main.py" está rodando.`
          : 'Não foi possível carregar a imagem da câmera. Confira a rota de imagem do backend.';
      }
    };
    pre.src = url;
  }

  /* ---------- status no topo ---------- */
  function setStatus(kind, text) {
    el.status.dataset.state = kind;
    el.statusText.textContent = text;
  }

  /* =========================================================
     Modo demonstração
     ========================================================= */
  const frames = [...CFG.demoFrames].sort((a, b) => a.count - b.count);

  function demoAcs(people, demand) {
    const ids = CFG.demoAcs;
    const plan = people === 0 ? { n: 0, t: 24 } : demand === 'high' ? { n: ids.length, t: 22 } : demand === 'medium' ? { n: 2, t: 23 } : { n: 1, t: 24 };
    return ids.map((id, i) => ({ id, on: i < plan.n, setpoint: plan.t }));
  }

  function demoRender() {
    const f = frames[state.demoIdx];
    const outdoor = clamp(parseFloat(el.demoOutdoor.value) || 25, 0, 50);
    const k = clamp(parseFloat(el.demoK.value) || 0, 0, 1);
    const est = outdoor + f.count * k;
    const demand = classify(est);
    const data = normalize({
      people: f.count, outdoor_temp: outdoor, k, estimated_temp: est, demand,
      acs: demoAcs(f.count, demand)
    });
    if (f.count === 0) data.rec = 'Desligar aparelhos ociosos';
    setFrame(f.file);
    render(data);
    el.demoScene.value = state.demoIdx;
    el.demoSceneLabel.textContent = `${f.count} ${f.count === 1 ? 'pessoa' : 'pessoas'}`;
  }

  function demoTick() {
    let next = state.demoIdx + state.demoDir;
    if (next >= frames.length || next < 0) { state.demoDir *= -1; next = state.demoIdx + state.demoDir; }
    state.demoIdx = next;
    demoRender();
  }

  function startDemo() {
    el.demoBar.hidden = false;
    el.demoScene.max = frames.length - 1;
    setStatus('demo', 'Modo demonstração');
    el.banner.hidden = true;
    demoRender();
    if (state.demoAuto) state.timer = setInterval(demoTick, CFG.demoCycleMs);
  }

  el.demoScene.addEventListener('input', () => {
    state.demoIdx = Number(el.demoScene.value);
    pauseDemo();
    demoRender();
  });
  [el.demoOutdoor, el.demoK].forEach((i) => i.addEventListener('input', () => { if (state.mode === 'demo') demoRender(); }));
  el.demoPlay.addEventListener('click', () => (state.demoAuto ? pauseDemo() : resumeDemo()));

  function pauseDemo() {
    state.demoAuto = false;
    clearInterval(state.timer);
    el.demoPlay.textContent = 'Retomar ciclo';
    el.demoPlay.setAttribute('aria-pressed', 'false');
  }
  function resumeDemo() {
    state.demoAuto = true;
    clearInterval(state.timer);
    state.timer = setInterval(demoTick, CFG.demoCycleMs);
    el.demoPlay.textContent = 'Pausar ciclo';
    el.demoPlay.setAttribute('aria-pressed', 'true');
  }

  /* =========================================================
     Modo backend
     ========================================================= */
  // monta o endereço da imagem: relativo ao backend e com "carimbo" para o navegador não usar cache
  function frameUrlFrom(u) {
    let url = u || CFG.framePath;
    if (!/^(data:|blob:|https?:)/i.test(url)) url = CFG.apiBase + (url.startsWith('/') ? '' : '/') + url;
    if (/^(data:|blob:)/i.test(url)) return url;
    return url + (url.includes('?') ? '&' : '?') + 't=' + Date.now();
  }

  let polling = false; // evita pedidos empilhados se o backend demorar mais que o intervalo
  async function poll() {
    if (polling) return;
    polling = true;
    const url = CFG.apiBase + CFG.statusPath;
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = normalize(await res.json());
      if (state.mode !== 'api') return; // o usuário já trocou de modo
      setFrame(frameUrlFrom(d.frameUrl));
      render(d);
      el.banner.hidden = true;
      setStatus('live', `Ao vivo · ${clock(d.ts)}`);
    } catch (err) {
      if (state.mode !== 'api') return;
      document.body.classList.add('stale');
      setStatus('error', 'Sem conexão com o backend');
      el.banner.hidden = false;
      el.banner.innerHTML = `Não foi possível ler <code>${escapeHtml(url)}</code> (${escapeHtml(err.message)}). ` +
        `Confira se o backend está rodando e se o CORS está liberado. A tela tenta de novo automaticamente.`;
    } finally {
      polling = false;
    }
  }

  function startApi() {
    el.demoBar.hidden = true;
    setStatus('error', 'Conectando…');
    poll();
    state.timer = setInterval(poll, CFG.pollMs);
  }

  /* =========================================================
     Modo WebCam
     Câmera do notebook (getUserMedia) + detecção de pessoas no navegador
     com TensorFlow.js / COCO-SSD. Nada é enviado para fora do computador,
     só o modelo é baixado da internet (uma vez, depois fica em cache).
     ========================================================= */
  const WC = Object.assign({
    tfUrl: 'https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4.22.0/dist/tf.min.js',
    modelUrl: 'https://cdn.jsdelivr.net/npm/@tensorflow-models/coco-ssd@2.2.3/dist/coco-ssd.min.js',
    modelBase: 'lite_mobilenet_v2', minScore: 0.55, smoothing: 7,
    capacity: 10, outdoor: 25, k: 0.4, mirror: true
  }, CFG.webcam || {});

  const wc = {
    session: 0,        // muda a cada (re)início/parada: cancela loops e awaits antigos
    stream: null,
    model: null,
    modelPromise: null,
    dets: [],          // caixas já convertidas para a moldura (0..1)
    counts: [],        // últimas contagens, para a mediana
    fps: 0,
    renderTimer: null,
    mirror: WC.mirror
  };

  // valores iniciais dos campos
  el.wcOutdoor.value = WC.outdoor;
  el.wcK.value = WC.k;
  el.wcCap.value = WC.capacity;
  el.wcScore.value = Math.round(clamp(WC.minScore, 0.5, 0.9) * 100);
  el.wcScoreLabel.textContent = `${el.wcScore.value}%`;
  el.wcMirror.setAttribute('aria-pressed', String(wc.mirror));

  const scriptCache = {};
  function loadScript(src) {
    return (scriptCache[src] ??= new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = src;
      s.async = true;
      s.onload = resolve;
      s.onerror = () => { delete scriptCache[src]; reject(new Error(`falha ao baixar ${src}`)); };
      document.head.appendChild(s);
    }));
  }

  function loadModel() {
    if (wc.modelPromise) return wc.modelPromise;
    wc.modelPromise = (async () => {
      if (!window.tf) await loadScript(WC.tfUrl);
      if (!window.cocoSsd) await loadScript(WC.modelUrl);
      await window.tf.ready();
      return window.cocoSsd.load({ base: WC.modelBase });
    })().catch((e) => { wc.modelPromise = null; throw e; });
    return wc.modelPromise;
  }

  function showLoading(text) { el.wcLoadingText.textContent = text; el.wcLoading.hidden = false; }
  function hideLoading() { el.wcLoading.hidden = true; }

  function showCamMessage(text, buttonLabel) {
    el.empty.hidden = false;
    el.empty.firstElementChild.textContent = text;
    el.camAction.hidden = !buttonLabel;
    if (buttonLabel) el.camAction.textContent = buttonLabel;
  }
  function hideCamMessage() { el.empty.hidden = true; el.camAction.hidden = true; }

  function syncToggle() { el.wcToggle.textContent = wc.stream ? 'Parar câmera' : 'Ligar câmera'; }

  function camErrorMessage(err) {
    switch (err && err.name) {
      case 'NotAllowedError':
      case 'SecurityError':
        return 'Permissão da câmera negada. Clique no cadeado ao lado do endereço, permita a câmera e tente de novo.';
      case 'NotFoundError':
      case 'DevicesNotFoundError':
        return 'Nenhuma webcam foi encontrada neste computador.';
      case 'NotReadableError':
      case 'TrackStartError':
        return 'A câmera está em uso por outro programa (Zoom, Meet, Teams…). Feche-o e tente de novo.';
      case 'OverconstrainedError':
        return 'A câmera escolhida não está mais disponível. Selecione outra.';
      case 'InsecureContext':
        return 'O navegador só libera a câmera em http://localhost ou https. Abra o painel por um servidor local (ex.: python -m http.server 5500) e acesse http://localhost:5500.';
      case 'TrackEnded':
        return 'A câmera foi desconectada.';
      default:
        return `Não foi possível abrir a câmera (${(err && err.message) || 'erro desconhecido'}).`;
    }
  }

  function stopWebcam() {
    wc.session++;                       // invalida loops/awaits em andamento
    clearInterval(wc.renderTimer);
    if (wc.stream) wc.stream.getTracks().forEach((t) => t.stop());
    wc.stream = null;
    el.video.srcObject = null;
    wc.dets = [];
    wc.counts = [];
    wc.fps = 0;
    hideLoading();
  }

  function camFail(err) {
    console.error('[webcam]', err);
    stopWebcam();
    state.dets = [];
    drawBoxes([]);
    syncToggle();
    el.banner.hidden = true;
    setStatus('error', 'Câmera indisponível');
    showCamMessage(camErrorMessage(err), 'Tentar de novo');
  }

  async function listCameras(activeId) {
    try {
      const devs = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === 'videoinput');
      el.wcDevice.innerHTML = devs.map((d, i) =>
        `<option value="${escapeHtml(d.deviceId)}">${escapeHtml(d.label || `Câmera ${i + 1}`)}</option>`).join('');
      if (activeId) el.wcDevice.value = activeId;
      el.wcDeviceField.hidden = devs.length < 2;
    } catch (_) { el.wcDeviceField.hidden = true; }
  }

  async function startWebcam(deviceId) {
    stopWebcam();
    const session = wc.session;
    el.banner.hidden = true;
    hideCamMessage();
    syncToggle();
    setStatus('demo', 'Abrindo a câmera…');
    showLoading('Abrindo a câmera…');

    // 1) câmera
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw Object.assign(new Error('getUserMedia indisponível'), { name: 'InsecureContext' });
      }
      const size = { width: { ideal: 1280 }, height: { ideal: 720 } };
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: deviceId ? { deviceId: { exact: deviceId }, ...size } : { facingMode: 'user', ...size }
      });
      if (session !== wc.session) { stream.getTracks().forEach((t) => t.stop()); return; }
      wc.stream = stream;
      const track = stream.getVideoTracks()[0];
      track.addEventListener('ended', () => { if (session === wc.session) camFail({ name: 'TrackEnded' }); });
      el.video.srcObject = stream;
      await el.video.play();
      if (session !== wc.session) return;
      await listCameras(track.getSettings().deviceId);
      if (session !== wc.session) return;
      syncToggle();
    } catch (err) {
      if (session === wc.session) camFail(err);
      return;
    }

    // painel já mostra a leitura inicial (0 pessoas) enquanto o modelo carrega
    wcRender();
    showLoading('Carregando modelo de IA… (na primeira vez pode demorar)');
    setStatus('demo', 'Carregando modelo de IA…');

    // 2) modelo de detecção
    try {
      wc.model = await loadModel();
    } catch (err) {
      if (session !== wc.session) return;
      console.error('[webcam] modelo', err);
      hideLoading();
      setStatus('error', 'Modelo de IA indisponível');
      el.banner.hidden = false;
      el.banner.textContent = 'Não foi possível baixar o modelo de detecção. Ele precisa de internet na primeira vez ' +
        '(cdn.jsdelivr.net e o repositório de modelos do TensorFlow). A câmera segue ligada, mas sem contagem. ' +
        'Verifique a conexão e clique em "Parar câmera" e depois "Ligar câmera" para tentar de novo.';
      return;
    }
    if (session !== wc.session) return;
    hideLoading();
    wc.renderTimer = setInterval(wcRender, 1000);
    detectLoop(session);
  }

  // converte a caixa do vídeo (pixels) para a moldura (0..1), considerando o recorte "cover" e o espelhamento
  function toFrameBox([x, y, w, h], label) {
    const cw = el.frame.clientWidth, ch = el.frame.clientHeight;
    const vw = el.video.videoWidth, vh = el.video.videoHeight;
    const sc = Math.max(cw / vw, ch / vh);
    const ox = (cw - vw * sc) / 2, oy = (ch - vh * sc) / 2;
    const bx = (x * sc + ox) / cw, by = (y * sc + oy) / ch;
    const bw = (w * sc) / cw, bh = (h * sc) / ch;
    return { x: wc.mirror ? 1 - bx - bw : bx, y: by, w: bw, h: bh, label };
  }

  const nextFrame = () => new Promise((r) => requestAnimationFrame(r));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function detectLoop(session) {
    let last = performance.now();
    while (session === wc.session) {
      const v = el.video;
      if (v.readyState >= 2 && v.videoWidth) {
        let preds;
        try {
          preds = await wc.model.detect(v, 50);
        } catch (err) {
          console.warn('[webcam] detect', err);
          await sleep(500);
          continue;
        }
        if (session !== wc.session) return;

        const min = Number(el.wcScore.value) / 100;
        const people = preds.filter((p) => p.class === 'person' && p.score >= min);
        wc.dets = people.map((p, i) => toFrameBox(p.bbox, `#${i + 1} · ${Math.round(p.score * 100)}%`));
        state.dets = wc.dets;
        drawBoxes(wc.dets);

        wc.counts.push(people.length);
        if (wc.counts.length > WC.smoothing) wc.counts.shift();

        const now = performance.now();
        const inst = 1000 / Math.max(1, now - last);
        wc.fps = wc.fps ? wc.fps * 0.8 + inst * 0.2 : inst;
        last = now;
      }
      await nextFrame();
    }
  }

  // atualiza o painel (1x por segundo) com a mediana das últimas leituras
  function wcRender() {
    if (state.mode !== 'webcam' || !wc.stream) return;
    const outdoor = clamp(parseFloat(el.wcOutdoor.value) || 0, 0, 50);
    const k = clamp(parseFloat(el.wcK.value) || 0, 0, 1);
    const capacity = Math.max(1, Math.round(parseFloat(el.wcCap.value)) || WC.capacity);
    const sorted = [...wc.counts].sort((a, b) => a - b);
    const people = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
    const est = outdoor + people * k;
    const demand = classify(est);
    const data = normalize({
      people, outdoor_temp: outdoor, k, estimated_temp: est, demand, capacity,
      camera: 'WebCam', room: 'Teste no notebook',
      acs: demoAcs(people, demand),
      detections: wc.dets
    });
    if (people === 0) data.rec = 'Desligar aparelhos ociosos';
    render(data);
    if (wc.model) setStatus('live', `WebCam ao vivo · ${Math.round(wc.fps)} fps`);
  }

  function startWebcamMode() {
    el.demoBar.hidden = true;
    el.webcamBar.hidden = false;
    el.frame.classList.toggle('mirror', wc.mirror);
    startWebcam();
  }

  el.camAction.addEventListener('click', () => startWebcam(el.wcDeviceField.hidden ? undefined : el.wcDevice.value));
  el.wcToggle.addEventListener('click', () => {
    if (wc.stream) {
      stopWebcam();
      state.dets = [];
      drawBoxes([]);
      syncToggle();
      setStatus('demo', 'Câmera parada');
      showCamMessage('Câmera desligada.', 'Ligar câmera');
    } else {
      startWebcam(el.wcDeviceField.hidden ? undefined : el.wcDevice.value);
    }
  });
  el.wcDevice.addEventListener('change', () => startWebcam(el.wcDevice.value));
  el.wcMirror.addEventListener('click', () => {
    wc.mirror = !wc.mirror;
    el.wcMirror.setAttribute('aria-pressed', String(wc.mirror));
    el.frame.classList.toggle('mirror', wc.mirror);
    wc.dets = []; state.dets = []; drawBoxes([]); // as caixas voltam na próxima leitura
  });
  el.wcScore.addEventListener('input', () => { el.wcScoreLabel.textContent = `${el.wcScore.value}%`; });
  [el.wcOutdoor, el.wcK, el.wcCap].forEach((i) => i.addEventListener('input', wcRender));

  /* =========================================================
     Troca de modo
     ========================================================= */
  function setMode(mode) {
    clearInterval(state.timer);
    stopWebcam();
    state.mode = mode;
    state.history = [];
    state.lastCount = null;
    state.shownTemp = null;
    state.dets = [];
    drawBoxes([]);
    frameToken++;
    el.img.removeAttribute('src');
    el.img.hidden = mode === 'webcam';
    el.video.hidden = mode !== 'webcam';
    el.frame.classList.toggle('is-webcam', mode === 'webcam');
    el.demoBar.hidden = mode !== 'demo';
    el.webcamBar.hidden = mode !== 'webcam';
    hideLoading();
    el.camAction.hidden = true;
    el.empty.hidden = false;
    el.empty.firstElementChild.textContent = 'Aguardando a primeira imagem da câmera.';
    document.querySelectorAll('.segmented button').forEach((b) =>
      b.setAttribute('aria-pressed', String(b.dataset.mode === mode)));
    if (mode === 'demo') startDemo();
    else if (mode === 'api') startApi();
    else startWebcamMode();
  }

  document.querySelectorAll('.segmented button').forEach((b) =>
    b.addEventListener('click', () => setMode(b.dataset.mode)));

  window.addEventListener('resize', () => drawBoxes(state.dets));

  /* ---------- início ---------- */
  const urlMode = new URLSearchParams(location.search).get('mode');
  const initial = [urlMode, CFG.mode].find((m) => m === 'demo' || m === 'api' || m === 'webcam') || 'demo';
  setMode(initial);
})();
