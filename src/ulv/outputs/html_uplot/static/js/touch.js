// Touch pinch-zoom and pan for uPlot, via its plugin/hooks approach —
// uPlot core ships no touch handling. Self-authored, derived from the
// zoom-touch demo in the pinned uPlot release (MIT; provenance
// recorded in the generator's VENDORED.md).
//
// Gestures act on the x scale only (y stays autoscaled, matching the
// mouse drag-zoom): one finger pans, two fingers pinch-zoom around
// the pinch midpoint. The CSS on the chart area sets
// `touch-action: pan-y`, so vertical page scrolling stays native.
// `onRange(min, max)` fires once per gesture end so the caller can
// persist the final range.

export function touchPlugin({ onRange } = {}) {
  function init(u) {
    const over = u.over;
    let rect = null;
    // gesture start: x positions (px) and the scale range at start
    let startX = 0;
    let startDist = 1;
    let startMin = 0;
    let startMax = 0;
    let startMidVal = 0;
    let startCount = 0;
    let active = false;
    let rafPending = false;
    let nextMin = 0;
    let nextMax = 0;

    function measure(event) {
      const t0 = event.touches[0];
      const x0 = t0.clientX - rect.left;
      if (event.touches.length === 1) {
        return { mid: x0, dist: 1 };
      }
      const x1 = event.touches[1].clientX - rect.left;
      return { mid: (x0 + x1) / 2, dist: Math.max(Math.abs(x1 - x0), 1) };
    }

    function apply() {
      rafPending = false;
      u.setScale("x", { min: nextMin, max: nextMax });
    }

    // Capture the gesture baseline: midpoint, finger spread, the scale
    // range, and the value under the midpoint. Re-run whenever the
    // finger count changes so a finger added or lifted mid-gesture stays
    // continuous instead of jumping.
    function capture(event) {
      rect = over.getBoundingClientRect();
      const { mid, dist } = measure(event);
      startX = mid;
      startDist = dist;
      startMin = u.scales.x.min;
      startMax = u.scales.x.max;
      startMidVal = u.posToVal(mid, "x");
      startCount = event.touches.length;
      // a tap with no move must not report a range change
      nextMin = startMin;
      nextMax = startMax;
    }

    function touchstart(event) {
      capture(event);
      active = true;
    }

    function touchmove(event) {
      if (!active) {
        return;
      }
      if (event.touches.length > 1) {
        // the browser must not treat a pinch as page zoom
        event.preventDefault();
      }
      if (event.touches.length !== startCount) {
        // a finger was added or lifted mid-gesture: re-baseline so the
        // scale stays continuous. Without this, lifting one finger of a
        // pinch keeps startDist at the two-finger spread while measure()
        // reports dist:1, exploding the range ~200× into the URL hash.
        capture(event);
        return;
      }
      if (startMax === startMin) {
        // a collapsed x-scale (single distinct revision) has no range to
        // pinch or pan; bail before frac would divide 0/0 into NaN.
        return;
      }
      const { mid, dist } = measure(event);
      const range = (startMax - startMin) * (startDist / dist);
      // keep the value under the gesture midpoint fixed while the
      // range scales, then pan by the midpoint's movement
      const frac = (startMidVal - startMin) / (startMax - startMin);
      let min = startMidVal - frac * range;
      min -= (mid - startX) * (range / u.over.clientWidth);
      nextMin = min;
      nextMax = min + range;
      if (!rafPending) {
        rafPending = true;
        requestAnimationFrame(apply);
      }
    }

    function touchend(event) {
      if (!active || event.touches.length > 0) {
        return;
      }
      active = false;
      if ((nextMin !== startMin || nextMax !== startMax) && onRange) {
        onRange(nextMin, nextMax);
      }
    }

    over.addEventListener("touchstart", touchstart, { passive: true });
    over.addEventListener("touchmove", touchmove, { passive: false });
    over.addEventListener("touchend", touchend, { passive: true });
    over.addEventListener("touchcancel", touchend, { passive: true });
  }

  return { hooks: { init } };
}
