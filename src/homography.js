/* Mapping a rectangle onto four points in a photograph.

   This is what makes the room page AR rather than a picture with buttons floating over
   it. The source picker does not hover in front of the television; it lies *on* the
   screen, in the screen's own plane, at whatever angle the camera happened to catch it.
   Same for the panel that opens on the light fixture, and for the tint layer that has to
   sit exactly inside the strip's diffuser and nowhere else.

   You cannot do this with rotate and skew. A rectangle photographed off-axis becomes a
   general quadrilateral: its opposite edges are not parallel, because the far edge is
   further away. That is a projective transform, and the only CSS that can express one is
   matrix3d with the perspective terms filled in.

   So: solve the homography that carries the element's own box onto the four points, and
   emit it. Then a plain absolutely-positioned div, with normal text and normal buttons
   inside it, lands on the real object.

   This file is the reference copy and is what the test runs against. index.html carries
   the same two functions inline, because the app is one file that fetches nothing.
*/

/* Solve for the 3x3 homography taking (0,0),(w,0),(w,h),(0,h) to the four given points.

   Eight unknowns, eight equations, one linear solve. Written out rather than pulled from
   a library for the usual reason: this has to run inside a single self-contained page
   with no network, and it is forty lines.

   Points must be given clockwise from the top left *as the object appears in the photo*.
   quadOk enforces that, for the reasons written above it. */

/* A quadrilateral is the projective image of a rectangle exactly when it is convex and
   has area, so that is what gets checked, and it is checked on the points rather than on
   the algebra. Three points in a line still give a solvable eight-by-eight system whose
   answer is a singular matrix, so watching the elimination pivots does not catch it: the
   solve succeeds and the element collapses to a line on screen with no error anywhere.

   Signs are compared rather than just tested for zero, which catches two bugs for the
   price of one. Mixed signs mean the points cross over into a bowtie. All-negative means
   the points are wound the wrong way round, and since the source rectangle is clockwise
   in screen coordinates, that renders a mirror image: text backwards, controls reversed,
   and nothing that looks like an error. */
function quadOk(pts){
  let sign = 0;
  for (let i = 0; i < 4; i++){
    const [ax, ay] = pts[i];
    const [bx, by] = pts[(i + 1) % 4];
    const [cx, cy] = pts[(i + 2) % 4];
    const cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx);
    if (Math.abs(cross) < 1e-9) return false;          // a corner that is not a corner
    const s = Math.sign(cross);
    if (sign === 0) sign = s;
    else if (s !== sign) return false;                 // bowtie
  }
  return sign > 0;                                     // clockwise, matching the source
}

function solveHomography(w, h, pts){
  if (!pts || pts.length !== 4 || !quadOk(pts)) return null;
  const src = [[0,0],[w,0],[w,h],[0,h]];
  const A = [], b = [];
  for (let i = 0; i < 4; i++){
    const [x, y] = src[i];
    const [u, v] = pts[i];
    A.push([x, y, 1, 0, 0, 0, -x*u, -y*u]); b.push(u);
    A.push([0, 0, 0, x, y, 1, -x*v, -y*v]); b.push(v);
  }

  /* Gaussian elimination with partial pivoting. Pivoting is not optional here: an
     object photographed square-on gives a matrix with zeros exactly where the naive
     algorithm wants to divide, so the un-pivoted version fails on the easiest case. */
  const n = 8;
  for (let col = 0; col < n; col++){
    let best = col;
    for (let r = col + 1; r < n; r++){
      if (Math.abs(A[r][col]) > Math.abs(A[best][col])) best = r;
    }
    if (Math.abs(A[best][col]) < 1e-12) return null;   // degenerate: three points in a line
    if (best !== col){
      [A[col], A[best]] = [A[best], A[col]];
      [b[col], b[best]] = [b[best], b[col]];
    }
    const p = A[col][col];
    for (let r = 0; r < n; r++){
      if (r === col) continue;
      const f = A[r][col] / p;
      if (!f) continue;
      for (let c = col; c < n; c++) A[r][c] -= f * A[col][c];
      b[r] -= f * b[col];
    }
  }
  return b.map((v, i) => v / A[i][i]);   // [a,b,c,d,e,f,g,h]
}

/* CSS matrix3d is column-major, and the two perspective terms live in the fourth row of
   each of the first two columns rather than anywhere you would guess. Getting this wrong
   produces something that looks nearly right at small angles and visibly wrong at large
   ones, which is the worst way for it to be wrong. */
function cssMatrix(w, h, pts){
  const m = solveHomography(w, h, pts);
  if (!m) return null;
  const [a, bb, c, d, e, f, g, hh] = m;
  return 'matrix3d(' + [
    a,  d,  0, g,
    bb, e,  0, hh,
    0,  0,  1, 0,
    c,  f,  0, 1,
  ].map(v => +v.toFixed(6)).join(',') + ')';
}

/* Apply the homography by hand, so the test can check where a corner actually lands
   rather than trusting the algebra. */
function project(m, x, y){
  const [a, b, c, d, e, f, g, h] = m;
  const w = g*x + h*y + 1;
  return [(a*x + b*y + c) / w, (d*x + e*y + f) / w];
}

if (typeof module !== 'undefined') module.exports = {solveHomography, cssMatrix, project, quadOk};
