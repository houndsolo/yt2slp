// Real curated replay fixtures; synthetic settings only for rejection policies.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const crypto=require('node:crypto');
const {classify,catalog}=require('./catalog-replays.cjs');

test('catalog rejects multiplayer, CPU, followers, PAL and unsupported timers',()=>{
  const settings={players:[{type:0,characterId:2},{type:0,characterId:20}],isTeams:false,isPAL:false,timerType:2,startingTimerSeconds:480};
  assert.equal(classify(settings),'eligible_singles_settings');
  for(const [change,wanted] of [
    [{isTeams:true},'skip_multiplayer'],[{players:[...settings.players,...settings.players]},'skip_multiplayer'],
    [{players:[{type:1,characterId:2},settings.players[1]]},'skip_non_human'],
    [{players:[{type:0,characterId:14},settings.players[1]]},'skip_followers'],
    [{isPAL:true},'skip_pal'],[{timerType:0},'skip_timer']]) assert.equal(classify({...settings,...change}),wanted);
});

test('content duplicates keep a reserved split and catalog reveals no controller/account fields',()=>{
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'yt2slp-catalog-'));
  try {
    const root=path.join(temp,'input');fs.mkdirSync(root);
    const data=fs.readFileSync(path.resolve(__dirname,'../../recordings/examples/Game_20260623T163435.slp'));
    fs.writeFileSync(path.join(root,'Game_20260623T163435.slp'),data);
    fs.writeFileSync(path.join(root,'duplicate.slp'),data);
    const digest=crypto.createHash('sha256').update(data).digest('hex');
    const output=path.join(temp,'catalog'), result=catalog(root,output,{matches:[{replay_sha256:digest,split:'validation'}]});
    assert.equal(result.files,2);assert.equal(result.unique_content_hashes,1);
    assert.equal(result.status_counts.duplicate,1);assert.equal(result.model_training_ready,false);
    const rows=fs.readFileSync(path.join(output,'entries.ndjson'),'utf8').trim().split('\n').map(JSON.parse);
    assert(rows.every(r=>r.split_reservation==='validation'));
    for(const row of rows) for(const forbidden of ['pre','post','inputs','connectCode','displayName','names']) assert(!(forbidden in row));
    assert.throws(()=>catalog(root,output));
  } finally {fs.rmSync(temp,{recursive:true,force:true});}
});
