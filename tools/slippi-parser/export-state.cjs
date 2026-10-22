// Independent Slippi parsing; omit player names/accounts from benchmark artifacts.
const fs = require('node:fs');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { SlippiGame, frameToGameTimer } = require('@slippi/slippi-js/node');
const floats = {x:'positionX',y:'positionY',facing:'facingDirection',percent:'percent',shield:'shieldSize',animation:'actionStateCounter'};
const integers = {action:'actionStateId',stocks:'stocksRemaining',character:'internalCharacterId'};
function floatBits(value) {
  assert(Number.isFinite(value), 'missing/non-finite post-frame value');
  const b=Buffer.alloc(4); b.writeFloatBE(value); return b.readUInt32BE();
}
function main() {
  assert.equal(process.argv.length,3,'usage: export-state.cjs REPLAY');
  const bytes=fs.readFileSync(process.argv[2]);
  const game=new SlippiGame(bytes), s=game.getSettings(), frames=game.getFrames();
  assert(s?.players.length===2 && !s.isTeams,'benchmark supports two-player singles');
  const rows=[];
  for(const frame of Object.keys(frames).map(Number).sort((a,b)=>a-b)) {
    for(const p of s.players) {
      const f=frames[frame].players[p.playerIndex];
      assert(f?.post && f.pre,'incomplete player frame');
      assert(!frames[frame].followers?.[p.playerIndex], 'followers are outside this benchmark');
      const fields={};
      for(const [key,name] of Object.entries(floats)) fields[key]=floatBits(f.post[name]);
      for(const [key,name] of Object.entries(integers)) {
        assert(Number.isInteger(f.post[name]),'missing integer post-frame value'); fields[key]=f.post[name];
      }
      rows.push({frame,player:p.playerIndex,fields});
    }
  }
  const settings={stage:s.stageId,seed:s.randomSeed,timer_type:s.timerType,timer_seconds:s.startingTimerSeconds,
    players:s.players.map(p=>({player:p.playerIndex,character:p.characterId,costume:p.characterColor,type:p.type}))};
  const timers={};
  for(let f=0;f<=Math.max(...Object.keys(frames).map(Number));f++) timers[f]=frameToGameTimer(f,{timerType:s.timerType,startingTimerSeconds:s.startingTimerSeconds});
  console.log(JSON.stringify({schema:1,parser:'@slippi/slippi-js@9.1.3',replay_sha256:crypto.createHash('sha256').update(bytes).digest('hex'),
    settings,rows,timers,game_end:game.getGameEnd()??null}));
}
try {main();} catch(e) {console.error(`State export failed: ${e.message}`);process.exitCode=1;}
