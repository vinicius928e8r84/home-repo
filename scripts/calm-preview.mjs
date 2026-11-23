// Preview of candidate replacements for Calm's working animation.
//
//   node scripts/calm-preview.mjs            animated, Ctrl+C to stop
//   node scripts/calm-preview.mjs --frames   three still frames per candidate
//
// Each candidate keeps the boat's geometry (a 3-cell top over a 5-cell base that
// bounces along one line of bars), so the chosen one drops into
// .pi/extensions/lib/fm-calm-working-ship-sprite.ts by changing glyphs and colors.

const SKINS = [
  {
    name: "1. Carrinho de mina",
    top: "▗▆▖",
    base: "╘o═o╛",
    bars: ["▁", "▁", "▂", "▃"],
    sprite: "\x1b[33m", // yellow
    ground: "\x1b[90m", // gray
  },
  {
    name: "2. Tocha na caverna",
    top: "◢▲◣",
    base: "▁▐█▌▁",
    bars: ["▁", "▂", "▄", "▆"],
    sprite: "\x1b[31m", // red
    ground: "\x1b[35m", // magenta
  },
  {
    name: "3. Nova",
    top: "╲│╱",
    base: "─╼█╾─",
    bars: [" ", "·", "·", "∙"],
    sprite: "\x1b[36m", // cyan
    ground: "\x1b[37m", // white
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

function draw(tick) {
  const out = [];
  for (const skin of SKINS) {
    const { position, direction, phase } = state(tick);
    out.push(skin.name, ...frame(skin, position, direction, phase), "");
  }
  return out;
}

if (process.argv.includes("--frames")) {
  for (const tick of [8, 60, 130]) console.log(draw(tick).join("\n"));
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
