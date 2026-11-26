/**
 * A reader of the glyph file of the map's lettering (public/glyphs/<stack>/<range>.pbf), shared by the tests that need the advance of a
 * character: a small varint walker, no dependency.
 */
import assert from 'node:assert/strict';

// The layout: fontstack { 1 name, 2 range, 3 glyph { 1 id, 2 bitmap, 3 width, 4 height, 5 left, 6 top, 7 advance } }
export function decode(buf) {
  let p = 0;
  const varint = () => {
    let r = 0;
    let shift = 0;
    for (;;) {
      const b = buf[p++];
      r += (b & 127) * 2 ** shift;
      if (!(b & 128)) return r;
      shift += 7;
    }
  };
  const zigzag = (n) => (n % 2 ? -(n + 1) / 2 : n / 2);
  const fields = (end, onField) => {
    while (p < end) {
      const tag = varint();
      const wire = tag & 7;
      if (wire === 0) onField(tag >> 3, varint());
      else if (wire === 2) {
        const len = varint();
        onField(tag >> 3, [p, p + len]);
        p += len;
      } else throw new Error(`unexpected wire type ${wire}`);
    }
  };
  const out = { name: null, range: null, glyphs: new Map() };
  fields(buf.length, (f, [s, e]) => {
    assert.equal(f, 1, 'the file holds one fontstack');
    const after = p;
    p = s;
    fields(e, (f2, v) => {
      if (f2 === 1) out.name = buf.toString('utf8', v[0], v[1]);
      else if (f2 === 2) out.range = buf.toString('utf8', v[0], v[1]);
      else if (f2 === 3) {
        const g = { bitmap: null };
        const inner = p;
        p = v[0];
        fields(v[1], (f3, x) => {
          if (f3 === 2) g.bitmap = buf.subarray(x[0], x[1]);
          else g[{ 1: 'id', 3: 'width', 4: 'height', 5: 'left', 6: 'top', 7: 'advance' }[f3]] = f3 === 5 || f3 === 6 ? zigzag(x) : x;
        });
        p = inner;
        out.glyphs.set(g.id, g);
      } else throw new Error(`unexpected fontstack field ${f2}`);
    });
    p = after;
  });
  return out;
}
