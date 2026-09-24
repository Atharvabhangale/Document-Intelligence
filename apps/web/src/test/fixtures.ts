/**
 * Realistic fixtures for SOP-00123 "Machine Maintenance SOP" A.3 (the synthetic mock Windchill
 * sample). Quotes are taken from the sample PDF's extracted text; C9 (unverified), C12
 * (approximate) and C15 (invalid page) simulate model errors the pipeline flags.
 */
import type {
  AskResponse,
  Citation,
  DocumentIntelligenceReport,
  DocumentPages,
  DocumentRecord,
  HealthResponse,
  Provenance,
  VerificationSummary,
  WindchillDocumentList,
} from "../api/types";

export const DOCUMENT_ID = "5f0c1d2e3a4b5c6d7e8f9a0b1c2d3e4f";

export const health: HealthResponse = {
  status: "ok",
  version: "0.1.0",
  ai: {
    provider: "anthropic",
    model: "claude-haiku-4-5-20251001",
    configured: true,
    developmentOnly: false,
  },
  windchill: { name: "mock-windchill", developmentOnly: true },
  limits: { maxUploadMb: 25, maxPages: 300, maxQuestionChars: 1000 },
};

export const documentRecord: DocumentRecord = {
  id: DOCUMENT_ID,
  source: "windchill",
  sourceProvider: "mock-windchill",
  developmentOnly: true,
  metadata: {
    number: "SOP-00123",
    name: "Machine Maintenance SOP",
    revision: "A",
    iteration: "3",
    state: "Released",
    location: "Manufacturing SOP Library / Maintenance",
    documentType: "SOP",
    modifiedDate: "2026-03-14T09:30:00Z",
    modifiedBy: "J. Alvarez",
    sourceRef: "mock://wtdocument/SOP-00123/A.3",
  },
  content: {
    filename: "SOP-00123_Machine_Maintenance_A.3.pdf",
    mediaType: "application/pdf",
    sizeBytes: 18_734,
    sha256: "9b0f3c8e2d1a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4",
    role: "primary",
  },
  extraction: {
    pageCount: 5,
    pagesWithText: 5,
    pagesNeedingOcr: [],
    totalChars: 17_912,
    extractor: "pdfplumber 0.11.10",
    warnings: [],
  },
  createdAt: "2026-09-24T10:12:00Z",
};

export const citations: Citation[] = [
  {
    id: "C1",
    page: 1,
    quote:
      "This procedure defines the monthly preventive maintenance (PM) of CNC vertical machining centers (VMCs).",
    status: "verified",
    matchedPage: 1,
    matchScore: 1,
  },
  {
    id: "C2",
    page: 2,
    quote:
      "The machine shall be locked out and tagged out in accordance with SOP-00087 before any guard is removed",
    status: "verified",
    matchedPage: 2,
    matchScore: 1,
  },
  {
    id: "C3",
    page: 2,
    quote:
      "Safety glasses with side shields and safety shoes (S3) are required for all tasks in this SOP.",
    status: "verified",
    matchedPage: 2,
    matchScore: 1,
  },
  {
    id: "C4",
    page: 3,
    quote: "The pressure shall be 55–65 bar.",
    status: "verified",
    matchedPage: 3,
    matchScore: 1,
  },
  {
    id: "C5",
    page: 3,
    quote: "The temperature shall be 40–60 °C.",
    status: "verified",
    matchedPage: 3,
    matchScore: 1,
  },
  {
    id: "C6",
    page: 4,
    quote: "The clamping force shall be at least 12 kN (nominal 14 kN).",
    status: "verified",
    matchedPage: 4,
    matchScore: 1,
  },
  {
    id: "C7",
    page: 3,
    quote: "The hydraulic return filter element shall be replaced every 500 operating hours",
    status: "relocated",
    matchedPage: 4,
    matchScore: 1,
  },
  {
    id: "C8",
    page: 4,
    quote:
      "Inspect filters regularly, including the coolant, hydraulic and electrical cabinet air filters, and replace them when they are dirty.",
    status: "verified",
    matchedPage: 4,
    matchScore: 1,
  },
  {
    id: "C9",
    page: 4,
    quote: "Spindle runout shall not exceed 0.005 mm",
    status: "unverified",
    matchedPage: null,
    matchScore: 0.41,
  },
  {
    id: "C10",
    page: 4,
    quote: "tension the belt in accordance with WI-2210 Spindle Belt Tensioning",
    status: "verified",
    matchedPage: 4,
    matchScore: 1,
  },
  {
    id: "C11",
    page: 5,
    quote: "Records shall be retained for 3 years from the date of the PM.",
    status: "verified",
    matchedPage: 5,
    matchScore: 1,
  },
  {
    id: "C12",
    page: 5,
    quote: "The Maintenance Supervisor shall review and sign the checklist within two working days",
    status: "approximate",
    matchedPage: 5,
    matchScore: 0.91,
  },
  {
    id: "C13",
    page: 2,
    quote: "Compressed air shall not be used to blow chips out of the machine",
    status: "verified",
    matchedPage: 2,
    matchScore: 1,
  },
  {
    id: "C14",
    page: 4,
    quote: "verify the spindle runout at the spindle nose and at 300 mm from the spindle nose",
    status: "verified",
    matchedPage: 4,
    matchScore: 1,
  },
  {
    id: "C15",
    page: 7,
    quote: "Oil samples shall be sent for laboratory analysis at every oil change",
    status: "invalid_page",
    matchedPage: null,
    matchScore: 0,
  },
  {
    id: "C16",
    page: 4,
    quote: "The air pressure at the machine regulator shall be 5.5–6.5 bar.",
    status: "verified",
    matchedPage: 4,
    matchScore: 1,
  },
  {
    id: "C17",
    page: 5,
    quote: "The machine may be returned to production only when all criteria in Table 2 are met",
    status: "verified",
    matchedPage: 5,
    matchScore: 1,
  },
  {
    id: "C18",
    page: 3,
    quote: "Instruments with an expired calibration must not be used.",
    status: "verified",
    matchedPage: 3,
    matchScore: 1,
  },
];

export const verification: VerificationSummary = {
  totalCitations: 18,
  verified: 14,
  relocated: 1,
  approximate: 1,
  unverified: 1,
  invalidPage: 1,
  itemsTotal: 30,
  itemsWithoutVerifiedSource: 4,
};

export const provenance: Provenance = {
  task: "summarize",
  promptId: "summarize",
  promptVersion: "1",
  provider: "anthropic",
  model: "claude-haiku-4-5-20251001",
  pipelineVersion: "1.0.0",
  schemaVersion: "1.0",
  extractor: "pdfplumber 0.11.10",
  generatedAt: "2026-09-24T10:15:00Z",
  durationMs: 18_420,
  attempts: 1,
  usage: { inputTokens: 9_412, outputTokens: 2_873, cacheReadInputTokens: null },
  cached: false,
};

export const report: DocumentIntelligenceReport = {
  schemaVersion: "1.0",
  task: "summarize",
  reportId: "a1b2c3d4e5f60718293a4b5c6d7e8f90",
  document: {
    documentId: DOCUMENT_ID,
    source: documentRecord.source,
    sourceProvider: documentRecord.sourceProvider,
    developmentOnly: documentRecord.developmentOnly,
    metadata: documentRecord.metadata,
    content: documentRecord.content,
    pageCount: 5,
  },
  summary: {
    purpose:
      "Defines the monthly preventive maintenance of the VMC-850 series CNC vertical machining centers in Machining Cells 1–3 at the Greenfield Plant.",
    executive: {
      text: "SOP-00123 specifies how maintenance technicians perform monthly preventive maintenance on VMC-850 machining centers: running checks of the hydraulic, lubrication, coolant, spindle and pneumatic systems, lockout/tagout isolation, interval-based replacements and return to service. Readings are checked against defined acceptance criteria before the machine is released to production.",
      citationIds: ["C1", "C2", "C17"],
    },
    keyPoints: [
      {
        id: "KP-001",
        text: "All work inside the enclosure or the electrical cabinet requires lockout/tagout per SOP-00087.",
        citationIds: ["C2"],
      },
      {
        id: "KP-002",
        text: "Hydraulic pressure must be 55–65 bar and oil temperature 40–60 °C during the running checks.",
        citationIds: ["C4", "C5"],
      },
      {
        id: "KP-003",
        text: "A drawbar clamping force below 12 kN takes the spindle out of service until the spring pack is replaced.",
        citationIds: ["C6"],
      },
      {
        id: "KP-004",
        text: "The hydraulic return filter is replaced every 500 operating hours of the hydraulic pump.",
        citationIds: ["C7"],
      },
      {
        id: "KP-005",
        text: "PM records are retained for 3 years from the date of the PM.",
        citationIds: ["C11"],
      },
    ],
  },
  requirements: [
    {
      id: "REQ-001",
      statement:
        "Lock out and tag out the machine in accordance with SOP-00087 before removing any guard or working inside the enclosure or electrical cabinet.",
      basis: "explicit",
      obligation: "mandatory",
      category: "Safety",
      citationIds: ["C2"],
    },
    {
      id: "REQ-002",
      statement: "Wear safety glasses with side shields and safety shoes (S3) for all tasks.",
      basis: "explicit",
      obligation: "mandatory",
      category: "PPE",
      citationIds: ["C3"],
    },
    {
      id: "REQ-003",
      statement: "Do not use compressed air to blow chips out of the machine.",
      basis: "explicit",
      obligation: "mandatory",
      category: "Safety",
      citationIds: ["C13"],
    },
    {
      id: "REQ-004",
      statement: "The hydraulic system pressure shall be 55–65 bar at gauge PG-1.",
      basis: "explicit",
      obligation: "mandatory",
      category: "Inspection",
      citationIds: ["C4"],
    },
    {
      id: "REQ-005",
      statement: "Replace the hydraulic return filter element every 500 operating hours.",
      basis: "explicit",
      obligation: "mandatory",
      category: "Maintenance",
      citationIds: ["C7"],
    },
    {
      id: "REQ-006",
      statement: "Inspect filters regularly and replace them when they are dirty.",
      basis: "inferred",
      obligation: "recommended",
      category: "Maintenance",
      citationIds: ["C8"],
    },
    {
      id: "REQ-007",
      statement: "Retain records for 3 years from the date of the PM.",
      basis: "explicit",
      obligation: "mandatory",
      category: "Records",
      citationIds: ["C11"],
    },
    {
      id: "REQ-008",
      statement:
        "The Maintenance Supervisor shall review and sign the completed checklist within 2 working days.",
      basis: "explicit",
      obligation: "mandatory",
      category: "Documentation",
      citationIds: ["C12"],
    },
    {
      id: "REQ-009",
      statement: "Do not use instruments with an expired calibration.",
      basis: "explicit",
      obligation: "mandatory",
      category: "Calibration",
      citationIds: ["C18"],
    },
    {
      id: "REQ-010",
      statement:
        "Spindle runout is measured at the spindle nose and at 300 mm, but no acceptance tolerance is stated.",
      basis: "inferred",
      obligation: "informational",
      category: null,
      citationIds: ["C14"],
    },
    {
      id: "REQ-011",
      statement: "Send hydraulic oil samples for laboratory analysis at every oil change.",
      basis: "explicit",
      obligation: "mandatory",
      category: "Maintenance",
      citationIds: ["C15"],
    },
  ],
  specifications: [
    {
      id: "SPEC-001",
      parameter: "Hydraulic system pressure",
      value: "55–65",
      unit: "bar",
      context: "At gauge PG-1, hydraulic unit running for at least 30 minutes",
      citationIds: ["C4"],
    },
    {
      id: "SPEC-002",
      parameter: "Hydraulic oil temperature",
      value: "40–60",
      unit: "°C",
      context: "Tank thermometer during running checks",
      citationIds: ["C5"],
    },
    {
      id: "SPEC-003",
      parameter: "Drawbar clamping force",
      value: "≥ 12 (nominal 14)",
      unit: "kN",
      context: "Lowest of three readings",
      citationIds: ["C6"],
    },
    {
      id: "SPEC-004",
      parameter: "Pneumatic supply pressure",
      value: "5.5–6.5",
      unit: "bar",
      context: "At the machine regulator",
      citationIds: ["C16"],
    },
    {
      id: "SPEC-005",
      parameter: "Hydraulic return filter replacement interval",
      value: "500",
      unit: "operating hours",
      context: "Hydraulic pump operating hours",
      citationIds: ["C7"],
    },
    {
      id: "SPEC-006",
      parameter: "Spindle runout",
      value: "≤ 0.005",
      unit: "mm",
      context: null,
      citationIds: ["C9"],
    },
  ],
  risks: [
    {
      id: "RISK-001",
      title: "Conflicting filter replacement instructions",
      description:
        "Step 7.4.6 says to replace filters when they are dirty, which conflicts with the fixed 500-hour interval for the hydraulic return filter in step 7.4.2 and may lead to inconsistent practice.",
      severity: "medium",
      basis: "explicit",
      citationIds: ["C8", "C7"],
    },
    {
      id: "RISK-002",
      title: "Hazardous stored energy during maintenance",
      description:
        "The machine contains electrical, hydraulic, pneumatic and stored mechanical energy; skipping isolation or accumulator bleed-down exposes technicians to serious injury.",
      severity: "high",
      basis: "explicit",
      citationIds: ["C2"],
    },
    {
      id: "RISK-003",
      title: "No acceptance tolerance for spindle runout",
      description:
        "Runout readings are recorded but no limit is given, so technicians cannot decide whether the spindle passes.",
      severity: "medium",
      basis: "inferred",
      citationIds: ["C14"],
    },
    {
      id: "RISK-004",
      title: "Referenced work instruction not listed",
      description:
        "WI-2210 is referenced for belt tensioning but is missing from the References section.",
      severity: "low",
      basis: "inferred",
      citationIds: ["C10"],
    },
  ],
  actions: [
    {
      id: "ACT-001",
      action: "Define an acceptance tolerance for spindle runout",
      rationale:
        "Step 7.2.7 requires the measurement, but Table 2 has no acceptance criterion for it.",
      priority: "high",
      basis: "inferred",
      citationIds: ["C14"],
    },
    {
      id: "ACT-002",
      action: "Align the general filter instruction with the 500-hour interval",
      rationale:
        "Steps 7.4.2 and 7.4.6 give different criteria for replacing the hydraulic filter.",
      priority: "medium",
      basis: "inferred",
      citationIds: ["C8", "C7"],
    },
    {
      id: "ACT-003",
      action: "Add WI-2210 to the References section",
      rationale: "The belt tensioning step depends on a work instruction that is not listed.",
      priority: "low",
      basis: "inferred",
      citationIds: [],
    },
  ],
  citations,
  verification,
  limitations: [
    "Tables 1 and 2 were interpreted from extracted text; column alignment may be imperfect.",
  ],
  warnings: ["4 items have no verified source."],
  provenance,
};

/** The fixture report with every list emptied (for empty-state tests). */
export function emptyReport(): DocumentIntelligenceReport {
  return {
    ...report,
    summary: { ...report.summary, keyPoints: [] },
    requirements: [],
    specifications: [],
    risks: [],
    actions: [],
    citations: [],
    limitations: [],
    warnings: [],
    verification: {
      totalCitations: 0,
      verified: 0,
      relocated: 0,
      approximate: 0,
      unverified: 0,
      invalidPage: 0,
      itemsTotal: 1,
      itemsWithoutVerifiedSource: 1,
    },
  };
}

export const pages: DocumentPages = {
  documentId: DOCUMENT_ID,
  pages: [
    {
      number: 1,
      text: "NORTHWIND INDUSTRIAL SOP-00123 | Rev. A.3 | Released\n1 Purpose\nThis procedure defines the monthly preventive maintenance (PM) of CNC vertical machining centers (VMCs). Its\nobjectives are to keep the machines within their specified operating conditions.",
      charCount: 230,
      hasTextLayer: true,
      needsOcr: false,
    },
    {
      number: 2,
      text: "5.1 The machine shall be locked out and tagged out in accordance with SOP-00087 before any guard is\nremoved or any work is performed inside the machine enclosure or the electrical cabinet.\n5.3 Safety glasses with side shields and safety shoes (S3) are required for all tasks in this SOP.\n5.5 Compressed air shall not be used to blow chips out of the machine or to clean clothing or skin.",
      charCount: 380,
      hasTextLayer: true,
      needsOcr: false,
    },
    {
      number: 3,
      text: "7.1.4 Confirm that the torque wrench and the drawbar force gauge carry a valid calibration label. Instruments with\nan expired calibration must not be used.\n7.2.1 Hydraulic pressure: The pressure shall be 55–65 bar.\n7.2.2 Hydraulic oil temperature: The temperature shall be\n40–60 °C.",
      charCount: 260,
      hasTextLayer: true,
      needsOcr: false,
    },
    {
      number: 4,
      text: "7.2.6 The clamping force shall be at least 12 kN (nominal 14 kN).\n7.2.7 Spindle runout: verify the spindle runout at the spindle nose and at 300 mm from the spindle\nnose while rotating the spindle slowly by hand.\n7.2.8 The air pressure at the machine regulator shall be 5.5–6.5 bar.\n7.4.2 Hydraulic return filter: The hydraulic return filter element shall be replaced every 500 operating hours of the\nhydraulic pump.\n7.4.3 If adjustment is required, tension the belt in accordance with WI-2210 Spindle\nBelt Tensioning.\n7.4.6 Filters: Inspect filters regularly, including the coolant, hydraulic and electrical cabinet air filters, and replace\nthem when they are dirty.",
      charCount: 640,
      hasTextLayer: true,
      needsOcr: false,
    },
    {
      number: 5,
      text: "8.1 The machine may be returned to production only when all criteria in Table 2 are met.\n8.3 The Maintenance Supervisor shall review and sign the completed checklist within 2 working days.\n9.2 Records shall be retained for 3 years from the date of the PM.",
      charCount: 250,
      hasTextLayer: true,
      needsOcr: false,
    },
  ],
};

export const windchillDocuments: WindchillDocumentList = {
  provider: { name: "mock-windchill", developmentOnly: true },
  items: [
    {
      reference: "mock://wtdocument/SOP-00123/A.3",
      metadata: documentRecord.metadata,
      primaryContent: {
        filename: "SOP-00123_Machine_Maintenance_A.3.pdf",
        mediaType: "application/pdf",
        sizeBytes: 18_734,
      },
      developmentOnly: true,
    },
    {
      reference: "mock://wtdocument/SOP-00141/A.1",
      metadata: {
        number: "SOP-00141",
        name: "Hydraulic Press Setup and Changeover",
        revision: "A",
        iteration: "1",
        state: "In Work",
        location: "Manufacturing SOP Library / Production",
        documentType: "SOP",
        modifiedDate: "2026-09-02T11:20:00Z",
        modifiedBy: "R. Okafor",
        sourceRef: "mock://wtdocument/SOP-00141/A.1",
      },
      primaryContent: {
        filename: "SOP-00141_Hydraulic_Press_Setup_A.1.pdf",
        mediaType: "application/pdf",
        sizeBytes: 15_210,
      },
      developmentOnly: true,
    },
  ],
};

export const askAnswer: AskResponse = {
  schemaVersion: "1.0",
  answerId: "f1e2d3c4b5a697887766554433221100",
  documentId: DOCUMENT_ID,
  question: "What PPE is required?",
  answerable: true,
  answer:
    "Safety glasses with side shields and safety shoes (S3) are required for all tasks in the SOP.",
  citations: [{ ...citations[2]!, id: "C1" }],
  verification: {
    totalCitations: 1,
    verified: 1,
    relocated: 0,
    approximate: 0,
    unverified: 0,
    invalidPage: 0,
    itemsTotal: 1,
    itemsWithoutVerifiedSource: 0,
  },
  warnings: [],
  provenance: { ...provenance, task: "ask", promptId: "ask", durationMs: 4_210 },
};

export const askUnanswerable: AskResponse = {
  ...askAnswer,
  answerId: "00112233445566778899aabbccddeeff",
  question: "What is the torque for the spindle nose bolts?",
  answerable: false,
  answer:
    "The document does not specify a torque for spindle nose bolts. It only gives 45 N·m for the M10 guard fasteners.",
  citations: [],
  verification: {
    ...askAnswer.verification,
    totalCitations: 0,
    verified: 0,
    itemsWithoutVerifiedSource: 1,
  },
};
