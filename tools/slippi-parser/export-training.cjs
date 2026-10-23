// Supervised TRAINING labels. Never expose this output to held-out inference.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {SlippiGame} = require('@slippi/slippi-js/node');
const {inspect} = require('./inspect-settings.cjs');

const effectiveFields = {buttons:'buttons', stick_x:'joystickX', stick_y:'joystickY',
  cstick_x:'cStickX', cstick_y:'cStickY', trigger:'trigger'};
const physicalFields = {buttons:'physicalButtons', trigger_l:'physicalLTrigger',
  trigger_r:'physicalRTrigger', raw_stick_x:'rawJoystickX', raw_stick_y:'rawJoystickY',
  raw_cstick_x:'rawCStickX', raw_cstick_y:'rawCStickY'};
const stateFields = {action:'actionStateId', animation:'actionStateCounter',
  character:'internalCharacterId', x:'positionX', y:'positionY', facing:'facingDirection',
  percent:'percent', stocks:'stocksRemaining', airborne:'isAirborne', jumps:'jumpsRemaining',
  velocity_air_x:'airX', velocity_y:'y', velocity_ground_x:'groundX'};

function project(source, fields) {
  const values={}, mask={};
  for (const [name,key] of Object.entries(fields)) {
    const value=source?.[key];
    mask[name]=typeof value==='boolean' || (typeof value==='number' && Number.isFinite(value));
    values[name]=mask[name] ? value : null;
  }
  return {values, mask};
}

function edges(current, previous, bits) {
  if (!Number.isInteger(current) || !Number.isInteger(previous))
    return {pressed:null, released:null, mask:false};
  const mask=bits===16 ? 0xffff : 0xffffffff;
  return {pressed:((current & ~previous) & mask)>>>0,
    released:((previous & ~current) & mask)>>>0, mask:true};
}

function exportTraining(file, first, last) {
  assert(Number.isInteger(first) && Number.isInteger(last) && first>=-123 && last>=first,
    'integer replay interval starting at -123 or later required');
  const game=new SlippiGame(fs.readFileSync(file)), settings=game.getSettings();
  assert(settings && !settings.isTeams && settings.players.length===2,
    'initial training exporter supports two-player singles');
  assert(settings.players.every(p=>p.characterId!==14), 'Ice Climbers followers unsupported');
  const frames=game.getFrames(), rows=[];
  for (let frame=first;frame<=last;frame++) {
    const entry=frames[frame];
    assert(entry, `missing frame ${frame}`);
    for (const player of settings.players) {
      const port=player.playerIndex, current=entry.players[port];
      assert(current?.pre && current?.post, `incomplete player frame ${frame}:${port}`);
      assert(!entry.followers?.[port], 'followers unsupported');
      assert(current.pre.frame===frame && current.post.frame===frame &&
        current.pre.playerIndex===port && current.post.playerIndex===port,
        'inconsistent event frame/player keys');
      const previous=frames[frame-1]?.players[port]?.pre;
      rows.push({frame, port,
        effective:project(current.pre,effectiveFields), physical:project(current.pre,physicalFields),
        effective_edges:edges(current.pre.buttons,previous?.buttons,32),
        physical_edges:edges(current.pre.physicalButtons,previous?.physicalButtons,16),
        state:project({...current.post,...current.post.selfInducedSpeeds},stateFields)});
    }
  }
  const setup=inspect(file); delete setup.file; delete setup.policy;
  return {schema:1,kind:'supervised-replay-labels',parser:'@slippi/slippi-js@9.1.3',
    replay_sha256:setup.replay_sha256,interval:[first,last],settings:setup,
    timing:{controls:'pre-frame effective controls and separate physical fields',
      state:'same-key post-frame state',image_phase_verified:false,native_vi_adapter_verified:false},
    unavailable_fields:{raw_stick_y:'not exposed by pinned parser 9.1.3',
      raw_cstick_x:'not exposed by pinned parser 9.1.3',raw_cstick_y:'not exposed by pinned parser 9.1.3'},
    policy:'training labels intentionally include original controls/state; no names, accounts or free-form metadata',rows};
}

if (require.main===module) {
  try {
    assert.equal(process.argv.length,5,'usage: export-training.cjs REPLAY FIRST LAST');
    console.log(JSON.stringify(exportTraining(process.argv[2],Number(process.argv[3]),Number(process.argv[4]))));
  } catch (error) {console.error(`Training export failed: ${error.message}`);process.exitCode=1;}
}
module.exports={exportTraining,project,edges};
