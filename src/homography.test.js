const {solveHomography, cssMatrix, project, quadOk} = require('./homography.js');
let fail = 0;
const near = (a,b,t=1e-6) => Math.abs(a-b) < t;

function check(name, w, h, pts){
  const m = solveHomography(w, h, pts);
  if (!m){ console.log('FAIL', name, 'no solution'); fail++; return; }
  const src = [[0,0],[w,0],[w,h],[0,h]];
  let worst = 0;
  src.forEach((s,i) => {
    const [u,v] = project(m, s[0], s[1]);
    worst = Math.max(worst, Math.abs(u-pts[i][0]), Math.abs(v-pts[i][1]));
  });
  const ok = worst < 1e-6;
  if (!ok) fail++;
  console.log((ok?'ok  ':'FAIL') + '  ' + name.padEnd(34) + ' max corner error ' + worst.toExponential(2));
}

// 1. identity: square-on, the case that breaks an un-pivoted solver
check('square on (identity)', 100, 60, [[0,0],[100,0],[100,60],[0,60]]);
// 2. pure translation + scale
check('translated and scaled', 100, 60, [[20,10],[220,10],[220,130],[20,130]]);
// 3. a real off-axis TV: far edge shorter than the near edge
check('keystone, far edge shorter', 480, 270, [[610,140],[990,152],[988,352],[608,338]]);
// 4. strong perspective
check('strong perspective', 200, 120, [[0,0],[300,60],[280,300],[30,220]]);
// 5. degenerate: three collinear points must return null, not nonsense
const bad = solveHomography(100, 60, [[0,0],[50,0],[100,0],[0,60]]);
console.log((bad === null ? 'ok  ' : 'FAIL') + '  ' + 'collinear points rejected'.padEnd(34));
if (bad !== null) fail++;

// 6. the CSS string is well formed and has 16 finite numbers
const s = cssMatrix(480, 270, [[610,140],[990,152],[988,352],[608,338]]);
const nums = s.slice('matrix3d('.length, -1).split(',').map(Number);
const okc = nums.length === 16 && nums.every(Number.isFinite);
console.log((okc?'ok  ':'FAIL') + '  ' + 'css matrix3d well formed'.padEnd(34) + ' ' + nums.length + ' terms');
if (!okc) fail++;


// 7. bowtie must be rejected
const bow = solveHomography(100,60,[[0,0],[100,0],[0,60],[100,60]]);
console.log((bow===null?'ok  ':'FAIL')+'  '+'bowtie rejected'.padEnd(34)); if(bow!==null) fail++;
// 8. counter-clockwise winding must be rejected, not silently mirrored
const ccw = solveHomography(100,60,[[0,60],[100,60],[100,0],[0,0]]);
console.log((ccw===null?'ok  ':'FAIL')+'  '+'reversed winding rejected'.padEnd(34)); if(ccw!==null) fail++;
// 9. a tiny quad still solves (no accidental absolute-size threshold)
check('tiny 6px quad', 480, 270, [[100,100],[106,100],[106,104],[100,104]]);

console.log(fail ? '\n' + fail + ' FAILED' : '\nall passed');
process.exit(fail ? 1 : 0);
