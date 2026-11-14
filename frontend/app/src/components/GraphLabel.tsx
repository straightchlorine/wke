import { LABEL_LINE_HEIGHT, type LabelBox } from "../lib/labelGeometry";
import { textBaselineY, textOriginX } from "../lib/labelText";
import { HaloText } from "./HaloText";

export interface GraphLabelProps {
  label: LabelBox;
  /** Draws the name heavier and darker. */
  emphasised: boolean;
  /** Keeps the name and its leader line in place but not visible. */
  hidden: boolean;
}

/** A dot's permanent name, with the leader line that joins it to a dot it stands away from. */
export function GraphLabel({ label, emphasised, hidden }: GraphLabelProps) {
  const x = textOriginX(label);
  const visibility = hidden ? "hidden" : undefined;
  return (
    <>
      {label.leader ? (
        <line
          data-plate-leader=""
          x1={label.leader.x1}
          y1={label.leader.y1}
          x2={label.leader.x2}
          y2={label.leader.y2}
          stroke="var(--wke-rule-strong)"
          strokeWidth={1}
          visibility={visibility}
          pointerEvents="none"
        />
      ) : null}
      <HaloText
        data-plate-label={label.leader ? "leader" : ""}
        data-label-relaxed={label.relaxed ?? undefined}
        visibility={visibility}
        x={x}
        textAnchor={label.textAnchor ?? "start"}
        y={textBaselineY(label)}
        emphasised={emphasised}
        pointerEvents="none"
      >
        {/* A native SVG tooltip needs a <title> child. fullText is set only when the name was cut, so
            the tooltip shows the whole article title. The visible text has its own tspan, so code
            that reads it does not pick up the title. */}
        {label.fullText ? <title>{label.fullText}</title> : null}
        {label.lines ? (
          <>
            <tspan x={x}>{label.lines[0]}</tspan>
            <tspan x={x} dy={LABEL_LINE_HEIGHT}>
              {label.lines[1]}
            </tspan>
          </>
        ) : (
          <tspan>{label.text}</tspan>
        )}
      </HaloText>
    </>
  );
}
