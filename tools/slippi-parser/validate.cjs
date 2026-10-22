// Independent format validation only; successful parsing is not playback proof.
const { SlippiGame } = require('@slippi/slippi-js/node');
const assert = require('node:assert/strict');
const game = new SlippiGame(process.argv[2]);
const settings = game.getSettings();
assert(settings && settings.players.length === 2, 'expected two recorded players');
const frames = game.getFrames();
const numbers = Object.keys(frames).map(Number).sort((a,b)=>a-b);
assert(numbers.length > 123 && numbers[0] === -123, 'missing opening/gameplay frames');
for (let i=0;i<numbers.length;i++) {
  assert.equal(numbers[i], i-123, 'noncontiguous frame stream');
  for (const player of settings.players) {
    const data = frames[numbers[i]].players[player.playerIndex];
    assert(data && data.pre && data.post, 'missing player frame events');
  }
}
console.log(JSON.stringify({parser:'@slippi/slippi-js@9.1.3', settings,
  firstFrame:numbers[0], lastFrame:numbers.at(-1), frameCount:numbers.length,
  gameEnd:game.getGameEnd() ?? null, metadata:game.getMetadata(), playbackValidated:false},null,2));
