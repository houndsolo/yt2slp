// Preparation only: settings/codes, with no controller, post-frame or account output.
const fs = require('node:fs');
const crypto = require('node:crypto');
const path = require('node:path');
const { SlippiGame } = require('@slippi/slippi-js/node');
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
function inspect(file, openingState = false) {
  const bytes = fs.readFileSync(file), game = new SlippiGame(bytes);
  const s = game.getSettings(), codes = game.getGeckoList();
  if (!s) throw new Error('missing replay settings');
  const result = {file, replay_sha256: hash(bytes), version: s.slpVersion,
    stage: s.stageId, is_teams: s.isTeams, seed: s.randomSeed,
    timer_type: s.timerType, timer_seconds: s.startingTimerSeconds,
    game_mode: s.inGameMode, is_pal: s.isPAL, scene: s.scene,
    players: s.players.map(p => ({port:p.playerIndex, character:p.characterId,
      costume:p.characterColor, type:p.type, stocks:p.startStocks,
      controller_fix:p.controllerFix})),
    last_frame: game.getMetadata()?.lastFrame,
    gecko_list_present: codes !== undefined,
    gecko_list_sha256: codes ? hash(codes.contents) : null,
    codes: codes?.codes.map(c => ({type:c.type, address:c.address,
      bytes:c.contents.length, sha256:hash(c.contents)})) ?? null,
    policy: 'supplied setup/code inspection only; no original controls or later player state exposed'};
  if (openingState) {
    const frames = game.getFrames();
    result.supplied_initial_state = [-123,-40].map(frame => ({frame,
      players:s.players.map(p => {
        const post = frames[frame]?.players[p.playerIndex]?.post;
        if (!post) throw new Error('missing declared initial-state frame');
        return {port:p.playerIndex, x:post.positionX, y:post.positionY, facing:post.facingDirection,
          action:post.actionStateId, animation:post.actionStateCounter, stocks:post.stocksRemaining,
          percent:post.percent, shield:post.shieldSize};
      })}));
    result.policy += '; only initial -123/-40 states explicitly supplied for startup verification';
  }
  return result;
}
if (require.main === module) {
  try {
    const input = process.argv[2];
    const openingState = process.argv[3] === '--opening-state';
    if (!(process.argv.length === 3 || (process.argv.length === 4 && openingState)))
      throw new Error('usage: inspect-settings.cjs FILE_OR_DIRECTORY [--opening-state]');
    const files = fs.statSync(input).isDirectory()
      ? fs.readdirSync(input).filter(n => n.endsWith('.slp')).sort().map(n => path.join(input,n)) : [input];
    console.log(JSON.stringify({schema:1, parser:'@slippi/slippi-js@9.1.3', replays:files.map(f => inspect(f,openingState))},null,2));
  } catch (e) { console.error(`Settings inspection failed: ${e.message}`); process.exitCode=1; }
}
module.exports = {inspect};
