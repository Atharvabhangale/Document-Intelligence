/* eslint-disable */
/**
 * Generated — do not edit.
 *
 * Source: packages/schemas/document-intelligence.v1.schema.json
 * Generated from apps/api/src/docintel/schemas/report.py — do not edit by hand. Schema version 1.0.
 * Regenerate with `npm run gen:types` (apps/web) after the backend contract changes.
 */

/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "DocumentSource".
 */
export type DocumentSource = "windchill" | "upload";

/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "AIInfo".
 */
export interface AIInfo {
  configured: boolean;
  developmentOnly: boolean;
  model: string;
  provider: string;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "AskRequest".
 */
export interface AskRequest {
  question: string;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "AskResponse".
 */
export interface AskResponse {
  answer: string;
  answerId: string;
  answerable: boolean;
  citations: Citation[];
  documentId: string;
  provenance: Provenance;
  question: string;
  schemaVersion?: "1.0";
  verification: VerificationSummary;
  warnings: string[];
}
/**
 * A source reference produced by the model and checked against the extracted text.
 *
 * - ``verified``: quote found on the cited page.
 * - ``relocated``: quote found, but on a different page (``matched_page``).
 * - ``approximate``: close (fuzzy) match on the cited or another page.
 * - ``unverified``: quote not found in the document.
 * - ``invalid_page``: cited page does not exist and the quote was not found elsewhere.
 *
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "Citation".
 */
export interface Citation {
  id: string;
  matchScore: number;
  matchedPage?: number | null;
  page: number;
  quote: string;
  status: "verified" | "relocated" | "approximate" | "unverified" | "invalid_page";
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "Provenance".
 */
export interface Provenance {
  attempts: number;
  cached?: boolean;
  durationMs: number;
  extractor: string;
  generatedAt: string;
  model: string;
  pipelineVersion: string;
  promptId: string;
  promptVersion: string;
  provider: string;
  schemaVersion?: "1.0";
  task: "summarize" | "requirements" | "risks" | "ask";
  usage: TokenUsage;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "TokenUsage".
 */
export interface TokenUsage {
  cacheReadInputTokens?: number | null;
  inputTokens?: number | null;
  outputTokens?: number | null;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "VerificationSummary".
 */
export interface VerificationSummary {
  approximate: number;
  invalidPage: number;
  itemsTotal: number;
  itemsWithoutVerifiedSource: number;
  relocated: number;
  totalCitations: number;
  unverified: number;
  verified: number;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "ContentDescriptor".
 */
export interface ContentDescriptor {
  filename: string;
  mediaType: string;
  sizeBytes?: number | null;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "ContentFile".
 */
export interface ContentFile {
  filename: string;
  mediaType?: string;
  role?: string;
  sha256: string;
  sizeBytes: number;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "DocumentIntelligenceReport".
 */
export interface DocumentIntelligenceReport {
  actions: RecommendedAction[];
  citations: Citation[];
  document: DocumentRef;
  limitations: string[];
  provenance: Provenance;
  reportId: string;
  requirements: Requirement[];
  risks: Risk[];
  schemaVersion?: "1.0";
  specifications: Specification[];
  summary: SummarySection;
  task?: "summarize";
  verification: VerificationSummary;
  warnings: string[];
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "RecommendedAction".
 */
export interface RecommendedAction {
  action: string;
  basis: "explicit" | "inferred";
  citationIds: string[];
  id: string;
  priority: "high" | "medium" | "low";
  rationale: string;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "DocumentRef".
 */
export interface DocumentRef {
  content: ContentFile;
  developmentOnly: boolean;
  documentId: string;
  metadata: DocumentMetadata;
  pageCount: number;
  source: DocumentSource;
  sourceProvider: string;
}
/**
 * Business metadata of a document (Windchill-like for WTDocuments).
 *
 * Comes from the document provider — NEVER from the LLM.
 *
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "DocumentMetadata".
 */
export interface DocumentMetadata {
  documentType?: string | null;
  iteration?: string | null;
  location?: string | null;
  modifiedBy?: string | null;
  modifiedDate?: string | null;
  name: string;
  number?: string | null;
  revision?: string | null;
  sourceRef?: string | null;
  state?: string | null;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "Requirement".
 */
export interface Requirement {
  basis: "explicit" | "inferred";
  category?: string | null;
  citationIds: string[];
  id: string;
  obligation: "mandatory" | "recommended" | "permitted" | "informational";
  statement: string;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "Risk".
 */
export interface Risk {
  basis: "explicit" | "inferred";
  citationIds: string[];
  description: string;
  id: string;
  severity: "high" | "medium" | "low";
  title: string;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "Specification".
 */
export interface Specification {
  citationIds: string[];
  context?: string | null;
  id: string;
  parameter: string;
  unit?: string | null;
  value: string;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "SummarySection".
 */
export interface SummarySection {
  executive: ExecutiveSummary;
  keyPoints: KeyPoint[];
  purpose: string;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "ExecutiveSummary".
 */
export interface ExecutiveSummary {
  citationIds: string[];
  text: string;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "KeyPoint".
 */
export interface KeyPoint {
  citationIds: string[];
  id: string;
  text: string;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "DocumentList".
 */
export interface DocumentList {
  items: DocumentRecord[];
}
/**
 * A document registered with the intelligence service (uploaded or loaded from a provider).
 *
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "DocumentRecord".
 */
export interface DocumentRecord {
  content: ContentFile;
  createdAt: string;
  developmentOnly: boolean;
  extraction: ExtractionSummary;
  id: string;
  metadata: DocumentMetadata;
  source: DocumentSource;
  sourceProvider: string;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "ExtractionSummary".
 */
export interface ExtractionSummary {
  extractor: string;
  pageCount: number;
  pagesNeedingOcr: number[];
  pagesWithText: number;
  totalChars: number;
  warnings?: string[];
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "DocumentPages".
 */
export interface DocumentPages {
  documentId: string;
  pages: ExtractedPage[];
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "ExtractedPage".
 */
export interface ExtractedPage {
  charCount: number;
  hasTextLayer: boolean;
  needsOcr: boolean;
  number: number;
  text: string;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "ErrorBody".
 */
export interface ErrorBody {
  code: string;
  details?: {
    [k: string]: unknown | undefined;
  } | null;
  message: string;
  retryable: boolean;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "ErrorResponse".
 */
export interface ErrorResponse {
  error: ErrorBody;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "HealthResponse".
 */
export interface HealthResponse {
  ai: AIInfo;
  limits: Limits;
  status?: "ok";
  version: string;
  windchill: SourceProviderInfo;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "Limits".
 */
export interface Limits {
  maxPages: number;
  maxQuestionChars: number;
  maxUploadMb: number;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "SourceProviderInfo".
 */
export interface SourceProviderInfo {
  developmentOnly: boolean;
  name: string;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "ImportFromWindchillRequest".
 */
export interface ImportFromWindchillRequest {
  reference: string;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "RequirementsReport".
 */
export interface RequirementsReport {
  citations: Citation[];
  document: DocumentRef;
  limitations: string[];
  provenance: Provenance;
  reportId: string;
  requirements: Requirement[];
  schemaVersion?: "1.0";
  task?: "requirements";
  verification: VerificationSummary;
  warnings: string[];
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "RisksReport".
 */
export interface RisksReport {
  citations: Citation[];
  document: DocumentRef;
  limitations: string[];
  provenance: Provenance;
  reportId: string;
  risks: Risk[];
  schemaVersion?: "1.0";
  task?: "risks";
  verification: VerificationSummary;
  warnings: string[];
}
/**
 * A document as described by the provider (metadata only, no content bytes).
 *
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "WindchillDocument".
 */
export interface WindchillDocument {
  developmentOnly: boolean;
  metadata: DocumentMetadata;
  primaryContent?: ContentDescriptor | null;
  reference: string;
}
/**
 * This interface was referenced by `DocumentIntelligenceContracts`'s JSON-Schema
 * via the `definition` "WindchillDocumentList".
 */
export interface WindchillDocumentList {
  items: WindchillDocument[];
  provider: SourceProviderInfo;
}
