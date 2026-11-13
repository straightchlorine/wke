import { describe, expect, it } from "vitest";
import { loadDossier } from "../test/fixtures";
import { firstSentence, leadSentence } from "./lede";

describe("firstSentence", () => {
  it("returns the first sentence verbatim", () => {
    expect(
      firstSentence("Alan Turing (1912 - 1954) was a mathematician. He worked at Bletchley Park."),
    ).toBe("Alan Turing (1912 - 1954) was a mathematician.");
  });

  it("does not cut after an abbreviation or an initial", () => {
    expect(firstSentence("Dr. Smith moved to St. Louis with J. R. Ewing. Later he left.")).toBe(
      "Dr. Smith moved to St. Louis with J. R. Ewing.",
    );
  });

  it("does not cut after a single-letter abbreviation", () => {
    expect(firstSentence("He was born c. 1500 in Rome. He died young.")).toBe(
      "He was born c. 1500 in Rome.",
    );
  });

  it.each([
    ["Smith vs. Jones was filed in 1893. It ended.", "Smith vs. Jones was filed in 1893."],
    ["The U.S. Army grew. It shrank.", "The U.S. Army grew."],
    ["Some states, e.g. Ohio, agreed. Others did not.", "Some states, e.g. Ohio, agreed."],
    ["Acme Inc. Smith sued it. It lost.", "Acme Inc. Smith sued it."],
  ])("does not cut after a multi-letter abbreviation: %s", (text, expected) => {
    expect(firstSentence(text)).toBe(expected);
  });

  it("does not cut inside a date", () => {
    expect(firstSentence("She was born on July 19, 1860, in Fall River. She died in 1927.")).toBe(
      "She was born on July 19, 1860, in Fall River.",
    );
  });

  it("keeps a closing quote or bracket with the sentence", () => {
    expect(firstSentence('He said "no." Then he left.')).toBe('He said "no."');
  });

  it("returns the whole passage when it is one sentence", () => {
    expect(firstSentence("A single sentence.")).toBe("A single sentence.");
  });

  it("returns null when no sentence ends", () => {
    expect(firstSentence("no end here")).toBeNull();
  });
});

describe("leadSentence", () => {
  it("returns the first sentence of the first section's first passage", () => {
    const dossier = loadDossier();
    const chunk = dossier.chunks.find((c) => c.id === dossier.sections[0]!.chunk_ids[0])!;
    const sentence = leadSentence(dossier);
    expect(sentence).toBe(firstSentence(chunk.text));
    expect(sentence).not.toBeNull();
  });

  it("returns null when the first section has no passage", () => {
    const dossier = loadDossier();
    const sections = [{ ...dossier.sections[0]!, chunk_ids: [] }, ...dossier.sections.slice(1)];
    expect(leadSentence({ ...dossier, sections })).toBeNull();
    expect(leadSentence({ ...dossier, sections: [] })).toBeNull();
  });
});
