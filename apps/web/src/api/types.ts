/**
 * Public API types for the web client.
 *
 * Everything is derived from the generated contract (`generated.ts`, produced from
 * packages/schemas/document-intelligence.v1.schema.json) so the UI cannot drift from the
 * backend's Pydantic models. Import types from here, not from `generated.ts`.
 */
import type { Citation, RecommendedAction, Requirement, Risk } from "./generated";

export type {
  AIInfo,
  AskRequest,
  AskResponse,
  Citation,
  ContentDescriptor,
  ContentFile,
  DocumentIntelligenceReport,
  DocumentList,
  DocumentMetadata,
  DocumentPages,
  DocumentRecord,
  DocumentRef,
  DocumentSource,
  ErrorBody,
  ErrorResponse,
  ExecutiveSummary,
  ExtractedPage,
  ExtractionSummary,
  HealthResponse,
  ImportFromWindchillRequest,
  KeyPoint,
  Limits,
  Provenance,
  RecommendedAction,
  Requirement,
  Risk,
  SourceProviderInfo,
  Specification,
  SummarySection,
  TokenUsage,
  VerificationSummary,
  WindchillDocument,
  WindchillDocumentList,
} from "./generated";

export type CitationStatus = Citation["status"];
export type Basis = Requirement["basis"];
export type Obligation = Requirement["obligation"];
export type Severity = Risk["severity"];
export type Priority = RecommendedAction["priority"];
