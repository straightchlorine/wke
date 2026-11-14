"""Model summaries with one fidelity defect each, from labelled dossier builds."""

from __future__ import annotations

# name -> (summary, source, a fragment of the evidence the gate returns).
DEFECTIVE_SUMMARIES: dict[str, tuple[str, str, str]] = {
    "swapped roles": (
        "SpaceX selected SpaceX in 2021 to develop a lunar lander .",
        "In April 2021, NASA selected SpaceX to develop a modified Starship as a lunar lander.",
        "'SpaceX selected SpaceX'",
    ),
    "quotation as narration": (
        "Hitler's National Socialist movement will go on for 1,000 years! He took power .",
        "At the risk of appearing to talk nonsense, I tell you that the National Socialist "
        "movement will go on for 1,000 years! Hitler and his allies began to suppress the "
        "remaining opposition.",
        "a quotation from the source is stated as fact",
    ),
    "merged facts and reversed location": (
        "To Catch a Predator shot in New Orleans and Sri Lanka . Filming shot on-location "
        "in Florida and New York . The producers shot in Louisiana tax credits .",
        "Principal photography began in New Orleans in early February 2025. Oppenheim wanted "
        "to shoot Primetime on-location in his native Florida, but Louisiana was chosen "
        "because of its tax incentives. Filming also took place in New York and Sri Lanka. "
        "To Catch a Predator is commonly viewed in the modern day.",
        "short phrases of the text appear nowhere in the source",
    ),
    "cut sentence with a stray period": (
        "Limonene is used as a solvent for cleaning purposes, such. as it is produced from "
        "a renewable source .",
        "Limonene is used as a solvent for cleaning purposes, as it is produced from a "
        "renewable source.",
        "a sentence is cut inside: 'such. as it is'",
    ),
    "repeated fact": (
        "The federation organised national trials in May . 11-member squad for Games . "
        "The federation announced 11-member squad for the Games .",
        "The federation organised national trials in May, and announced 11-member squad "
        "for the Games.",
        "a sentence is repeated inside another: '11-member squad for Games .'",
    ),
    "misdated event": (
        "Bertha Manchester was found hacked to death in her kitchen in 1894 .",
        "Bertha Manchester was found hacked to death in her kitchen in 1891. "
        "Lizzie Borden was convicted of the murders in 1894.",
        "the number 1894",
    ),
}
