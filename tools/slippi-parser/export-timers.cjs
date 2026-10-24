// Clock lookup from supplied settings only; never export source inputs/posts.
const fs = require('node:fs');
const { SlippiGame, frameToGameTimer } = require('@slippi/slippi-js/node');
try {
  const last = Number(process.argv[3]);
  if (process.argv.length !== 4 || !Number.isInteger(last) || last < 0 || last > 28800)
    throw new Error('usage: export-timers.cjs REPLAY LAST_FRAME (0..28800)');
  const settings = new SlippiGame(fs.readFileSync(process.argv[2])).getSettings();
  if (!settings || settings.timerType !== 2) throw new Error('countdown settings required');
  const timers = {};
  for (let i=0;i<=last;i++) timers[i]=frameToGameTimer(i,{timerType:settings.timerType,
    startingTimerSeconds:settings.startingTimerSeconds});
  console.log(JSON.stringify(timers));
} catch (e) { console.error(`Timer export failed: ${e.message}`); process.exitCode=1; }
