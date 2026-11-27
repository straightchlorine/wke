import { createFileRoute } from "@tanstack/react-router";
import { CURRENT_VERSION, PROJECT_2025, joinNames } from "../lib/people";
import { REPO_URL } from "../lib/links";
import { ABOUT_DESCRIPTION, aboutJsonLd, useSeo } from "../lib/seo";

export const Route = createFileRoute("/about")({
  component: About,
});

const PROSE = "mt-4 max-w-(--container-prose) font-serif text-16 text-ink-2 lg:text-18";

const GROUPS = [
  { id: "current", label: "Current version", people: CURRENT_VERSION },
  { id: "2025", label: "2025 project", people: PROJECT_2025 },
];

function About() {
  useSeo({
    title: "About",
    description: ABOUT_DESCRIPTION,
    path: "/about",
    jsonLd: aboutJsonLd(),
  });
  return (
    <div className="py-8">
      <section className="border-b-(length:--hairline) border-rule-strong pb-6">
        <h1 tabIndex={-1} className="font-serif text-36 text-ink lg:text-44">
          About
        </h1>
        <p className={PROSE}>
          Wikipedia Knowledge Explorer began in 2025 as a university project by{" "}
          {joinNames(PROJECT_2025.map((person) => person.name))}. The current version is a rewrite
          by {joinNames(CURRENT_VERSION.map((person) => person.name))}.
        </p>
      </section>
      {GROUPS.map((group) => (
        <section key={group.id} aria-labelledby={`h-${group.id}`} className="py-6">
          <h2 id={`h-${group.id}`} className="font-serif text-22 font-medium text-ink">
            {group.label}
          </h2>
          <div className="mt-3 max-w-(--container-prose)">
            <ul aria-label={group.label} className="border-t-(length:--hairline) border-ink">
              {group.people.map((person) => (
                <li
                  key={person.name}
                  className="border-b-(length:--hairline) border-rule-strong py-3"
                >
                  <p className="font-serif text-16 text-ink">{person.name}</p>
                  <p className="mt-1 flex gap-x-5 text-13">
                    {person.links.map((link) => (
                      <a key={link.href} href={link.href} className="hit-44 text-accent">
                        {link.label}
                      </a>
                    ))}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        </section>
      ))}
      <section
        aria-labelledby="h-licence"
        className="border-t-(length:--hairline) border-rule-strong py-6"
      >
        <h2 id="h-licence" className="font-serif text-22 font-medium text-ink">
          Licence
        </h2>
        <p className={PROSE}>The code is MIT. Text from Wikipedia is CC BY-SA 4.0.</p>
        <p className="mt-3 text-13 pointer-coarse:mt-5">
          <a href="https://www.wikipedia.org/" className="hit-44 text-accent">
            wikipedia.org
          </a>
          ,{" "}
          <a href="https://creativecommons.org/licenses/by-sa/4.0/" className="hit-44 text-accent">
            licence
          </a>
          ,{" "}
          <a href={REPO_URL} className="hit-44 text-accent">
            repository
          </a>
        </p>
      </section>
    </div>
  );
}
