import { getDossier, getDossierMarkdown, requestDossier } from "./generated";
import type {
  ApiError,
  Citation,
  DossierContent,
  DossierMetadata,
  DossierResponse,
  Job,
  GetDossierData,
  GetDossierMarkdownData,
} from "./generated";

/**
 * The parts query for a whole dossier. Without it the API returns only the
 * sections and passages, and the page also needs the revision pin, the budget
 * and the citations.
 */
export const FULL_PARTS = "dossier,metadata,sources";

/** The dossier as the components read it: the API response with its three parts merged into one object. */
export type DossierView = DossierContent &
  DossierMetadata & {
    schema_version: DossierResponse["schema_version"];
    license_notice: string;
    citations: Citation[];
  };

/** Flattens a full dossier response into a DossierView, and throws when the metadata or sources part is missing. */
export function flattenDossier(response: DossierResponse): DossierView {
  const { metadata, sources } = response;
  if (metadata == null || sources == null) {
    throw new Error("dossier response lacks the metadata or sources part");
  }
  return {
    schema_version: response.schema_version,
    license_notice: response.license_notice,
    ...response.dossier,
    ...metadata,
    citations: sources,
  };
}

/** Splits a DossierView back into the nested API response, the shape the JSON download saves. */
export function nestDossier(view: DossierView): DossierResponse {
  const { schema_version, license_notice, sections, chunks, graph, citations, ...metadata } = view;
  return {
    schema_version,
    license_notice,
    dossier: { sections, chunks, graph },
    metadata,
    sources: citations,
  };
}

type FlatResult<T> = {
  data?: T;
  error?: ApiError;
  response?: Response;
};

/** Fetches a dossier as JSON with every part and returns the generated result with its data flattened. */
export async function getDossierView(options: {
  path: GetDossierData["path"];
  query?: Omit<NonNullable<GetDossierData["query"]>, "parts">;
}): Promise<FlatResult<DossierView>> {
  const result = await getDossier({ ...options, query: { ...options.query, parts: FULL_PARTS } });
  return {
    data: result.data ? flattenDossier(result.data) : undefined,
    error: result.error,
    response: result.response,
  };
}

/** Fetches a dossier as Markdown with every part, the text behind Copy and Download. */
export function getFullDossierMarkdown(options: {
  path: GetDossierMarkdownData["path"];
  query?: Omit<NonNullable<GetDossierMarkdownData["query"]>, "parts">;
}) {
  return getDossierMarkdown({ ...options, query: { ...options.query, parts: FULL_PARTS } });
}

/**
 * Posts a build request. A 200 body is an already built dossier and comes back
 * flattened, and a 202 body is the queued job.
 */
export async function requestDossierView(title: string): Promise<FlatResult<DossierView | Job>> {
  const result = await requestDossier({ body: { title }, query: { parts: FULL_PARTS } });
  const data = result.data;
  return {
    data: data && "schema_version" in data ? flattenDossier(data) : data,
    error: result.error,
    response: result.response,
  };
}
