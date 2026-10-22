// Synthetic parsed objects only: these tests never fabricate .slp files.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { validateParsedReplay } = require('./validate.cjs');
function fixture() {
  return {
    settings: { players: [{playerIndex:0},{playerIndex:1}] },
    frames: Object.fromEntries(Array.from({length:125}, (_, i) => [i-123, {
      players: {0:{pre:{},post:{}},1:{pre:{},post:{}}}
    }])),
    end: {gameEndMethod:1,lrasInitiatorIndex:-1,placements:[{playerIndex:0,position:1},{playerIndex:1,position:0}]},
    metadata: {lastFrame:1},
  };
}
function validate(f, options={requireComplete:true}) {
  return validateParsedReplay(f.settings,f.frames,f.end,f.metadata,options);
}
test('complete ending validates with expected native frame/method/placements', () => {
  const result = validate(fixture(), {requireComplete:true,lastFrame:1,endMethod:1,placements:[1,0]});
  assert(result.completeMatchValidated && !result.playbackValidated);
});
test('partial export is allowed only without complete-match requirement', () => {
  const f=fixture(); f.end=undefined;
  assert.equal(validate(f,{}).gameEnd,null);
  assert.throws(()=>validate(f), /Game End/);
});
for(const [name, change, error] of [
  ['unresolved ending',f=>f.end.gameEndMethod=0,/Game End/],
  ['metadata mismatch',f=>f.metadata.lastFrame=0,/metadata final frame/],
  ['invalid placement',f=>f.end.placements[0].position=-1,/placement/],
  ['missing player frame',f=>delete f.frames[0].players[1].post,/player frame/],
  ['missing frame',f=>delete f.frames[0],/noncontiguous/],
  ['unexpected quit initiator',f=>f.end.lrasInitiatorIndex=0,/quit initiator/],
]) test(name,()=>{const f=fixture();change(f);assert.throws(()=>validate(f),error);});
test('wrong expected result cannot pass',()=>{
  for(const options of [{lastFrame:2},{endMethod:2},{placements:[0,1]}]) {
    assert.throws(()=>validate(fixture(),{requireComplete:true,...options}));
  }
});
