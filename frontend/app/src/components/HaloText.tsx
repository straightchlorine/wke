import type { SVGProps } from "react";
import { LABEL_FONT_PX } from "../lib/labelGeometry";

/** The width of the outline drawn behind graph text, in the frame's background colour, so lines behind the text do not cut through it. */
const HALO_STROKE_PX = 4;

export interface HaloTextProps extends SVGProps<SVGTextElement> {
  /** Draws the text heavier and in the full ink colour; otherwise it is regular weight and the second ink colour. */
  emphasised?: boolean;
}

/** SVG text in the graph's label style, with an outline behind the glyphs. Props other than `emphasised` go to the `<text>`. */
export function HaloText({ emphasised = false, ...rest }: HaloTextProps) {
  return (
    <text
      fontFamily="var(--font-sans)"
      fontSize={LABEL_FONT_PX}
      fontWeight={emphasised ? 500 : 400}
      fill={emphasised ? "var(--wke-ink)" : "var(--wke-ink-2)"}
      paintOrder="stroke"
      stroke="var(--wke-sheet)"
      strokeWidth={HALO_STROKE_PX}
      strokeLinejoin="round"
      {...rest}
    />
  );
}
