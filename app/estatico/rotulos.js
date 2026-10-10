"use strict";

// Onde vai cada rótulo de uma caixa de detecção sem cobrir os outros: usado na página do celular e no
// espelho do celular no computador. Peças aninhadas (o para-raio contém as aletas e os terminais)
// costumam ter caixas com o mesmo canto, e o rótulo fixo no canto se sobrepunha.

/** Lugares em volta da caixa, na ordem de preferência: fora acima, fora abaixo, dentro, dos lados. */
function lugaresDoRotulo(c, lw, lh, m) {
  return [
    [c.x, c.y - lh - m], [c.x + c.w - lw, c.y - lh - m],
    [c.x, c.y + c.h + m], [c.x + c.w - lw, c.y + c.h + m],
    [c.x + m, c.y + m], [c.x + m, c.y + c.h - lh - m],
    [c.x + c.w + m, c.y], [c.x - lw - m, c.y],
  ];
}

function areaComum(a, b) {
  const x = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
  const y = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
  return x * y;
}

/**
 * Posição de cada rótulo, em pixels da área de desenho.
 *
 * itens: [{ chave, caixa: {x, y, w, h}, largura, altura }]; limites: {x0, y0, x1, y1} (onde o rótulo
 * pode ficar); anteriores: Map de chave → lugar usado no quadro passado, para o rótulo não pular de
 * um lado para o outro enquanto o lugar antigo continuar livre. As caixas menores escolhem primeiro:
 * têm menos lugares bons. Custo de um lugar: sair dos limites (proibido), cobrir outro rótulo (área
 * coberta) e, mais leve, cobrir outra caixa.
 */
function posicionarRotulos(itens, limites, anteriores = new Map(), margem = 4) {
  const ocupados = [];
  const saida = new Array(itens.length);
  const ordem = itens.map((_, i) => i).sort((a, b) => itens[a].caixa.w * itens[a].caixa.h - itens[b].caixa.w * itens[b].caixa.h);
  for (const i of ordem) {
    const { caixa, largura: lw, altura: lh, chave } = itens[i];
    const lugares = lugaresDoRotulo(caixa, lw, lh, margem).map(([x, y], lugar) => {
      const r = { x: Math.min(Math.max(x, limites.x0), limites.x1 - lw), y, w: lw, h: lh };
      const fora = r.y < limites.y0 || r.y + lh > limites.y1;
      let custo = fora ? Infinity : 0;
      for (const o of ocupados) custo += areaComum(r, o);
      itens.forEach((outro, j) => { if (j !== i) custo += 0.15 * areaComum(r, outro.caixa); });
      return { ...r, lugar, custo };
    });
    const menor = Math.min(...lugares.map((l) => l.custo));
    const antes = lugares[anteriores.get(chave)];
    const escolhido = antes && antes.custo <= menor ? antes : lugares.find((l) => l.custo === menor);
    anteriores.set(chave, escolhido.lugar);
    ocupados.push(escolhido);
    saida[i] = escolhido;
  }
  return saida;
}

/** Chave estável de cada detecção (classe + ordem dentro da classe), para lembrar o lugar do rótulo. */
function chavesDasDeteccoes(lista) {
  const conta = new Map();
  return lista.map((d) => {
    const n = (conta.get(d.classe) || 0) + 1;
    conta.set(d.classe, n);
    return `${d.classe}#${n}`;
  });
}

// Ordem das cores de série (tokens): azul, âmbar, verde-azulado, violeta. Vizinhas na lista ficam com
// tons bem diferentes; azul e violeta, os mais parecidos, só se repetem a três classes de distância.
const ORDEM_SERIES = [1, 4, 2, 3];

/** Cor de cada tipo de peça, pela posição da classe na lista do modelo. */
function corDaClasse(classe, classes = []) {
  const i = Math.max(0, classes.indexOf(classe));
  return `var(--serie-${ORDEM_SERIES[i % ORDEM_SERIES.length]})`;
}
