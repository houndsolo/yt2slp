// Settings-only corpus inventory. Never output accounts, inputs or player states.
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {SlippiGame}=require('@slippi/slippi-js/node');

function classify(s) {
  if (s.isTeams || s.players.length!==2) return 'skip_multiplayer';
  if (s.players.some(p=>p.type!==0)) return 'skip_non_human';
  if (s.isPAL) return 'skip_pal';
  if (s.players.some(p=>p.characterId===14)) return 'skip_followers';
  if (s.timerType!==2 || !(s.startingTimerSeconds>0)) return 'skip_timer';
  return 'eligible_singles_settings';
}

function* replayFiles(root) {
  for (const entry of fs.readdirSync(root,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))) {
    const file=path.join(root,entry.name);
    if (entry.isDirectory()) yield* replayFiles(file);
    else if (entry.isFile() && entry.name.toLowerCase().endsWith('.slp')) yield file;
  }
}

function catalog(root, output, splitPlan) {
  root=path.resolve(root);output=path.resolve(output);
  fs.mkdirSync(output,{recursive:false});
  const reservations=new Map((splitPlan?.matches??[]).map(m=>[m.replay_sha256,m.split]));
  const seen=new Map(), counts={}, stages={}, rosters={}, dates=new Set();
  let total=0,bytes=0,eligibleUnique=0,narrowUnique=0;
  const fd=fs.openSync(path.join(output,'entries.ndjson'),'wx');
  try {
    for (const file of replayFiles(root)) {
      let row={file:path.relative(root,file)};
      try {
        // Bound memory even for a damaged or accidentally renamed bulk import.
        if (fs.statSync(file).size>64*1024*1024) throw new Error('Replay exceeds 64 MiB settings-catalog limit; left untouched and unhashed');
        const data=fs.readFileSync(file);
        const digest=crypto.createHash('sha256').update(data).digest('hex');
        bytes+=data.length;
        const reserved=reservations.get(digest)??null;
        const date=/^Game_(\d{8})T\d{6}/.exec(path.basename(file))?.[1]??null;
        if (date) dates.add(date);
        row={...row,replay_sha256:digest,bytes:data.length,capture_date_from_filename:date,
          split_reservation:reserved};
        if (seen.has(digest)) row={...row,status:'duplicate',duplicate_of:seen.get(digest)};
        else {
          seen.set(digest,row.file);
          const game=new SlippiGame(data),s=game.getSettings();
          if (!s) throw new Error('missing replay settings');
          row={...row,status:classify(s),version:s.slpVersion,stage:s.stageId,is_teams:s.isTeams,
            is_pal:s.isPAL,timer_type:s.timerType,timer_seconds:s.startingTimerSeconds,
            players:s.players.map(p=>({port:p.playerIndex,character:p.characterId,costume:p.characterColor,
              type:p.type,stocks:p.startStocks,controller_fix:p.controllerFix})),
            last_frame:game.getMetadata()?.lastFrame??null};
          if (row.status==='eligible_singles_settings') {
            eligibleUnique++;
            const roster=s.players.map(p=>p.characterId).sort((a,b)=>a-b).join(',');
            stages[s.stageId]=(stages[s.stageId]??0)+1;rosters[roster]=(rosters[roster]??0)+1;
            if (s.stageId===31 && roster==='2,20') narrowUnique++;
          }
        }
      } catch(error) {row={...row,status:'parse_error',error:error.message};}
      counts[row.status]=(counts[row.status]??0)+1;total++;
      fs.writeSync(fd,JSON.stringify(row)+'\n');
      if (total%100===0) console.error(`Catalogued ${total} replay files`);
    }
  } finally {fs.closeSync(fd);}
  const summary={schema:1,kind:'replay-settings-catalog',parser:'@slippi/slippi-js@9.1.3',
    files:total,bytes_read:bytes,unique_content_hashes:seen.size,status_counts:counts,
    eligible_unique_singles_settings:eligibleUnique,fox_falco_battlefield_unique:narrowUnique,
    eligible_stage_counts:stages,eligible_roster_counts:rosters,capture_dates:dates.size,
    rendering_validated:false,model_training_ready:false,
    policy:'settings-only inventory; doubles/non-singles skipped; no original controls/posts/accounts output; dates are filename heuristics, not verified sessions; content identity and reserved split follow duplicates'};
  fs.writeFileSync(path.join(output,'summary.json'),JSON.stringify(summary,null,2)+'\n');
  return summary;
}

if (require.main===module) {
  try {
    if (![4,5].includes(process.argv.length)) throw new Error('usage: catalog-replays.cjs ROOT NEW_OUTPUT [SPLIT_PLAN]');
    const plan=process.argv[4] ? JSON.parse(fs.readFileSync(process.argv[4],'utf8')) : undefined;
    console.log(JSON.stringify(catalog(process.argv[2],process.argv[3],plan),null,2));
  } catch(error) {console.error('Catalog failed: '+error.message);process.exitCode=1;}
}
module.exports={classify,catalog};
