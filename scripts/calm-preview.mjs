const SKINS = [
  {
    name: "1. Carrinho de mina",
    top: "▗▆▖",
    base: "╘o═o╛",
    bars: ["▁", "▁", "▂", "▃"],
    sprite: "\x1b[33m",
    ground: "\x1b[90m",
  },
  {
    name: "2. Tocha na caverna",
    top: "◢▲◣",
    base: "▁▐█▌▁",
    bars: ["▁", "▂", "▄", "▆"],
    sprite: "\x1b[31m",
    ground: "\x1b[35m",
  },
  {
    name: "3. Nova",
    top: "╲│╱",
    base: "─╼█╾─",
    bars: [" ", "·", "·", "∙"],
    sprite: "\x1b[36m",
    ground: "\x1b[37m",
  },
  {
    name: "4. Impressora de dinheiro (brrr)",
    top: "$$$",
    base: "[BRR]",
    bars: ["▁", "▁", "$", "$"],
    sprite: "\x1b[32m",
    ground: "\x1b[32m",
  },
  {
    name: "5. Queimando token",
    top: "◢▲◣",
    base: "[TOK]",
    bars: ["▁", "·", "¢", "$"],
    sprite: "\x1b[31m",
    ground: "\x1b[33m",
  },
  {
    name: "6. Starship",
    top: "╱▲╲",
    base: "▐█X█▌",
    bars: ["▁", "▃", "▅", "▇"],
    sprite: "\x1b[37m",
    ground: "\x1b[33m",
  },
  {
    name: "7. Starship explodindo (RUD)",
    top: "╲│╱",
    base: "*RUD*",
    bars: [" ", ".", "'", "*"],
    sprite: "\x1b[31m",
    ground: "\x1b[33m",
  },
  {
    name: "8. A IA trabalhando por você",
    top: "·┬·",
    base: "[o_o]",
    bars: [" ", "0", "1", "1"],
    sprite: "\x1b[36m",
    ground: "\x1b[32m",
  },
  {
    name: "9. Aqui jaz o seu saldo",
    top: "┌┼┐",
    base: "│RIP│",
    bars: ["▁", "▁", "▂", "▂"],
    sprite: "\x1b[37m",
    ground: "\x1b[32m",
  },
  {
    name: "10. +18",
    top: "   ",
    base: "8===D",
    bars: [" ", " ", "~", "~"],
    sprite: "\x1b[35m",
    ground: "\x1b[36m",
  },
  {
    name: "0. Barco (atual)",
    top: "◿│◣",
    base: "╲▁▁▁╱",
    bars: ["▁", "▂", "▃", "▄"],
    sprite: "\x1b[33m",
    ground: "\x1b[34m",
  },
];

const RESET = "\x1b[39m";
const WIDTH = Math.min(60, (process.stdout.columns || 80) - 2);
const TICK_MS = 220;
const TICKS_PER_MOVE = 4;
const TROUGH = 5;

function level(column, center, bars) {
  const distance = Math.abs(column - center);
  if (distance <= TROUGH) return 0;
  const wave = (Math.sin((distance - TROUGH) / 3.2 - Math.PI / 2) + 1) / 2;
  return Math.round(wave * (bars.length - 1));
}

function frame(skin, position, direction, phase) {
  const center = position + 2 + (direction * phase) / TICKS_PER_MOVE;
  let line = "";
  for (let column = 0; column < WIDTH; column += 1) {
    if (column === position) {
      line += skin.sprite + skin.base + RESET;
      column += 4;
    } else {
      line += skin.ground + skin.bars[level(column, center, skin.bars)] + RESET;
    }
  }
  return [" ".repeat(position + 1) + skin.sprite + skin.top + RESET, line];
}

function state(tick) {
  const span = WIDTH - 5;
  const moves = Math.floor(tick / TICKS_PER_MOVE) % (span * 2);
  const position = moves <= span ? moves : span * 2 - moves;
  return { position, direction: moves < span ? 1 : -1, phase: tick % TICKS_PER_MOVE };
}

const C = { cyan: "\x1b[36m", green: "\x1b[32m", yellow: "\x1b[33m", red: "\x1b[31m", blue: "\x1b[34m", magenta: "\x1b[35m", white: "\x1b[37m", gray: "\x1b[90m" };

function canvas() {
  const row = () => Array.from({ length: WIDTH }, () => [" ", ""]);
  return [row(), row()];
}

function put(row, column, text, color) {
  Array.from(text).forEach((glyph, index) => {
    const at = column + index;
    if (at >= 0 && at < WIDTH) row[at] = [glyph, color];
  });
}

function paint(rows) {
  return rows.map((row) => row.map(([glyph, color]) => (color ? color + glyph + RESET : glyph)).join(""));
}

function bounce(tick, span) {
  const moves = Math.floor(tick / TICKS_PER_MOVE) % (span * 2);
  return { position: moves <= span ? moves : span * 2 - moves, direction: moves < span ? 1 : -1 };
}

function paintBits(base, tick) {
  const flow = Math.floor(tick / 2);
  for (let column = 0; column < WIDTH; column += 1) {
    const gap = (column + flow) % 4 === 0;
    base[column] = [gap ? " " : "01"[(column * 31 + flow) & 1], C.green];
  }
}

function paintCoins(base, coins, passed) {
  for (const column of coins) put(base, column, passed(column) ? "·" : "$", passed(column) ? C.gray : C.yellow);
}

function robotExpression(tick, coinAhead, afterBug, onBug) {
  let face = "[o_o]";
  let speech = tick % 2 ? "*┬*" : "·┬·";
  if (tick % 23 === 0) face = "[-_-]";
  if (tick % 61 < 6) speech = "brr";
  if (coinAhead) [face, speech] = ["[$_$]", "$$$"];
  if (afterBug) [face, speech] = ["[>_<]", "ops"];
  if (onBug) [face, speech] = ["[x_x]", "404"];
  return { face, speech };
}

function paintSweat(top, tick, position, direction) {
  ["'", "°", "·"].forEach((drop, index) => {
    if ((tick + index) % 3 === 0) return;
    const column = direction === 1 ? position - index : position + 4 + index;
    put(top, column, drop, C.blue);
  });
}

function robotSituation(position, direction, coins, passed) {
  const bug = Math.floor(WIDTH / 2) - 4;
  const front = direction === 1 ? position + 5 : position - 1;
  const justAfterBug = direction === 1 ? position - bug : bug - (position + 4);
  return {
    bug,
    coinAhead: coins.some((column) => !passed(column) && Math.abs(column - front) <= 2),
    onBug: bug >= position && bug <= position + 4,
    afterBug: justAfterBug >= 1 && justAfterBug <= 2,
  };
}

function robotScene(tick) {
  const [top, base] = canvas();
  const { position, direction } = bounce(tick, WIDTH - 5);
  paintBits(base, tick);
  const passed = (column) => (direction === 1 ? column < position : column > position + 4);
  const coins = [];
  for (let column = 8; column < WIDTH - 2; column += 11) coins.push(column);
  paintCoins(base, coins, passed);
  const { bug, coinAhead, onBug, afterBug } = robotSituation(position, direction, coins, passed);
  put(base, bug, "ж", C.red);

  const { face, speech } = robotExpression(tick, coinAhead, afterBug, onBug);
  put(base, position, face, onBug ? C.red : C.cyan);
  put(top, position + 1, speech, onBug ? C.red : coinAhead ? C.yellow : C.cyan);

  paintSweat(top, tick, position, direction);
  return paint([top, base]);
}

function paintWaves(base, tick) {
  for (let column = 0; column < WIDTH; column += 1) {
    if ((column + Math.floor(tick / 3)) % 6 < 2) base[column] = ["~", C.cyan];
  }
}

function adultLength(cycle, boosted) {
  if (boosted) return 5;
  if (cycle < 8) return 1;
  if (cycle < 16) return 2;
  return cycle < 28 ? 3 : 1;
}

function paintSpray(top, base, { cycle, tip, direction }) {
  const spray = ["~", "~·", "~·°", " ·°'"][cycle - 24];
  const text = direction === 1 ? spray : Array.from(spray).reverse().join("");
  put(base, direction === 1 ? tip + 1 : tip - text.length, text, C.white);
  put(top, direction === 1 ? tip + 1 : tip - 2, "!!", C.white);
}

function paintMood(top, start, cycle, boosted) {
  if (cycle >= 28) put(top, start, "zzz", C.gray);
  else if (boosted) put(top, start + 1, "!!!", C.blue);
}

function paintAdult(base, position, direction, length) {
  const shaft = "=".repeat(length);
  const start = direction === 1 ? position : position + 6 - (length + 1);
  put(base, start, direction === 1 ? `8${shaft}D` : `C${shaft}8`, C.magenta);
  return { start, tip: direction === 1 ? start + length + 1 : start };
}

function adultScene(tick) {
  const [top, base] = canvas();
  const { position, direction } = bounce(tick, WIDTH - 8);
  paintWaves(base, tick);
  const pill = Math.floor(WIDTH / 2);
  const past = direction === 1 ? position - pill : pill - (position + 6);
  if (past < 0) put(base, pill, "o", C.blue);
  const boosted = past > 0 && past <= 7;

  const cycle = tick % 32;
  const length = adultLength(cycle, boosted);
  const { start, tip } = paintAdult(base, position, direction, length);

  if (cycle >= 24 && cycle < 28) paintSpray(top, base, { cycle, tip, direction });
  else paintMood(top, start, cycle, boosted);
  return paint([top, base]);
}

SKINS.push({ name: "11. IA trabalhando por você (animada)", scene: robotScene });
SKINS.push({ name: "12. +18 (animado)", scene: adultScene });

const picked = process.argv.slice(2).filter((arg) => /^\d+$/.test(arg));
const SHOWN = picked.length ? SKINS.filter((skin) => picked.includes(skin.name.split(".")[0])) : SKINS;

function draw(tick) {
  const out = [];
  for (const skin of SHOWN) {
    if (skin.scene) {
      out.push(skin.name, ...skin.scene(tick), "");
      continue;
    }
    const { position, direction, phase } = state(tick);
    out.push(skin.name, ...frame(skin, position, direction, phase), "");
  }
  return out;
}

const stills = process.argv.find((arg) => arg.startsWith("--frames"));
if (stills) {
  const ticks = stills.includes("=") ? stills.split("=")[1].split(",").map(Number) : [8, 60, 130];
  for (const tick of ticks) console.log(draw(tick).join("\n"));
} else {
  let tick = 0;
  const lines = draw(0).length;
  process.stdout.write("\x1b[?25l" + draw(0).join("\n") + "\n");
  const timer = setInterval(() => {
    tick += 1;
    process.stdout.write(`\x1b[${lines}A` + draw(tick).map((l) => "\x1b[2K" + l).join("\n") + "\n");
  }, TICK_MS);
  process.on("SIGINT", () => {
    clearInterval(timer);
    process.stdout.write("\x1b[?25h");
    process.exit(0);
  });
}
