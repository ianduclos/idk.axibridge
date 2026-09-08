const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const context={globalThis};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'vendor/polygon-clipping-0.15.7.js'),'utf8'),context);
require('./corner-envelope.js');
