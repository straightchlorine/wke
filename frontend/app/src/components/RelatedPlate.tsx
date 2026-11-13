import { useNavigate } from "@tanstack/react-router";
import type { DossierView } from "../api/dossier";
import type { Budget } from "../lib/budget";
import { formatNumber } from "../lib/format";
import type { ConceptGraphNode } from "../lib/graphNodeInfo";
import { useMediaQuery } from "../lib/hooks/useMediaQuery";
import { usePlateWidth } from "../lib/hooks/usePlateWidth";
import { namesShownText } from "../lib/plateLabels";
import { slugify } from "../lib/slug";
import { ConceptGraph } from "./ConceptGraph";
import { Plate } from "./Plate";

const RELATED_GUIDE = [
  { label: "Size", value: "similarity to this article" },
  { label: "Lines", value: "each article's two most similar neighbours" },
  { label: "Hull", value: "the related set" },
  { label: "Method", value: "similarity 0.35 or more" },
];
const STRUCTURAL_GUIDE = [
  { label: "Size", value: "not measured" },
  { label: "Lines", value: "the article's own Wikipedia links" },
  { label: "Hull", value: "the related set" },
  { label: "Method", value: "none; no embeddings ran" },
];

export interface RelatedPlateProps {
  dossier: DossierView;
  /** The dossier's related articles as graph nodes. */
  nodes: ConceptGraphNode[];
  budget: Budget;
}

/** The framed graph of the articles related to the dossier's topic. Selecting a node opens that article's dossier. */
export function RelatedPlate({ dossier, nodes, budget }: RelatedPlateProps) {
  const navigate = useNavigate();
  const [setFrameEl, plateWidth] = usePlateWidth();
  const touchOnly = useMediaQuery("(hover: none)");
  const isNarrowViewport = useMediaQuery("(max-width: 599px)");
  const structural = dossier.build.analysis === "structural";
  const relatedCount = nodes.filter((node) => node.role !== "seed").length;
  // On a short landscape window the frame is capped to the window height less the header and gaps,
  // so the whole frame is on screen. The record rows follow under it.
  return (
    <div
      ref={setFrameEl}
      className="mx-auto mb-6 max-w-[520px] min-[900px]:max-w-none short:max-w-[calc(100dvh-96px)]"
    >
      <Plate
        hud={structural ? "related, by Wikipedia links" : "related, by Wikipedia search"}
        captionLead="Plate 1."
        captionBody={
          structural
            ? `${formatNumber(relatedCount)} related articles from Wikipedia's own links. Select a node to open its dossier.`
            : `${formatNumber(relatedCount)} articles Wikipedia search lists as similar. Select a node to open its dossier.`
        }
        guide={structural ? STRUCTURAL_GUIDE : RELATED_GUIDE}
        guideNote={namesShownText("related", touchOnly)}
      >
        <ConceptGraph
          nodes={nodes}
          edges={dossier.graph.edges}
          variant="related"
          width={plateWidth}
          height={plateWidth}
          compact={isNarrowViewport}
          onOpen={(id) => {
            const node = dossier.graph.nodes.find((n) => n.id === id);
            if (node) {
              void navigate({
                to: "/t/$slug",
                params: { slug: slugify(node.title) },
                search: { budget },
              });
            }
          }}
          hrefSuffix={`?budget=${budget}`}
          ariaLabel={`Articles related to ${dossier.topic.title}, ${structural ? "by Wikipedia links" : "by Wikipedia search"}.`}
        />
      </Plate>
    </div>
  );
}
