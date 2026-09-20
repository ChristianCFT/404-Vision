/* 404 Vision — frontend
   Dois modos de dados:
   - demo: fotos reais da base + cálculo local (não precisa de backend)
   - api:  consulta o backend Python (formato em frontend/README.md) */
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
    demoOutdoor: $('demoOutdoor'), demoK: $('demoK'), demoPlay: $('demoPlay')
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

  /* ---------- caixas de detecção (só se o backend enviar) ---------- */
  function drawBoxes(dets) {
    const c = el.canvas;
    const w = c.clientWidth, h = c.clientHeight;
    const dpr = window.devicePixelRatio || 1;
    if (c.width !== w * dpr || c.height !== h * dpr) { c.width = w * dpr; c.height = h * dpr; }
    const ctx = c.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#ffb14a';
    ctx.fillStyle = 'rgba(255, 138, 61, .14)';
    dets.forEach((b) => {
      const x = b.x * w, y = b.y * h, bw = b.w * w, bh = b.h * h;
      ctx.beginPath();
      ctx.roundRect ? ctx.roundRect(x, y, bw, bh, 4) : ctx.rect(x, y, bw, bh);
      ctx.fill();
      ctx.stroke();
    });
  }

  /* ---------- imagem da câmera ---------- */
  function setFrame(url) {
    if (!url) return;
    const pre = new Image();
    pre.onload = () => {
      el.img.src = url;
      el.empty.hidden = true;
    };
    pre.onerror = () => {
      if (!el.img.getAttribute('src')) {
        el.empty.hidden = false;
        el.empty.firstElementChild.textContent = 'Não foi possível carregar a imagem da câmera.';
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
  async function poll() {
    const url = CFG.apiBase + CFG.statusPath;
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = normalize(await res.json());
      const bust = Date.now();
      const frameUrl = d.frameUrl
        ? d.frameUrl
        : `${CFG.apiBase}${CFG.framePath}?t=${bust}`;
      setFrame(frameUrl);
      render(d);
      el.banner.hidden = true;
      setStatus('live', `Ao vivo · ${clock(d.ts)}`);
    } catch (err) {
      document.body.classList.add('stale');
      setStatus('error', 'Sem conexão com o backend');
      el.banner.hidden = false;
      el.banner.innerHTML = `Não foi possível ler <code>${escapeHtml(url)}</code> (${escapeHtml(err.message)}). ` +
        `Confira se o backend está rodando e se o CORS está liberado. A tela tenta de novo automaticamente.`;
    }
  }

  function startApi() {
    el.demoBar.hidden = true;
    setStatus('error', 'Conectando…');
    poll();
    state.timer = setInterval(poll, CFG.pollMs);
  }

  /* =========================================================
     Troca de modo
     ========================================================= */
  function setMode(mode) {
    clearInterval(state.timer);
    state.mode = mode;
    state.history = [];
    state.lastCount = null;
    state.shownTemp = null;
    el.img.removeAttribute('src');
    el.empty.hidden = false;
    el.empty.firstElementChild.textContent = 'Aguardando a primeira imagem da câmera.';
    document.querySelectorAll('.segmented button').forEach((b) =>
      b.setAttribute('aria-pressed', String(b.dataset.mode === mode)));
    mode === 'demo' ? startDemo() : startApi();
  }

  document.querySelectorAll('.segmented button').forEach((b) =>
    b.addEventListener('click', () => setMode(b.dataset.mode)));

  window.addEventListener('resize', () => drawBoxes(state.dets));

  /* ---------- início ---------- */
  const urlMode = new URLSearchParams(location.search).get('mode');
  const initial = [urlMode, CFG.mode].find((m) => m === 'demo' || m === 'api') || 'demo';
  setMode(initial);
})();
