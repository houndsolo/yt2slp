const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const {SlippiGame}=require('@slippi/slippi-js/node');
const {exportTraining,project,edges}=require('./export-training.cjs');
const replay=path.resolve(__dirname,'../../recordings/examples/Game_20260622T203533.slp');

test('training export matches original pre/post events with no account metadata',()=>{
  const labels=exportTraining(replay,-40,180), frames=new SlippiGame(replay).getFrames();
  assert.equal(labels.rows.length,442);
  assert.equal(labels.replay_sha256,'c13e36c0f079200b6f00e2b3bef22ffe1165cde23797325218509718d794b40f');
  for (const row of labels.rows) {
    const original=frames[row.frame].players[row.port];
    assert.equal(row.effective.values.buttons,original.pre.buttons);
    assert.equal(row.physical.values.buttons,original.pre.physicalButtons);
    assert.equal(row.effective.values.stick_y,original.pre.joystickY);
    assert.equal(row.state.values.action,original.post.actionStateId);
    assert.equal(row.state.values.y,original.post.positionY);
    assert.equal(row.state.values.airborne,original.post.isAirborne);
    assert.equal(row.state.values.velocity_y,original.post.selfInducedSpeeds.y);
    assert.equal(row.physical.mask.raw_stick_y,false);
    const prev=frames[row.frame-1].players[row.port].pre.physicalButtons;
    assert.equal(row.physical_edges.pressed,(original.pre.physicalButtons & ~prev)&0xffff);
    assert.equal(row.physical_edges.released,(prev & ~original.pre.physicalButtons)&0xffff);
  }
  assert(!/displayName|connectCode|nametag|netplayName|startAt|consoleNickname/.test(JSON.stringify(labels)));
});

test('unknown values stay masked; unsigned button edges preserve releases',()=>{
  assert.deepEqual(project({a:0,b:false,c:NaN},{zero:'a',boolean:'b',bad:'c',missing:'d'}),
    {values:{zero:0,boolean:false,bad:null,missing:null},mask:{zero:true,boolean:true,bad:false,missing:false}});
  assert.deepEqual(edges(0,0x80000400,32),{pressed:0,released:0x80000400,mask:true});
  assert.deepEqual(edges(0,undefined,16),{pressed:null,released:null,mask:false});
  assert.equal(exportTraining(replay,-123,-123).rows[0].physical_edges.mask,false);
});

test('incomplete or invalid training intervals fail explicitly',()=>{
  for (const interval of [[-124,0],[0,1.5],[3,2],[9438,9439]])
    assert.throws(()=>exportTraining(replay,...interval));
});
