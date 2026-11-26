/** Whether the particle overlay redraws this frame: always, unless the system asks for reduced motion, then only when something changed. */
export function shouldDraw(s: { reduced: boolean; dirty: boolean; repaint: boolean }): boolean {
  return !s.reduced || s.dirty || s.repaint;
}
