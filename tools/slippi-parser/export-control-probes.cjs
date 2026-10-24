// Parse real native-generated probe recordings in one pinned-parser process.
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {exportTraining}=require('./export-training.cjs');
function main(){
  assert.equal(process.argv.length,3,'usage: export-control-probes.cjs MANIFEST');
  const file=path.resolve(process.argv[2]), manifest=JSON.parse(fs.readFileSync(file,'utf8'));
  assert.equal(manifest.kind,'native-pad-probe-manifest');
  const probes={};
  for(const probe of manifest.probes){
    assert(!Object.hasOwn(probes,probe.name),'duplicate probe name');
    probes[probe.name]=exportTraining(path.resolve(path.dirname(file),probe.replay),probe.first,probe.last);
  }
  console.log(JSON.stringify({schema:1,kind:'native-pad-probe-labels',parser:'@slippi/slippi-js@9.1.3',probes}));
}
try{main();}catch(error){console.error('Control probe export failed: '+error.message);process.exitCode=1;}
