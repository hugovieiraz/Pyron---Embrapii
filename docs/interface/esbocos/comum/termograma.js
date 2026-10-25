// Termograma sintético (320 × 240) para os esboços: transformador com três buchas e uma conexão quente.
// Faixa de exibição manual (22–60 °C), como o termografista ajusta: a conexão a 96 °C satura em branco.
const TERMO = { largura: 320, altura: 240, min: 22, max: 60 };

function campoTermico() {
  const { largura: W, altura: H } = TERMO;
  const t = new Float32Array(W * H);
  const blob = (x, y, cx, cy, r, amp) => amp * Math.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * r * r));
  const dentro = (x, y, x0, y0, x1, y1) => x >= x0 && x < x1 && y >= y0 && y < y1;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      let v = 19 + (y / H) * 6 + Math.sin(x * 0.05 + y * 0.03) * 0.6; // céu e fundo
      if (dentro(x, y, 40, 150, 280, 236)) v = 30.5 + Math.sin(y * 0.4) * 0.8 + (x > 100 && x < 220 ? 2 : 0); // tanque com aletas
      for (const cx of [100, 160, 220]) {
        if (dentro(x, y, cx - 10, 58, cx + 10, 150)) v = 34 + Math.sin(y * 0.9) * 1.2 + (cx === 100 ? 12 * (1 - (y - 58) / 92) : 0); // bucha com saias
        if (dentro(x, y, cx - 3, 20, cx + 3, 58)) v = 36; // condutor
      }
      v += blob(x, y, 100, 44, 6, 60) + blob(x, y, 160, 42, 5, 10) + blob(x, y, 220, 44, 5, 9.5);
      t[y * W + x] = v;
    }
  }
  return t;
}

// Paleta ferro (dado térmico, não é cor de interface).
const FERRO = [[0, 0, 0], [30, 4, 110], [120, 6, 150], [200, 30, 110], [240, 100, 30], [252, 180, 20], [255, 240, 140], [255, 255, 255]];

function corFerro(f) {
  const p = Math.max(0, Math.min(1, f)) * (FERRO.length - 1);
  const i = Math.min(FERRO.length - 2, Math.floor(p));
  const k = p - i;
  return FERRO[i].map((c, j) => Math.round(c + (FERRO[i + 1][j] - c) * k));
}

function desenharTermograma(canvas) {
  const { largura: W, altura: H, min, max } = TERMO;
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(W, H);
  const t = campoTermico();
  for (let i = 0; i < t.length; i++) {
    const [r, g, b] = corFerro((t[i] - min) / (max - min));
    img.data.set([r, g, b, 255], i * 4);
  }
  ctx.putImageData(img, 0, 0);
}

function desenharEscala(canvas) {
  canvas.width = 1;
  canvas.height = 256;
  const ctx = canvas.getContext("2d");
  for (let y = 0; y < 256; y++) {
    const [r, g, b] = corFerro(1 - y / 255);
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    ctx.fillRect(0, y, 1, 1);
  }
}

// Caixas das regiões em porcentagem da imagem, com a cor da severidade vinda dos tokens.
function caixasRegioes(palco, regioes, { rotulos = true, selecionada = null } = {}) {
  const { largura: W, altura: H } = TERMO;
  for (const r of regioes) {
    const [x0, y0, x1, y1] = r.caixa;
    const c = document.createElement("div");
    c.className = `caixa${r.id === selecionada ? " selecionada" : ""}`;
    c.style.cssText = `left:${(x0 / W) * 100}%;top:${(y0 / H) * 100}%;width:${((x1 - x0) / W) * 100}%;height:${((y1 - y0) / H) * 100}%;border-color:var(--${r.severidade})`;
    if (rotulos && r.severidade !== "normal") {
      const e = document.createElement("span");
      e.className = "etq";
      e.textContent = `${r.nome} ${fmt(r.tmax)} °C`;
      c.append(e);
    }
    palco.append(c);
  }
}
