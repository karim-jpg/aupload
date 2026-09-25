#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ecg_extract_v7.py — v6 + the EINTHOVEN ARBITER.

v7 keeps v6's behaviour and adds one thing: the limb-lead identities are now a
first-class DECISION MAKER instead of a 12x1-only score nudge.

    III = II - I      aVR = -(I+II)/2      aVL = I - II/2      aVF = II - I/2

These are EXACT for any genuine 12-lead recording, so - unlike coverage, jump,
duration or the aVR-polarity heuristic - a WRONG layout or a swapped row/col
convention CANNOT satisfy them by accident.  That makes them the strongest
available arbiter between competing candidates.

Where they are testable (a test needs all its leads to share ONE time window):

  * 12x1             all six limb leads share the one 10 s time base
                     (all four identities testable)
  * 6x2 "col"        the left column holds all six limb leads and rows 0-2
                     ARE simultaneous (measured III = II - I at r = 0.98 on
                     800px-1.png), so all four identities are testable
  * 4x3 "col"        column 0 = I,II,III,aVR  -> III = II - I and aVR = -(I+II)/2
  * 3x4 "col" (GE)   column 0 = I,II,III      -> III = II - I
                     column 1 = aVR,aVL,aVF   -> aVR = -(aVL + aVF)
                     (each column is ONE simultaneous 2.5 s snapshot)
  * any "row"        rows are sequential strips -> no shared window, the
                     identity is NOT testable (polarity heuristic still used)

The rule is DERIVED, not hard-coded: an identity is testable iff all of its
leads land in the same column under the tested convention.

Used three ways:
  (a) score x1.10 when limb >= 0.80 (identities confirmed) and x0.70 when
      limb <= 0.30 (anti-correlated -> the naming is definitely wrong).  An
      INCONCLUSIVE result (0.30 .. 0.80) deliberately does NOT touch the score:
      a test that carries no information must not change the ranking.
  (b) the winner's lead-order convention is taken straight from the limb result
      when it is decisive, before falling back to the polarity heuristic
  (c) score / convention / per-identity values go into report["chosen"], so the
      confidence is visible in the console AND machine-readable in report.json

A convention must supply at least MIN_LIMB_CHECKS (=2) identities before it may
arbitrate: one correlated triple can pass by accident (V4/V5/V6 reach r = 0.91
on 1000_F_711187533 without being I/II/III at all).

MEASURED on the sample images (so future changes have a baseline):
  800px-1.png         6x2   col -> 0.92 over FIVE identities; this CONFIRMS the
                                    column lead order that v6 only guessed from
                                    aVR/II/V1 polarity (III=II-I r = 0.94)
  ecg_1.jpg           3x4   col -> 0.58  inconclusive (polarity fallback)
  1000_F_711187533    3x4   col -> 0.61  inconclusive
  Hay-Block-2         4x3   col -> 0.53  inconclusive
  Ab1OndesTinversees  3x4   col -> 0.50  inconclusive
So the arbiter is DECISIVE exactly where it should be (a genuine simultaneous
limb group) and silent elsewhere.  Layout choice is intentionally left
UNCHANGED for the inconclusive cases - verified identical to v6 on all six.

WHAT CHANGED vs v4/v5 (driven by the pink-paper "Sequentiell" 6x2 render)
------------------------------------------------------------------------
1. GRID PITCH: v4's comb could lock onto a 2x HARMONIC of the 5 mm grid
   (55 px -> "11 px/mm" on a true 5.8 px/mm render).  That halved every
   duration, made the CORRECT 6x2 layout look "non-standard" and let the
   WRONG 4x3 layout win -> REFUSED with 12/12 valid leads.  v6 prefers the
   FUNDAMENTAL (smallest lag within 90% of the best 6-harmonic comb) and
   also measures the VERTICAL pitch for amplitude (mV) calibration.
2. DURATION CREDIT: cell spans snapping to 2.5/5/10 s = full credit;
   printout dead zones (1.2-2.1 / 2.9-4.4 / 5.9-8.4 s) mean WRONG LAYOUT
   (x0.6); compact-figure spans (<1.2 s) get partial credit + an info
   note, never a refusal.  The CELL (ROI) width is used, not the trace
   extent (labels and margins are part of the cell).
3. HR CROSS-CHECK: v4's secondary HR ran autocorr on the TILED 10 s signal,
   where the strongest period IS the tile length (60/0.91 s = 66 bpm
   artifact).  v6 runs autocorr per RAW strip (fs = px/s) and pools.
4. JUMP METRIC: the old threshold (0.10 x strip height) counted steep QRS
   slopes as jumps on small-row renders; it is now a PHYSICAL slope limit
   (~2 mm per mm of paper) that real QRS never exceeds.
5. AMPLITUDE: signal_mv.npz stores the 12 leads in mV at 500 Hz (gain
   --gain, default 10 mm/mV) next to the z-scored signal_12x5000.npy.
6. TILING: tiles are joined with a 40 ms linear crossfade (no seam steps
   that feed downstream detectors fake "QRS" at the joins).
7. BUG FIX: density_ratio UnboundLocalError when some strips have no
   signal (v5 crashed with --layout 6x2 on a 10/12-valid image).
8. REPORT: per-strip detail (cov / jump / valid / signal px) and a
   coverage-within-trace check, so geometry issues are visible without
   opening the debug PNGs.

WHAT CHANGED vs v3 (driven by the two real-image failures)
----------------------------------------------------------
1. LAYOUT:  v3's threshold row-banding merged rows on real printouts (found 5 rows
   where 6 exist, offset bands, contaminated strips).  v4 searches the STANDARD
   layouts (6x2, 4x3, 3x4, 12x1, +detected-with-rhythm) and snaps each row band
   to the periodic row-core centers (projection profile + least-squares pitch fit).
   The (strategy x layout) pair with the best quality score wins.
2. AMPLITUDE: v3 followed the binary mask run MIDPOINT -> flat-topped, "squared"
   QRS and clipped R-peaks ("un peu coupe en dessus").  v4 follows the trace with
   an INTENSITY-WEIGHTED SUB-PIXEL CENTROID (soft ink weights + anti-aliased halo),
   so peak tips and steep slopes keep their true position.
3. DETREND:  v3 subtracted a short moving average (creates baseline steps and
   squared-off complexes).  v4 subtracts a running MEDIAN baseline (~0.9 s window)
   and smooths with a small Gaussian - morphology (P/QRS/T) is preserved.
4. HR:       v3 compared single-lead autocorr vs single-lead R-peaks and got
   56 vs 88 bpm on a ~70 bpm ECG.  v4 computes the R-peak HR on several leads
   (II, aVF, V1, V5, I) with RR-outlier pruning, takes the cross-lead MEDIAN,
   and cross-checks with comb-refined autocorrelation.
5. INK MAP:  new separation strategy F_ink_map  ink = darkness x (1 - redness)
   targets BLACK ink on ANY grid color (red/pink/blue/green).  It is the
   algorithmic answer to "should we recolor the black trace?": instead of
   recoloring the photo we compute a trace-likelihood score and render it as a
   pseudo-color image (debug_1b_inkmap.png) where the trace is bright and the
   grid/text are dim.
6. TIME:     strip duration is measured from the SIGNAL extent (calibration pulse
   excluded) and snapped to 2.5/5/10 s (tolerance 15%) before tiling to 10 s.
   Tiling REPEATS the strip (no time dilation), so heart rate is preserved.

SAFETY GATE (unchanged philosophy)
----------------------------------
Coverage / valid strips / cross-lead rhythm consistency / HR range / layout
sanity must all pass, else the extractor REFUSES (usable=False, no signal file).
Garbage in -> refused, never a confident hallucinated diagnosis.

USAGE
-----
  python ecg_extract_v6.py 800px-1.png [-o ecg_out] [--gain 10]
       [--layout auto|6x2|4x3|3x4|12x1] [--strategy auto|A|B|C|D|E|F]
       [--paper-speed 25] [--px-per-mm 0] [--strip-sec 2.5]
       [--lead-order row|col] [--min-valid 10] [--min-coverage 0.55]
       [--force] [--no-debug]

Integration (drop-in for ecg_analyzer.py):

  from ecg_extract_v6 import extract_full
  ecg, report = extract_full(image_path, out_dir="ecg_out")
  if not report["usable"]:
      print("REFUSED:", "; ".join(report["reasons"]))   # -> do NOT call ECGFounder
  else:
      model(ecg)   # ecg: float32 (1, 12, 5000), z-scored per lead, 10 s @ 500 Hz
      # next: np.save'd to <out_dir>/signal_12x5000.npy

Exit codes: 0 = usable, 2 = refused, 1 = error.
"""
import argparse
import json
import math
import os
import sys

import cv2
import numpy as np

EPS = 1e-9
LEAD_NAMES = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
HR_LEADS = ["II", "aVF", "V1", "V5", "I"]     # cross-lead HR estimation
STD_LAYOUTS = [(6, 2), (4, 3), (3, 4), (12, 1)]


# --------------------------------------------------------------------------
# small utilities
# --------------------------------------------------------------------------
def _odd(n):
    n = int(n)
    return n + 1 if n % 2 == 0 else n


def autocorr(x):
    x = np.asarray(x, np.float64)
    x = x - x.mean()
    if x.size < 4:
        return np.zeros(2)
    ac = np.correlate(x, x, "full")[x.size - 1:]
    return ac / (ac[0] + EPS)


def local_maxima(ac, lo, hi):
    """Indices/heights of local maxima of ac in [lo, hi] (inclusive)."""
    lo = max(1, int(lo))
    hi = min(len(ac) - 2, int(hi))
    if hi - lo < 2:
        return []
    seg = ac[lo:hi + 1]
    out = []
    for i in range(1, len(seg) - 1):
        if seg[i] > seg[i - 1] and seg[i] >= seg[i + 1]:
            out.append((lo + i, float(seg[i])))
    return out


def parabolic(ac, i):
    """Sub-sample peak refinement."""
    i = int(i)
    if 0 < i < len(ac) - 1:
        a, b, c = ac[i - 1], ac[i], ac[i + 1]
        d = a - 2 * b + c
        if abs(d) > EPS:
            return i + 0.5 * (a - c) / d
    return float(i)


def medfilt3(y):
    """3-wide median filter: removes single-pixel salt noise, keeps apexes."""
    y = np.asarray(y, np.float64)
    if y.size < 3:
        return y.copy()
    pad = np.concatenate([[y[0]], y, [y[-1]]])
    w = np.lib.stride_tricks.sliding_window_view(pad, 3)
    return np.median(w, axis=1)


def gaussian_smooth1d(y, sigma):
    """Small Gaussian smoothing that preserves QRS sharpness."""
    y = np.asarray(y, np.float64)
    if sigma < 0.5 or y.size < 5:
        return y.copy()
    r = int(math.ceil(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    pad = np.concatenate([np.full(r, y[0]), y, np.full(r, y[-1])])
    return np.convolve(pad, k, mode="valid")


def running_median(y, win):
    """Running median with edge replication (robust baseline, keeps P/QRS/T)."""
    y = np.asarray(y, np.float64)
    win = _odd(max(3, int(win)))
    if y.size < 5 or win < 3:
        return y.copy()
    r = win // 2
    pad = np.concatenate([np.full(r, y[0]), y, np.full(r, y[-1])])
    w = np.lib.stride_tricks.sliding_window_view(pad, win)
    return np.median(w, axis=1)


def pearson(a, b):
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    if a.size < 3:
        return 0.0
    a = a - a.mean()
    b = b - b.mean()
    den = (np.sqrt((a * a).sum()) * np.sqrt((b * b).sum())) + EPS
    return float((a * b).sum() / den)


def limb_consistency(non_rhythm):
    """Einthoven/Goldberger check: III≈II-I etc. Only meaningful for
    simultaneous (12x1) layouts where all leads share the same time base.
    Returns 0..1 (0.5 = uncorrelated, 1 = perfect) or None if not computable.
    Sequential printouts (3x4/6x2/4x3) are time-multiplexed -> return None."""
    by = {s["name"]: s.get("yv") for s in non_rhythm if s.get("yv") is not None}
    need = ["I", "II", "III", "aVR", "aVL", "aVF"]
    if not all(k in by for k in need):
        return None
    try:
        ml = min(by[k].size for k in need)
        if ml < 30:
            return None

        def _rs(a):
            return np.interp(np.linspace(0, 1, ml), np.linspace(0, 1, a.size), a)

        def _zs(a):
            a = np.asarray(a, np.float64)
            return (a - a.mean()) / (a.std() + 1e-9)

        I, II, III, aVR, aVL, aVF = [_rs(by[k]) for k in need]
        I, II, III, aVR, aVL, aVF = map(_zs, [I, II, III, aVR, aVL, aVF])
        c1 = pearson(III, _zs(II - I))
        c2 = pearson(aVR, _zs(-(I + II) * 0.5))
        c3 = pearson(aVL, _zs(I - II * 0.5))
        c4 = pearson(aVF, _zs(II - I * 0.5))
        avg = float(np.mean([c1, c2, c3, c4]))
        return float(np.clip((avg + 1.0) * 0.5, 0.0, 1.0))
    except Exception:
        return None


# --------------------------------------------------------------------------
# v7: Einthoven / Goldberger arbiter (geometry-based, convention-aware)
# --------------------------------------------------------------------------
# Exact identities that hold for ANY real 12-lead ECG.  A candidate can be
# tested only where the leads involved share one time window (see module
# docstring); each check below carries that requirement implicitly because all
# of its leads are looked up in the SAME column of the tested convention.
LIMB_CHECKS = (
    ("III=II-I", "III", {"II": 1.0, "I": -1.0}),
    ("aVR=-(I+II)/2", "aVR", {"I": -0.5, "II": -0.5}),
    ("aVL=I-II/2", "aVL", {"I": 1.0, "II": -0.5}),
    ("aVF=II-I/2", "aVF", {"II": 1.0, "I": -0.5}),
    # equivalent to aVR + aVL + aVF = 0; this is the ONLY self-contained check
    # for an augmented-lead triple, so it is what makes the classic 3x4 column 1
    # (aVR, aVL, aVF) testable at all
    ("aVR=-(aVL+aVF)", "aVR", {"aVL": -1.0, "aVF": -1.0}),
)

# A convention needs at least this many independent identities before it may
# arbitrate; one correlated triple can pass by accident (e.g. V4/V5/V6 reach
# r=0.91 on 1000_F_711187533 without being I/II/III at all).
MIN_LIMB_CHECKS = 2
LIMB_STRONG = 0.80      # identities confirmed -> promote / decide lead order
LIMB_DEAD = 0.30        # anti-correlated      -> naming is definitely wrong


def _names_from_cells(cells, rows, cols, conv):
    """lead name -> signal, DERIVED from (row, col) geometry for one wiring
    convention.  Names are never read from s["name"], so this is independent
    of whatever order the strips were built with."""
    out = {}
    for (r, c), yv in cells.items():
        if yv is None:
            continue
        idx = (r * cols + c) if conv == "row" else (c * rows + r)
        if 0 <= idx < 12:
            out[LEAD_NAMES[idx]] = yv
    return out


def _limb_checks_for(rows, cols, conv):
    """Identities that are physically testable for this layout + convention.

    A check is only valid where ALL of its leads share ONE column, i.e. one
    simultaneous time window.  Deriving that from the convention instead of
    hard-coding layouts generalises the arbiter for free (measured on the real
    sample images, see the module docstring):

      12x1  col/row -> all four checks  (every limb lead on one time base)
      6x2   col     -> all four checks  (left column holds all six limb leads,
                                         and rows 0-2 really are simultaneous:
                                         III=II-I measured r=0.98 on 800px-1)
      4x3   col     -> III=II-I (col 0) and aVR=-(I+II)/2 (col 0)
      3x4   col     -> III=II-I (col 0) and aVR=-(aVL+aVF) (col 1) [GE classic]
      any   row     -> none             (rows are sequential strips)
    """
    if rows <= 0 or cols <= 0:
        return []

    def rc(nm):
        i = LEAD_NAMES.index(nm)
        return (i // cols, i % cols) if conv == "row" else (i % rows, i // rows)

    out = []
    for desc, tgt, preds in LIMB_CHECKS:
        ccols = {rc(tgt)[1]} | {rc(n)[1] for n in preds}
        if len(ccols) == 1:
            out.append((desc, tgt, preds))
    return out


def limb_algebra(strips, rows, cols, conv):
    """(score 0..1, [(name, score), ...]) for one layout + convention.

    0.5 = untestable or uncorrelated (a wrong assignment lands near 0.5; an
    anti-correlated one near 0.0; a correct one near 1.0).
    """
    cells = {(s["row"], s["col"]): s.get("yv")
             for s in strips if not s.get("rhythm")}
    sig = _names_from_cells(cells, rows, cols, conv)
    scores = []
    for desc, tgt, preds in _limb_checks_for(rows, cols, conv):
        need = [tgt] + list(preds)
        if not all(n in sig for n in need):
            continue
        try:
            ml = min(sig[n].size for n in need)
            if ml < 30:
                continue
            z = {}
            for n in need:
                a = np.interp(np.linspace(0, 1, ml),
                              np.linspace(0, 1, sig[n].size),
                              np.asarray(sig[n], np.float64))
                z[n] = (a - a.mean()) / (a.std() + 1e-9)
            pred = sum(w * z[n] for n, w in preds.items())
            r = pearson(z[tgt], pred)
            scores.append((desc, float(np.clip((r + 1.0) * 0.5, 0.0, 1.0))))
        except Exception:
            continue
    if not scores:
        return None, []
    return float(np.mean([sc for _, sc in scores])), scores


def limb_best_conv(strips):
    """(score, conv, detail) - best over the row/col wiring conventions.

    Returns (None, None, []) when no identity is testable for this layout.
    """
    geo = [(s["row"], s["col"]) for s in strips if not s.get("rhythm")]
    if not geo:
        return None, None, []
    rows = max(r for r, _ in geo) + 1
    cols = max(c for _, c in geo) + 1
    best = (None, None, [])
    for conv in ("col", "row"):
        sc, det = limb_algebra(strips, rows, cols, conv)
        if sc is None or len(det) < MIN_LIMB_CHECKS:
            continue
        if best[0] is None or sc > best[0]:
            best = (sc, conv, det)
    return best


# --------------------------------------------------------------------------
# image diagnostics
# --------------------------------------------------------------------------
def diagnose(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    S = hsv[..., 1].astype(int)
    V = hsv[..., 2].astype(int)
    colored = float(((S >= 60) & (V >= 90)).mean())
    dark = float((V <= 80).mean())
    grid = _grid_mask(img)
    return dict(
        size="%dx%d" % (img.shape[1], img.shape[0]),
        colored_fraction=round(colored, 3),
        very_dark_fraction=round(dark, 4),
        saturation_median=int(np.median(S)),
        value_median=int(np.median(V)),
        red_grid_fraction=round(float(grid.mean()), 3),
    )


# --------------------------------------------------------------------------
# strategy masks + soft ink maps
# --------------------------------------------------------------------------
def _otsu_inv(ch, domain=None):
    ch8 = ch.astype(np.uint8)
    ch8 = cv2.GaussianBlur(ch8, (5, 5), 0)
    if domain is not None:
        ch8 = np.where(domain, ch8, 255).astype(np.uint8)
    _, m = cv2.threshold(ch8, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if domain is not None:
        m = (m > 0) & domain
    return m.astype(np.uint8) * 255


def ink_map(img):
    """Soft trace-likelihood in [0, 1]: darkness x (1 - redness).

    Black ink scores high whatever the grid color is (red/pink/blue/green/gray):
      red grid (200, 80, 80) -> redness 1 -> ink ~ 0
      black trace ( 60, 60, 60) -> redness 0, darkness high -> ink high
      paper (245,240,240)     -> ink ~ 0
    This is the principled version of "recolor the black so we can target it".
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    V = hsv[..., 2].astype(np.float64)
    b = img[..., 0].astype(np.float64)
    g = img[..., 1].astype(np.float64)
    r = img[..., 2].astype(np.float64)
    darkness = 1.0 - V / 255.0
    redness = np.clip((r - np.maximum(g, b)) / 48.0, 0.0, 1.0)
    ink = darkness * (1.0 - redness)
    return cv2.GaussianBlur(ink.astype(np.float32), (5, 5), 0)


def build_strategy_masks(img):
    """Returns (masks, cand_frac): binary masks per strategy + candidate fraction."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    S = hsv[..., 1]
    V = hsv[..., 2]
    b = img[..., 0].astype(int)
    g = img[..., 1].astype(int)
    r = img[..., 2].astype(int)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    masks = {}
    # A: the old v2 rule (baseline for comparison)
    masks["A_black_strict"] = ((S <= 100) & (V <= 80)).astype(np.uint8) * 255
    # B: non-colored pixels, then Otsu on Value
    masks["B_desat_otsu"] = _otsu_inv(V, domain=(S <= 45))
    # C: Otsu on grayscale minus strongly-red pixels
    g_otsu = _otsu_inv(gray)
    notred = ~(((r - b) >= 40) & (S >= 60))
    masks["C_gray_otsu_notred"] = ((g_otsu > 0) & notred).astype(np.uint8) * 255
    # D: blue-dominant dark ink
    blue = (b - r >= 25) & (b - g >= 15) & (V <= 200)
    if blue.sum() < 200:
        masks["D_blue_ink"] = np.zeros_like(gray)
    else:
        masks["D_blue_ink"] = _otsu_inv(V, domain=blue)
    # E: local adaptive threshold (grayscale photocopies)
    bw = _odd(max(11, int(min(img.shape[:2]) / 28)))
    masks["E_adaptive_gray"] = cv2.adaptiveThreshold(
        cv2.GaussianBlur(gray, (5, 5), 0), 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, bw, 14)
    # F: the ink map (darkness x not-red) -> Otsu on the soft score
    ink = ink_map(img)
    ink8 = (np.clip(ink, 0, 1) * 255).astype(np.uint8)
    _, mf = cv2.threshold(ink8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    masks["F_ink_map"] = mf
    cand = {k: float((m > 0).mean()) for k, m in masks.items()}
    return masks, cand


# --------------------------------------------------------------------------
# mask cleaning: deskew, grid-line removal, closing, speck removal
# --------------------------------------------------------------------------
def remove_straight_lines(mask, w, h):
    """Remove long straight runs (grid lines) while keeping the trace.

    Horizontal SE = 0.30*W : flat ECG baselines are far shorter than grid lines.
    Vertical   SE = 0.60*H : tall R waves are far shorter than page-spanning lines.
    """
    Lh = max(40, int(0.30 * w))
    Lv = max(40, int(0.60 * h))
    mh = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                          cv2.getStructuringElement(cv2.MORPH_RECT, (Lh, 1)))
    mv = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                          cv2.getStructuringElement(cv2.MORPH_RECT, (1, Lv)))
    lines = cv2.bitwise_or(mh, mv)
    return cv2.bitwise_and(mask, cv2.bitwise_not(lines))


def deskew_for_lines(mask):
    """Rotate so horizontal structures align with rows (max row-profile variance)."""
    h, w = mask.shape
    best_ang, best_v = 0.0, -1.0
    for ang in np.arange(-1.75, 1.76, 0.25):
        M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), ang, 1.0)
        m2 = cv2.warpAffine(mask, M, (w, h), flags=cv2.INTER_NEAREST)
        v = float(m2.sum(axis=1).astype(np.float64).var())
        if v > best_v:
            best_v, best_ang = v, ang
    if abs(best_ang) < 0.2:
        return mask, 0.0
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), best_ang, 1.0)
    return cv2.warpAffine(mask, M, (w, h), flags=cv2.INTER_NEAREST), float(best_ang)


def clean_mask(mask, w, h, deskew=False):
    m = mask.copy()
    ang = 0.0
    if deskew:
        m, ang = deskew_for_lines(m)
    m = remove_straight_lines(m, w, h)
    if ang:
        M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), -ang, 1.0)
        m = cv2.warpAffine(m, M, (w, h), flags=cv2.INTER_NEAREST)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    # drop specks AND solid blocks (the 1 mV calibration pulses, stamps, dots)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    min_area = max(10, int(w * h / 40000))
    keep = np.zeros(m.shape, bool)
    for i in range(1, n):
        cw = stats[i, cv2.CC_STAT_WIDTH]
        area = stats[i, cv2.CC_STAT_AREA]
        fill = area / max(cw * stats[i, cv2.CC_STAT_HEIGHT], 1)
        if area < min_area:
            continue
        if fill > 0.55 and 10 <= cw <= 0.12 * w:   # filled rectangle = cal pulse
            continue
        keep |= lab == i
    return keep.astype(np.uint8) * 255


# --------------------------------------------------------------------------
# layout: row bands + column gaps
# --------------------------------------------------------------------------
def _row_profile(mask, k=None):
    h = mask.shape[0]
    prof = mask.sum(axis=1).astype(np.float64)
    if k is None:
        k = _odd(max(3, h // 200))
    if k > 1:
        prof = np.convolve(prof, np.ones(k) / k, mode="same")
    return prof


def detect_row_bands(mask):
    """Coarse horizontal bands containing the lead traces (v3 heuristic).

    Used only to get the trace VERTICAL EXTENT and a rhythm-strip candidate:
    precise band edges are re-snapped to row cores by snap_bands_to_cores().
    """
    h = mask.shape[0]
    prof = _row_profile(mask)
    pos = prof[prof > 0]
    if pos.size < 10:
        return []
    thr_hi = 0.20 * pos.mean()
    floor = 0.06 * pos.mean()
    on = prof > thr_hi
    bands = []
    y = 0
    while y < h:
        if on[y]:
            y0 = y
            while y < h and on[y]:
                y += 1
            bands.append([y0, y])
        else:
            y += 1
    if not bands:
        return []
    for bnd in bands:
        while bnd[0] > 0 and prof[bnd[0] - 1] > floor:
            bnd[0] -= 1
        while bnd[1] < h and prof[bnd[1]] > floor:
            bnd[1] += 1
    bands.sort()
    merged = [bands[0]]
    for b in bands[1:]:
        if b[0] <= merged[-1][1] + 2:
            merged[-1][1] = max(merged[-1][1], b[1])
        else:
            merged.append(list(b))
    medh = float(np.median([b[1] - b[0] for b in merged]))
    out = [b for b in merged if (b[1] - b[0]) >= 0.5 * medh]
    out.sort(key=lambda b: b[0])
    return [tuple(b) for b in out]


def snap_bands_to_cores(prof, y0, y1, rows):
    """Row bands snapped to the periodic row-core centers of the projection.

    1. row PITCH from the autocorrelation of the profile inside [y0, y1]
       (the 6 periodic trace rows are the strongest periodic feature)
    2. anchor = strongest core in the extent
    3. each predicted center a + k*pitch is refined to the nearest local
       maximum within +/- 25% of the pitch (NON-overlapping windows, unlike
       per-band argmax which re-claims the previous row's peak)
    4. periodic least-squares refit, bands = a + (k +/- 0.5) * pitch
    """
    h = prof.size
    y0 = max(0, int(y0))
    y1 = min(h, int(y1))
    span = y1 - y0
    if span < rows * 4:
        return [(int(y0 + i * span / rows),
                 int(y0 + (i + 1) * span / rows)) for i in range(rows)]
    pitch0 = span / rows
    # -- 1) pitch from the profile autocorrelation -------------------------
    seg = prof[y0:y1].astype(np.float64)
    seg = seg - seg.mean()
    pitch = pitch0
    if seg.size > 8:
        ac = np.correlate(seg, seg, "full")[seg.size - 1:]
        if ac.size > 3 and ac[0] > 0:
            ac = ac / ac[0]
            lmx = local_maxima(ac, max(3, int(0.55 * pitch0)),
                               min(len(ac) - 2, int(1.45 * pitch0)))
            if lmx:
                pitch_ac = float(max(lmx, key=lambda t: t[1])[0])
                if 0.7 * pitch0 <= pitch_ac <= 1.35 * pitch0:
                    pitch = pitch_ac
    # -- 2) anchor = strongest core, with its ROW INDEX --------------------
    a = y0 + int(np.argmax(prof[y0:y1]))
    a_val = float(prof[a])
    k0 = int(np.clip(round((a - (y0 + pitch0 / 2.0)) / pitch0), 0, rows - 1))
    # -- 3) snap each predicted center (non-overlapping windows) ----------
    centers = []
    for k in range(rows):
        pred = a + (k - k0) * pitch
        if k == k0:
            centers.append(a)
            continue
        lo = max(0, int(pred - 0.25 * pitch))
        hi = min(h, int(pred + 0.25 * pitch) + 1)
        if hi - lo < 2 or float(prof[lo:hi].max()) < 0.30 * a_val:
            centers.append(int(round(pred)))      # trust the periodic prediction
        else:
            centers.append(lo + int(np.argmax(prof[lo:hi])))
    # -- 4) periodic refit --------------------------------------------------
    ks = np.arange(rows, dtype=np.float64)
    c = np.asarray(centers, np.float64)
    try:
        A = np.polyfit(ks, c, 1)
        pitch_f, a_f = float(A[0]), float(A[1])
    except Exception:
        pitch_f, a_f = pitch, float(a)
    resid = float(np.median(np.abs(c - (a_f + ks * pitch_f))))
    if not (0.7 * pitch0 <= pitch_f <= 1.35 * pitch0) or resid > 0.25 * pitch0:
        pitch_f, a_f = pitch, float(a)
    bands = []
    for k in range(rows):
        top = a_f + k * pitch_f - pitch_f / 2.0
        bot = a_f + k * pitch_f + pitch_f / 2.0
        bands.append((int(max(0, min(h - 1, round(top)))),
                      int(max(1, min(h, round(bot))))))
    return bands


def detect_columns(mask, bands, exclude_last=False):
    """Split the trace region into columns at blank vertical gaps."""
    h, w = mask.shape[:2]
    occ = np.zeros(w, bool)
    for (y0, y1) in bands:
        y0, y1 = max(0, y0), min(h, y1)
        occ |= mask[y0:y1, :].any(axis=0)
    on = occ
    gaps = []
    x = 0
    while x < w:
        if not on[x]:
            x0 = x
            while x < w and not on[x]:
                x += 1
            gaps.append((x0, x))
        else:
            x += 1
    if not gaps:
        return 0, [], w
    min_gap = max(5, int(0.006 * w))
    interior = [gp for gp in gaps if 0 < gp[0] and gp[1] < w and (gp[1] - gp[0]) >= min_gap]
    x_start = 0
    x_end = w
    if gaps[0][0] == 0 and gaps[0][1] - gaps[0][0] >= min_gap:
        x_start = gaps[0][1]
    if gaps[-1][1] >= w and gaps[-1][1] - gaps[-1][0] >= min_gap:
        x_end = gaps[-1][0]
    splits = [int((gp[0] + gp[1]) / 2) for gp in interior
              if x_start < (gp[0] + gp[1]) / 2 < x_end]
    return int(x_start), splits, int(x_end)


def build_strips(mask_shape, bands, x_start, splits, x_end, lead_order="row"):
    """Strips from explicit bands + column edges; handles a full-width rhythm band."""
    h, w = mask_shape
    strips = []
    rhythm_band = None
    core = bands
    if len(bands) >= 2:
        heights = [b[1] - b[0] for b in bands[:-1]]
        medh = float(np.median(heights)) if heights else 0
        if medh > 0 and (bands[-1][1] - bands[-1][0]) >= 1.8 * medh:
            rhythm_band = bands[-1]
            core = bands[:-1]
    edges = [x_start] + list(splits) + [x_end]
    edges = [e for e in edges if 0 <= e <= w]
    if len(edges) < 2:
        edges = [0, w]
    cols = len(edges) - 1
    for i, (y0, y1) in enumerate(core):
        for j in range(cols):
            strips.append(dict(y0=int(y0), y1=int(y1), x0=int(edges[j]),
                               x1=int(edges[j + 1]), row=i, col=j, rhythm=False))
    if rhythm_band is not None:
        strips.append(dict(y0=int(rhythm_band[0]), y1=int(rhythm_band[1]),
                           x0=0, x1=w, row=len(core), col=0, rhythm=True))
    non_rhythm = [s for s in strips if not s["rhythm"]]
    rows, cols_ = len(core), cols
    for k, s in enumerate(non_rhythm):
        if lead_order == "row":
            idx = s["row"] * cols_ + s["col"]
        else:
            idx = s["col"] * rows + s["row"]
        s["name"] = LEAD_NAMES[idx] if idx < 12 else "S%d" % (k + 1)
    for s in strips:
        if s["rhythm"]:
            s["name"] = "II_rhythm"
    return strips


def uniform_strips(shape, rows, cols, lead_order, x_start, x_end, y0, y1, snapped,
                   edges=None):
    h, w = shape
    bands = snapped if snapped else [
        (int(y0 + i * (y1 - y0) / rows), int(y0 + (i + 1) * (y1 - y0) / rows))
        for i in range(rows)]
    if not edges or len(edges) != cols + 1:
        edges = [int(x_start + j * (x_end - x_start) / cols) for j in range(cols + 1)]
    return build_strips((h, w), bands, edges[0], edges[1:-1], edges[-1],
                        lead_order=lead_order)


# --------------------------------------------------------------------------
# per-strip cleaning + SUB-PIXEL trace following
# --------------------------------------------------------------------------
def clean_strip(mask, st):
    """Keep only trace-like components inside a strip ROI (drops labels/text)."""
    y0, y1, x0, x1 = st["y0"], st["y1"], st["x0"], st["x1"]
    y0, y1 = max(0, y0), min(mask.shape[0], y1)
    x0, x1 = max(0, x0), min(mask.shape[1], x1)
    crop = mask[y0:y1, x0:x1]
    if crop.size == 0:
        return np.zeros((1, 1), np.uint8), 0.0
    sw = max(2, crop.shape[1])
    sh = max(2, crop.shape[0])
    n, lab, stats, _ = cv2.connectedComponentsWithStats(crop, 8)
    keep = np.zeros(crop.shape, bool)
    for i in range(1, n):
        cw = stats[i, cv2.CC_STAT_WIDTH]
        ch = stats[i, cv2.CC_STAT_HEIGHT]
        area = stats[i, cv2.CC_STAT_AREA]
        fill = area / max(cw * ch, 1)
        if area < 20:
            continue
        if fill > 0.5 and cw < 0.10 * sw:        # calibration pulse / solid marks
            continue
        if cw < 0.16 * sw and ch < 0.45 * sh:    # text glyphs
            continue
        keep |= lab == i
    cov = float(keep.any(axis=0).mean())
    return keep.astype(np.uint8) * 255, cov


def _norm_ink(Wcrop):
    """Per-strip ink normalization: paper -> 0, trace core -> 1.

    A washed photo has compressed contrast (paper ink 0.25, trace 0.6); without
    this normalization the centroid averages as much PAPER as trace and R
    peaks turn into smooth hills.  Normalizing per strip restores separation.
    """
    Wc = Wcrop.astype(np.float64)
    bg = float(np.percentile(Wc, 60))          # paper-dominated
    dark = float(np.percentile(Wc, 5))         # trace core
    if bg - dark < 0.02:
        dark = float(Wc.min())
        bg = float(Wc.max())
    if bg - dark < 1e-6:
        return np.zeros_like(Wc)
    return np.clip((bg - Wc) / (bg - dark), 0.0, 1.0)


def extract_strip_signal(strip_mask, W, px_mm=None):
    """Column-by-column trace following with SUB-PIXEL weighted centroid.

    For each column: vertical runs of the (vertically dilated) mask; the run
    closest to the previous position is followed (continuity).  Inside the run
    +/- halo the position is the ink-weighted centroid (weights = normalized
    ink squared) -> anti-aliased peak tips count, paper does not.
    Sustained tall runs = solid blocks (1 mV calibration pulses) -> skipped.
    Returns (signal_px, used_mask, heights, jump_frac).
    """
    h, w = strip_mask.shape[:2]
    W = _norm_ink(W)
    dil = int(np.clip(round(h / 30.0), 2, 6))
    m = cv2.dilate(strip_mask, np.ones((2 * dil + 1, 1), np.uint8), iterations=1)
    signal = np.full(w, np.nan)
    used = np.zeros((h, w), bool)
    heights = np.zeros(w, np.int32)
    # start following at the most occupied row (the baseline), not the center
    occupancy = m.sum(axis=1)
    init_y = float(np.argmax(occupancy)) if occupancy.max() > 0 else h / 2.0
    prev = init_y
    for x in range(w):
        ys = np.where(m[:, x] > 0)[0]
        if ys.size == 0:
            continue
        brk = np.where(np.diff(ys) > 1)[0]
        starts = np.concatenate([[0], brk + 1])
        ends = np.concatenate([brk, [ys.size - 1]])
        centers = (ys[starts] + ys[ends]) / 2.0
        ci = int(np.argmin(np.abs(centers - prev)))
        ya, yb = int(ys[starts[ci]]), int(ys[ends[ci]])
        # the dilated mask's run already spans the anti-aliased shoulders; the
        # NORMALIZED ink weights (paper -> 0) pin the centroid to the stroke
        # core, so R-peak tips are recovered WITHOUT a variable-size halo
        # (a per-column adaptive extent would add sub-pixel jitter)
        a, b = ya, yb
        wcol = W[a:b + 1, x].astype(np.float64) ** 2
        seg = m[a:b + 1, x] > 0
        if wcol.sum() > EPS:
            centroid = float((np.arange(a, b + 1) * wcol).sum() / wcol.sum())
        else:
            centroid = (ya + yb) / 2.0
        # centroid must stay within the (halo-extended) run
        if not (a - 0.5 <= centroid <= b + 0.5):
            centroid = (ya + yb) / 2.0
        signal[x] = centroid
        heights[x] = b - a + 1
        used[a:b + 1, x] = seg | (wcol > 0.10)
        prev = centroid
    # kill sustained tall blocks (calibration pulses): tall for >= 5 columns,
    # plus a margin around the block (the pulse's steep EDGES survive the
    # tall-run rule as isolated spikes and would masquerade as R peaks)
    # NOTE: np.convolve(mode="same") returns max(len(a), len(k)) entries, so
    # this is only safe when the strip is wider than the kernels (a v4 crash
    # on sub-17-px strips from exotic layout candidates).
    tall = (heights > max(10, 0.30 * h)).astype(np.int8)
    if tall.any() and w >= 21:
        sus = np.convolve(tall, np.ones(5, np.int32), mode="same") >= 5
        kill = np.convolve(sus.astype(np.int32), np.ones(17, np.int32),
                           mode="same") > 0          # +/- 8 columns of margin
        for x in np.where(kill & (heights > 0))[0]:
            signal[x] = np.nan
            used[:, x] = False
    # isolated single-column spikes (taller than any legit steep QRS stroke)
    spike = (heights > max(14, 0.45 * h)) & np.isfinite(signal)
    for x in np.where(spike)[0]:
        signal[x] = np.nan
        used[:, x] = False
    # jump fraction: columns where the followed position leaps (wrong layout /
    # trace follower crossing into another lead's line).  Legit QRS slopes are
    # steep but stay below ~10% of the strip height per column.
    ok = np.where(np.isfinite(signal))[0]
    jump = 0.0
    if ok.size > 10:
        d = np.abs(np.diff(signal[ok]))
        # PHYSICAL slope limit: a steep-but-real QRS rises ~10 mm over ~20 mm
        # of paper (~0.5 mm/mm, up to ~2 mm/mm in ventricular rhythms); a hop
        # onto another lead's trace is a 15+ px instantaneous leap.  The old
        # 0.10*h rule flagged genuine QRS slopes on small-row renders.
        thr = max(6.0, 2.0 * px_mm) if (px_mm and px_mm > 0) else max(6.0, 0.10 * h)
        jump = float((d > thr).mean())
    return signal, used, heights, jump


def strip_to_signal(strip_mask, W, px_mm=None):
    """Full per-strip signal: follow, interpolate, flip, smooth, median-detrend."""
    h, w = strip_mask.shape[0], strip_mask.shape[1]
    sig, used, _, jump = extract_strip_signal(strip_mask, W, px_mm=px_mm)
    finite = np.where(np.isfinite(sig))[0]
    if finite.size < max(30, 0.25 * w):
        return None, used, 0.0, jump
    a, b = int(finite[0]), int(finite[-1])
    cov = float(finite.size) / max(1, w)         # coverage over the FULL strip width
    y = sig[a:b + 1]
    nan = np.isnan(y)
    if (~nan).sum() < 4:
        return None, used, cov, jump
    y = np.interp(np.arange(y.size), np.where(~nan)[0], y[~nan])
    yv = (h - 1.0) - y                           # flip: up = positive
    yv = gaussian_smooth1d(yv, sigma=max(1.0, w / 300.0))
    yv = medfilt3(yv)                           # salt-noise removal, keeps apexes
    # running-MEDIAN baseline (window ~ 1 beat) - no morphology distortion
    yv = yv - running_median(yv, win=max(31, int(0.55 * w)))
    # trim a LEADING transient (calibration-pulse edge / follower lock-on):
    # a big excursion inside the first ~5% followed by a stable in-band run is
    # never a real beat (the first real beat sits after a TP segment)
    med = float(np.median(yv))
    rob = float(np.percentile(yv, 95) - np.percentile(yv, 5))
    if rob > 0:
        n_edge = max(12, int(0.05 * yv.size))
        edge = yv[:n_edge]
        if np.any(np.abs(edge - med) > 0.8 * rob):
            for i0 in range(0, n_edge):
                win = yv[i0:i0 + 12]
                if win.size == 12 and np.all(np.abs(win - med) < 0.5 * rob):
                    yv = yv[i0:]
                    cov *= float(yv.size) / max(1, float(b - a + 1))
                    break
    return yv, used, cov, jump


# --------------------------------------------------------------------------
# time calibration from the paper grid
# --------------------------------------------------------------------------
def _grid_mask(img, strict=False):
    """Pink/red ECG-paper grid pixels (works down to heavily washed photos).

    strict=True keeps only clearly-saturated line cores; used for the
    contamination metric: on pink-paper renders the halo around a followed
    trace is pinkish PAPER, and the sensitive mask would count it as grid.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    b = img[..., 0].astype(int)
    r = img[..., 2].astype(int)
    smin, vmin, rb = (40, 120, 25) if strict else (25, 90, 12)
    return (((H <= 28) | (H >= 150)) & (S >= smin) & (V >= vmin) & ((r - b) >= rb))


def _comb6(ac, n, lag):
    """6-harmonic comb score: ac(L)+.6ac(2L)+.35ac(3L)+.25ac(4L)+.18ac(5L)+.12ac(6L)."""
    s = 0.0
    for mult, wgt in ((1, 1.0), (2, 0.6), (3, 0.35), (4, 0.25), (5, 0.18), (6, 0.12)):
        idx = int(round(lag * mult))
        if idx < n:
            s += wgt * ac[idx]
    return s


def detect_grid_pitch(img):
    """px/mm from the periodic pink/red grid (autocorr of the line profiles).

    v4 could lock onto a 2x harmonic of the 5 mm grid: a 55 px peak
    ("10 mm" -> 11 px/mm) beat the true 29 px 5 mm period on real renders,
    halving every duration.  v6 prefers the FUNDAMENTAL: among the peaks
    whose 6-harmonic comb is within 90% of the best, the SMALLEST lag wins
    (harmonics of the true period comb nearly as high, but are larger).
    The VERTICAL pitch (row profile) is measured too, for mV calibration.
    """
    grid = _grid_mask(img)
    frac = float(grid.mean())
    if frac < 0.005 or frac > 0.6:
        return None
    out = dict(px_per_mm=None, px_per_mm_y=None, fundamental_px=0,
               grid_fraction=round(frac, 3))
    for axis, key in ((0, "px_per_mm"), (1, "px_per_mm_y")):
        prof = grid.sum(axis=axis).astype(np.float64)
        prof = prof - prof.mean()
        ac = autocorr(prof)
        n = len(ac)
        lmx = local_maxima(ac, 5, min(100, n // 3))
        if not lmx:
            continue
        scored = [(_comb6(ac, n, t[0]), t[0]) for t in lmx]
        best_comb = max(s for s, _ in scored)
        elig = [L for s, L in scored if s >= 0.90 * best_comb]
        L = int(min(elig)) if elig else int(max(scored, key=lambda t: t[0])[1])
        # NO half-period halving: with the fundamental preference above it is
        # redundant, and it corrupted real 5 mm periods (29 px -> "14.5 px 1
        # mm") whenever the sub-line-width aliasing left ac[L/2] moderately
        # high.  The L<15 -> 1 mm / L>=15 -> 5 mm interpretation already
        # handles both dense and sparse grids.
        ppm = float(L) if L < 15 else L / 5.0
        if 2.5 <= ppm <= 30:
            out[key] = round(ppm, 2)
            if key == "px_per_mm":
                out["fundamental_px"] = int(L)
    if out["px_per_mm"] is None:
        return None
    if out["px_per_mm_y"] is None:
        out["px_per_mm_y"] = out["px_per_mm"]        # square-grid fallback
    return out


# --------------------------------------------------------------------------
# resampling / tiling to (1, 12, 5000)
# --------------------------------------------------------------------------
def _tile_crossfade(s, target_len, xf):
    """Repeat s up to target_len, blending xf samples at every join.

    A hard seam creates a step edge whose slew looks like a QRS to downstream
    detectors; a 40 ms linear crossfade removes it without shifting beats.
    """
    out = np.asarray(s, np.float64)
    src = np.asarray(s, np.float64)
    while out.size < target_len:
        if xf > 0 and out.size > xf and src.size > 2 * xf:
            ramp = np.linspace(0.0, 1.0, xf)
            out = np.concatenate([out[:-xf],
                                  out[-xf:] * (1.0 - ramp) + src[:xf] * ramp,
                                  src[xf:]])
        else:
            out = np.concatenate([out, src])
    return out[:target_len]


def to_ecg_array(signals_px, px_per_sec, target_hz=500, target_len=5000,
                 px_per_mm_y=None, gain=10.0):
    """Resample to target_hz, tile to target_len with crossfades, z-score.

    Returns (ecg_z, ecg_mv):
      ecg_z  float32 (1, 12, target_len), z-scored per lead  -> ECGFounder
      ecg_mv same signal in mV (px / (px_per_mm_y * gain)) or None if the
             vertical calibration is unknown
    """
    raw = []
    for yv in signals_px:
        n1 = max(2, int(round(yv.size / px_per_sec * target_hz)))
        x_old = np.linspace(0.0, 1.0, yv.size)
        s = np.interp(np.linspace(0.0, 1.0, n1), x_old, yv)
        if n1 < target_len:
            xf = int(max(4, min(0.04 * target_hz, n1 // 4)))
            s = _tile_crossfade(s, target_len, xf)      # tile, do NOT stretch
        else:
            s = s[:target_len]                          # crop
        raw.append(s)
    arr = np.stack(raw).astype(np.float32)
    ecg_mv = None
    if px_per_mm_y and px_per_mm_y > 0:
        ecg_mv = (arr / float(px_per_mm_y * gain))[np.newaxis].astype(np.float32)
    arr = (arr - arr.mean(axis=1, keepdims=True)) / (arr.std(axis=1, keepdims=True) + 1e-8)
    return arr[np.newaxis], ecg_mv


# --------------------------------------------------------------------------
# rhythm / R-peaks / PR measurements
# --------------------------------------------------------------------------
def rhythm_hr(sig, fs, lo_s=0.33, hi_s=2.0):
    """Comb-refined autocorrelation HR: score lag L by ac(L)+ac(2L)+ac(3L)."""
    ac = autocorr(sig)
    lo, hi = int(lo_s * fs), int(hi_s * fs)
    lmx = local_maxima(ac, lo, min(hi, len(ac) - 2))
    if not lmx:
        return 0.0, None
    best, best_v = None, -1.0
    n = len(ac)
    for lag, val in lmx:
        score = val
        for mult, wgt in ((2, 0.6), (3, 0.35)):
            idx = int(round(lag * mult))
            if idx < n:
                score += wgt * ac[idx]
        if score > best_v:
            best_v, best = score, lag
    if best is None or ac[best] < 0.10:
        return float(ac[best]) if best is not None else 0.0, None
    lagf = parabolic(ac, best)
    hr = 60.0 * fs / lagf
    if not (15.0 <= hr <= 250.0):
        return float(ac[best]), None
    return float(ac[best]), float(hr)


def detect_r_peaks(sig, fs=500, seam_period=None):
    """Pan-Tompkins-lite: 3.5-25 Hz bandpass (FFT), derivative^2, envelope, peaks.

    Peaks within +/-40 samples of a tiling seam are rejected.  RR intervals
    that deviate wildly from the median (double detections / misses) are pruned
    by hr_from_peaks, not here.
    """
    x = np.asarray(sig, np.float64)
    x = x - x.mean()
    n = x.size
    if n < int(fs):
        return []
    Xf = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    Xf[(freqs < 5.0) | (freqs > 25.0)] = 0      # 5-25 Hz: QRS slew, not smooth T/P
    y = np.fft.irfft(Xf, n)
    sq = np.diff(y) ** 2
    w = max(3, int(0.06 * fs))
    env = np.convolve(sq, np.ones(w) / w, mode="same")
    mx = float(env.max())
    if mx <= 0:
        return []
    thr = 0.4 * mx
    refr = int(0.28 * fs)
    cands = []
    last = -refr
    for i in range(1, n - 1):
        if env[i] >= thr and env[i] >= env[i - 1] and env[i] > env[i + 1] and (i - last) >= refr:
            if seam_period and ((i % seam_period) < 40 or (i % seam_period) > seam_period - 40):
                continue
            cands.append(i)
            last = i
    if not cands:
        return []
    # amplitude discrimination: refine each candidate to the local max of the
    # bandpassed signal and drop deflections far below the dominant ones
    # (P waves / seam kinks masquerading as R peaks).  Sign-agnostic: inverted
    # leads (aVR) produce dominant NEGATIVE deflections.
    amps = []
    refined = []
    for i in cands:
        lo, hi = max(0, i - int(0.06 * fs)), min(n, i + int(0.06 * fs) + 1)
        j = lo + int(np.argmax(np.abs(y[lo:hi])))
        refined.append(j)
        amps.append(abs(float(y[j])))
    amps = np.asarray(amps)
    top = float(np.median(np.sort(amps)[-min(4, amps.size):])) if amps.size else 0.0
    peaks = [p for p, a_ in zip(refined, amps) if a_ >= 0.5 * top]
    # re-enforce the refractory after refinement
    out = []
    for p in peaks:
        if out and (p - out[-1]) < refr:
            continue
        out.append(int(p))
    return out


def hr_from_peaks(peaks, fs=500):
    """Median-RR HR with one round of RR outlier pruning (robust to FP doubles)."""
    if len(peaks) < 2:
        return None, None
    rr = np.diff(np.asarray(peaks)) / fs
    for _ in range(2):
        m = float(np.median(rr))
        if m <= 0:
            return None, None
        ok = (rr >= 0.55 * m) & (rr <= 1.9 * m)
        if ok.sum() < 2:
            break
        rr = rr[ok]
    if rr.size < 2:
        return None, None
    hr = 60.0 / float(np.median(rr))
    if not (20.0 <= hr <= 250.0):
        return None, None
    return float(hr), float(np.median(rr))


def prune_peaks(peaks, fs=500):
    """Keep only beats whose RR intervals are consistent with the median RR.

    Drops double-detections and seam / calibration-pulse artifacts BEFORE they
    can pollute a beat template or an HR estimate.
    """
    if len(peaks) < 3:
        return list(peaks)
    rr = np.diff(np.asarray(peaks)) / fs
    m = float(np.median(rr))
    if m <= 0:
        return list(peaks)
    ok = np.concatenate([[True], (rr >= 0.55 * m) & (rr <= 1.9 * m)])
    # also drop a peak if the interval AFTER it is an outlier
    rr_after = np.concatenate([rr, [m]])
    ok2 = (rr_after >= 0.55 * m) & (rr_after <= 1.9 * m)
    ok = ok & ok2
    return [p for p, k in zip(peaks, ok) if k]


def estimate_pr(sig, peaks, fs=500):
    """Rough PR interval from the averaged beat template (P peak -> R peak).

    Indicative only (+/- 40 ms): sufficient to flag 1AVB (PR > 200 ms).
    Beats with inconsistent RR are pruned before templating.
    """
    peaks = prune_peaks(peaks, fs)
    if len(peaks) < 2:
        return None
    w0, w1 = int(0.55 * fs), int(0.20 * fs)
    tmpl = np.zeros(w0 + w1)
    cnt = 0
    for p in peaks:
        a, b = p - w0, p + w1
        if a < 0 or b > len(sig):
            continue
        tmpl += sig[a:b]
        cnt += 1
    if cnt < 2:
        return None
    tmpl /= cnt
    i0 = w0 - int(0.50 * fs)
    i1 = w0 - int(0.08 * fs)
    if i0 < 0 or i1 - i0 < 3:
        return None
    seg = tmpl[i0:i1]
    noise = tmpl[:max(2, w0 - int(0.50 * fs))]
    nstd = float(np.std(noise)) + 1e-9
    amp = float(seg.max() - np.median(noise))
    if amp < 2.5 * nstd:
        return None
    t_p = -0.50 + float(np.argmax(seg)) / fs
    pr = -t_p
    if 0.06 <= pr <= 0.60:
        return pr - 0.02
    return None


def measure_rhythm_px(strips, pps, fs=500):
    """Pixel-domain beat detection on SINGLE strips (no tiling -> no seams).

    For every lead strip: resample yv to fs, bandpass 5-25 Hz, envelope, then
    classify candidates as QRS by DEFLICTION WIDTH (<= 130 ms) — a huge but
    slow T wave is wide, a sharp R wave is narrow.  RR intervals are pooled
    across ALL leads, so the median RR (and HR) is extremely robust.
    Returns dict(pooled_hr, pooled_rr_s, per_lead=[(name, hr)], beats_total,
                 segs={name: (sig500, beats)}).
    """
    rrs_all = []
    per_lead = []
    segs = {}
    beats_total = 0
    for st in strips:
        yv = st.get("yv")
        if yv is None or yv.size < 40 or not pps:
            continue
        n1 = max(64, int(round(yv.size / pps * fs)))
        sig = np.interp(np.linspace(0, 1, n1), np.linspace(0, 1, yv.size), yv)
        sig = (sig - sig.mean()) / (sig.std() + 1e-9)
        n = sig.size
        # bandpass 5-25 Hz
        Xf = np.fft.rfft(sig)
        freqs = np.fft.rfftfreq(n, 1.0 / fs)
        Xf[(freqs < 5.0) | (freqs > 25.0)] = 0
        y = np.fft.irfft(Xf, n)
        env = np.convolve(np.diff(y) ** 2, np.ones(max(3, int(0.06 * fs))) /
                          max(3, int(0.06 * fs)), mode="same")
        mx = float(env.max())
        if mx <= 0:
            continue
        # candidates: envelope peaks
        refr = int(0.28 * fs)
        cands = []
        last = -refr
        for i in range(1, n - 1):
            if env[i] >= 0.30 * mx and env[i] >= env[i - 1] and env[i] > env[i + 1] \
                    and (i - last) >= refr:
                cands.append(i)
                last = i
        if not cands:
            continue
        # refine + width-classify
        beats = []
        amps = []
        for c in cands:
            lo, hi = max(0, c - int(0.05 * fs)), min(n, c + int(0.05 * fs) + 1)
            j = lo + int(np.argmax(np.abs(y[lo:hi])))
            amps.append(abs(float(y[j])))
            beats.append(j)
        amax = max(amps) if amps else 0.0
        keep = []
        for j, a_ in zip(beats, amps):
            if a_ < 0.25 * amax:
                continue
            # half-height width of |y| around j
            half = 0.5 * a_
            l = j
            while l > 0 and abs(y[l]) > half:
                l -= 1
            r = j
            while r < n - 1 and abs(y[r]) > half:
                r += 1
            if (r - l) <= int(0.13 * fs):
                keep.append(j)
        # re-enforce refractory
        kb = []
        for p in keep:
            if kb and (p - kb[-1]) < refr:
                continue
            kb.append(p)
        segs[st["name"]] = (sig, kb)
        beats_total += len(kb)
        if len(kb) >= 2:
            rr = np.diff(np.asarray(kb)) / fs
            rr = rr[(rr >= 0.30) & (rr <= 2.0)]
            if rr.size:
                rrs_all.extend(rr.tolist())
                per_lead.append((st["name"], round(60.0 / float(np.median(rr)), 1)))
    # pass 2 (de-double): drop beats that follow the previous kept beat by less
    # than ~0.55x the pooled median R-R (double detections, seam kinks)
    if rrs_all:
        m1 = float(np.median(rrs_all))
        if m1 >= 0.50:
            for nm in list(segs.keys()):
                sig, kb = segs[nm]
                if len(kb) < 2:
                    continue
                kb2 = [kb[0]]
                for p in kb[1:]:
                    if (p - kb2[-1]) / fs < 0.55 * m1:
                        continue
                    kb2.append(p)
                segs[nm] = (sig, kb2)
    # pass 3 (T-beat removal): a real R-R gap is ~1x, 2x or 3x the pooled
    # median (2x/3x = a missed beat); a T wave coupled at ~0.7x is neither.
    # Keep only beats whose gap to the previous OR next beat is consistent.
    if rrs_all:
        m2 = float(np.median(rrs_all))

        def _ok_gap(g):
            r = g / m2
            for base in (1.0, 2.0, 3.0):
                if abs(r - base) <= 0.25:
                    return True
            return False

        for nm in list(segs.keys()):
            sig, kb = segs[nm]
            if len(kb) < 2:
                continue
            gaps = np.diff(np.asarray(kb)) / fs
            keep = []
            for i in range(len(kb)):
                gprev = float(gaps[i - 1]) if i > 0 else None
                gnext = float(gaps[i]) if i < len(gaps) else None
                ok = ((gprev is not None and _ok_gap(gprev)) or
                      (gnext is not None and _ok_gap(gnext)))
                keep.append(ok)
            kb2 = [p for p, k in zip(kb, keep) if k]
            segs[nm] = (sig, kb2)
        # re-pool: only single-beat gaps contribute R-R intervals
        rrs_all = []
        per_lead = []
        for nm, (sig, kb) in segs.items():
            if len(kb) >= 2:
                gaps = np.diff(np.asarray(kb)) / fs
                single = [g for g in gaps if 0.70 <= g / m2 <= 1.35]
                if single:
                    rrs_all.extend(single)
                    per_lead.append((nm, round(60.0 / float(np.median(single)), 1)))
        beats_total = sum(len(kb) for kb in
                          (segs[nm][1] for nm in segs))
    out = dict(pooled_hr=None, pooled_rr_s=None, per_lead=per_lead,
               beats_total=beats_total, segs=segs, n_rr=len(rrs_all))
    if len(rrs_all) >= 4:
        rr_med = float(np.median(rrs_all))
        if rr_med > 0:
            out["pooled_rr_s"] = round(rr_med, 3)
            out["pooled_hr"] = round(60.0 / rr_med, 1)
    return out


def estimate_pr_pooled(segs, fs=500, leads=("II", "aVF", "V5", "I", "V4", "V6", "III")):
    """PR interval from a POOLED, R-aligned beat template across P-positive leads.

    A single 2.5 s strip holds only 2-3 beats and the first one is often too
    close to the start for a pre-R window; pooling every usable beat from
    several leads gives enough windows and a cleaner P wave.
    Indicative only (+/- 40 ms): sufficient to flag 1AVB (PR > 200 ms).
    """
    w0, w1 = int(0.55 * fs), int(0.20 * fs)
    # window-local indices (window starts at t = -0.55 s)
    i_pre = (int(0.10 * fs), int(0.20 * fs))     # t in [-0.45, -0.35]: PQ baseline
    i_p0, i_p1 = int(0.20 * fs), int(0.45 * fs)  # t in [-0.35, -0.10]: P search
    i_pq = (int(0.40 * fs), int(0.49 * fs))      # t in [-0.15, -0.06]: flat PQ
    windows = []
    for nm in leads:
        seg = segs.get(nm)
        if seg is None:
            continue
        sig, kb = seg
        for p in kb:
            a, b = p - w0, p + w1
            if a < 0 or b > len(sig):
                continue
            wnd = np.asarray(sig[a:b], np.float64)
            # baseline-align: each lead's z-scored signal sits at its own PQ
            # level; without this the pooled template baseline wanders and
            # buries the P wave
            wnd = wnd - float(np.median(wnd[i_pre[0]:i_pre[1]]))
            # windows keep the per-lead z-scored units (comparable scales);
            # normalizing by QRS amplitude would crush the P-wave SNR
            windows.append(wnd)
    if len(windows) < 2:
        return None
    # robust template: MEDIAN first (a misaligned lead smears a mean), then
    # drop windows that do not correlate with the median shape and re-average
    Wmat = np.stack(windows)
    tmpl = np.median(Wmat, axis=0)
    keep = [wnd for wnd in windows if pearson(wnd, tmpl) >= 0.50]
    if len(keep) >= 2:
        tmpl = np.mean(np.stack(keep), axis=0)
    if i_p1 >= len(tmpl) - 3:
        return None
    seg = np.asarray(tmpl[i_p0:i_p1], np.float64)
    # noise from the FLAT PQ segment after the P wave (the P-search region
    # itself contains the P bump, which inflates its own MAD)
    pq = np.asarray(tmpl[i_pq[0]:i_pq[1]], np.float64)
    if pq.size < 8:
        return None
    pq_med = float(np.median(pq))
    noise = 1.4826 * float(np.median(np.abs(pq - pq_med))) + 1e-9
    med = float(np.median(seg))
    # candidate P peaks: LOCAL maxima clearly above the segment level.  The P
    # wave is the LAST such maximum before the QRS (the previous beat's T tail
    # sits earlier in the window and is not followed by a flat PQ segment).
    lmax = [i for i in range(3, len(seg) - 3)
            if seg[i] > seg[i - 1] and seg[i] >= seg[i + 1]
            and seg[i] == float(seg[max(0, i - 3):i + 4].max())
            and (seg[i] - med) >= 3.0 * noise]
    if not lmax:
        return None
    j = lmax[-1]
    t_p = -0.55 + float(i_p0 + j) / fs
    pr = -t_p
    if 0.06 <= pr <= 0.60:
        return pr - 0.02
    return None


def _negdom(yv):
    """-1..1: negative-dominance of a strip (|S| vs |R| proxy)."""
    if yv is None or yv.size < 30:
        return 0.0
    hi, lo = float(np.percentile(yv, 95)), float(np.percentile(yv, 5))
    if abs(hi) + abs(lo) < 1e-9:
        return 0.0
    return (abs(lo) - abs(hi)) / (abs(lo) + abs(hi))


def auto_lead_order(non_rhythm, rows, cols):
    """'row' or 'col' for 6x2 / 4x3 / 3x4 printouts, from lead POLARITY.

    Two wiring conventions exist and both are common:
      row: 6x2 rows are [I II] [III aVR] [aVL aVF] [V1 V2] ... (pair style)
      col: 6x2 LEFT column I..aVF top-to-bottom, RIGHT column V1..V6
           (Schiller / "Sequentiell" style; 3x4-col = the GE classic)
    Discriminators (aVR is always negative-dominant, II tall-positive,
    V1 S-dominant): returns 'col', 'row', or None when undecided.
    """
    g = {(s["row"], s["col"]): s.get("yv") for s in non_rhythm}

    def nd(rc):
        return _negdom(g.get(rc))

    if (rows, cols) == (6, 2):
        # row: (0,1)=II +, (1,1)=aVR -, (1,0)=III +- ; col: (0,1)=V1 -,
        # (1,0)=II +, (3,0)=aVR -
        fit_row = -2.0 * nd((0, 1)) + 1.0 * nd((1, 1)) - 0.5 * nd((1, 0))
        fit_col = 2.0 * nd((0, 1)) - 1.0 * nd((1, 0)) + 1.0 * nd((3, 0))
    elif (rows, cols) == (4, 3):
        # row: (1,0)=aVR -, (0,1)=II + ; col(GE): (1,0)=II +, (0,1)=aVR -
        fit_row = 2.0 * nd((1, 0)) - 2.0 * nd((0, 1))
        fit_col = -fit_row
    elif (rows, cols) == (3, 4):
        # row: (0,3)=aVR -, (0,1)=II + ; col(GE): (0,3)=V4 +, (0,1)=aVR -,
        # (1,0)=II +
        fit_row = 2.0 * nd((0, 3)) - 2.0 * nd((0, 1))
        fit_col = -2.0 * nd((0, 3)) + 2.0 * nd((0, 1)) - 1.0 * nd((1, 0))
    else:
        return None
    if abs(fit_col - fit_row) < 0.3:
        return None
    return "col" if fit_col > fit_row else "row"


def snap_duration(dur):
    for target in (2.5, 5.0, 10.0):
        if abs(dur - target) / target <= 0.15:
            return target
    return None


def duration_credit(span_s):
    """0..1 credit for a per-lead CELL span at the calibrated px/s.

    1.0   span snaps to a standard printout duration (2.5 / 5 / 10 s)
    0.60  near-standard (within 25% of 2.5/5/10) — lenient for grid error
    0.55  compact figure / cropped thumbnail (>= 0.7 s: >= ~1 beat per lead)
          or a near-standard span just outside the snap window
    0.0   printout DEAD ZONES (1.2-2.1 / 2.9-4.4 / 5.9-8.4 s): no real
          printout shows 1.7 s of a lead -> this layout is WRONG
    0.35  very short (< 0.7 s) or very long (> 11.5 s): unusual, keep going
    """
    if span_s is None or span_s <= 0:
        return 0.5
    if snap_duration(span_s):
        return 1.0
    # lenient near-standard before dead-zone penalty (e.g. 3.02s ≈2.5s with grid error)
    for tgt in (2.5, 5.0, 10.0):
        if abs(span_s - tgt) / tgt <= 0.25:
            return 0.60
    if span_s < 0.7 or span_s > 11.5:
        return 0.35
    if 1.2 <= span_s <= 2.1 or 2.9 <= span_s <= 4.4 or 5.9 <= span_s <= 8.4:
        return 0.0
    return 0.55


# --------------------------------------------------------------------------
# candidate evaluation (per strategy x layout)
# --------------------------------------------------------------------------
def _col_extent(cleaned, det):
    """Column x-extent, ignoring a full-width rhythm band if present."""
    bands = det
    if det and len(det) >= 2:
        heights = [b[1] - b[0] for b in det[:-1]]
        medh = float(np.median(heights)) if heights else 0
        if medh > 0 and (det[-1][1] - det[-1][0]) >= 1.8 * medh:
            bands = det[:-1]
    return detect_columns(cleaned, bands)


def row_count_evidence(prof, y0, y1, rows):
    """Is `rows` the REAL number of trace rows on the page?

    Compare the top-`rows` projection peaks with the NEXT `rows` peaks: if the
    page really has `rows` rows, the next peaks are noise (ratio << 1); if it
    has more rows, they are equally strong traces (ratio ~ 1).  Grid-independent
    layout evidence, catches e.g. 4x3 forced onto a 6x2 printout.
    """
    h = prof.size
    y0, y1 = max(0, int(y0)), min(h, int(y1))
    if y1 - y0 < rows * 4:
        return 0.0
    pitch0 = (y1 - y0) / rows
    cands = [(i, float(prof[i])) for i in range(y0 + 1, y1 - 1)
             if prof[i] >= prof[i - 1] and prof[i] > prof[i + 1]]
    cands.sort(key=lambda t: -t[1])
    kept = []
    for c, v in cands:
        if all(abs(c - kc) >= 0.55 * pitch0 for kc, kv in kept):
            kept.append((c, v))
        if len(kept) >= 2 * rows:
            break
    if len(kept) < rows + 1:
        return 0.0            # no extra cores -> row count plausible
    top = [v for _, v in kept[:rows]]
    nxt = [v for _, v in kept[rows:2 * rows]]
    if not top or not nxt:
        return 0.0
    return float(np.median(nxt)) / max(EPS, float(np.median(top)))


def build_layout_candidates(cleaned, lead_order, fixed_layout=None):
    """[(label, strips, row_evidence), ...]: standard layouts + detected."""
    h, w = cleaned.shape[:2]
    prof = _row_profile(cleaned)
    det = detect_row_bands(cleaned)
    y0, y1 = (det[0][0], det[-1][1]) if det else (0, h)
    # EXTENT FIX: threshold banding merges rows on crisp renders (grid
    # remnants + labels keep the profile above the inter-row floor) and the
    # median-height filter then DROPS the un-merged top row -> the row snap
    # shifts by one and the last band lands on an empty sliver (V5/V6 dead).
    # Expand the extent to cover the STRONG periodic core peaks instead.
    if det:
        vmax = float(prof.max())
        cores = [i for i in range(2, h - 2)
                 if prof[i] >= prof[i - 1] and prof[i] > prof[i + 1]
                 and prof[i] >= 0.45 * vmax]
        if len(cores) >= 2:
            cores.sort()
            dm = float(np.median(np.diff(cores))) if len(cores) > 2 else \
                float(cores[-1] - cores[0])
            pad = 0.55 * dm if dm > 0 else 0.0
            y0 = int(max(0, min(y0, cores[0] - pad)))
            y1 = int(min(h, max(y1, cores[-1] + pad)))
    xs, splits, xe = _col_extent(cleaned, det)
    if xe <= xs:
        xs, xe = 0, w
    # true ROW PITCH: strongest periodic peak of the profile autocorr,
    # preferring the FUNDAMENTAL (smallest strong peak - a 2x harmonic here
    # would invert every band-ratio judgement).
    # A correct layout's bands are ONE row pitch tall; a band ~2 pitches
    # tall is mixing two trace rows (e.g. full-extent 3x4 over a GE 3+3).
    core_pitch = 0.0
    seg = prof[y0:y1].astype(np.float64)
    if seg.size > 30:
        seg = seg - seg.mean()
        acp = np.correlate(seg, seg, "full")[seg.size - 1:]
        if acp.size > 4 and acp[0] > 0:
            acp = acp / acp[0]
            lo = max(8, int((y1 - y0) / 13))
            hi = min(len(acp) - 2, int((y1 - y0) / 3))
            lmx = local_maxima(acp, lo, hi)
            if lmx:
                acmx = max(v for _, v in lmx)
                fund = [p for p, v in lmx if v >= 0.70 * acmx]
                core_pitch = float(min(fund)) if fund else \
                    float(max(lmx, key=lambda t: t[1])[0])
    # column count estimate over the CELL SECTION (top rows): with more
    # than 3 trace rows there may be full-width rhythm rows below, and the
    # whole-image column gaps vanish; the cell section keeps them.  Used to
    # penalize layouts with the wrong number of columns (e.g. 6x2 on a
    # 4-column GE 3+3 printout).
    n_cols_est = 0
    if not fixed_layout and row_count_evidence(prof, y0, y1, 3) > 0.5:
        cy1 = int(y0 + 0.55 * (y1 - y0))
        colprof = cleaned[y0:cy1, :].sum(axis=0).astype(np.float64)
        colprof = colprof - colprof.mean()
        if colprof.size > 60:
            acc = np.correlate(colprof, colprof, "full")[colprof.size - 1:]
            if acc.size > 4 and acc[0] > 0:
                acc = acc / acc[0]
                lo2 = max(int(0.05 * w), 30)
                hi2 = min(len(acc) - 2, int(0.8 * (xe - xs)))
                lmx2 = local_maxima(acc, lo2, hi2)
                if lmx2 and max(v for _, v in lmx2) >= 0.20:
                    amx = max(v for _, v in lmx2)
                    fund2 = [p for p, v in lmx2 if v >= 0.60 * amx]
                    cp2 = int(min(fund2)) if fund2 else 0
                    if cp2 and (xe - xs) > 0.8 * cp2:
                        n_cols_est = int(round((xe - xs) / float(cp2)))
    cands = []
    layouts = [fixed_layout] if fixed_layout else STD_LAYOUTS
    for (rows, cols) in layouts:
        try:
            snapped = snap_bands_to_cores(prof, y0, y1, rows)
        except Exception:
            snapped = None
        label = "%dx%d" % (rows, cols)
        ratio = 0.0 if fixed_layout else row_count_evidence(prof, y0, y1, rows)
        # use DETECTED column edges when their count matches this layout
        edges = None
        if splits and len(splits) == cols - 1:
            edges = [xs] + [int(s) for s in splits] + [xe]
        mism = False    # column-count estimate disabled: on compressed
                        # scans the column profile's periodicity is dominated
                        # by BEAT spacing (R peaks are tall ink columns),
                        # which produced false column counts and penalized
                        # the CORRECT layout.
        cands.append((label, uniform_strips((h, w), rows, cols, lead_order,
                                            xs, xe, y0, y1, snapped,
                                            edges=edges), ratio, core_pitch,
                      mism))
    if not fixed_layout and det and 2 <= len(det) <= 13:
        cands.append(("detected %d rows" % len(det),
                      build_strips((h, w), det, xs, splits, xe, lead_order=lead_order),
                      0.0, core_pitch, False))
    # GE "3+3" family: 12-lead cells (3 rows x 4 cols) on top + full-width
    # rhythm rows (V1/II/V5) below.  The rhythm rows merge the column gaps
    # and poison every full-extent layout, so try the CELL SECTION alone at
    # a few split fractions; snap-to-cores absorbs the rough split.  Added
    # whenever the page has ink beyond 3 rows (they self-demote on plain
    # layouts via the duration dead zone / coverage).
    if not fixed_layout and row_count_evidence(prof, y0, y1, 3) > 0.03:
        for frac in (0.50, 0.58, 0.66):
            cy1 = int(y0 + frac * (y1 - y0))
            if cy1 - y0 < 60:
                continue
            try:
                snapped_c = snap_bands_to_cores(prof, y0, cy1, 3)
            except Exception:
                continue
            cands.append(("3x4top%d" % int(frac * 100),
                          uniform_strips((h, w), 3, 4, lead_order, xs, xe,
                                         y0, cy1, snapped_c), 0.0, core_pitch,
                          False))
    return cands


def evaluate_candidate(cleaned, Wimg, strips, pitch_pps, strip_sec, row_evidence=0.0,
                       px_mm=None, row_pitch=0.0, col_mismatch=False,
                       layout_label=""):
    """Score one (strategy, layout) pair on REAL beat quality.

    The strongest term is the pixel-domain rhythm measurement (pooled R-R
    agreement across lead strips): a candidate whose strips yield consistent
    beat intervals is the correct layout+separation, whatever the coverage.
    """
    h, w = cleaned.shape[:2]
    non_rhythm = [s for s in strips if not s["rhythm"]]
    if not non_rhythm:
        return dict(label="", strips=[], score=0.0, n_leads=0, n_valid=0,
                    mean_cov=0.0, rhythm=0.0, border=1.0, jump=1.0, dur_ok=None)
    n_valid = 0
    covs, borders, widths, jumps, sig_ws = [], [], [], [], []
    best = None
    for st in strips:
        sy0, sy1 = max(0, st["y0"]), min(h, st["y1"])
        sx0, sx1 = max(0, st["x0"]), min(w, st["x1"])
        st["roi"] = (sy0, sy1, sx0, sx1)
        smask, _ = clean_strip(cleaned, st)
        Wcrop = Wimg[sy0:sy1, sx0:sx1]
        if Wcrop.shape != smask.shape[:2]:
            Wcrop = np.zeros(smask.shape[:2], np.float32)
        yv, used, cov, jump = strip_to_signal(smask, Wcrop, px_mm=px_mm)
        # coverage-within-trace: labels/margins legitimately shrink the
        # absolute cov, but holes (follower losing the trace) do not
        cov_rel = (cov * max(1, sx1 - sx0) / yv.size) if yv is not None else 0.0
        st.update(smask=smask, yv=yv, used=used, cov=cov, jump=jump,
                  valid=(yv is not None and
                         (cov >= 0.50 or (cov >= 0.35 and cov_rel >= 0.85))))
        if not st["rhythm"]:
            covs.append(cov)
            widths.append(sx1 - sx0)
            jumps.append(jump if yv is not None else 1.0)
            if yv is not None:
                sig_ws.append(int(yv.size))
            if used.size and used.shape[0] >= 4:
                touch = float((used[:2].any(axis=0) |
                               used[-2:].any(axis=0)).mean())
            else:
                touch = 1.0
            borders.append(touch)
        if st["valid"]:
            n_valid += 1
            if best is None or cov > best[0]:
                best = (cov, yv, st)
    n_leads = len(non_rhythm)
    mean_cov = float(np.mean(covs)) if covs else 0.0
    border = float(np.mean(borders)) if borders else 1.0
    jump = float(np.mean(jumps)) if jumps else 1.0
    rhythm = 0.0
    if best is not None and pitch_pps:
        rhythm, _ = rhythm_hr(best[1], pitch_pps)
    # pixel-domain rhythm quality: pooled R-R intervals, cross-lead agreement,
    # AND the fraction of leads that yield consistent beats (a separation that
    # reads 10/12 leads is better than one that reads 6, whatever the coverage)
    rhy_q = 0.0
    rhy_px = None
    if pitch_pps and n_valid >= 6:
        rhy_px = measure_rhythm_px(non_rhythm, pitch_pps)
        n_rr = rhy_px.get("n_rr", 0)
        per = rhy_px.get("per_lead", [])
        hr_p = rhy_px.get("pooled_hr")
        if n_rr >= 4 and hr_p and len(per) >= 2:
            agree = [abs(hv - hr_p) <= 0.20 * hr_p for _, hv in per]
            frac_agree = float(np.mean(agree)) if agree else 0.0
            frac_leads = min(1.0, len(per) / max(1, n_leads))
            rhy_q = min(1.0, n_rr / 10.0) * (0.5 * frac_agree + 0.5 * frac_leads)
    # duration sanity: a correct layout makes each lead CELL span a standard
    # printout duration (2.5 / 5 / 10 s) at the calibrated px/s.  The CELL
    # (ROI) width is used, not the trace extent: lead labels and margins are
    # part of the cell but the trace starts after them.
    dur_ok = None
    dur_credit = 0.5
    span_roi_s = None
    if pitch_pps and widths:
        span_roi_s = float(np.median(widths)) / pitch_pps
        dur_ok = snap_duration(span_roi_s) is not None
        dur_credit = duration_credit(span_roi_s)
    valid_frac = n_valid / max(1, n_leads)
    score = (0.25 * valid_frac
             + 0.15 * min(1.0, mean_cov / 0.85)
             + 0.10 * min(1.0, rhythm / 0.35)
             + 0.10 * (1.0 - min(1.0, 4.0 * border))
             + 0.10 * (1.0 - min(1.0, jump / 0.12))
             + 0.15 * rhy_q
             + 0.15 * dur_credit)
    if n_valid < 6:
        score *= 0.3
    if n_leads != 12:
        score *= 0.2
    if dur_credit <= 0.0:
        score *= 0.6              # printout dead zone (e.g. 1.7 s per lead)
    if row_evidence > 0.35:             # more/fewer real rows than this layout
        # strong penalty: extra strong row cores below/inside the layout's
        # bands mean the strips are MIXING rows (e.g. full-extent 3x4 on a
        # GE 3+3 printout follows the rhythm rows and looks "great" while
        # every lead is actually a mixture) - the top-section candidate is
        # the correct one there.
        score *= max(0.35, 1.0 - 0.9 * (row_evidence - 0.35))
    # band-height sanity: a correct band is ONE row pitch tall.  A band
    # ~2 pitches tall made the follower lock onto a single trace inside a
    # two-row mixture (high coverage, no jumps, WRONG lead - it looks great
    # to every other metric).
    band_ratio = None
    if row_pitch and row_pitch > 4 and non_rhythm:
        bh = float(np.median([s["y1"] - s["y0"] for s in non_rhythm]))
        band_ratio = bh / row_pitch
        if band_ratio > 1.40:
            score *= 0.55
        elif band_ratio < 0.65:
            score *= 0.85
    if col_mismatch:
        score *= 0.6        # estimated column count disagrees with this layout
    # ---- v7: Einthoven / Goldberger arbiter ------------------------------
    # Testable for 12x1 (shared time base) and the 3x4 "col" convention
    # (column 0 = I,II,III ; column 1 = aVR,aVL,aVF, each one simultaneous
    # snapshot).  A WRONG layout or a swapped row/col convention lands near
    # 0.5 (uncorrelated) or near 0, never near 1 — which is why this replaces
    # the old 12x1-only, weak-correlation bonus.
    limb, limb_conv, limb_detail = limb_best_conv(non_rhythm)
    if limb is not None:
        # Only a DECISIVE result may move the score.  In the inconclusive band
        # (LIMB_DEAD..LIMB_STRONG) the test carries no information, so it must
        # not perturb the ranking - otherwise a merely correlated triple can
        # tip the layout choice for no reason.  Measured on the sample images:
        # a genuine 6x2 scores 0.92-0.94, a sequential 3x4 scores 0.46-0.58.
        if limb >= LIMB_STRONG:
            score *= 1.10                     # identities confirmed
        elif limb <= LIMB_DEAD:
            score *= 0.70                     # identities violated -> wrong
    # prevent 12x1 from beating a clearly valid 3x4/6x2/4x3 when that layout
    # has high coverage and many valid strips — 12x1 with 6/12 valid is not
    # better than 3x4top with 11-12/12 valid, even if duration_credit favors it.
    # This is a soft demotion applied at scoring; winner selection also has
    # a hard rule in extract_full.
    if layout_label == "12x1" and n_valid <= 6 and mean_cov < 0.55:
        score *= 0.80
    return dict(label="", strips=strips, score=round(float(score), 3),
                n_leads=n_leads, n_valid=n_valid,
                mean_cov=round(mean_cov, 3), rhythm=round(float(rhythm), 3),
                border=round(border, 3), jump=round(jump, 3), dur_ok=dur_ok,
                dur_credit=round(float(dur_credit), 2),
                span_roi_s=(round(span_roi_s, 2) if span_roi_s else None),
                band_ratio=(round(band_ratio, 2) if band_ratio else None),
                rhy_q=round(rhy_q, 3), row_evidence=round(row_evidence, 2),
                limb_consistency=(round(limb, 3) if limb is not None else None),
                limb_conv=limb_conv,
                limb_detail=[(d, round(sc, 3)) for d, sc in limb_detail])


# --------------------------------------------------------------------------
# debug rendering
# --------------------------------------------------------------------------
def _caption(img, text):
    bar = np.full((34, img.shape[1], 3), 245, np.uint8)
    cv2.putText(bar, text, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1,
                cv2.LINE_AA)
    return np.vstack([bar, img])


def render_strategy_board(raw_masks, best_evs, cand, path, panel_w=470):
    rows = []
    for name in raw_masks:
        raw = raw_masks[name]
        ev = best_evs.get(name)
        cln = ev["cleaned"] if ev else None
        if cln is None:
            cln = np.zeros_like(raw)
        pair = []
        for m in (raw, cln):
            s = panel_w / m.shape[1]
            m2 = cv2.resize(m, (panel_w, max(1, int(m.shape[0] * s))),
                            interpolation=cv2.INTER_NEAREST)
            pair.append(cv2.cvtColor(m2, cv2.COLOR_GRAY2BGR))
        gap = np.full((pair[0].shape[0], 6, 3), 200, np.uint8)
        combo = np.hstack([pair[0], gap, pair[1]])
        if ev:
            cap = "%-18s cand=%4.1f%%  score=%.2f  %s  valid=%d/%d  cov=%.2f" % (
                name, 100 * cand.get(name, 0), ev["score"], ev.get("label", ""),
                ev["n_valid"], ev["n_leads"], ev["mean_cov"])
        else:
            cap = "%-18s cand=%4.1f%%  (skipped)" % (name, 100 * cand.get(name, 0))
        rows.append(_caption(combo, cap))
    cv2.imwrite(path, np.vstack(rows))


def render_inkmap(img, path):
    """Pseudo-color 'ink map': trace likelihood as a bright color we can target."""
    ink = ink_map(img)
    ink8 = np.clip(ink * 255.0, 0, 255).astype(np.uint8)
    heat = cv2.applyColorMap(ink8, cv2.COLORMAP_INFERNO)
    cv2.imwrite(path, _caption(heat, "ink = darkness x (1-redness): trace bright, red grid / text dim"))


def render_trace_only(shape, strips, path):
    h, w = shape
    canvas = np.full((h, w, 3), 255, np.uint8)
    for st in strips:
        sy0, sy1, sx0, sx1 = st["roi"]
        used = st.get("used")
        if used is None or used.size == 0:
            continue
        roi = canvas[sy0:sy1, sx0:sx1]
        if roi.shape[:2] == used.shape[:2]:
            roi[used] = (0, 0, 0)
    cv2.imwrite(path, canvas)


def render_layout(img, strips, path):
    vis = img.copy()
    for st in strips:
        sy0, sy1, sx0, sx1 = st["roi"]
        color = (0, 170, 0) if st.get("valid") else (0, 0, 220)
        cv2.rectangle(vis, (sx0, sy0), (sx1, sy1), color, 2)
        cv2.putText(vis, st.get("name", "?"), (sx0 + 6, min(sy0 + 22, sy1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)
    cv2.imwrite(path, vis)


def render_signals_plot(ecg, names, hr, pr, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        n = ecg.shape[1]
        t = np.arange(ecg.shape[2]) / 500.0
        fig, axes = plt.subplots(n, 1, figsize=(10, 9), sharex=True,
                                 constrained_layout=True)
        if n == 1:
            axes = [axes]
        for i, ax in enumerate(axes):
            ax.plot(t, ecg[0, i], lw=0.7, color="k")
            nm = names[i] if i < len(names) else str(i)
            ax.set_ylabel(nm, rotation=0, ha="right", va="center", fontsize=8)
            ax.set_yticks([])
        axes[-1].set_xlabel("time (s)")
        title = "Extracted 12-lead signal (z-scored, 10 s @ 500 Hz)"
        if hr:
            title += "   HR ~ %.0f bpm" % hr
        if pr:
            title += "   PR ~ %.0f ms" % (pr * 1000)
        fig.suptitle(title)
        fig.savefig(path, dpi=100)
        plt.close(fig)
    except Exception:
        n = ecg.shape[1]
        row_h, W = 80, 1000
        canvas = np.full((n * row_h + 50, W, 3), 255, np.uint8)
        for i in range(n):
            y0 = 25 + i * row_h
            sig = ecg[0, i]
            xs = np.linspace(10, W - 10, sig.size)
            ys = y0 + row_h / 2 - np.clip(sig * 28, -row_h / 2 + 6, row_h / 2 - 6)
            cv2.polylines(canvas, [np.stack([xs, ys], 1).astype(np.int32)], False,
                          (30, 30, 30), 1)
            cv2.putText(canvas, names[i] if i < len(names) else str(i), (6, y0 + 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 120, 120), 1)
        cv2.imwrite(path, canvas)


# --------------------------------------------------------------------------
# main pipeline
# --------------------------------------------------------------------------
def extract_full(image_path, out_dir="ecg_out", layout="auto", strategy="auto",
                 paper_speed=25.0, px_per_mm=None, strip_sec=2.5, lead_order="row",
                 min_valid=10, min_coverage=0.55, force=False, no_debug=False,
                 target_hz=500, target_samples=5000, gain=10.0, verbose=True,
                 return_mv=False):
    """Digitize an ECG printout photo. Returns (ecg_or_None, report).

    ecg: float32 (1, 12, 5000), z-scored per lead, 10 s @ 500 Hz - or None if the
    safety gate refuses (report['usable'] == False, report['reasons'] says why).

    return_mv=True returns a 3-tuple (ecg, report, ecg_mv) where ecg_mv is the
    (12, 5000) mV-scaled signal in CANONICAL lead order - the input ECGFounder
    should get (cross-lead amplitude ratios preserved, unlike the per-lead
    ink-normalized ecg).  Both are None together on refusal.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError("image not found: %s" % image_path)
    h, w = img.shape[:2]

    def say(msg):
        if verbose:
            print(msg)

    say("=" * 62)
    say("🔬 ecg_extract_v7 — %s" % os.path.basename(image_path))
    say("=" * 62)
    diag = diagnose(img)
    say("🖼️  image %s | colored %.0f%% | red-grid %.1f%% | median S=%d V=%d" % (
        diag["size"], 100 * diag["colored_fraction"],
        100 * diag["red_grid_fraction"], diag["saturation_median"],
        diag["value_median"]))

    # ---- time calibration -------------------------------------------------
    calib_src = "assumed"
    pitch = None
    if px_per_mm:
        pitch = dict(px_per_mm=float(px_per_mm), px_per_mm_y=float(px_per_mm),
                     fundamental_px=0, grid_fraction=0.0)
        calib_src = "user"
    else:
        pitch = detect_grid_pitch(img)
        if pitch:
            calib_src = "grid-autocorr"
    pps = (pitch["px_per_mm"] * paper_speed) if pitch else None
    px_mm_y = (pitch.get("px_per_mm_y") if pitch else None)
    if pitch:
        say("📐 paper grid: %.2f px/mm x, %.2f px/mm y (%s) -> %.0f px/s @ %.0f mm/s" % (
            pitch["px_per_mm"], (px_mm_y or pitch["px_per_mm"]), calib_src, pps,
            paper_speed))
    else:
        say("📐 paper grid not detected -> assuming %.1f s per strip (--strip-sec)" % strip_sec)

    fixed_layout = None
    if layout and layout.lower() != "auto":
        r, c = layout.lower().split("x")
        fixed_layout = (int(r), int(c))

    # ---- evaluate every (strategy x layout) pair --------------------------
    raw_masks, cand = build_strategy_masks(img)
    Wimg = ink_map(img)
    results = []           # (score, strategy, label, ev)
    best_evs = {}          # per-strategy best (for the board)
    for name, m in raw_masks.items():
        if strategy.lower() != "auto" and strategy.lower() not in name.lower():
            continue
        cf = cand.get(name, 0.0)
        if cf < 0.001 or cf > 0.50:
            continue                          # degenerate mask
        cleaned = clean_mask(m, w, h, deskew=name.startswith("E_adaptive"))
        if (cleaned > 0).mean() < 0.0005:
            continue
        cand_list = build_layout_candidates(cleaned, lead_order, fixed_layout)
        px_mm = (pps / paper_speed) if pps else None
        for label, strips, ratio, row_pitch, mism in cand_list:
            ev = evaluate_candidate(cleaned, Wimg, strips, pps, strip_sec,
                                    row_evidence=ratio, px_mm=px_mm,
                                    row_pitch=row_pitch, col_mismatch=mism,
                                    layout_label=label.split("top")[0] if "top" in label else label)
            ev["label"] = label
            ev["cleaned"] = cleaned
            results.append((ev["score"], name, label, ev))
            if name not in best_evs or ev["score"] > best_evs[name]["score"]:
                best_evs[name] = ev
    if not results:
        rep = dict(usable=False,
                   reasons=["no separation strategy produced candidate strips"])
        return (None, rep, None) if return_mv else (None, rep)
    results.sort(key=lambda t: -t[0])

    # ---- hard rule: 12x1 must not steal a sequential layout's win ---------
    # 12x1 can win on duration_credit while actually reading only ~6/12 strips
    # of a 3x4/6x2 printout (its scanline crosses the row gaps).  When that
    # happens and a 3x4/6x2/4x3 candidate is geometrically strong, the latter
    # wins - unless the 12x1 trace passes the Einthoven limb-lead algebra, which
    # is strong evidence it really is a simultaneous 12-lead recording.
    def _base_layout(lb):
        return lb.split("top")[0] if "top" in lb else lb

    def _is_seq(lb):
        return _base_layout(lb) in ("3x4", "6x2", "4x3")

    top_lbl = results[0][2] if results else ""
    if _base_layout(top_lbl) == "12x1":
        top_e = results[0][3]
        weak_12x1 = (top_e["n_valid"] <= 6 and top_e["mean_cov"] < 0.55)
        limb_12x1 = top_e.get("limb_consistency")
        # Einthoven passing (limb high) means 12x1 is genuinely simultaneous
        if weak_12x1 and (limb_12x1 is None or limb_12x1 < 0.50):
            best_seq = None
            for t in results:
                if not _is_seq(t[2]):
                    continue
                if (t[3]["n_valid"] >= 10 and t[3]["mean_cov"] >= 0.55
                        and t[3]["jump"] < 0.25):
                    best_seq = t
                    break
            if best_seq is not None:
                results.remove(best_seq)
                results.insert(0, best_seq)

    # final winner is results[0] after hard-rule adjustment
    say("📊 top (strategy x layout) candidates:")
    for sc, nm, lb, e in results[:6]:
        extra = ""
        if e.get("limb_consistency") is not None:
            extra = " limb=%.2f/%s" % (e["limb_consistency"],
                                       e.get("limb_conv") or "?")
        say("   %-18s @ %-14s score=%.2f  valid=%2d/%2d  cov=%.2f  jump=%.2f  span=%s  dur_ok=%s%s" % (
            nm, lb, sc, e["n_valid"], e["n_leads"], e["mean_cov"], e["jump"],
            ("%.2fs" % e["span_roi_s"]) if e.get("span_roi_s") else "-",
            e["dur_ok"], extra))
    say("📊 strategies (best layout each — see debug_1_strategies.png):")
    for name in raw_masks:
        ev = best_evs.get(name)
        if ev is None:
            continue
        say("   %-18s cand=%4.1f%%  score=%.2f  %-14s valid=%2d/%2d  cov=%.2f  rhythm=%.2f" % (
            name, 100 * cand.get(name, 0), ev["score"], ev["label"],
            ev["n_valid"], ev["n_leads"], ev["mean_cov"], ev["rhythm"]))
    _, winner_name, winner_label, ev = results[0]
    say("🏆 winner: %s @ %s" % (winner_name, winner_label))

    strips = ev["strips"]
    non_rhythm = [s for s in strips if not s["rhythm"]]
    names = [s["name"] for s in non_rhythm]
    n12 = len(non_rhythm)
    warnings = []

    # ---- lead-order auto-detection ---------------------------------------
    # 6x2/4x3/3x4 printouts exist in two wiring conventions; the wrong one
    # silently swaps almost every lead label (only I and V6 survive) and
    # ECGFounder would then diagnose the wrong heart.  aVR/II/V1 polarity
    # tells them apart; the user can always force --lead-order.
    lead_order_eff = lead_order
    if lead_order == "row" and n12 == 12:
        rows_c, cols_c = 0, 0
        try:
            rc = {(s["row"], s["col"]) for s in non_rhythm}
            rows_c = max(r for r, _ in rc) + 1
            cols_c = max(c for _, c in rc) + 1
        except Exception:
            pass
        # (1) EINTHOVEN ARBITER first: when the limb identities are decisive
        # under one wiring convention, that settles layout AND lead order.
        limb_sc = ev.get("limb_consistency")
        limb_conv = ev.get("limb_conv")
        decided, how = None, None
        if limb_conv and limb_sc is not None and limb_sc >= LIMB_STRONG:
            decided = limb_conv
            how = "Einthoven limb algebra %s (score %.2f)" % (
                ", ".join("%s=%.2f" % (d, sc)
                          for d, sc in (ev.get("limb_detail") or [])), limb_sc)
        else:
            # (2) fall back to the aVR / II / V1 polarity heuristic
            try:
                o = auto_lead_order(non_rhythm, rows_c, cols_c)
            except Exception:
                o = None
            if o is not None:
                decided, how = o, "lead polarity heuristic"
                # be honest about how weak that evidence is
                if limb_sc is not None and LIMB_DEAD < limb_sc < LIMB_STRONG:
                    warnings.append(
                        "lead order from polarity only: limb algebra is "
                        "inconclusive (score %.2f over %d identit%s) - verify "
                        "the lead labels in debug_3_layout.png"
                        % (limb_sc, len(ev.get("limb_detail") or []),
                           "y" if len(ev.get("limb_detail") or []) == 1 else "ies"))
                elif limb_sc is None:
                    warnings.append("lead order from polarity only: limb algebra "
                                    "not testable for this layout")
            elif (rows_c, cols_c) in ((6, 2), (4, 3), (3, 4)):
                warnings.append("lead order convention uncertain (row assumed by "
                                "default; if labels look swapped try -"
                                "-lead-order col)")
        if decided and decided != lead_order:
            for s in non_rhythm:
                idx = (s["col"] * rows_c + s["row"]) if decided == "col" \
                    else (s["row"] * cols_c + s["col"])
                if idx < 12:
                    s["name"] = LEAD_NAMES[idx]
            names = [s["name"] for s in non_rhythm]
            lead_order_eff = decided
            say("🧭 lead order: %s (%s - auto-detected via %s)" % (
                decided,
                "limb leads down the left column, precordials down the right"
                if decided == "col" else "lead pairs across rows", how))

    # ---- finalize time scale ----------------------------------------------
    # pps priority: (1) grid comb autocorr (physical px/mm), refined by the
    # ROI span snapping to a standard duration (2.5/5/10 s) within 15%;
    # (2) if no grid: ROI span / assumed --strip-sec.
    if pitch is None:
        warnings.append("paper grid not detected: time scale assumed from "
                        "--strip-sec %.1f s; HR may be scaled if wrong" % strip_sec)
    med_roi_w = float(np.median([s["roi"][3] - s["roi"][2] for s in non_rhythm])) \
        if non_rhythm else 0.0
    if pps is None and med_roi_w > 0:
        pps = med_roi_w / strip_sec
    # grid HARMONIC safety net: the grid autocorr can lock onto a harmonic of
    # the true px/mm (e.g. 3.2 instead of 4.0 px/mm -> every cell span, and the
    # mV amplitude, scales by 1.25x).  If the winner's cell span is not a
    # standard duration, solve for the px/s that WOULD make it one (med_roi_w /
    # 2.5, /5, /10) and take whichever stays closest to the detected pitch while
    # snapping to a standard duration.  This covers arbitrary ratios (1.25x,
    # 0.8x, 2x...), unlike a fixed {0.25,0.5,2,4} multiplier ladder.
    if pitch is not None and pps and med_roi_w > 0 and calib_src == "grid-autocorr":
        span0 = med_roi_w / pps
        if duration_credit(span0) < 1.0:
            best_c, best_pps = duration_credit(span0), pps
            for d in (2.5, 5.0, 10.0):
                pps_d = med_roi_w / d
                # keep only a plausible correction: within 0.4x-2.5x of the
                # detected pitch, and inside the legal px/s band
                if not (0.4 * pps <= pps_d <= 2.5 * pps):
                    continue
                if not (2.5 * 25.0 <= pps_d <= 30.0 * 25.0):
                    continue
                c_d = duration_credit(med_roi_w / pps_d)
                if (c_d > best_c + 1e-9 or
                        (abs(c_d - best_c) <= 1e-9 and
                         abs(pps_d - pps) < abs(best_pps - pps))):
                    best_c, best_pps = c_d, pps_d
            if best_pps != pps:
                warnings.append("grid harmonic corrected: %.0f -> %.0f px/s "
                                "(cell span %.2f -> %.2f s)" % (
                                    pps, best_pps, span0, med_roi_w / best_pps))
                scale = best_pps / pps
                pitch = dict(pitch, px_per_mm=round(pitch["px_per_mm"] * scale, 2),
                             px_per_mm_y=round((px_mm_y or pitch["px_per_mm"]) * scale, 2))
                pps = best_pps
                px_mm_y = pitch["px_per_mm_y"]
    dur = None
    good_yv = [s for s in non_rhythm if s["yv"] is not None]
    if good_yv and pps and med_roi_w > 0:
        med_sig_w = float(np.median([s["yv"].size for s in good_yv]))
        dur = med_sig_w / pps                    # signal seconds (pulse excluded)
        snapped = snap_duration(med_roi_w / pps) # ROI = pulse + trace + margins
        if snapped and abs(med_roi_w / snapped - pps) <= 0.15 * pps:
            pps = med_roi_w / snapped            # small refinement, keeps grid close
            dur = med_sig_w / pps
        elif pitch is not None:
            span_roi = med_roi_w / pps
            if duration_credit(span_roi) <= 0.0:
                warnings.append("cell span %.2f s sits in a printout dead zone "
                                "(1.2-2.1 / 2.9-4.4 / 5.9-8.4 s) - layout or pitch "
                                "is suspect" % span_roi)
            else:
                warnings.append("cell span %.2f s does not match a standard "
                                "duration (2.5/5/10 s) - non-standard printout or "
                                "compact figure; tiling will be used" % span_roi)

    # ---- build the 12-lead array + measurements --------------------------
    ecg = None
    ecg_mv = None
    hr = hr_pk = pr = None
    r_count = 0
    rhythm_500 = 0.0
    hr_leads_used = []
    hr_consistent = False
    density_ratio = None
    rhy_px = dict(pooled_hr=None, pooled_rr_s=None, per_lead=[], beats_total=0,
                  segs={}, n_rr=0)
    reasons = []
    _rhythm_warnings = []   # rhythm-quality diagnostics gathered below; the gate
                            # promotes them to hard reasons only when the layout
                            # gate also failed (see "safety gate" section)
    good_strips = [s for s in non_rhythm if s["yv"] is not None]
    names_ecg = list(names)
    if n12 == 12 and len(good_strips) >= max(4, min_valid - 2) and pps:
        # primary HR: pixel-domain beat detection on SINGLE strips, RR pooled
        # across the leads that produced a signal (no tiling seams, no pulse
        # edges can pollute it).  Runs even when 1-2 leads are dead, so the
        # report explains the coverage problem instead of hiding the rhythm.
        rhy_px = measure_rhythm_px(good_strips, pps, target_hz)
        hr_pk = rhy_px["pooled_hr"]
        hr_leads_used = rhy_px["per_lead"]
        r_count = rhy_px["beats_total"]
        if len(good_strips) == n12:
            by_name = {s["name"]: s["yv"] for s in non_rhythm}
            if all(nm in by_name for nm in LEAD_NAMES):
                # ECGFounder expects the CANONICAL lead order on axis 1
                # (I, II, III, aVR, aVL, aVF, V1..V6).  A col-convention
                # grid traverses as I, V1, II, V2... so the strips MUST be
                # re-ordered by name before stacking.
                signals = [by_name[nm] for nm in LEAD_NAMES]
                names_ecg = list(LEAD_NAMES)
            else:
                signals = [s["yv"] for s in non_rhythm]
            ecg, ecg_mv = to_ecg_array(signals, pps, target_hz, target_samples,
                                        px_per_mm_y=px_mm_y, gain=gain)
        # cross-lead consistency: most leads must agree with the pooled HR,
        # and the per-lead HRs must be TIGHT (garbage yields incoherent medians)
        # These are rhythm quality — downgraded to warnings when geometry is strong;
        # will be promoted to reasons only if layout_ok is False (handled at gate).
        if hr_pk and len(hr_leads_used) >= 3:
            agree = [abs(h - hr_pk) <= 0.20 * hr_pk for _, h in hr_leads_used]
            hr_consistent = (sum(agree) >= max(3, int(0.6 * len(agree))))
            if not hr_consistent:
                _rhythm_warnings.append("R-peak HR inconsistent across leads (%s) — "
                               "layout or trace following unreliable" % hr_leads_used)
        if hr_pk and len(hr_leads_used) >= 5:
            vals = np.sort(np.array([h for _, h in hr_leads_used]))
            p25, p50, p75 = np.percentile(vals, [25, 50, 75])
            if p50 > 0 and (p75 - p25) / p50 > 0.12:
                _rhythm_warnings.append("per-lead heart rates scatter (IQR/median %.2f) — "
                               "not a coherent cardiac rhythm" %
                               ((p75 - p25) / p50))
        # secondary cross-check: autocorr on the RAW single strips (fs = px/s).
        # The old tiled-signal autocorr locked onto the TILE length (60/0.91 s
        # = 66 bpm artifact on compact figures) instead of the heart rate.
        ac_vs, ac_hrs = [], []
        for s in non_rhythm:
            if s["yv"] is not None and s["yv"].size > 60:
                acv, h_ac = rhythm_hr(s["yv"], pps)
                if h_ac:
                    ac_vs.append(acv)
                    ac_hrs.append(h_ac)
        rhythm_500 = float(np.median(ac_vs)) if ac_vs else 0.0
        hr = round(float(np.median(ac_hrs)), 1) if ac_hrs else None
        # beat-density coherence: a real recording shows ~HR/60 beats per second
        # on EVERY lead; random clutter yields far fewer beats than its claimed
        # R-R median.  Downgraded to _rhythm_warnings when layout is strong.
        if hr_pk and dur and n12:
            expected = n12 * dur * hr_pk / 60.0
            if expected > 1:
                density_ratio = round(r_count / expected, 2)
                if density_ratio < 0.55 and ev["rhythm"] < 0.10:
                    _rhythm_warnings.append("detected only %d beats where %.0f expected at "
                                   "%.0f bpm over %.0f s of strips — not a coherent "
                                   "ECG recording (non-ECG image?)" % (
                                       r_count, expected, hr_pk, n12 * dur))
        # PR from the pooled multi-lead beat template
        pr = estimate_pr_pooled(rhy_px["segs"], target_hz)
        if pr is not None and pr < 0.12:
            warnings.append("PR %.0f ms is implausibly short — P detection "
                            "uncertain" % (pr * 1000))
        if dur is not None and dur < 9.0:
            warnings.append("sequential printout: %.1f s per lead tiled to 10 s "
                            "(beats are repeated, HR is preserved)" % dur)
        if hr is not None and hr_pk is not None and \
                abs(hr - hr_pk) > max(15.0, 0.25 * hr_pk):
            warnings.append("autocorr HR %.0f bpm vs pooled R-peak HR %.0f bpm "
                            "(autocorr on tiled signal is a weak estimator; "
                            "pooled cross-lead RRs are primary)" % (hr, hr_pk))

    # ---- safety gate (decoupled: layout vs rhythm) -----------------------
    # Layout gate = geometry/validity (hard). Rhythm gate = soft when layout strong.
    layout_ok = True
    if n12 != 12:
        reasons.append("layout: %d lead strips detected (expected 12) — try "
                       "--layout 6x2 / 4x3 / 12x1" % n12)
        layout_ok = False
    if ev["n_valid"] < min_valid:
        reasons.append("only %d/%d strips have usable trace coverage" % (
            ev["n_valid"], max(n12, 1)))
        layout_ok = False
    if ev["mean_cov"] < min_coverage:
        reasons.append("mean trace coverage %.2f below %.2f" % (
            ev["mean_cov"], min_coverage))
        layout_ok = False
    if ev.get("border", 0.0) > 0.25:
        reasons.append("traces touch strip borders on %.0f%% of columns — "
                       "layout looks wrong" % (100 * ev["border"]))
        layout_ok = False
    if ev["score"] < 0.35:
        reasons.append("best (strategy x layout) score too low (%.2f)" % ev["score"])
        layout_ok = False

    # Rhythm gate: soft when layout is strong -> warning, not refusal.
    # Distinguish the two failure classes:
    #   * cannot read ANY rhythm (hr_pk None) or an impossible rate -> rhythm gate
    #   * cross-lead HR disagreement / HR scatter / beat-density mismatch -> also
    #     rhythm quality only; a geometrically solid 12-lead extraction is still
    #     fed to the analyzer, with the caveat surfaced as a warning.
    rhythm_reasons = list(_rhythm_warnings)
    if hr_pk is None:
        rhythm_reasons.append("no consistent cardiac rhythm detected across lead strips")
    elif not (25.0 <= hr_pk <= 200.0):
        rhythm_reasons.append("implausible heart rate %.0f bpm" % hr_pk)

    # Only hard-fail on rhythm if layout itself is weak OR ecg could not be built
    if rhythm_reasons:
        if not layout_ok or ecg is None:
            reasons.extend([r + " — refusing to guess" for r in rhythm_reasons])
        else:
            for r in rhythm_reasons:
                warnings.append(r + " — layout gate passed, signal still usable; "
                                "treat HR/rhythm with caution")

    # If still no ecg (e.g. no pps), that's a hard fail regardless
    if ecg is None and layout_ok:
        # try to build ecg without HR: layout was good but pps missing — infer from layout
        # fallback: if grid missing, assume standard 2.5s per strip for sequential layouts
        if pitch is None and ev.get("span_roi_s") is None and med_roi_w > 0:
            # use strip_sec assumption already handled above; still no signal means
            # not enough valid strips - keep refusal
            reasons.append("could not build 12-lead signal (no time base)")

    usable = (not reasons) and (ecg is not None)

    # ---- contamination metric (used pixels that are grid pixels) ---------
    grid_m = _grid_mask(img, strict=True)
    used_all = np.zeros((h, w), bool)
    for s in strips:
        u = s.get("used")
        if u is not None and u.size:
            sy0, sy1, sx0, sx1 = s["roi"]
            sub = used_all[sy0:sy1, sx0:sx1]
            if sub.shape == u.shape:
                sub |= u
    inter = float((used_all & grid_m).sum()) / max(1, int(used_all.sum()))

    # ---- report ------------------------------------------------------------
    report = dict(
        image=os.path.abspath(image_path), size=diag["size"], color=diag,
        calibration=dict(source=calib_src,
                         px_per_mm=(pitch["px_per_mm"] if pitch else None),
                         px_per_mm_y=(px_mm_y if pitch else None),
                         px_per_sec=(round(pps, 1) if pps else None),
                         paper_speed=paper_speed,
                         gain_mm_per_mv=float(gain),
                         cell_span_s=(round(med_roi_w / pps, 2)
                                      if (med_roi_w > 0 and pps) else None),
                         strip_sec=(round(dur, 2) if dur else None)),
        strips_detail=[dict(name=s["name"], cov=round(s.get("cov", 0.0), 2),
                            jump=round(s.get("jump", 0.0), 3),
                            valid=bool(s.get("valid")),
                            sig_px=(int(s["yv"].size) if s.get("yv") is not None
                                    else 0))
                       for s in non_rhythm],
        strategies=[dict(name=n, cand_frac=round(cand.get(n, 0.0), 4),
                         score=best_evs[n]["score"], layout=best_evs[n]["label"],
                         n_valid=best_evs[n]["n_valid"], n_leads=best_evs[n]["n_leads"],
                         mean_cov=best_evs[n]["mean_cov"],
                         rhythm=best_evs[n]["rhythm"])
                    for n in raw_masks if n in best_evs],
        chosen=dict(strategy=winner_name, layout=winner_label, n_lead_strips=n12,
                    lead_order=lead_order_eff, lead_names=names_ecg,
                    coverage=[round(s["cov"], 2) for s in non_rhythm],
                    border_frac=ev.get("border"),
                    limb_consistency=ev.get("limb_consistency"),
                    limb_conv=ev.get("limb_conv"),
                    limb_detail=ev.get("limb_detail")),
        measurements=dict(
            hr_pooled_bpm=hr_pk,
            pooled_rr_s=(rhy_px.get("pooled_rr_s") if rhy_px.get("pooled_rr_s") else None),
            beat_density_ratio=density_ratio,
            hr_autocorr_bpm=(round(hr, 1) if hr else None),
            hr_per_lead=hr_leads_used,
            r_peaks_detected=r_count,
            rhythm_score=round(rhythm_500, 3),
            pr_interval_s=(round(pr, 3) if pr else None)),
        quality=dict(mean_coverage=ev["mean_cov"], valid_strips=ev["n_valid"],
                     grid_contamination=round(inter, 4)),
        usable=usable, reasons=reasons, warnings=warnings,
    )

    # ---- outputs ----------------------------------------------------------
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        if not no_debug:
            cv2.imwrite(os.path.join(out_dir, "debug_0_input.png"), img)
            render_strategy_board(raw_masks, best_evs, cand,
                                  os.path.join(out_dir, "debug_1_strategies.png"))
            render_inkmap(img, os.path.join(out_dir, "debug_1b_inkmap.png"))
            render_trace_only((h, w), strips,
                              os.path.join(out_dir, "debug_2_trace_only.png"))
            render_layout(img, strips,
                          os.path.join(out_dir, "debug_3_layout.png"))
            if ecg is not None:
                render_signals_plot(ecg, names_ecg, hr_pk or hr, pr,
                                    os.path.join(out_dir, "debug_4_signals.png"))
        with open(os.path.join(out_dir, "report.json"), "w") as f:
            json.dump(report, f, indent=2)
        if ecg is not None and (usable or force):
            np.save(os.path.join(out_dir, "signal_12x5000.npy"), ecg)
            say("💾 signal saved: %s  ->  feed this to ECGFounder" %
                os.path.join(out_dir, "signal_12x5000.npy"))
            if ecg_mv is not None:
                np.savez(os.path.join(out_dir, "signal_mv.npz"),
                         ecg_mv=ecg_mv, names=np.array(names_ecg), fs=target_hz,
                         gain_mm_per_mv=float(gain),
                         px_per_mm=(float(pitch["px_per_mm"]) if pitch else 0.0),
                         px_per_mm_y=float(px_mm_y or 0.0),
                         hr_bpm=float(hr_pk or 0.0), pr_s=float(pr or 0.0),
                         layout=str(winner_label), strategy=str(winner_name))
                say("💾 mV signal saved: %s (gain %.0f mm/mV, fs=%d Hz)" % (
                    os.path.join(out_dir, "signal_mv.npz"), gain, target_hz))
        say("📁 debug outputs: %s" % out_dir)

    # ---- console verdict --------------------------------------------------
    say("")
    say("📋 verdict: " + ("✅ USABLE" if usable else "🛑 REFUSED"))
    if hr_pk:
        say("❤️  HR ≈ %.0f bpm (pooled R-R over %d intervals, %d beats across strips)" % (
            hr_pk, rhy_px.get("n_rr", 0), r_count))
        say("   per-lead: %s" % (hr_leads_used,))
    if hr:
        say("❤️  HR ≈ %.0f bpm (autocorr cross-check)" % hr)
    if pr:
        say("🧡 PR ≈ %.0f ms (indicative; > 200 ms suggests 1AVB)" % (pr * 1000))
    if not usable:
        for r in reasons:
            say("   ⚠️  " + r)
    for wn in warnings:
        say("   ℹ️  " + wn)
    ok = usable or force
    if return_mv:
        return (ecg if ok else None), report, (ecg_mv if ok else None)
    return (ecg if ok else None), report


# v2/v3-compatible helper (raises instead of returning None on refusal)
def extract_clean_signal(image_path, **kw):
    ecg, report = extract_full(image_path, **kw)
    if ecg is None:
        raise RuntimeError("extraction refused: " + "; ".join(report["reasons"]))
    return ecg


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(
        description="Multi-strategy ECG printout digitizer (see module docstring)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("image", help="path to the ECG photo")
    p.add_argument("-o", "--out-dir", default="ecg_out", help="output directory")
    p.add_argument("--layout", default="auto",
                   choices=["auto", "6x2", "4x3", "3x4", "12x1"],
                   help="strip layout (auto = standard layouts are searched + scored)")
    p.add_argument("--strategy", default="auto",
                   help="force a separation strategy (A/B/C/D/E/F or auto)")
    p.add_argument("--paper-speed", type=float, default=25.0, help="mm/s")
    p.add_argument("--px-per-mm", type=float, default=0.0,
                   help="force px/mm calibration (0 = auto from grid)")
    p.add_argument("--strip-sec", type=float, default=2.5,
                   help="seconds per strip when the grid cannot be detected")
    p.add_argument("--lead-order", default="row", choices=["row", "col"],
                   help="how leads map to strips (row-major is standard)")
    p.add_argument("--gain", type=float, default=10.0,
                   help="mm per mV of the printout (standard 10)")
    p.add_argument("--min-valid", type=int, default=10)
    p.add_argument("--min-coverage", type=float, default=0.55)
    p.add_argument("--force", action="store_true",
                   help="save the signal even if the safety gate refuses")
    p.add_argument("--no-debug", action="store_true")
    args = p.parse_args()
    pxmm = args.px_per_mm if args.px_per_mm > 0 else None
    try:
        _, report = extract_full(args.image, out_dir=args.out_dir, layout=args.layout,
                                 strategy=args.strategy, paper_speed=args.paper_speed,
                                 px_per_mm=pxmm, strip_sec=args.strip_sec,
                                 lead_order=args.lead_order, min_valid=args.min_valid,
                                 min_coverage=args.min_coverage, force=args.force,
                                 no_debug=args.no_debug, gain=args.gain, verbose=True)
    except Exception as exc:
        print("❌ error: %s" % exc)
        return 1
    return 0 if report["usable"] else 2


if __name__ == "__main__":
    sys.exit(main())
