// Real curated replay; no fabricated replay-event fixtures.
const test = require('node:test');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const path = require('node:path');
const {inspect} = require('./inspect-settings.cjs');
const replay = path.resolve(__dirname,'../../recordings/examples/Game_20260622T203533.slp');

function keys(value, output=[]) {
  if (value && typeof value === 'object') for (const [key,item] of Object.entries(value)) {
    output.push(key);keys(item,output);
  }
  return output;
}

test('setup projection excludes accounts, original input values and later state', () => {
  const setup = inspect(replay);
  assert.equal(setup.stage,31);
  assert.deepEqual(setup.players.map(p=>[p.port,p.character,p.costume]),[[0,2,2],[1,20,3]]);
  assert(setup.codes.some(c=>c.address===0x8016e510));
  assert(!('supplied_initial_state' in setup));
  const forbidden = new Set(['pre','post','frames','joystickX','joystickY','buttons','positionX','positionY',
    'displayName','connectCode','nametag','netplayName','metadata']);
  assert(!keys(setup).some(k=>forbidden.has(k)));
});

test('explicit supplied-state projection exposes only the two startup boundaries', () => {
  const setup = inspect(replay,true);
  assert.deepEqual(setup.supplied_initial_state.map(s=>s.frame),[-123,-40]);
  assert(!keys(setup).some(k=>['pre','post','buttons','joystickX','joystickY'].includes(k)));
  assert.equal(setup.supplied_initial_state[0].players[0].x, -38.79999923706055);
});

test('timer lookup uses settings without input/state exports and rejects invalid bounds', () => {
  const tool=path.join(__dirname,'export-timers.cjs');
  const table=JSON.parse(execFileSync(process.execPath,[tool,replay,'2'],{encoding:'utf8',stdio:['ignore','pipe','pipe']}));
  assert.deepEqual(table,{'0':'08:00.00','1':'07:59.99','2':'07:59.98'});
  for (const bound of ['-1','1.5','1801']) {
    assert.throws(()=>execFileSync(process.execPath,[tool,replay,bound],{stdio:'pipe'}));
  }
});
