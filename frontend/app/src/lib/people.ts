/** One link shown next to a person's name. */
export interface PersonLink {
  label: string;
  href: string;
  /** Shown on the About page only, not in the footer. */
  aboutOnly?: true;
}

/** A credited person. */
export interface Person {
  /** The full name. A name with a Polish letter is written with a \u escape, so the source stays ASCII. */
  name: string;
  /** The person's id in structured data, shared with their other sites; absent when they have none. */
  id?: string;
  /** The links shown after the name; the first is also the person's url in structured data. */
  links: PersonLink[];
}

/** The author of the current version. */
export const AUTHOR: Person = {
  name: "Piotr Krzysztof Lis",
  id: "https://piotrkrzysztof.dev/#piotr",
  links: [
    { label: "piotrkrzysztof.dev", href: "https://piotrkrzysztof.dev" },
    { label: "GitHub", href: "https://github.com/straightchlorine" },
    { label: "Codeberg", href: "https://codeberg.org/piotrkrzysztof", aboutOnly: true },
    { label: "LinkedIn", href: "https://www.linkedin.com/in/straightchlorine" },
  ],
};

/** The people of the current version. To credit one more person for it, add one entry here. */
export const CURRENT_VERSION: readonly Person[] = [AUTHOR];

/** The people of the 2025 group project, in alphabetical order by surname. A new name goes in its place. */
export const PROJECT_2025: readonly Person[] = [
  {
    name: "Wiktor Jarosi\u0144ski",
    links: [
      { label: "GitHub", href: "https://github.com/wiktorjarosinski" },
      {
        label: "LinkedIn",
        href: "https://www.linkedin.com/in/wiktor-jarosi%C5%84ski-719885244/",
      },
    ],
  },
  {
    name: "Daniel Ka\u0142mucki",
    links: [
      { label: "GitHub", href: "https://github.com/Mastermod1" },
      { label: "LinkedIn", href: "https://www.linkedin.com/in/danielkalmucki/" },
    ],
  },
  {
    name: "Jakub Kucharski",
    id: "https://piotrkrzysztof.dev/#jakub",
    links: [
      { label: "GitHub", href: "https://github.com/kubson2002k" },
      { label: "LinkedIn", href: "https://www.linkedin.com/in/jakub-kucharski-360811305/" },
    ],
  },
  AUTHOR,
];

/** The people of the 2025 project other than the author. */
export const CONTRIBUTORS_2025: readonly Person[] = PROJECT_2025.filter(
  (person) => person !== AUTHOR,
);

/** Joins names as "A, B and C". */
export function joinNames(names: readonly string[]): string {
  if (names.length < 2) {
    return names.join("");
  }
  return `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`;
}
