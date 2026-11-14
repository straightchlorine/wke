#!/usr/bin/env python3
"""Checks the contrast pairs of tokens.css against their minimum ratios and expected ratios."""

import re
import sys
from pathlib import Path

TOKENS_PATH = Path(__file__).resolve().parent.parent / "src" / "tokens.css"
TOLERANCE = 0.05


def srgb_to_linear(channel: float) -> float:
    """Converts one 0..1 sRGB channel to linear light.

    Args:
        channel: The channel value, 0..1.

    Returns:
        The linearised channel value.
    """
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_colour: str) -> float:
    """Computes WCAG relative luminance for a #rrggbb colour.

    Args:
        hex_colour: A 6-digit hex colour, with or without leading '#'.

    Returns:
        The relative luminance, 0..1.
    """
    hex_colour = hex_colour.lstrip("#")
    r, g, b = (int(hex_colour[i : i + 2], 16) / 255 for i in (0, 2, 4))
    r, g, b = (srgb_to_linear(c) for c in (r, g, b))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """Computes the WCAG contrast ratio between two colours.

    Args:
        fg_hex: Foreground (text or stroke) colour, #rrggbb.
        bg_hex: Background colour, #rrggbb.

    Returns:
        The contrast ratio, 1..21.
    """
    l1 = relative_luminance(fg_hex)
    l2 = relative_luminance(bg_hex)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def parse_tokens(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Extracts --wke-* hex values from :root and [data-theme="dark"].

    Args:
        path: Path to tokens.css.

    Returns:
        A (light, dark) pair of {token name (without --wke- prefix): hex}.
    """
    text = path.read_text(encoding="ascii")
    root_match = re.search(r":root\s*{([^}]*)}", text, re.DOTALL)
    dark_match = re.search(r'\[data-theme="dark"\]\s*{([^}]*)}', text, re.DOTALL)
    if not root_match or not dark_match:
        raise SystemExit(f"could not find :root or [data-theme=dark] block in {path}")

    hex_pattern = r"--wke-([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})"
    return (
        dict(re.findall(hex_pattern, root_match.group(1))),
        dict(re.findall(hex_pattern, dark_match.group(1))),
    )


# Each row is the label, the foreground and background tokens, the minimum
# ratio, the expected light and dark ratios, and the gate flag.
# A gated row fails the run when a theme is under the minimum or differs from
# its expected ratio by more than TOLERANCE.
TEXT_PAIRS = [
    ("ink on paper", "ink", "paper", 4.5, 14.58, 14.63, True),
    ("ink on sheet", "ink", "sheet", 4.5, 15.93, 13.28, True),
    ("ink on wash", "ink", "wash", 4.5, 13.61, 10.21, True),
    ("ink-2 on paper", "ink-2", "paper", 4.5, 7.74, 8.69, True),
    ("ink-2 on model", "ink-2", "model", 4.5, 7.13, 7.48, True),
    ("ink-2 on wash", "ink-2", "wash", 4.5, 7.22, 6.07, True),
    ("ink-2 on sunken", "ink-2", "sunken", 4.5, 7.00, 9.11, True),
    ("ink-3 on paper", "ink-3", "paper", 4.5, 5.08, 5.25, True),
    ("ink-3 on sheet", "ink-3", "sheet", 4.5, 5.55, 4.76, True),
    ("ink-3 on sunken", "ink-3", "sunken", 4.5, 4.60, 5.50, True),
    ("ink on sunken", "ink", "sunken", 4.5, 13.18, 15.34, True),
    ("accent on sunken", "accent", "sunken", 4.5, 6.15, 9.30, True),
    ("ink-3 on model", "ink-3", "model", 4.5, 4.68, 4.52, True),
    ("ink-2 on stamp-wash", "ink-2", "stamp-wash", 4.5, 7.04, 7.20, True),
    ("accent on paper", "accent", "paper", 4.5, 6.81, 8.87, True),
    ("accent on sheet", "accent", "sheet", 4.5, 7.44, 8.05, True),
    ("accent on wash", "accent", "wash", 4.5, 6.35, 6.19, True),
    ("accent-ink on wash", "accent-ink", "wash", 4.5, 9.54, 8.29, True),
    ("on-accent on accent", "on-accent", "accent", 4.5, 8.04, 8.51, True),
    ("stamp on paper", "stamp", "paper", 4.5, 5.79, 7.24, True),
    ("stamp on sheet", "stamp", "sheet", 4.5, 6.32, 6.57, True),
    ("stamp on stamp-wash", "stamp", "stamp-wash", 4.5, 5.27, 5.99, True),
    ("on-accent on stamp", "on-accent", "stamp", 4.5, 6.83, 6.94, True),
]

# This pair fails the minimum ratio in the dark theme only.
# It is printed for reference and never gates the run.
FORBIDDEN_PAIRS = [
    ("ink-3 on wash", "ink-3", "wash", 4.5, 4.74, 3.66, False),
]

# These pairs are hairlines and frames, which are not text.
# Rule-strong on paper is below 3:1 in light, which is acceptable because frames
# that carry meaning sit on sheet.
DECORATIVE_PAIRS = [
    ("rule-strong on paper", "rule-strong", "paper", 3.0, 2.88, 3.57, False),
    ("rule on paper", "rule", "paper", 3.0, 1.37, 1.47, False),
]

STROKE_PAIRS = [
    ("c1 on sheet", "c1", "sheet", 3.0, 6.61, 7.12, True),
    ("c2 on sheet", "c2", "sheet", 3.0, 5.15, 7.98, True),
    ("c3 on sheet", "c3", "sheet", 3.0, 5.23, 6.79, True),
    ("c4 on sheet", "c4", "sheet", 3.0, 6.89, 6.72, True),
    ("c5 on sheet", "c5", "sheet", 3.0, 5.69, 8.01, True),
    ("c6 on sheet", "c6", "sheet", 3.0, 6.86, 6.75, True),
]

# c3 against stamp is not a text or stroke contrast check. It is printed only
# and never gates the run.
INFO_ONLY = [("c3 against stamp", "c3", "stamp", 1.0, 1.21, 1.03, False)]


def check(label, fg_hex, bg_hex, threshold, expected_light, expected_dark, gate, rows, failures):
    """Computes one pair for both themes and records pass/fail.

    Args:
        label: Human-readable pair name.
        fg_hex: (light_hex, dark_hex) foreground colours.
        bg_hex: (light_hex, dark_hex) background colours.
        threshold: Minimum contrast ratio for both themes.
        expected_light: The expected light ratio; a gated row fails when the
        computed ratio differs by more than TOLERANCE.
        expected_dark: The expected dark ratio, compared the same way.
        gate: Whether a failure here should fail the build.
        rows: Output row accumulator (mutated).
        failures: Failure message accumulator (mutated).
    """
    light_ratio = contrast_ratio(fg_hex[0], bg_hex[0])
    dark_ratio = contrast_ratio(fg_hex[1], bg_hex[1])

    light_ok = light_ratio >= threshold
    dark_ok = dark_ratio >= threshold
    light_matches_expected = abs(light_ratio - expected_light) <= TOLERANCE
    dark_matches_expected = abs(dark_ratio - expected_dark) <= TOLERANCE

    status = "ok" if (light_ok and dark_ok) else "FAIL"
    rows.append(
        (
            label,
            light_ratio,
            expected_light,
            light_matches_expected,
            dark_ratio,
            expected_dark,
            dark_matches_expected,
            status,
            gate,
        )
    )

    if not gate:
        return
    if not light_ok:
        failures.append(f"{label}: light {light_ratio:.2f} < {threshold}")
    if not dark_ok:
        failures.append(f"{label}: dark {dark_ratio:.2f} < {threshold}")
    if not light_matches_expected:
        failures.append(
            f"{label}: computed light {light_ratio:.2f} disagrees with expected {expected_light}"
        )
    if not dark_matches_expected:
        failures.append(
            f"{label}: computed dark {dark_ratio:.2f} disagrees with expected {expected_dark}"
        )


def main() -> int:
    light, dark = parse_tokens(TOKENS_PATH)
    rows = []
    failures = []

    all_pairs = TEXT_PAIRS + STROKE_PAIRS + FORBIDDEN_PAIRS + DECORATIVE_PAIRS + INFO_ONLY
    for label, fg, bg, threshold, expected_light, expected_dark, gate in all_pairs:
        check(
            label,
            (light[fg], dark[fg]),
            (light[bg], dark[bg]),
            threshold,
            expected_light,
            expected_dark,
            gate,
            rows,
            failures,
        )

    header = (
        f"{'pair':<24}{'light':>8}{'expected':>8}{'':>3}"
        f"{'dark':>8}{'expected':>8}{'':>3}{'status':>8}  gated"
    )
    print(header)
    print("-" * len(header))
    for label, lr, el, lm, dr, ed, dm, status, gate in rows:
        lmark = "" if lm else "*"
        dmark = "" if dm else "*"
        print(
            f"{label:<24}{lr:>8.2f}{el:>8.2f}{lmark:>3}"
            f"{dr:>8.2f}{ed:>8.2f}{dmark:>3}{status:>8}  {'yes' if gate else 'no'}"
        )

    if failures:
        print("\nfailures:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\nall gated pairs pass their threshold and match the expected numbers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
