// Independent format validation only; parsing is not official playback proof.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const crypto = require('node:crypto');
const { parseArgs } = require('node:util');

function validateParsedReplay(settings, frames, gameEnd, metadata, options = {}) {
  assert(settings && settings.players.length === 2, 'expected two recorded players');
  const numbers = Object.keys(frames).map(Number).sort((a, b) => a - b);
  assert(numbers.length > 123 && numbers[0] === -123, 'missing opening/gameplay frames');
  for (let i = 0; i < numbers.length; i++) {
    assert.equal(numbers[i], i - 123, 'noncontiguous frame stream');
    for (const player of settings.players) {
      const data = frames[numbers[i]].players[player.playerIndex];
      assert(data && data.pre && data.post, 'missing player frame events');
    }
  }
  const lastFrame = numbers.at(-1);
  if (options.lastFrame !== undefined) {
    assert.equal(lastFrame, options.lastFrame, 'final frame differs from native recording status');
  }
  if (options.requireComplete) {
    assert(gameEnd && [1, 2, 3, 7].includes(gameEnd.gameEndMethod), 'missing or unresolved Game End');
    assert.equal(metadata?.lastFrame, lastFrame, 'metadata final frame differs from event stream');
    const placements = new Map(gameEnd.placements.map(p => [p.playerIndex, p.position]));
    for (const player of settings.players) {
      assert([0, 1].includes(placements.get(player.playerIndex)), 'invalid active player placement');
    }
    if (gameEnd.gameEndMethod !== 7) {
      assert.equal(gameEnd.lrasInitiatorIndex, -1, 'unexpected quit initiator for a natural ending');
    } else {
      assert(settings.players.some(p => p.playerIndex === gameEnd.lrasInitiatorIndex), 'invalid quit initiator');
    }
  }
  if (options.endMethod !== undefined) {
    assert.equal(gameEnd?.gameEndMethod, options.endMethod, 'unexpected game end method');
  }
  if (options.placements !== undefined) {
    const actual = settings.players.map(p => gameEnd?.placements.find(v => v.playerIndex === p.playerIndex)?.position);
    assert.deepEqual(actual, options.placements, 'unexpected player placements');
  }
  return { parser: '@slippi/slippi-js@9.1.3', settings,
    firstFrame: numbers[0], lastFrame, frameCount: numbers.length,
    gameEnd: gameEnd ?? null, metadata, completeMatchValidated: options.requireComplete === true,
    playbackValidated: false };
}

function main() {
  const { values, positionals } = parseArgs({ allowPositionals: true, options: {
    'require-complete': { type: 'boolean', default: false },
    'last-frame': { type: 'string' }, 'end-method': { type: 'string' },
    placements: { type: 'string' },
  }});
  assert.equal(positionals.length, 1, 'usage: validate.cjs REPLAY [--require-complete --last-frame N --end-method N --placements 1,0]');
  const integer = value => {
    assert(/^-?[0-9]+$/.test(value), 'expected integer option');
    const n = Number(value);
    assert(Number.isSafeInteger(n), 'integer option out of range');
    return n;
  };
  const options = { requireComplete: values['require-complete'] };
  if (values['last-frame'] !== undefined) options.lastFrame = integer(values['last-frame']);
  if (values['end-method'] !== undefined) options.endMethod = integer(values['end-method']);
  if (values.placements !== undefined) options.placements = values.placements.split(',').map(integer);
  const { SlippiGame } = require('@slippi/slippi-js/node');
  const replay = fs.readFileSync(positionals[0]);
  const game = new SlippiGame(replay);
  const settings = game.getSettings();
  const frames = game.getFrames();
  const result = validateParsedReplay(settings, frames, game.getGameEnd(), game.getMetadata(), options);
  result.replaySha256 = crypto.createHash('sha256').update(replay).digest('hex');
  console.log(JSON.stringify(result, null, 2));
}

module.exports = { validateParsedReplay };
if (require.main === module) {
  try { main(); }
  catch (error) { console.error(`Replay validation failed: ${error.message}`); process.exitCode = 1; }
}
