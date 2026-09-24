# Windchill AI Document Intelligence: Research Report

| | |
|---|---|
| **Status** | Research draft, revision 1. **No application code has been written. No Windchill configuration has been changed.** |
| **Date** | 2026-09-24 |
| **Scope** | Learn PTC Windchill well enough to design an AI "Document Intelligence" capability for `WTDocument`, starting with *AI Summarize*. |
| **Audience** | The project team, before any implementation decision. |

---

## 0. Read this first

### 0.1 Research constraints (these affect every confidence rating below)

1. **No PTC page could be opened in full.** The research environment's egress policy blocked `support.ptc.com`, `www.ptc.com` and `community.ptc.com`.
   - Everything attributed to the PTC Help Center, PTC Knowledge Base (CS articles) or PTC Community comes from search-engine result snippets of those pages. The pages themselves were not read.
   - No PTC-sourced finding is rated High. Every URL listed is one that appeared in search results, and each should be opened by someone with PTC access before we rely on its exact wording.
2. **Javadoc came from an unofficial mirror.** Java API signatures were read from PTC-generated Javadoc HTML for Windchill 13.1.2 that a third party mirrors on GitHub (`srinivasmd/Windchill_13_1_2_JavaDocs.github.io`).
   - The text is PTC's, but the hosting is unofficial and the pages were read through a summarising fetch tool.
   - The official Javadoc ships with every install at `<WT_HOME>/codebase/wt/clients/library/api/index.html` (per a Help Center snippet and PTC KB CS17101). **Every signature must be re-checked there for our target release.**
3. **The web-search budget ran out mid-research.** A few topics (security labels, audit events, some UI details) therefore have thin coverage and are marked NOT VERIFIED.
4. **We did not receive the proof-of-concept screenshots.** The repository was empty when this research started. Section 9.8 assesses the PoC only from the written description in the brief.
5. **The AI and open-source tooling research (Ollama, extraction libraries, OCR, OWASP) is on firmer ground.** It was verified against the projects' own GitHub repositories (source code, docs folders, LICENSE files).

### 0.2 Confidence legend

| Label | Meaning |
|---|---|
| **H** | Primary source read in full. Applies to open-source/AI findings verified on GitHub. **No Windchill finding is H in this revision.** |
| **M+** | PTC-authored Javadoc text, read via the unofficial 13.1.2 mirror. The wording is PTC's, but it must be re-verified locally. |
| **M** | Official PTC Help Center page, or a PTC KB/Community item, seen only as a search snippet. |
| **L** | Third-party code, blog or forum post, or our own inference. |
| **NOT VERIFIED** | No adequate source was found. Treat it as an open question, not a fact. |

### 0.3 Key conclusions (summary)

1. **Content retrieval.** Never read the vault or the database directly. Two supported routes exist:
   - Server-side Java inside the Method Server: `ContentHelper` / `ContentServerHelper.service.findContentStream(ApplicationData)`, both marked Supported API (M+).
   - Windchill REST Services: `.../DocMgmt/Documents('<oid>')/PrimaryContent` and `/Attachments` (M).
   - Both run as an authenticated Windchill principal. Direct vault access bypasses access control and depends on internal, unsupported storage layout.
2. **Permissions.** Windchill has a separate **Download** permission, distinct from **Read** (M).
   - A user with Read but without Download can see a document's metadata but not its files.
   - **Anything derived from file content (summaries, extracted requirements, answers) must therefore require Download on that exact document iteration, not just Read.** This is the single most important security rule for this project.
3. **The action.** An *AI Summarize* action is added with the Windchill Action Framework:
   - Define it in `<WT_HOME>/codebase/config/actions/custom-actions.xml` under the `document` object type (`wt.doc.WTDocument`).
   - Add it incrementally to the document action model (`docs row actions toolbar`, `menufor="wt.doc.WTDocument"` in the releases we could see) through `custom-actionModels.xml`.
   - The selected object arrives as an OID (`OR:`/`VR:wt.doc.WTDocument:<id>`) through `NmCommandBean` (M/L).
4. **Architecture for the first version.** Use a thin **in-Windchill bridge** plus an **external AI Gateway**:
   - The bridge runs inside the Method Server, as the logged-in user. It checks access, fetches the content and pushes the bytes to the gateway.
   - The gateway runs outside Windchill and holds no Windchill credentials. It does extraction, OCR and Ollama inference, and returns structured JSON with page citations.
   - A second pattern (an external web app calling WRS with the user's delegated OAuth token) is kept as the path for Windchill+ and for a richer UI later.
5. **PTC already sells an overlapping product.** PTC released a **Windchill AI Assistant** plugin on 28 April 2026 (M). It offers:
   - chat grounded in Windchill documents, with cited sources;
   - a **"Summarize Document"** action;
   - enforcement of Windchill access control.

   Its on-prem deployment requires **Azure OpenAI, Azure AI Search and Azure Storage** in the customer's subscription (M). **Before building, the business should decide how this project relates to it** (section 1.3). Our differentiators would be fully local inference (Ollama), structured engineering extraction (requirements, specifications, risks) and revision comparison. PTC's feature coverage in those areas is NOT VERIFIED.
6. **Version sensitivity is high.** Several things vary by release:
   - WRS was a separately versioned module until Windchill 12.1.2.11 and is bundled with Windchill after that (M).
   - Windchill 13.1.2 introduced a "Next Gen UI" (M), and how custom actions extend it is NOT VERIFIED.
   - Windchill+ (SaaS) enforces customization guardrails and requires that integrations use REST over HTTP (M).

   **We need the exact release, CPS and deployment type before choosing implementation mechanics.**

---

## 1. Windchill overview

### 1.1 What Windchill is

PTC Windchill is PTC's Product Lifecycle Management (PLM) system. It manages product data under version control, life cycles and workflows, with access control scoped to contexts (products, libraries, projects). The main data types are parts and BOMs, CAD documents (`EPMDocument`), general documents (`WTDocument`) and change objects.

| Topic | Finding | Source | Conf. |
|---|---|---|---|
| Current releases | Help Centers exist for 12.0.2, 12.1.2, 13.0.x and 13.1.x. The 13.1 line has maintenance releases 13.1.0.0 through 13.1.3.0. | https://support.ptc.com/help/windchill/r13.1.2.0/en/ | M |
| Windchill 14 | No evidence of a 14.0 release as of Sept 2026. | Search found nothing | NOT VERIFIED |
| LTS designation | One third-party partner calls 13.1.3 the "latest long-term-support release". No official PTC statement was found. | https://fishbowlsolutions.com/2026/05/why-now-is-the-time-to-upgrade-to-ptc-windchill-13-1-3-and-why-fishbowl-solutions-is-the-partner-to-get-you-there/ | L |
| Windchill+ | PTC's SaaS edition, with its own Help Center. PTC delivers CPS updates on an upgrade calendar. | https://support.ptc.com/help/windchill/plus/r13.1.2.0/en/Windchill_Help_Center.html | M |
| Modules | PDMLink (product data), ProjectLink (projects), MPMLink (manufacturing process), Windchill Visualization Services (WVS, publishing and Creo View). | Various Help Center snippets | M |

### 1.2 PTC's own AI capabilities in Windchill

| Capability | What it does | Release | Source | Conf. |
|---|---|---|---|---|
| Hannover Messe 2025 preview | "Windchill AI" was previewed, including a "Document Vault AI agent" that pulls product information from documents stored in Windchill. | Announced 25 Mar 2025 | https://www.ptc.com/en/news/2025/ptc-brings-ai-powered-plm-to-hannover-messe | M |
| **Windchill AI Assistant** (plugin) | Natural-language chat grounded in Windchill document content. Answers cite their sources, and "access control rules are enforced". Includes a **"Summarize Document"** action. Links in answers open the document's info page. Administration covers an Indexing Dashboard, a per-container indexing scope, and indexing driven by an event queue. | Released 28 Apr 2026 | https://www.ptc.com/en/news/2026/ptc-launches-windchill-ai-assistant ; https://support.ptc.com/help/windchill/ai_plugin/en/Windchill_Help_Center/document_vault/WCAIAssistAIPluginReleaseNotes.html ; https://support.ptc.com/help/windchill/ai_plugin/en/Windchill_Help_Center/document_vault/NewandChanged_EnhancementsWCAIAssistant.html | M |
| AI Assistant, on-prem prerequisites | The customer's own **Azure** subscription must provide Azure OpenAI (the example deployment is "gpt-5.4-mini"), Azure Storage, Azure AI Search and an Entra ID service principal. On SaaS it consumes "AI credits". | 2026 | https://support.ptc.com/help/windchill/ai_plugin/en/Windchill_Help_Center/document_vault/WCAIAssistAIPluginDeployAzureResource.html ; .../WCAIAssistAIPluginAICredits.html | M |
| Windchill AI Parts Rationalization | Finds duplicate or similar parts. Ships as a plugin for 12.1.2.22, 13.0.2.10 and 13.1.3.0 on-prem, and for SaaS. | Released 27 Jan 2026 | https://www.ptc.com/en/news/2026/ptc-launches-windchill-ai-parts-rationalization ; https://support.ptc.com/help/windchill/ai_plugin/en/Windchill_Help_Center/parts_rationalization/AIPluginIntroduction.html | M |
| Plugin Manager | Newer Windchill releases have a Plugin Manager, and PTC ships its AI features through it. | 2026 | AI plugin install pages | M |

### 1.3 Implication for this project

PTC's AI Assistant already covers:
- document Q&A with citations;
- a "Summarize Document" action;
- permission-aware retrieval.

It depends on Azure cloud AI services. Our brief requires a **locally hosted LLM (Ollama)**. That constraint, plus **structured engineering extraction** (requirements, specifications, risks, actions), **revision and change comparison**, and full control over prompts, models and data residency, are the plausible differentiators. Which content types PTC indexes, and whether it does structured extraction, is NOT VERIFIED.

**This is a business decision for you (Open Question Q1).** If we proceed, we should also:
- avoid the action label "Summarize Document", to prevent confusion if both are installed;
- keep our customization in our own namespace (`ext.*` packages, our own action names).

---

## 2. Relevant Windchill architecture

### 2.1 Runtime tiers and request flow

```
Browser (HTML/JS)
   │  HTTPS
   ▼
HTTP Server (Apache-based "PTC HTTP Server", or IIS)        ← web-tier authentication (sets REMOTE_USER)
   │
   ▼
Method Server JVM(s)  ── Embedded Servlet Engine (Tomcat) + HTTP gateway servlet
   │                     Windchill services, business logic, access control
   │                     "the only Windchill process that communicates directly with the database"
   ├──► Database (Oracle / SQL Server)          metadata, BLOB content (if not vaulted)
   ├──► File vaults / File Server replicas       content files
   ├──► Solr ("Windchill Index Search")           full-text index
   └──► LDAP directory                            users, groups
Server Manager (one per host)  — brokers method servers, holds session credentials, manages background processing
Background Method Server(s)    — optional, executes queue entries
```

| Finding | Source | Conf. |
|---|---|---|
| Windchill has three tiers: a client tier (browser), an application tier (HTTP server plus method servers) and a database tier. | "Three-Tier Architecture", https://support.ptc.com/help/windchill/r12.1.2.0/en/Windchill_Help_Center/WCSysAdminWCRuntimeEnvironment/WCRuntimeEnvironment_ThreeTierArchitecture.html | M |
| The **Method Server** is "the only Windchill process that communicates directly with the database". | "Windchill Runtime Architectural Overview", https://support.ptc.com/help/windchill/plus/r12.0.2.0/en/Windchill_Help_Center/WCArchOview.html | M |
| The **Server Manager** runs as its own JVM, one per host. It manages method servers and session credentials. Clients get a method-server reference from it and then talk to that method server directly. | "Server Software Components", https://support.ptc.com/help/windchill/cloud/r12.0.2.0/en/Windchill_Help_Center/WCRuntimeEnvironment_ServerSoftwareComponent.html | M |
| The servlet engine (Tomcat-based) is embedded in the Method Server. An HTTP gateway servlet connects the HTTP server to the method servers. | Same page | M |
| **Background method servers** execute queues (schedule, pool and process queues), configured with `wt.manager.monitor.services=MethodServer BackgroundMethodServer`, `wt.queue.executeQueues=false`, and so on. | https://support.ptc.com/help/windchill/r12.1.2.0/en/Windchill_Help_Center/WCAdvDeployGuide/WCAdvDepAdv_BackgroundMethServConfig.html ; https://support.ptc.com/help/windchill/r13.0.0.0/en/Windchill_Help_Center/queuemgmt_chp/queuemgmtChp_ConfigBackgroundQueueRelateProp.html | M |
| **Database:** Oracle and Microsoft SQL Server are supported; exact versions are in the Software Matrices. PostgreSQL support was not found. | https://support.ptc.com/help/windchill/r13.1.1.0/en/Windchill_Help_Center/WCInstallConfigGuide/WCInstall_SQLServerArchitechture.html | M |
| **Search:** "Windchill Index Search" is Apache Solr, in standalone or SolrCloud mode, protected with basic auth. | https://support.ptc.com/help/windchill/r13.0.1.0/en/Windchill_Help_Center/WCInstallConfigGuide/WCInstall_WCIndexSearchStandalone.html | M |
| **LDAP:** PTC stopped shipping Windchill Directory Server from 12.0.1.0. Any LDAPv3-compliant directory is supported. | KB CS335696, https://www.ptc.com/en/support/article/CS335696 | M |

### 2.2 File vaults and replication

- **Vaults and folders.** Content lives in *vaults*, which contain *folders* mapped to file-system mount points. A vaulting policy decides where uploads land.
- **Sites and replicas.** There is a master site ("Master"). Remote sites can run a lightweight **Windchill File Server** with no database, and content is replicated to replica vaults according to replication rules.
- Sources: "About Replication", https://support.ptc.com/help/windchill/plus/r12.0.2.0/en/Windchill_Help_Center/ReplicateChp_About.html ; "Windchill Vault Configuration", https://support.ptc.com/help/windchill/cloud/r12.0.2.0/en/Windchill_Help_Center/filevaultChp_WCExtStorageAdmin.html. Confidence: **M**.
- **Not verified from official sources:**
  - Content can also be stored as BLOBs in the database; "revaulting" moves it into file vaults.
  - Files on disk use internal names rather than the original file names.
  - Background knowledge (**L**), corroborated only indirectly by KB CS112169 ("only when the content is stored in BLOB"). **NOT VERIFIED officially.**

### 2.3 Services and configuration

| Finding | Source | Conf. |
|---|---|---|
| Windchill services implement `wt.services.Manager`. `wt.services.StandardManager` (Supported and Extendable) is the base class. It has `performStartupProcess()` and `getManagerService()` for registering event listeners. | "Service Management", https://support.ptc.com/help/wnc/r12.1.1.0/en/Windchill_Help_Center/customization/WCCG_Serv_DevelopServerLogic_ServMgmt.html ; Javadoc `wt/services/StandardManager.html` | M / M+ |
| A service is registered with a `wt.properties` entry of the form `wt.services.service.<n>=<Interface>/<StandardImpl>`, set through `xconfmanager`. | Help Center snippet plus third-party repos | M/L |
| Properties are changed with **`xconfmanager`**, not by hand. Site changes are stored in `<WT_HOME>/site.xconf`. Flags: `-s` (set), `-t` (target file), `-p` (propagate). | "Using the xconfmanager Utility", https://support.ptc.com/help/windchill/r12.1.2.0/en/Windchill_Help_Center/customization/WCCG_Oview_WCUtilities_AboutXconfmanager.html ; https://support.ptc.com/help/windchill/r13.1.2.0/en/Windchill_Help_Center/customization/WCCG_Oview_WCUtilities_XconfmanagerCommandSyntax.html | M |
| Custom service provider files (`*.service.properties`) and "lightweight services" are documented. `wt.services/svc/default/<interface>/<selector>/<requestor>/<priority>` entries are the delegate/lookup mechanism used, for example, to register UI validators. | https://support.ptc.com/help/windchill/r13.0.0.0/en/Windchill_Help_Center/customization/WCCG_Serv_DevelopServerLogic_LightweightServices.html | M/L |

### 2.4 Persistence and modeling

- **Persistence API.** Everything goes through `wt.fc.PersistenceHelper.manager` (`PersistenceManager`): `find(StatementSpec)`, `navigate(...)`, `refresh(...)`, `store/modify/delete`. Queries use `wt.query.QuerySpec` and `SearchCondition` (**M+**). A snippet says `find` runs with access control applied (**M**).
- **Modeling.** Business classes are modeled with annotations such as `@GenAsPersistable`, and an annotation processor generates the class's parent source ("Modeling Business Objects", https://support.ptc.com/help/windchill/r12.1.2.0/en/Windchill_Help_Center/customization/WCCG_Serv_SysGen_ModelBusinessObjects.html, **M**).
- **Prefer types over modeling.** PTC recommends **subtypes and soft attributes** (Type and Attribute Management) over modeled schema extensions (**M**). This project should not need any modeled classes.

### 2.5 Object model capabilities (interfaces)

Windchill business classes are built by combining capability interfaces. For documents this matters because each capability corresponds to a service we will touch:

| Interface | Capability | Relevant service/helper |
|---|---|---|
| `Persistable` | Stored in the database; has an OID | `PersistenceHelper` |
| `Mastered` / `Versioned` / `Iterated` | Master–version–iteration identity | `VersionControlHelper` |
| `Workable` | Check-out and check-in | `WorkInProgressHelper` |
| `LifeCycleManaged` | Life cycle state | `LifeCycleHelper` |
| `Foldered` / `CabinetBased` | Folder location | `FolderHelper` |
| `WTContained` | Belongs to a container (Product, Library, ...) | `WTContainerHelper` (NOT VERIFIED) |
| `AccessControlled` / `DomainAdministered` | ACL-governed; belongs to an administrative domain | `AccessControlHelper` |
| `ContentHolder` / `FormatContentHolder` | Holds files and URLs; has a primary format | `ContentHelper`, `ContentServerHelper` |
| `Representable` | Can have visualization representations | `RepresentationHelper` |
| `IBAHolder` / `Typed` | Soft attributes and subtypes | `PersistableAdapter`, `TypeIdentifier` |

`WTDocument` implements all of these (Javadoc `wt/doc/WTDocument.html`, **M+**). The Help Center says `RevisionControlled` bundles Foldered, Indexable, Notifiable, DomainAdministered, AccessControlled, BusinessInformation, LifeCycleManaged, Versioned, Workable and Changeable ("Part Abstractions", https://support.ptc.com/help/windchill/r12.1.2.0/en/Windchill_Help_Center/customization/WCCG_Serv_EnterpriseLayer_PartAbstract.html, **M**).

### 2.6 Containers and participants

**Container hierarchy** (all implement `wt.inf.container.WTContainer`). The class names come from tertiary sources (**L**) and must be verified in the Javadoc.

```
Site  (wt.inf.container.ExchangeContainer)
 └─ Organization  (wt.inf.container.OrgContainer)
      ├─ Product   (wt.pdmlink.PDMLinkProduct)
      ├─ Library   (wt.inf.library.WTLibrary)
      └─ Project   (wt.projmgmt.admin.Project2)
```

**Participants:**
- Users (`WTUser`), groups (`WTGroup`) and organizations (`WTOrganization`) are all principals (`WTPrincipal`).
- Roles are assigned per context through context teams, and access rules can target roles.
- These class names come from background knowledge: **NOT VERIFIED** in this session.

**How the parts relate:**
- Every business object lives in exactly one container (`WTContained`) and belongs to an administrative domain.
- Access-control policy rules are defined per domain, object type and life cycle state, for participants (users, groups, roles, organizations).
- A user's effective access to a `WTDocument` therefore depends on:
  - the container's team membership;
  - the object's domain;
  - its type;
  - its current life cycle state;
  - any ad hoc ACLs;
  - security labels and agreements (section 8).

---

## 3. WTDocument architecture

### 3.1 WTDocument and WTDocumentMaster

| Class | Role | Supported | Source | Conf. |
|---|---|---|---|---|
| `wt.doc.WTDocumentMaster` | Identity shared by all versions: **number** (unique among WTDocuments) and **name**. Implements `Mastered`, `WTContained` and `IBAHolder`. | Supported, Extendable | Javadoc `wt/doc/WTDocumentMaster.html` | M+ |
| `wt.doc.WTDocument` | One specific **iteration** of a **version**. "can be checked in and out, revised and holds content (one or more files)". Title, description and department can differ per iteration. | Supported, Extendable | Javadoc `wt/doc/WTDocument.html` | M+ |
| Document abstractions | "A WTDocument is a content holder… can have files or URLs". Attributes live either on the master or on the version/iteration. `docType` is common to all iterations. | — | https://support.ptc.com/help/windchill/r13.0.1.0/it/Windchill_Help_Center/customization/WCCG_Serv_EnterpriseLayer_DocAbstract.html | M |

### 3.2 Versions, revisions and iterations

- **Creating a document** creates a master plus version **A.1**: revision **A**, iteration **1**.
- **Check-in** increments the iteration (A.1 → A.2).
- **Revise** creates the next revision from the latest iteration (A.2 → B.1).
- In Windchill, "version" means the revision label plus the iteration.
- Sources: "Object Versions", https://support.ptc.com/help/windchill/plus/r12.0.2.0/en/Windchill_Help_Center/CommonRevisableObjAbout.html ; "Understanding Revisions, Iterations, and Versions in Folders", https://support.ptc.com/help/windchill/plus/r12.0.2.0/en/Windchill_Help_Center/OverviewFolderRevisIterVers.html. Confidence: **M**.

| Need | Supported API (M+) |
|---|---|
| Revision label | `VersionControlHelper.getVersionIdentifier(Versioned)`; for display, `getVersionDisplayIdentifier(Versioned)` |
| Iteration number | `VersionControlHelper.getIterationIdentifier(Iterated)`; for display, `getIterationDisplayIdentifier(...)` |
| Is this the latest iteration? | `VersionControlHelper.isLatestIteration(Iterated)` |
| Latest iteration of this version | `VersionControlHelper.service.getLatestIteration(Iterated, boolean includeMarkedForDelete)` |
| All versions, newest first | `VersionControlHelper.service.allVersionsOf(Mastered)`. Returns an "ordered list of versions (i.e., latest iterations) from the most recent one to the first one created". What "most recent" means when revisions branch is **NOT VERIFIED**. |
| All iterations | `allIterationsOf(Mastered)`, `allIterationsFrom(Iterated)`, `iterationsOf(Iterated)` |

The REST equivalent is the `ptc.search.latestversion=true|false` query option (section 6.7).

**Rule for the AI capability:** every AI result is about a specific **iteration**, for example `B.3`, and a specific content item (identified by its checksum). A result produced for B.2 must never be shown as the result for B.3.

### 3.3 Check-out, check-in and working copies

- While a document is checked out there is an **original** and a **working copy**. Only the person who checked it out sees the working copy; everyone else sees the last checked-in iteration.
- Sources: "Checking Out an Object", https://support.ptc.com/help/windchill/cloud/r12.0.2.0/en/Windchill_Help_Center/CommonObjCheckOut.html ; "Checking In Documents", https://support.ptc.com/help/windchill/cloud/r12.0.2.0/en/Windchill_Help_Center/DocMgmtDocCheckIn.html. Confidence: **M**.
- Supported APIs (M+):
  - `WorkInProgressHelper.isCheckedOut(Workable)`, `isWorkingCopy(Workable)`, `isPrivateWorkingCopy(...)`, `getState(...)`
  - `WorkInProgressHelper.service.workingCopyOf(...)`, `originalCopyOf(...)`, `checkout(...)`, `checkin(...)`
- **Decision for MVP:** summarize only checked-in iterations. If the user runs the action on their own working copy, either refuse or clearly label the result as a working-copy result that is not cached.

### 3.4 Life cycle, workflow, folders and containers

| Aspect | API (M+) | Relevance to AI |
|---|---|---|
| Life cycle state | `LifeCycleManaged.getLifeCycleState()`; `wt.lifecycle.State` (documented constants `INWORK`, `UNDERREVIEW`, `RELEASED`; others are site-defined) | Show the state in the result header. **Access rules can depend on state**, so a document's permissions can change when it is promoted. |
| Workflow | `wt.workflow.engine.WfProcess` (Supported) | Future feature: AI assistance for review tasks. Not in the MVP. |
| Folder | `FolderHelper.getFolderPath(CabinetBased)`, `getLocation(...)` | Show the location. |
| Container | `WTContained.getContainer()` / `getContainerReference()` (Supported flag unclear on the summarized page) | Show the context, and possibly scope AI enablement per product or library. |

### 3.5 Document structures and part–document relationships (M+)

| Link | From → To | Semantics |
|---|---|---|
| `wt.doc.WTDocumentUsageLink` | WTDocument (iteration) → WTDocumentMaster | Parent/child document structure; attribute `structureOrder` |
| `wt.doc.WTDocumentDependencyLink` | WTDocument ↔ WTDocument (iteration to iteration) | The "References" relationship. Copied forward on revise and check-out. Has `linkDescription`. |
| `wt.part.WTPartDescribeLink` | WTPart (iteration) → WTDocument (iteration) | "Described by" documents; specific to an iteration |
| `wt.part.WTPartReferenceLink` | WTPart → WTDocumentMaster | "Reference" documents; independent of the document's version. The UI resolves it to the latest Released version (configurable by preference). ("Object Relationships", https://support.ptc.com/help/windchill/r13.0.1.0/en/Windchill_Help_Center/objectoview/ObjectOviewObjectRelationships.html, M) |

Links are navigated with `PersistenceHelper.manager.navigate(Persistable, String role, Class linkClass, boolean onlyOtherSide)` (M+).

### 3.6 Metadata, primary content, attachments, versions and iterations

| Concept | What it is | Where it lives |
|---|---|---|
| **Metadata** | Number, name (master); title, description, state, type, soft attributes (IBAs), creator, dates (version/iteration) | Database rows on the master and iteration |
| **Primary content** | The document's main content item, exactly one (a file, a URL, or external storage). "The information in a document is its primary content." | An `ApplicationData`, `URLData` or `ExternalStoredData` item with role `PRIMARY` on the iteration |
| **Attachments** | Secondary content items, zero or more | `ContentItem`s with role `SECONDARY` on the iteration |
| **Version (revision)** | Business-significant increment (A, B, C…) created by *Revise* | A new version branch of the same master |
| **Iteration** | Each check-in inside a revision (.1, .2 …). **Content can differ between iterations.** | A new `WTDocument` row in the same version branch |

Sources: "Documents in Windchill", https://support.ptc.com/help/windchill/cloud/r12.0.2.0/en/Windchill_Help_Center/DocMgmtAbout.html ; "Attachments", https://support.ptc.com/help/windchill/r12.1.2.0/en/Windchill_Help_Center/attachments/AttachmentAbout.html. Confidence: **M**.

### 3.7 Types and soft attributes

- Soft types are read and written through `com.ptc.core.lwc.server.PersistableAdapter` (Supported; `load/get/set/apply`; server-side only) (**M+**). It covers modeled attributes, global and standard soft attributes, and alias attributes.
- The type of an object is available from `wt.type.ClientTypedUtility.getTypeIdentifier(Object)`, which returns a `com.ptc.core.meta.common.TypeIdentifier` (Supported, **M+**).
- This matters because the customer may use document subtypes (for example Specification, Test Report). The AI action could be enabled only for some subtypes, and future AI output could be written back to a soft attribute. Write-back is not in scope now.

---

## 4. Document and content storage

### 4.1 Content object model (M+, from the 13.1.2 Javadoc mirror)

```
ContentHolder (interface; WTDocument, WTPart, change objects, WfProcess … implement it)
 └─ FormatContentHolder (interface; adds a primary format — WTDocument, EPMDocument, Representation)
       │
       │ has 0..n
       ▼
ContentItem (abstract; getRole(), getFormat(), getDescription())
 ├─ ApplicationData      — a file: getFileName(), getFileSize(), getChecksum(); bytes behind a separate streamData reference
 ├─ URLData              — a URL link: getUrlLocation()  (no bytes to summarize)
 └─ ExternalStoredData   — a pointer string to storage outside Windchill (no bytes via Windchill)

ContentRoleType: PRIMARY, SECONDARY (documented constants; other roles such as thumbnails exist
                 as enumeration values but are NOT VERIFIED)
DataFormat: format name ↔ MIME type ↔ extensions (e.g., "PDF")
```

- The Javadoc says content roles are "a customization point… does not reflect any particular behavior to content in the ContentService" (M+).
- **Consequence:** only `ApplicationData` items have bytes we can extract text from. For `URLData` and `ExternalStoredData`, the MVP should report "content not stored in Windchill" rather than try to fetch the URL. Fetching arbitrary URLs from the server would be an SSRF risk.

### 4.2 Content APIs (M+)

| API | Where it runs | Purpose |
|---|---|---|
| `ContentHelper.service.getContents(ContentHolder)` | Client or server (remote interface) | Populates the holder's content information. **Must be called before `getPrimary`.** |
| `ContentHelper.getPrimary(FormatContentHolder)` | Static | Returns the primary `ContentItem` |
| `ContentHelper.getContentList(ContentHolder)` | Static | Content items **excluding** the primary of a FormatContentHolder |
| `ContentHelper.getContentListAll(ContentHolder)` | Static | The primary **and** all other items |
| `ContentHelper.service.getContentsByRole(ContentHolder, ContentRoleType)` | Remote | Items by role, e.g. `SECONDARY` for attachments |
| `ContentHelper.getDownloadURL(ContentHolder, ApplicationData[, replicatedContent[, fileName[, forceDownload]]])` | Static | The **supported** way to produce a download URL |
| `ContentServerHelper.service.findContentStream(ApplicationData)` → `InputStream` | **Server only** (`ContentServiceSvr`: "only able to be invoked from classes running in the server") | Reads the bytes of a file content item |
| `ContentServerHelper.service.writeContentStream(ApplicationData, String path)` | Server only | Writes the bytes to a server-side path. Avoid; streaming is preferred. |

Things to avoid:
- **`findLocalContentStream(ApplicationData)`** is widely used in community code but is **not listed as Supported** in the 13.1.2 Javadoc (M+).
- **Hand-built `.../wt.content.ContentHttp/viewContent/...` URLs:** `ContentHttp` is not in the Supported API (M+). Use `getDownloadURL` instead.
- **Calling `findContentStream` from a JSP:** KB CS112169 reports connection errors when the content is stored as a BLOB (https://www.ptc.com/en/support/article/cs112169, M). Stream content in server-side Java classes and always close the stream.
- KB CS344061 (https://www.ptc.com/en/support/article/CS344061, versions 11.0–13.1) explains how the `ContentServerHelper` stream APIs differ. It could not be read; it should be read before implementation.

### 4.3 How a PDF on a WTDocument is actually stored and retrieved

A PDF related to a WTDocument can be in **three** places. The action must decide which one to summarize.

| Case | Where the PDF is | How to get it | Notes |
|---|---|---|---|
| 1. **Primary content** | `ApplicationData` with role `PRIMARY` and format "PDF" | `getContents` → `getPrimary` → `findContentStream` | The most common case for PDF-native documents |
| 2. **Attachment** | `ApplicationData` with role `SECONDARY` | `getContentsByRole(doc, SECONDARY)` → filter by format or extension → `findContentStream` | Common when the primary is a native format (e.g. DOCX) and a PDF copy is attached |
| 3. **Published representation** | `wt.representation.Representation` (e.g. `wt.viewmarkup.DerivedImage`), itself a `FormatContentHolder` | `RepresentationHelper.service.getDefaultRepresentation(Representable)` → `ContentHelper` APIs on the representation | This happens when WVS publishes Office files to PDF. Third-party evidence shows PDFs served with `ContentHolder=wt.viewmarkup.DerivedImage:<id>` (L). Which content role the PDF has inside a representation is **NOT VERIFIED**. |

**Proposed MVP selection rule** (to be confirmed with the business):
1. Use the primary content if it is a supported format (PDF first; DOCX, XLSX and PPTX later).
2. Otherwise, use the default representation's PDF if one exists.
3. Otherwise, fail with a clear message.
4. Summarize attachments only when the user explicitly chooses them (a later feature).

The result always records which content item was used: its role, file name and checksum.

**Where the bytes physically live** (vault folder, BLOB or replica) is invisible to the supported APIs, and that is the point. `findContentStream` and the download servlet resolve the location, replication and storage type for us.

### 4.4 The three access approaches compared

| | **A. Java APIs in the Method Server** | **B. Windchill REST Services (WRS)** | **C. Reading the vault or database directly** |
|---|---|---|---|
| Mechanism | `ContentHelper` + `ContentServerHelper.service.findContentStream` inside custom server-side code | HTTPS/OData: `Documents('<oid>')/PrimaryContent`, `/Attachments`, then download the `Content` URL | Reading vault mount folders or BLOB tables |
| Supported by PTC | **Yes.** Supported API (M+), but on-prem only in practice; Windchill+ restricts server-side code (section 11) | **Yes.** PTC's recommended integration surface, and required for integrations on Windchill+ (M) | **No.** It is outside the Supported API, and the vault layout is internal (M+/L) |
| Identity used | The Method Server session principal: the logged-in user in a UI request | The authenticated WRS caller: a user (Basic auth, SSO, delegated OAuth) or an M2M identity | None. The file system has no Windchill identity. |
| Access control | Object lookup respects access control when enforcement is on. **Whether `findContentStream` itself enforces Download is NOT VERIFIED, so check explicitly with `AccessControlHelper.manager.hasAccess(..., AccessPermission.DOWNLOAD)`.** | Runs inside the Method Server as the caller, so standard enforcement applies (L). The exact 403/404 behaviour is NOT VERIFIED and must be tested. | **Bypassed entirely**: ACLs, Download permission, security labels, audit |
| Code runs | Inside Windchill (the upgrade surface) | Outside Windchill | Outside Windchill |
| Coupling to the release | Java APIs, the JDK version, and recompiling on upgrades | Domain versions (`/v5/`, `/v6/`); pin explicitly | Breaks with revaulting, replication and storage changes |
| Verdict | **Recommended for the MVP (on-prem)**, as the "AI Bridge" in section 9 | **Recommended for external clients and Windchill+**; the future path | **Never.** |

---

## 5. Windchill Action Framework (UI customization)

### 5.1 Client architecture

- **Two page technologies coexist.** Windchill Client Architecture (JCA) pages are built by **MVC builders** (Java `ComponentBuilder`s that produce component configs) or by **JSP** pages. The `jcaDebug` tool shows which builder or JSP renders each page ("What information does jcaDebug display?", https://support.ptc.com/help/windchill/r13.0.0.0/en/Windchill_Help_Center/customization/WCCG_UICust_CustHTMLClients_ToolsOview_InformationjcaDebug.html, **M**).
- **Info pages** are customized by overriding `buildInfoConfig()` in a custom builder ("Customization Points", https://support.ptc.com/help/windchill/r13.0.0.0/en/Windchill_Help_Center/customization/WCCG_UICust_InfoPages_InfoPages_CustPoints.html, **M**).
- **Windchill 13.1.2 added a "Next Gen UI".** It is described as a new design "with more features and greater customization than the classic user interface". Users switch the new Home and Folders pages on with toggles, and 13.1.3 adds "Enabling Next Gen UI" ("Next Gen UI in Windchill", https://support.ptc.com/help/windchill/r13.1.2.0/en/Windchill_Help_Center/NewandChanged/NewandChanged_13_1_20_NGUI_NextGenUIinWindchill.html, **M**).
  - **How custom actions appear in, or extend, the Next Gen UI is NOT VERIFIED.** This is a version risk (section 11).

### 5.2 Registering the action

| Finding | Source | Conf. |
|---|---|---|
| Out-of-the-box (OOTB) actions and action models are in `<WT_HOME>/codebase/config/actions` (`actions.xml`, `actionmodels.xml` and module files such as `DocumentManagement-actionmodels.xml`). **Custom actions go in `custom-actions.xml`**, which follows `customActions.dtd`. | "Windchill Action Framework", https://support.ptc.com/help/windchill/plus/r13.0.2.0/en/Windchill_Help_Center/customization/WCCG_UICust_AddActionsHook_WCClientArchAction_wncplus.html | M |
| **Custom action models go in `custom-actionModels.xml`**, inside `<actionModels>`. | https://support.ptc.com/help/wnc/r12.0.0.0/en/Windchill_Help_Center/WCCG_BusLogicCust_DTIFrameworkRMB.html | M |
| `<objecttype>` "is a way to create a name space as well as packaging for actions related to a specific object". The objecttype named `document` covers `wt.doc.WTDocument`. OOTB wrapper: `<objecttype name="document" class="wt.doc.WTDocument" resourceBundle="com.ptc.windchill.enterprise.doc.documentResource">`. | "Defining a New Custom Action", https://support.ptc.com/help/windchill/plus/r13.1.2.0/en/Windchill_Help_Center/customization/WCCG_UICust_AddActionsHook_WCClientArchAction_Defining_a_new_action_wncplus.html | M (wrapper: L) |
| Official example command: `<command class="com.ptc.windchill.enterprise.doc.forms.CreateDocFormProcessor" method="execute" windowType="popup" onClick="validateCreateLocation(event)"/>`. With `windowType="popup"`, "the framework adds JavaScript that launches the action in a new window". | Same page | M |
| `windowType` values in the DTD copy we saw: `applet`, `new` (like popup but with the browser bar), `no_content` (no window), `normal` (submit form), `page` (new page), `popup` (non-modal popup, typically a wizard), `wizard_step`. `ajax` is a separate attribute of `<action>` (`page`, `component`, `row`, `thirdLevelNav`, `popupMenu`). The command `url` attribute "override[s] the generated URL". | Third-party copy of an OOTB `actions.dtd` (older release) | L |
| Labels and tooltips are localized through the objecttype's resource bundle, with keys of the form `<objecttype>.<action>.<property>`. | "Localizing Actions and Action Models", https://support.ptc.com/help/wnc/r12.0.0.0/en/Windchill_Help_Center/WCCG_UICust_AddActionsHook_WCClientArchAction_Localizing_actions.html (existence only) plus DTD | M/L |

### 5.3 Placing the action on WTDocument menus

- **One `menufor` model per type.** An action model declares `menufor="<class>"`, and "there can only be one action model per type with the menufor attribute". That model supplies the info page **Actions** menu and the row (right-click) actions in tables ("Displaying Actions Menu on an Information Page", https://support.ptc.com/help/windchill/r12.1.2.0/es/Windchill_Help_Center/customization/WCCG_UICust_AddActionsHook_DefineMenus_DisplayingActionsMenuInformationPage.html ; "Displaying Actions Column in a Table", https://support.ptc.com/help/windchill/r12.1.2.0/en/Windchill_Help_Center/customization/WCCG_UICust_AddActionsHook_DefineMenus_DisplayingActionsColumnTable.html, **M**).
- **The WTDocument model name.** An official Windchill 11.0 page tells you to add an action to `<model name="docs row actions toolbar" menufor="wt.doc.WTDocument">` in `DocumentManagement-actionmodels.xml`. Two third-party repositories confirm the same model name ("Enabling Mass Updates", http://support.ptc.com/help/windchill/wc110_hc/whc_en/Windchill_Help_Center/WCInstall_WCMPMLinkPostInstall_WCInstall_WCMPMLinkPostInstall_EnableMassUpdates.html, **M** for 11.0, **L** for current releases). **Confirm it on our release with `jcaDebug`.**
- **Add, don't override.** Custom action models "can either be merged with out-of-the-box action models if specified as incremental, or override the existing action models if not specified as incremental" ("Update the Action Model to Add Custom Actions", https://support.ptc.com/help/windchill/plus/r13.1.2.0/en/Windchill_Help_Center/customization/WCCG_Oview_GetStartCust_UpdExisActionModel_wncplus.html, **M**). **We should use the incremental form.** Overriding an OOTB model copies PTC's menu into our file, and it silently diverges on upgrade. The exact incremental and `insertAt` syntax is **NOT VERIFIED**.
- **Discovery tools:**
  - Append `&jcaDebug=true` to a page URL to see the action model names on it.
  - Open the Action Model Report (Navigator → Customization → Tools → Action Model). Source: https://support.ptc.com/help/windchill/r13.0.0.0/en/Windchill_Help_Center/customization/WCCG_UICust_CustHTMLClients_ToolsOview_ActionModel_Report.html, **M**.

### 5.4 Controlling visibility

- **`supportedTypes`.** "By specifying supportedTypes or nonSupportedTypes, the action framework either enables or disables the action depending on the object types". This filtering "is applied before any other validation service class" ("Implementing Validation Filters", https://support.ptc.com/help/windchill/r13.0.0.0/en/Windchill_Help_Center/customization/WCCG_UICust_PresentInfoUI_UIValid_implementing2.html, **M**).
- **Simple validation filters.** Extend `DefaultSimpleValidationFilter` and implement `preValidateAction`. Register the filter under the service `com.ptc.core.ui.validation.SimpleValidationFilter` in xconf, and attach it with `<includeFilter name="..."/>` (**M/L**). Use this to hide the action for unsupported subtypes, working copies, URL-only content, or users who are not in a pilot group.
- **Validators.** `UIComponentValidator` / `DefaultUIComponentValidator` (`com.ptc.core.ui.validation`) (**L**). Method signatures are **NOT VERIFIED**.
- **Hiding an action is not a security control.** The server-side bridge must re-check access on every request (section 8).

### 5.5 How the selected WTDocument reaches the action

- The request carries the object's OID as the `oid` parameter, for example `oid=VR%3Awt.doc.WTDocument%3A<id>` (version reference) or `OR:wt.doc.WTDocument:<id>` (object reference) (**L**).
- Server-side code reads it from `com.ptc.netmarkets.util.beans.NmCommandBean`:
  - `getActionOid()`, which returns `NmOid`, resolved with `getRefObject()`;
  - `getPrimaryOid()`;
  - `getSelectedOidForPopup()`.

  These are seen only in third-party code (**L**). Their official semantics are NOT VERIFIED.
- An OID string is resolved with `new wt.fc.ReferenceFactory().getReference(oidString).getObject()`; `ReferenceFactory` and `WTReference.getObject()` are both Supported (**M+**).
- A `VR:` reference resolves to the **latest iteration** of a version branch ("foreign key pointing to the latest iteration within a branch", `VersionReference` Javadoc, **M+**).
  - **Implication:** the bridge must resolve the OID to a concrete iteration on the server and put that iteration's identity in the result. It must never trust an iteration or content identity sent by the browser.

### 5.6 How the action invokes backend logic

| Mechanism | Evidence | Fit |
|---|---|---|
| **Form processor.** `<command class="…FormProcessor" method="execute">`; custom processors extend `com.ptc.core.components.forms.DefaultObjectFormProcessor` and override `doOperation(NmCommandBean, List<ObjectBean>)`, which returns a `FormResult` | Official example (M); pattern seen in about 30 third-party processors (L) | Good for submit-style actions. A long LLM call should not run synchronously here. |
| **JSP page.** `<command url="/netmarkets/jsp/ext/.../page.jsp" windowType="popup"/>` | Third-party (L) | Good for the result popup shell. Keep the logic in Java classes, not in the JSP (see CS112169, section 4.2). |
| **Wizard.** Steps are actions with `windowType="wizard_step"`, and the wizard opens as a popup | "Windchill Client Architecture Wizard", https://support.ptc.com/help/windchill/cloud/r12.0.2.0/en/Windchill_Help_Center/WCCG_UICust_ConstructWizards_WCClientArchWizard.html (M) | Useful later ("choose which content item to analyze"). |
| **MVC component action.** `<component name="..." windowType="page"/>` | Official snippet (M) plus third-party (L) | For info-page tabs and tables. |
| **Custom WRS domain or action.** | "Windchill Customization Using Windchill REST Services (WRS)", https://support.ptc.com/help/windchill/r13.1.2.0/en/Windchill_Help_Center/customization/WindchillCustomizationUsingWRS.html (M). 13.1.2 also adds a `WRSCaller` Java wrapper (M). | A REST endpoint running as the authenticated user, reusable by future external clients. Its customization details are NOT VERIFIED. |
| Spring MVC controllers inside Windchill | Seen only in third-party copies of PTC internal classes (L) | **Do not rely on it.** It is not documented for customers. |

### 5.7 Displaying the result

- **MVP: a popup.** Use a `windowType="popup"` page hosted by Windchill, which keeps the same origin and session. The page shows the structured result: summary, key points and a citations list. It renders model output **as text only**; model output is untrusted (section 8.7).
- **Later: an info-page tab** ("AI Insights") on the WTDocument info page, through the page's tab-set action model. `jcaDebug` shows the tab-set model name (the part page's is `partInfoPageTabSet`). **The WTDocument tab-set name and the supported way to add a tab are NOT VERIFIED.**
- **Feedback messages.** `FormResult.addFeedbackMessage(new FeedbackMessage(FeedbackType.SUCCESS, …))` (**L**) can report short statuses, for example "analysis queued".

### 5.8 Opening a modern external web UI from Windchill

- **Possible in principle.** The command `url` attribute can override the generated URL (L), and `windowType="new"` or `popup` opens a new window. KB CS420730 covers opening a custom action "as a new tab, but not as a pop-up" (https://www.ptc.com/en/support/article/CS420730, M, title only).
- **ThingWorx hook.** The OOTB document action model includes a `thingworxActionsMenu` submodel (L), which suggests an established hook for ThingWorx/Navigate apps.
- **No official page on launching external URLs was read: NOT VERIFIED.**
- **Security rules if we do this:**
  - Pass **only the object OID** in the URL, never credentials or tokens.
  - The external app must authenticate the user itself, through the shared IdP/SSO, and read content through WRS **as that user** (delegated OAuth, section 6.3).
  - Allowlist the target host.
- This is Pattern P2 in section 9.3.

### 5.9 Deployment of UI customizations

- **Files:** `custom-actions.xml` and `custom-actionModels.xml` go in `<WT_HOME>/codebase/config/actions/` (**M**).
- **Resource bundles and Java classes** are compiled and deployed into `codebase` (the `ext.*` package convention, **L**). Properties are set with `xconfmanager -p`, and the Method Server must be restarted for new classes and services (**L**).
- **Not verified:** whether action XML changes need a restart, or whether a reload utility exists.
- **Release 12.1.2 changed action customization management.** See "Managing Custom Actions, Action Models, and Action Filters", https://support.ptc.com/help/windchill/plus/r12.1.2.0/en/Windchill_Help_Center/NewandChanged/NewandChanged_12_1_20_ActionCustomization.html (**M**, existence only). **Read it for our release.**

### 5.10 Answers to the brief's UI questions

| # | Question | Answer (confidence) |
|---|---|---|
| 1 | How is the action registered? | An `<action>` under `<objecttype name="document" class="wt.doc.WTDocument">` in `custom-actions.xml`, with a label in a resource bundle (M) |
| 2 | How does it appear in the UI? | It is added incrementally to the WTDocument `menufor` action model (`docs row actions toolbar` in 11.0; confirm for our release) through `custom-actionModels.xml`. It then shows in the info page Actions menu and in row actions (M/L). |
| 3 | How is the selected WTDocument passed? | As the `oid` request parameter (`OR:` or `VR:` reference), available from `NmCommandBean` (L) |
| 4 | How does the action get the object identity? | `NmCommandBean.getActionOid()` / `getPrimaryOid()` → `NmOid` → persistable; or `ReferenceFactory.getReference(oid).getObject()` (L / M+) |
| 5 | How does it invoke backend functionality? | A popup page (JSP) plus server-side Java (a form processor, or a custom WRS action) in the Method Server, which calls the AI Gateway (M/L) |
| 6 | How can the result be displayed? | A popup page for the MVP; an info-page tab later (M/L) |
| 7 | Can a modern external web UI be launched? | Yes in principle, through a URL-based action (L). It must authenticate independently and use WRS as the user. |
| 8 | Supported approaches for embedding or opening an external app | URL actions, ThingWorx/Navigate hooks (L). No official embedding guidance found: **NOT VERIFIED**. |

---

## 6. Windchill REST Services (WRS)

### 6.1 Overview

| Finding | Source | Conf. |
|---|---|---|
| WRS "enables developers to configure OData services in Windchill. An OData service… is called a **domain**, and domains expose Windchill object types… as OData **entity types** and **entity sets**." The metadata is OData v4 CSDL. | "Windchill REST Services", https://support.ptc.com/help/windchill_rest_services/r2.0/en/windchill_rest_services/WCCG_RESTAPIsWRS.html ; "OData Services as Domains", https://support.ptc.com/help/windchill_rest_services/r2.5/en/windchill_rest_services/WCCG_RESTAPIsODataAsService.html | M |
| **Service root:** `https://<Windchill server>/Windchill/servlet/odata/`. A GET on it lists the domains. | "Accessing Domains", https://support.ptc.com/help/windchill_rest_services/r1.6/en/windchill_rest_services/WCCG_RESTAPIsAccess.html | M |
| **Versioned domain root:** `https://<Windchill server>/<Windchill App Context>/servlet/odata/<Domain Version>/<Domain Identifier>/`, where the version is `v1`, `v2`, and so on. An unversioned URL uses the domain's default version. | Same page ; Summary of Changes 2.6, https://support.ptc.com/help/windchill_rest_services/r2.6/en/windchill_rest_services/WCCG_REST_atechsum_2.6.html | M |
| **Metadata:** `https://<Windchill server>/Windchill/servlet/odata/<Domain>/$metadata` returns the domain's entity data model in CSDL. | Same | M |
| Domains named in official snippets: `ProdMgmt`, `DocMgmt`, `PrincipalMgmt`, `ChangeMgmt`, `MfgProcMgmt`, `Visualization`, `CADDocumentMgmt`, `PTC` (common). | Various | M |
| **PTC common domain functions:** `GetCSRFToken()`, `GetWindchillVersion()` ("returns a list of installed modules along with the currently installed version of Windchill"), `GetEnumTypeConstraint()`, `GetAllStates()`. | "Functions Available in the PTC Common Domain", https://support.ptc.com/help/windchill_rest_services/r2.7/en/windchill_rest_services/WCCG_RESTAPIsAccessPTCCommonDomainsfunctions.html | M |
| **API catalog (Swagger).** Opened from the Windchill UI (Preference "Client Customization" = Yes → Customization → Documentation → REST APIs). It lists every endpoint and lets you run requests interactively. Catalog files are in `<Windchill>/codebase/netmarkets/html/wrs/catalog`. | "API Catalog for Windchill REST Services Endpoints", https://support.ptc.com/help/windchill/r13.0.2.0/en/Windchill_Help_Center/WCRESTFramework/API_catalog.html ; KB CS335170, https://www.ptc.com/en/support/article/CS335170 | M |
| Community-reported URLs: `/Windchill/netmarkets/html/wrs/doc.html`, and `/Windchill/netmarkets/html/wrs/odata-to-swagger.jsp?v=<n>&d=<Domain>` (Swagger JSON per domain) | https://community.ptc.com/t5/Windchill-Customization/Swagger-URL-for-the-Odata-API/td-p/809504 | M (Community) |

**Practice for this project:** pin domain versions explicitly (e.g. `/v6/DocMgmt/`), and generate our understanding of entities from `$metadata` on *our* server, not from documentation.

### 6.2 How WRS is versioned and shipped

- **From 12.1.2.11, WRS ships with Windchill.** "WRS has been integrated with Windchill 12.1.2.11… WRS follows the same release version as Windchill". It "is bundled with Windchill and is installed and updated with a full or CPS release" ("Windchill REST Services Integrated with Windchill", https://support.ptc.com/help/windchill/plus/r12.1.2.0/en/Windchill_Help_Center/NewandChanged/NewandChanged_12_1_2_11_WRSWindchillIntegration.html, **M**).
- **Before that, it was a separate module** with its own releases (1.1–1.7, 2.0–2.7) that had to be staged in PSI at install time (**M**).
- **The mapping from WRS version to Windchill release** is in KB CS318837 (https://www.ptc.com/en/support/article/CS318837), which could not be read: **NOT VERIFIED**.

### 6.3 Authentication

| Method | Finding | Source | Conf. |
|---|---|---|---|
| Basic / web-server authentication | The default on-prem web-tier authentication applies to `/Windchill/servlet/odata/...` | Community (AuthResAdditions thread) | M |
| **OAuth 2.0 bearer** | "the client must call URLs containing the 'oauth' prefix". Example: `GET https://<HOSTNAME>/Windchill/oauth/servlet/odata/ProdMgmt/Parts` with `Authorization: Bearer <access_token>`. Two flows: **Client Credentials** (M2M) and the **delegated authorization-code flow** (interactive). The docs advise short-lived tokens. | "WRS OAuth Authorization", https://support.ptc.com/help/windchill_rest_services/r2.7/en/windchill_rest_services/oauth_for_wrs.html | M |
| Windchill as the resource server | Delegated authorization means "the user authorizes the service provider (application) to act on their behalf to retrieve their information from the resource server (Windchill)". Configured through `securityContext.properties` and `web.xml`. Authorization servers: **PingFederate** as central authorization server, and **Microsoft Entra ID** ("for Windchill 12.0.2.2 and later"). | "Configure OAuth Delegated Authorization" (13.1.0.0), https://support.ptc.com/help/windchill/r13.1.0.0/it/Windchill_Help_Center/WCAdvDeployGuide/WCAdvDepAuth_ConfigAltAuth_RegisterScope.html ; https://support.ptc.com/help/identity_and_access_management/en/iam/AzureADasCASandIdP_Windchill.html | M |
| M2M identity | The machine identity "must be defined in LDAP like any other user… used only for integration purposes". It has no direct login and must never be assigned workflow or e-signature tasks. | "Registering a Non-interactive Client with Windchill through WRS", https://support.ptc.com/help/windchill/plus/r12.1.2.0/en/Windchill_Help_Center/customization/WCAdvDepAuth_M2MAuthorizationSOS.html ; https://support.ptc.com/help/windchill/r13.1.2.0/en/Windchill_Help_Center/WCAdvDeployGuide/WCAdvDepAuth_M2MAuthorization.html | M |
| Windchill+ | "the application must present an OAuth access token to Windchill+ through the Windchill Rest Services". OAuth clients are created on the PTC Admin Center **Integrations** page. | https://support.ptc.com/help/ptc_saas/admin/en/admin/IntegrationsPage.html | M |

### 6.4 CSRF protection

- **Fetch the nonce:** `GET /Windchill/servlet/odata/PTC/GetCSRFToken()`. The response contains `"NonceKey": "CSRF_NONCE"` and `"NonceValue": "<token>"`.
- **Send it:** as a **`CSRF_NONCE`** request header on POST, PUT, PATCH and DELETE.
- Sources: "Fetching a NONCE Token from a Service", https://support.ptc.com/help/windchill_rest_services/r2.7/en/windchill_rest_services/WCCG_RESTAccessExamplesFetchNONCE.html ; KB CS330422, https://www.ptc.com/en/support/article/CS330422. Confidence: **M**.
- **What this means for us:**
  - A read-only integration that uses only GETs needs no nonce.
  - Any POST action or `$batch` request needs one, including a custom `Summarize` action called from our popup.
  - Whether bearer-token calls need the nonce is **NOT VERIFIED**.

### 6.5 Document Management domain (DocMgmt)

- **Purpose:** "provides entities that enable users to manage Windchill documents (WTDocuments)… create documents, and… upload and download content" ("PTC Document Management Domain", https://support.ptc.com/help/windchill_rest_services/r2.6/en/windchill_rest_services/docmgmtdomain.html, **M**).
- **Entity set:** `Documents`.
- **Navigation properties** confirmed officially: `PrimaryContent` and `Attachments` (**M**). Generated third-party clients also show `Context`, `Creator`, `DocUsageLinks`, `Representations` and `Revisions` (**L**).
- **Actions:** `CheckInDocuments()`, `CheckOutDocuments()`, and a three-stage upload (`PTC.DocMgmt.UploadStage3Action`) (**M**).
- **Scalar properties** (Number, Name, Version/Revision, Iteration, State, ...) are **NOT VERIFIED**. Read them from `/DocMgmt/$metadata` on the target system.

### 6.6 Content and download

| Operation | Official example (quoted) | Conf. |
|---|---|---|
| Primary content | `PUT /Windchill/servlet/odata/DocMgmt/Documents('OR:wt.doc.WTDocument:2626068')/PrimaryContent` (update). GET on the same navigation reads it. | M |
| Attachments | `POST /Windchill/servlet/odata/DocMgmt/Documents('{document_ID}')/Attachments` (create). GET reads them; for change objects, `GET /Windchill/servlet/odata/ChangeMgmt/ChangeRequests('OR:wt.change2.WTChangeRequest2:229667')/Attachments`. | M |
| Expand through links | `GET /Windchill/servlet/odata/MfgProcMgmt/Sequences('OR:…MPMSequence:11223344')/DocumentDescribeLinks?$expand=DescribedBy($expand=PrimaryContent)` | M |
| Download | A content item's `Content` property has a `URL` (KB CS372037, https://www.ptc.com/en/support/article/CS372037). The URL points to a Windchill download servlet (`/Windchill/servlet/WindchillAuthGW/wt.fv.master.RedirectDownload/redirectDownload/...`, L). The download sequence is **401 → 302 → 200** (KB CS400695, https://www.ptc.com/en/support/article/CS400695): the client must authenticate and follow the redirect. | M/L |

Not verified:
- whether the download servlet accepts OAuth bearer tokens under `/oauth`;
- whether the `$value` media stream is supported;
- exactly how Download permission is enforced for WRS-issued URLs.

**These are the first things to test** (Phase 1, section 13).

### 6.7 The brief's ten WRS questions

| # | Need | How (status) |
|---|---|---|
| 1 | Identify a WTDocument | Key `Documents('OR:wt.doc.WTDocument:<id>')`, URL-encoded (M). By number: `$filter=Number eq '...'` is standard OData but **NOT VERIFIED** for WRS. KB CS345886 covers getting content by document number. |
| 2 | Read metadata | `GET .../DocMgmt/Documents('<oid>')`, using `$select` and `$expand` (M). Property names come from `$metadata` (NOT VERIFIED). |
| 3 | Read primary content | `GET .../Documents('<oid>')/PrimaryContent` (M) |
| 4 | Read attachments | `GET .../Documents('<oid>')/Attachments` (M) |
| 5 | Download content | Follow the item's `Content/URL` with authentication and redirects (M/L) |
| 6 | Version or revision | Entity properties (NOT VERIFIED names). A `Revisions` navigation exists (L). |
| 7 | Current iteration | `ptc.search.latestversion=true` returns the latest version; `false` returns "the latest iteration of each revision" ("Retrieving the Latest Version of an Entity", https://support.ptc.com/help/windchill_rest_services/r2.7/en/windchill_rest_services/wccg_restapis_latest_version_search.html, M) |
| 8 | Related documents | ProdMgmt "references the PTC Document Management domain to provide navigations to reference and describe documents" (https://support.ptc.com/help/windchill_rest_services/r2.7/en/windchill_rest_services/prodmgmtdomain.html, M). A `DocUsageLinks` navigation exists (L). Exact names are NOT VERIFIED. |
| 9 | Current user | **NOT VERIFIED.** No "GetCurrentUser" function was found. `PrincipalMgmt` has `Users` (L). Inspect `PrincipalMgmt/$metadata` and `PTC/$metadata` on the target. |
| 10 | Respect authorization | Calls execute as the authenticated principal (M, from the OAuth docs' framing). Filtering and 403/404 semantics are NOT VERIFIED and need negative tests. **No impersonation ("run-as") mechanism was found**, so per-user enforcement requires the user's own credential or token. |

**Limits:**
- Paging with `Prefer: odata.maxpagesize` and `@odata.nextLink` is seen only in third-party code (L).
- No documented rate limits were found.
- Large files come through the download servlet, not the OData payload.

---

## 7. Relevant Java APIs

### 7.1 Supported APIs this project would use (all M+; verify against local Javadoc)

| Area | API | Use |
|---|---|---|
| Identity | `wt.fc.ReferenceFactory#getReference(String)`, `#getReferenceString(Persistable)`; `WTReference#getObject()`; `wt.fc.ObjectIdentifier` | Resolve an OID to an object and back |
| Persistence | `PersistenceHelper.manager.find(StatementSpec)`, `.refresh(...)`, `.navigate(...)`; `wt.query.QuerySpec`, `SearchCondition` | Look up documents; navigate links |
| Versions | `VersionControlHelper.getVersionIdentifier`, `getIterationIdentifier`, `isLatestIteration`; `.service.getLatestIteration`, `allVersionsOf` | Pin results to an iteration |
| WIP | `WorkInProgressHelper.isWorkingCopy`, `isCheckedOut` | Exclude or label working copies |
| Content | `ContentHelper.service.getContents`, `ContentHelper.getPrimary`, `getContentListAll`, `ContentHelper.service.getContentsByRole`; `ApplicationData#getFileName/getFileSize/getChecksum`; `ContentServerHelper.service.findContentStream(ApplicationData)` | Select and stream content |
| Representations | `RepresentationHelper.service.getDefaultRepresentation(Representable)`; `com.ptc.wvs.server.util.PublishUtils` | Find published PDFs |
| Access | `AccessControlHelper.manager.hasAccess(Object, AccessPermission)` and `hasAccess(WTPrincipal, Object, AccessPermission)`; `AccessPermission.READ`, `AccessPermission.DOWNLOAD` | Explicit permission gate |
| Session | `SessionHelper.manager.getPrincipal()`, `SessionHelper.getLocale()`; `SessionServerHelper.manager.isAccessEnforced()` | Who is asking; assert enforcement is on |
| Types | `PersistableAdapter`; `ClientTypedUtility.getTypeIdentifier` | Subtype gating; later attribute write-back |
| Services / events | `StandardManager`, `ManagerService#addEventListener`, `ServiceEventListenerAdapter`, `KeyedEvent.generateEventKey(Class, String)`, `WorkInProgressServiceEvent.POST_CHECKIN`, `PersistenceManagerEvent` | Later: pre-compute results on check-in |
| Queues | `QueueHelper.manager.getQueue(String)`, `addEntry(...)` | Later: background processing inside Windchill, if needed |
| Remote invocation | `RemoteMethodServer.getDefault().invoke(...)`; classes tagged `wt.method.RemoteAccess` | Only needed for client-side Java; not planned |

### 7.2 APIs and practices to avoid

| Item | Why |
|---|---|
| `SessionServerHelper.manager.setAccessEnforced(false)` | It "suspends… all access & authorization enforcement" for the thread (Javadoc, M+). Any content read this way ignores ACLs, Download, labels and agreements. Windchill+ explicitly forbids bypassing access control (M). **Never use it in the AI path.** |
| `SessionHelper.manager.setAdministrator()` / `setPrincipal(...)` | Privilege escalation or impersonation. The same objection applies. |
| `ContentServerHelper.service.findLocalContentStream` | Not in the Supported API (M+) |
| `RemoteMethodServer.ServerFlag`, `QueueHelper.manager.createQueue`, the single-argument `WorkInProgressServiceEvent.generateEventKey(String)` | Common in community code, but not documented as Supported (M+) |
| Hand-built `ContentHttp` URLs | Unsupported; use `ContentHelper.getDownloadURL` |
| Reading vault folders or BLOB tables | Unsupported; bypasses security (section 4.4) |
| Decompiling or replacing PTC classes, or editing shipped source | Prohibited or unsupported (PTC Customer Support Guide, https://www.ptc.com/en/support/customer-support-guide/guidelines_legal-windchill-solutions/supported-and-nonsupported-usage-of-the-api, M) |
| Heavy third-party jars in `codebase/WEB-INF/lib` | Upgrades have removed libraries (XStream, `javax.ws.rs`), breaking customizations (PTC Community, M). Prefer the JDK's own `java.net.http.HttpClient` for outbound calls. |

**What "Supported API" means:** "The Javadoc provided with Windchill defines the Supported API". Classes and methods carry *Supported* and *Extendable* flags, and supported elements "will not be changed without notification and a deprecation period, whenever possible" ("Windchill Customization Points", https://support.ptc.com/help/windchill/r12.1.2.0/en/Windchill_Help_Center/customization/WCCG_Oview_CustOview_WCCustPoints.html, **M**).

### 7.3 What runs inside the Method Server and what runs outside

| Inside Windchill (Method Server, as the logged-in user) | Outside Windchill (AI zone) |
|---|---|
| Action definition, labels, visibility filters | Text extraction (PDF, Office), OCR |
| Resolving the OID to a concrete iteration | Chunking, prompt construction, schema enforcement |
| **The authorization decision** (READ + DOWNLOAD) | LLM inference (Ollama) |
| Selecting the content item; streaming the bytes (`findContentStream`) | Validation, citation verification |
| Calling the AI Gateway (short, with timeouts; asynchronous job) | Result cache and job store |
| Rendering the result popup (escaped text) | Model and prompt management, evaluation |

**Rationale:**
- The Method Server is a shared, stateful, upgrade-sensitive JVM that serves every Windchill user. CPU- and GPU-heavy or long-running work does not belong there, and neither do Python ML dependencies.
- The authorization decision *must* happen in Windchill, because only Windchill can evaluate ACLs, labels, agreements and state-based rules correctly.

---

## 8. Authentication and security

### 8.1 Authentication chain

- **The web tier authenticates.** Windchill identifies the user from `HttpServletRequest.getRemoteUser()` / `getUserPrincipal()`, which the web tier sets, normally as REMOTE_USER. Most alternative schemes (SSO agents and so on) work by populating REMOTE_USER ("Configuring an Alternative Authentication in Windchill", https://support.ptc.com/help/wnc/r12.0.0.0/en/Windchill_Help_Center/WCAdvDepAuth_ConfigAltAuth.html, **M**).
- **The Method Server ties calls to that user.** It binds each call to the authenticated user, using credentials carried with RMI calls plus digital signatures ("User Authentication", https://support.ptc.com/help/windchill/wc111_hc/whc_en/Windchill_Help_Center/WCRuntimeEnvironment_ServerSoftwareComponent_UserAuthenticate.html, **M**).
- **Supported mechanisms:**
  - web-server authentication backed by LDAP;
  - SSL/TLS client certificates;
  - SSO, with **PingFederate** as the central authorization server and Windchill as OAuth resource server ("Single Sign-on Authentication", https://support.ptc.com/help/windchill/r13.1.2.0/en/Windchill_Help_Center/WCAdvDeployGuide/WCAdvDepAuth_ConfigAltAuth_SSO.html, **M**);
  - Entra ID as CAS and IdP, for 12.0.2.2 and later (**M**).
- **`wt.auth.trustedHosts`** lists hosts, such as publishing workers and ThingWorx Navigate servers, that Windchill trusts as servers (KB CS220310, **M**).
  - **We should not make the AI Gateway a trusted host.** A trusted host is effectively allowed to assert identity. If the gateway were one and were compromised, an attacker could impersonate any user (L, inferred).
- **Reverse proxies.** Because Windchill trusts the web tier's REMOTE_USER, the servlet engine must not be directly reachable, and identity headers from clients must be stripped. We found no official PTC page on this (L).

### 8.2 Authorization model

| Element | Finding | Source | Conf. |
|---|---|---|---|
| Rule types | **Policy** rules (per domain, type and state) and **ad hoc** rules (per object). Permissions can be **granted, denied or absolutely denied** to users, groups, organizations and roles. | "Access Permissions", https://support.ptc.com/help/windchill/r12.1.2.0/en/Windchill_Help_Center/policyadmin/PolicyAdminPermissionAbout.html ; "Using the Absolute Deny Permission", https://support.ptc.com/help/windchill/plus/r12.0.2.0/en/Windchill_Help_Center/PolicyAdminAbsoluteDenyUse.html ; "How ACLs Work", https://support.ptc.com/help/windchill/plus/r12.0.2.0/en/Windchill_Help_Center/AccessControlChp_HowACLsWork.html | M |
| **Read vs Download** | **Download:** "the right to access the primary content and attachments of a content holder where the source is a local file." **Read:** needed to access an object and see its information page. **Modify Content:** add, replace or delete content. | "Access Permissions" (above) ; "Content Holder Information", https://support.ptc.com/help/windchill/cloud/r12.0.2.0/en/Windchill_Help_Center/AccessControlChp_ContentHolderInfo.html | M |
| Primary vs secondary content | One Download permission covers both primary content and attachments. Out of the box they cannot be separated. | https://community.ptc.com/t5/Windchill/Policy-Rules-vs-Primary-Content-Secondary-Content-Download/td-p/889786 | M (Community) |
| Life cycle state | Policy access is keyed by type, domain **and state**: `hasAccess(WTPrincipal, String type_id, AdminDomainRef, State, AccessPermission)` | KB CS240370, https://www.ptc.com/en/support/article/CS240370 | M |
| Teams and contexts | Container team membership and roles drive access. Project content is limited to members by default. | "Accessing Team Permissions", https://support.ptc.com/help/windchill/cloud/r12.0.2.0/en/Windchill_Help_Center/SecurityMgmtTeamAccess.html ; https://support.ptc.com/help/windchill/r13.0.1.0/en/Windchill_Help_Center/orgadmin_chp/OrgAdminChp_BestPracticeProjProgAllowAllOrgMemberReadAccess.html | M |
| Security labels and agreements | Labels (standard and custom, e.g. for export control) further restrict access beyond ACLs, and agreements grant time-limited authorization. Only the existence of agreements and the Agreement Manager role is confirmed ("Setting Access Control Permissions for Agreement Managers", https://support.ptc.com/help/windchill/plus/r12.0.2.0/en/Windchill_Help_Center/SecurityLabelConfigAgreementManagerAccessControlPermissions.html). The evaluation semantics are **NOT VERIFIED**. | — | M / NOT VERIFIED |

### 8.3 Checking access in code, and the pitfalls

- **API:** `AccessControlHelper.manager.hasAccess(obj, AccessPermission.READ)` checks the session principal, and `hasAccess(principal, obj, AccessPermission.DOWNLOAD)` checks a given principal (M+ / KB CS316454, https://www.ptc.com/en/support/article/CS316454, **M**).
- **Pitfall 1: enforcement may be suspended.** In workflow robots and expressions, access control is **not checked**, and `hasAccess` has been reported to **always return true** there (CS316454). PTC's workflow documentation recommends `SessionServerHelper.manager.setAccessEnforced(true)` when checks are needed ("Access Control and Workflow Templates", https://support.ptc.com/help/windchill/plus/r13.1.2.0/en/Windchill_Help_Center/workflow_chp/WFChp_AccessControl.html, **M**).
  - Our bridge must assert that `isAccessEnforced()` is true before its check.
  - It must be tested with **negative cases**: a user with Read but no Download, and a user without the clearance for a labelled document.
- **Pitfall 2: a Community report** shows `hasAccess(user, doc, DOWNLOAD)` returning true while the UI denied the download (https://community.ptc.com/t5/Windchill/AccessControlHelper-to-check-Download-Access-permission/td-p/360339, **M**). The root cause is unknown. This is exactly why negative tests are mandatory.
- **Unknown:** whether `ContentHelper` and `ContentServerHelper` enforce Download themselves. **Assume they do not** and check explicitly.
- **`wt.access.enforce`.** A global property of this name exists (KB CS291509). Deployment checks should confirm it is at its default, enforced. Its exact semantics are **NOT VERIFIED**.

### 8.4 CSRF, hardening, TLS, current threats

- **CSRF.** Windchill UI actions built with JCA and GWT are CSRF-protected. Custom code on Windchill+ must use `CSRFProtector` APIs for create, modify and delete actions (M). For WRS, see section 6.4.
- **Hardening.** "Best Practices for Securing Your Windchill Solution" (https://support.ptc.com/help/windchill/r13.1.2.0/en/Windchill_Help_Center/WCSysAdminWCConsiderSecureInfrastructure/WCConsiderSecureInfrastructure_SecurityBestPractice.html ; KB CS310152, **M**) recommends:
  - a trusted network;
  - HTTPS/TLS;
  - 256-bit encryption keys;
  - database encryption at rest (TDE);
  - removing samples;
  - OS hardening;
  - auditing critical events.
- **Threat context:** CVE-2026-4681 is a critical deserialization remote code execution flaw in Windchill PDMLink 11.0 M030 through 13.1.3.0. It was reported exploited in the wild and added to CISA's Known Exploited Vulnerabilities list (CISA ICSA-26-085-03, https://www.cisa.gov/news-events/ics-advisories/icsa-26-085-03 ; PTC advisory https://www.ptc.com/en/about/trust-center/advisory-center/active-advisories/windchill-flexplm-critical-vulnerability, **M**). **Implications:**
  - The add-on must not open new unauthenticated paths into Windchill.
  - Our target system's patch level matters.

### 8.5 Which identity performs the content read

| Option | How | Per-user enforcement | Verdict |
|---|---|---|---|
| **S1. Session user, inside Windchill** (Pattern P1) | The bridge runs in the user's own Method Server request. It checks READ + DOWNLOAD and streams the content. | **Yes. Windchill evaluates everything natively.** | **Recommended for the MVP (on-prem)** |
| **S2. Delegated OAuth through WRS** (Pattern P2) | An external app obtains the *user's* token (authorization-code flow) and calls `/Windchill/oauth/servlet/odata/...` | **Yes.** Needs OAuth infrastructure (PingFederate or Entra ID). Bearer support on the download URL is NOT VERIFIED. | **Recommended for Windchill+ and the future external UI** |
| S3. Service account (M2M client credentials) | A single integration identity reads the content | **No.** It sees the union of everything it was granted. Acceptable only for background pre-processing, and then **every result must be gated by a fresh per-user S1 or S2 check before display**. | Deferred; only with strict gating |
| S4. Trusted host / impersonation / enforcement disabled | — | Bypassable | **Rejected** |

### 8.6 Security rules for the AI capability

1. **Windchill makes every authorization decision** for the requesting user at request time, **including when the result comes from cache**. The AI Gateway never decides who may see what.
2. **Content-derived output requires READ + DOWNLOAD** on the specific document iteration whose content was used. For multi-document features, the user needs this on *every* source document.
3. **Never** read content with access enforcement disabled, as Administrator, or through a trusted-host or impersonation mechanism.
4. In the MVP the **AI Gateway holds no Windchill credentials**. It only processes content that an authorized Windchill request pushed to it. It authenticates its caller with mTLS or a signed service token.
5. **Cache key** = document iteration OID + content-item checksum + pipeline version (extractor, prompt, schema, model digest). A cached result is served **only** in response to a request that just passed rule 1.
6. **No cross-document retrieval in the MVP.** Q&A (a later phase) is scoped to documents that were authorized in the same request. A corpus-wide vector index would need per-user filtering plus a live re-check (rule 1), and is explicitly deferred.
7. **Do not log document text**, prompts or completions in general logs. Keep an audit trail of ids only: user, object and iteration, content checksum, permission decision, task, time, and pipeline version.
8. **Treat model output as untrusted.** Render it as text (HTML-encoded), with no auto-loaded links or images. This addresses OWASP LLM05 and prevents XSS and data exfiltration.
9. **The LLM has no tools and no write access** to Windchill (OWASP LLM06).
10. **Transport:** TLS everywhere. Ollama listens only on localhost or a private interface behind the gateway, with `OLLAMA_NO_CLOUD=1` (section 9.6).
11. **Security labels and export control.** Whether labelled or export-controlled documents may be processed at all, even locally, is a **policy decision for the customer** (Q-SEC-2). The design supports excluding them through a validation filter plus a server-side check.
12. **Retention.** Define how long cached results and extracted text are kept. Purge them when a document is deleted or when its iteration is superseded.

### 8.7 AI-specific threats and mitigations (OWASP Top 10 for LLM Applications 2025)

Source: https://github.com/OWASP/www-project-top-10-for-large-language-model-applications/tree/main/2_0_vulns — **H**.

| Threat | Relevance here | Mitigation |
|---|---|---|
| LLM01 Prompt Injection (indirect, through document text) | A document can contain text that tries to steer the model, including hidden white-on-white text (OWASP LLM08 example) | Mark and delimit document text as data. Use schema-constrained output and deterministic validation. Give the model no tools. Detect hidden or invisible text. Verify quotes (section 9.6). |
| LLM02 Sensitive Information Disclosure | Cached or indexed content shown to the wrong user | Rules 1, 5, 6 and 7 |
| LLM05 Improper Output Handling | Model output rendered in Windchill pages | Rule 8 |
| LLM06 Excessive Agency | — | Rule 9 |
| LLM08 Vector and Embedding Weaknesses | Future RAG index | Per-document scoping. Permission-aware retrieval plus live re-check. Treat the store like Windchill's Solr index or stricter. |
| LLM09 Misinformation | Hallucinated requirements or values in engineering documents | Citations with quote verification. Label unverified items. Show a "review before use" notice. |
| LLM10 Unbounded Consumption | Large PDFs, many concurrent users | Size and page limits, timeouts, a queue, rate limits |
| Ollama API exposure | **Ollama has no built-in authentication.** Model-management routes (`pull`, `push`, `create`, `delete`) are unauthenticated by design (GHSA-f6mr-38g8-39rg). CVE-2026-7482 was a memory disclosure bug through `/api/create`, fixed in 0.17.1 (secondary reports, M). | Bind to localhost. Put an authenticating proxy in front that allowlists only `/api/chat`, `/api/embed` and `/api/version`. Pin a patched version. Set `OLLAMA_NO_CLOUD=1`. |

---

## 9. Recommended integration architecture

### 9.1 Design principles

1. **Windchill is the system of record and the only authority on access.** The AI layer never becomes a second way into documents.
2. **Keep the in-Windchill footprint thin** and limited to supported APIs: action XML, one validation filter, one small bridge component and one result page. Everything heavy runs outside.
3. **The AI layer does not know how content reached it.** The gateway accepts content plus metadata through a versioned API. Today content arrives by push from the bridge (P1); tomorrow a WRS connector (P2) can supply it, without changing extraction, prompts or schemas.
4. **Every output is structured, versioned and grounded.** JSON schema, citations and provenance.
5. **Asynchronous by default.** LLM work takes seconds to minutes, so no Method Server thread waits on the LLM.
6. **Build incrementally.** New capabilities are new *tasks* in the same pipeline, not new integrations.

### 9.2 Where each component runs

```
┌──────────────────────────── WINDCHILL (customer data center) ────────────────────────────┐
│                                                                                           │
│  Browser — user's normal Windchill session                                                │
│   WTDocument info page / table row ──► [AI Summarize] action  (custom-actions.xml,        │
│                                          incremental add to the WTDocument action model,  │
│                                          visibility via supportedTypes + filter)          │
│        │ opens popup (windowType="popup")                                                 │
│        ▼                                                                                  │
│   "AI Insights" page (Windchill-hosted, same origin; renders JSON as escaped text)        │
│        │ XHR within the Windchill session (CSRF-protected)                                │
│        ▼                                                                                  │
│  Method Server — "AI Bridge" (ext.* package, supported APIs only)                         │
│    1. resolve oid → concrete WTDocument iteration (server-side, never trust client)       │
│    2. assert access enforcement ON; hasAccess(user, doc, READ) && hasAccess(…, DOWNLOAD)  │
│    3. select content item (primary PDF → default representation PDF → error)             │
│    4. submit job to AI Gateway: metadata + requester id + content stream (bounded size)   │
│       or, if cache hit for (iteration, checksum, pipelineVersion), fetch cached result     │
│    5. poll: re-check access (steps 1-2) on every poll before returning result             │
│    6. audit event (ids only)                                                              │
└────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                             │ HTTPS + mTLS (bridge ⇄ gateway only)
┌────────────────────────────────────────────▼─── AI ZONE (customer network, no internet) ──┐
│  AI Gateway (e.g. Python FastAPI) — authenticates the bridge; job queue; result store;    │
│                                       schema registry; audit; rate/size limits            │
│    ├── Document Processor: type sniffing, page-aware PDF text extraction,                 │
│    │                        OCR for pages without a text layer, Office conversion,        │
│    │                        hidden-text detection, page-tagged chunking                   │
│    └── AI Engine: task templates (summary, key points, …) + JSON schema                   │
│                   → Ollama (localhost / private interface only, OLLAMA_NO_CLOUD=1)         │
│                   → Pydantic validation → citation/quote verification → result JSON       │
│  Result store: keyed by (iteration OID, content checksum, pipeline version); no ACLs      │
│                stored here because it is never queried except via the bridge              │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

**Mapping to the brief's target diagram:**
- *Windchill Integration* is the action, the page and the AI Bridge, all inside Windchill.
- *AI Gateway*, *Document Processor*, *AI Engine / Ollama* and *Structured AI Response* all run in the AI zone.
- *AI Experience* is the Windchill-hosted popup now and an info-page tab later. Under P2 it would be an external SPA.

### 9.3 Two integration patterns

| | **P1: In-Windchill bridge (push)** | **P2: External app + delegated OAuth (pull)** |
|---|---|---|
| Flow | The action opens a Windchill page. The bridge in the Method Server checks access and pushes the content to the gateway. | The action opens an external web app, passing only the OID. The app signs the user in through the IdP, obtains the user's OAuth token and calls WRS `/oauth/servlet/odata/...` as that user. |
| Who enforces access | Windchill, natively, in the user's session | Windchill, through WRS under the user's token |
| Infrastructure prerequisites | None beyond network reachability from the Method Server to the gateway | OAuth authorization server (PingFederate or Entra ID) configured for Windchill; SSO for the external app |
| Windchill footprint | Action XML, a filter, a bridge class and a JSP page (recompiled and tested on upgrades) | Action XML only (URL action) |
| Windchill+ | Server-side Java needs the CCD process and guardrail approval; outbound calls from SaaS to an on-prem Ollama may be impossible | **The natural fit.** Integrations must be REST over HTTP (M). |
| UI | Classic Windchill look; limited to the JSP page | A modern single-page app, with the richest UX (chat, side-by-side revision diff) |
| Unknowns | Outbound HTTP from the Method Server (no official guidance found); the result page mechanism on the Next Gen UI | Bearer tokens on the download URL; CSRF with bearer tokens; the current-user function |
| **Recommendation** | **The MVP, if on-prem** | **Phase 2+, or from the start if the customer runs Windchill+ or already has OAuth for WRS** |

The gateway API is the same for both patterns (principle 3), so choosing P1 now does not block P2 later.

### 9.4 "AI Summarize" request flow (MVP, P1)

1. The user clicks **AI Summarize** on a WTDocument. The action is visible only for supported subtypes and checked-in iterations with file content.
2. The popup opens and requests a summary from the bridge for `oid` (a session XHR with CSRF protection).
3. The bridge resolves the OID to the iteration (e.g. `0000123 B.3`) and asserts access enforcement is on. It checks READ and DOWNLOAD for `SessionHelper.manager.getPrincipal()`. On failure it returns "You do not have permission to view this document's content" and writes an audit record.
4. The bridge selects the content item and computes the cache key from the iteration, `ApplicationData.getChecksum()` and the pipeline version. On a cache hit it returns the stored result.
5. On a miss, it streams the content through `findContentStream` to `POST /v1/jobs` on the gateway (mTLS). The job carries the task `summary`, the metadata (number, name, revision, iteration, state, type, file name, checksum), the requester's user id (for audit only) and the content. The gateway returns `jobId`.
6. The popup polls the bridge, and the bridge re-runs step 3 **on every poll** before calling `GET /v1/jobs/{id}`.
7. The gateway pipeline runs: extract → OCR if needed → chunk → map/reduce with Ollama under a schema → validate → verify citations → store.
8. The popup renders the header (document, revision, iteration, content file, generated time, model), the summary, key points and citations as `p. N`. Unverified items are flagged. A notice says "AI-generated; verify against the source".

### 9.5 Gateway API and response schema (design sketch, not code)

**API** (versioned, internal):
- `POST /v1/jobs` creates an analysis job.
- `GET /v1/jobs/{id}` returns the status or the result.
- `GET /v1/capabilities` lists the tasks, schema versions and limits.
- Only the bridge (later also the P2 connector) can call it. It authenticates with mTLS or a client certificate.

**Result envelope**, with the task-specific payload in `result`:

```json
{
  "schemaVersion": "1.0.0",
  "task": "summary",
  "status": "completed",
  "document": {
    "oid": "OR:wt.doc.WTDocument:123456",
    "number": "0000123", "name": "Pump housing specification",
    "revision": "B", "iteration": "3", "state": "RELEASED",
    "contentItem": { "role": "PRIMARY", "fileName": "pump-spec.pdf", "checksum": "…", "pages": 42 }
  },
  "result": {
    "summary":        { "text": "…", "citations": [ { "page": 3, "quote": "…", "verified": true } ] },
    "keyPoints":      [ { "text": "…", "citations": [ … ] } ],
    "requirements":   [ { "id": "R-001", "statement": "Operating temperature shall be -20 °C to 80 °C",
                          "modality": "shall", "citations": [ { "page": 3, "quote": "…", "verified": true } ] } ],
    "specifications": [ { "parameter": "Operating temperature", "min": -20, "max": 80, "unit": "°C",
                          "citations": [ … ] } ],
    "risks":          [ { "text": "…", "severity": "medium", "citations": [ … ] } ],
    "actions":        [ { "text": "…", "citations": [ … ] } ]
  },
  "quality": { "pagesTotal": 42, "pagesOcr": 0, "itemsUnverified": 1, "truncated": false, "warnings": [] },
  "provenance": { "extractor": "…", "model": "…", "modelDigest": "…", "promptVersion": "summary@1.2",
                  "generatedAt": "2026-09-24T10:00:00Z" }
}
```

- **MVP scope:** the MVP fills only `summary` and `keyPoints`. The other arrays belong to the same schema family, so later capabilities are additive.
- **Citation shape:** a citation always names the content item (implicitly, the one in `document.contentItem`), the page number (plus the printed page label when it differs) and a short verbatim quote. `verified` is set by deterministic code, not by the model.

### 9.6 AI layer design (the brief's section 11)

The open-source findings below are **H** unless marked; they were verified against each project's GitHub repository.

**Extraction:**
- Digital PDFs: **pdfplumber** (MIT; per-page characters and words with `page_number`; tables) or **pypdf** (BSD-3; per-page text; `page_labels`).
- Layout- and table-aware extraction, and DOCX, XLSX and PPTX: **Docling** (MIT code). It gives provenance (`page_no`, `bbox`) on every item. Models must be pre-downloaded for air-gapped use (`docling-tools models download`, `DOCLING_ARTIFACTS_PATH`), and remote services stay off unless explicitly enabled.
- **Avoid PyMuPDF/PyMuPDF4LLM without a commercial licence.** It is **AGPL-3.0**, which is risky for a network service.
- JVM alternative: Apache Tika 4.x or PDFBox (Apache-2.0). Do not configure Tika 4's cloud VLM parsers.
- Legacy DOC, XLS and PPT, and RTF: convert with headless LibreOffice.

**OCR:**
- Detect pages that need it: few characters, a high share of U+FFFD replacement characters, or a page that is mostly image. Tika's AUTO rule uses fewer than 10 characters.
- OCR those pages with **OCRmyPDF `--mode skip`** (MPL-2.0) using **Tesseract 5** (Apache-2.0).
- Record OCR use per page, since it lowers confidence in the result.
- PaddleOCR and Docling OCR engines are later options.

**Chunking and long documents:**
- Chunks respect page and section boundaries, and each carries `chunk_id`, `page_start`, `page_end`, `page_label`, `section_path` and `text_hash`.
- Documents longer than the context window use **map-reduce / hierarchical summarization**:
  - Map: extract items with verbatim quotes and chunk ids, under a schema.
  - Reduce: merge and deduplicate into the final schema.
- "Lost in the Middle" (Liu et al., TACL 2024, **M**) argues against stuffing one very long prompt.

**Inference (Ollama):**
- **Structured outputs:** `format` accepts a **JSON Schema** on `/api/chat` and `/api/generate`, available since **v0.5.0**. Ollama enforces it through a llama.cpp GBNF grammar.
- **Recommended settings:**
  - Also describe the schema in the prompt.
  - Temperature 0 and a fixed `seed`.
  - Set `num_ctx` explicitly. The default depends on VRAM (4k, 32k or 256k per the source; the FAQ says 4096).
  - `truncate:false`, so an oversized input fails instead of being silently cut.
- **llama.cpp schema limits:** unsupported JSON-Schema features are **silently skipped**, nested `$ref`s are broken, and `minimum`/`maximum` work only on integers. **Keep schemas flat**, with `maxItems`, enums, and nullable or "not_found" fields.
- **Concurrency:** `OLLAMA_NUM_PARALLEL` defaults to 1 and multiplies KV-cache memory. `OLLAMA_MAX_QUEUE` defaults to 512 and returns 503 when full. `keep_alive` defaults to 5m.
- **Hardening:** bind to 127.0.0.1 (the default). Set `OLLAMA_NO_CLOUD=1`. Keep `OLLAMA_DEBUG_LOG_REQUESTS` off, because it writes request bodies to disk. Pin at least the patched version; the current release is v0.34.4.

**Model choice:**
- Benchmark 2–3 models on a golden set of real customer documents before choosing. Candidates:
  - **gpt-oss-20b** (Apache-2.0, 128k context, runs in about 16 GB);
  - a **Qwen3** model (Apache-2.0; check the Qwen3.5+ weight licences);
  - **IBM Granite 4.0** (Apache-2.0) as a small fallback.
- Llama and Gemma use custom licences and need legal review.
- Model-card context lengths and licences for several models could not be verified. Sources: https://github.com/openai/gpt-oss ; https://github.com/QwenLM/Qwen3 ; https://github.com/ibm-granite/granite-4.0-language-models.

**Validation and grounding:**
1. **Pydantic** `model_validate_json` validates the output. On failure, re-prompt with the error at most 2 times, then fail cleanly.
2. **Citation verification (deterministic):**
   - the cited `chunk_id` was actually supplied to the model;
   - the page falls inside that chunk's page range;
   - the quote appears in the chunk, after normalizing whitespace, hyphenation and ligatures, with a fuzzy threshold.
3. Items that fail are dropped or flagged `verified:false`. This follows OWASP LLM01's mitigation: "use deterministic code to validate adherence".
4. **Extract before summarizing:** pull verbatim requirements and specifications first, then summarize from them.

**Evaluation:**
- Build a small labelled evaluation set during the MVP: faithfulness, citation precision, and recall of requirements.
- **RAGAS** (Apache-2.0) and **ALCE**-style citation checks are options for later automation.

**Later capabilities on the same pipeline:**
- *Ask AI* (per-document RAG):
  - Embeddings through Ollama `/api/embed` (`qwen3-embedding` or `bge-m3`, both with a long context).
  - A per-document index in **pgvector** or **Qdrant**.
  - Hybrid BM25 + vector search with RRF, and optionally a reranker such as `bge-reranker-v2-m3` run outside Ollama (Ollama has no rerank API).
- *Revision comparison:*
  - Extract both iterations.
  - Align sections by requirement id or heading, falling back to embeddings.
  - Diff deterministically (`difflib` with `autojunk=False`; diff-match-patch is archived).
  - The LLM **only classifies and summarizes the hunks**, with page citations to both revisions.

### 9.7 Extensibility

| Future capability | What changes | What stays the same |
|---|---|---|
| Executive summary, key points, requirements, specifications, risks, actions | New gateway task templates and schema sections; new tabs in the result page | Bridge, access checks, content retrieval |
| Ask AI (Q&A) | Chat UI; per-document embedding index; task `qa` | Access rule 1 applies per question; scope limited to authorized documents |
| Revision comparison / change summary | The bridge resolves **two** iterations and checks both for DOWNLOAD; task `compare` | Everything else |
| Other object types (WTPart attachments, change objects, EPMDocument derived PDFs) | Action registration for other objecttypes; content selection rules | `ContentHolder` / `ContentHelper` APIs are shared across types (M+) |
| Pre-computation on check-in | A `POST_CHECKIN` listener or queue entry that warms the cache (S3 read, still gated per user at display) | Display-time authorization |
| Info-page tab or Next Gen UI | UI surface | Gateway API and schema |
| External SPA / Windchill+ | P2 connector (WRS + OAuth) | Gateway, AI engine, schemas |

### 9.8 Assessment of the current proof of concept (from the written description only; no screenshots received)

**Worth keeping:**
- The entry point is right: an object action on `WTDocument` is the most natural place for this in Windchill.
- The LLM is local (Ollama), which keeps engineering IP on-prem. This is the key difference from PTC's Azure-based AI Assistant.
- The chain works end to end: action → content → text → LLM → display.

**To redesign:**
- **Free-form text → a versioned JSON schema** with page citations and provenance.
- **Add grounding:** citations checked by deterministic code; unverified content flagged.
- **Handle long documents:** chunking and map-reduce instead of a single prompt, which might be silently truncated because of Ollama's `truncate` default and VRAM-dependent `num_ctx`.
- **Make it asynchronous:** a job model with polling, with no request thread blocked on the LLM.
- **Cache per iteration and checksum**, with authorization on every hit.
- **Output handling:** render as escaped text, never as HTML.

**Move out of Windchill** if it currently runs there: text extraction, OCR, prompt construction, LLM calls, caching and model configuration. They all go to the AI Gateway zone.

**Keep inside Windchill:** the action, the visibility filter, the authorization decision, content selection and streaming (for P1), and the result page shell.

**Security questions to answer for the current PoC.** We cannot see it, so these are questions, not findings:
1. How does it obtain the content? A supported API, WRS, or **vault or file-system access**? The last is unsupported and bypasses permissions.
2. Under which identity? The user's session, a hard-coded or admin account, or `setAccessEnforced(false)`?
3. Does it check **Download**, not just Read?
4. Is Ollama reachable directly from browsers or the network, without authentication?
5. Is model output inserted into the page as HTML?
6. Are document text or summaries written to logs or temp files?
7. Are credentials or tokens present in URLs, JavaScript or config files?

**Scalability issues to expect:**
- Synchronous LLM calls tying up Method Server threads.
- A single Ollama instance with `NUM_PARALLEL=1`, so requests queue.
- Summaries recomputed on every click, with no cache.
- Large scanned PDFs driving OCR CPU load.

**Upgrade and maintenance issues to expect:**
- Overriding (instead of incrementally extending) OOTB action models.
- Unsupported APIs (e.g. `findLocalContentStream`, `ContentHttp` URLs).
- Third-party jars in `WEB-INF/lib`.
- JSP-embedded business logic.
- Dependence on the classic UI while the Next Gen UI arrives.

---

## 10. Risks and limitations

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | **Research confidence.** No PTC page read in full, and the Javadoc came from a mirror. | Some API or endpoint details could be wrong for our release | Phase 0 verification against local Javadoc, `$metadata`, `jcaDebug` and the Help Center for the exact release |
| R2 | **Overlap with PTC Windchill AI Assistant** | Duplicate investment, user confusion, support questions | Business decision Q1. Differentiate (local LLM, structured extraction, revision compare). Use a distinct action name. |
| R3 | **Permission leak through derived content** (summaries, cache, index) | Severe: IP exposure, export-control violations | Section 8.6 rules. Negative security tests are mandatory before any pilot. |
| R4 | `hasAccess` returning true unexpectedly (enforcement suspended, reported anomalies) | False permission grants | Assert enforcement is on. Negative tests with Read-without-Download users and labelled documents. Consider an additional check through the standard download path. |
| R5 | **Hallucinated engineering facts** | Wrong requirements or values acted upon | Verified citations. Unverified items flagged. A "review before use" notice. Extraction-first prompting. An evaluation set. |
| R6 | Prompt injection through document content | Manipulated output | No tools. Schema constraint. Quote verification. Hidden-text detection. Output escaping. |
| R7 | **Next Gen UI** (13.1.2+) may not host classic JCA custom actions the same way | UI rework on upgrade | Keep the UI thin and the logic in the gateway. Verify for our release (Q-VER-4). |
| R8 | Windchill+ guardrails (CCD, "Fit for SaaS" scanning, REST-only integrations) | P1 may be disallowed | Choose P2 for Windchill+ |
| R9 | Outbound HTTP from the Method Server (no official guidance found); firewall rules | Bridge cannot reach the gateway | Network design in Phase 0. Use JDK `HttpClient` with timeouts. Keep the gateway in the same data center. |
| R10 | Method Server resource pressure (large files, long calls) | Windchill slowdown for all users | Asynchronous jobs, size and page limits, streaming, strict timeouts, no heavy work in the Method Server |
| R11 | GPU capacity or latency for local LLMs | Slow UX; queueing | Benchmark. Cache. Asynchronous UX. Possibly pre-compute on check-in later (with display-time gating). |
| R12 | Licensing: PyMuPDF AGPL; model licences (Llama, Gemma custom; Qwen3.5+ weights unverified) | Legal exposure | Use permissive tools (pdfplumber, pypdf, Docling, Tesseract, OCRmyPDF). Legal review of the chosen model. |
| R13 | Ollama's security posture (no auth, unauthenticated model-management routes, past CVEs) | Model tampering, data disclosure | Localhost bind, allowlisting proxy, pinned patched version, `OLLAMA_NO_CLOUD=1` |
| R14 | Content in URL or external storage, or PDFs only as representations | Nothing to summarize, or the wrong file summarized | Explicit content-selection rules, with the chosen item shown in the result |
| R15 | Scanned or low-quality PDFs | Poor extraction, weak citations | OCR with per-page flags. Show extraction quality in the result. |
| R16 | Windchill's own critical vulnerabilities (CVE-2026-4681) | Platform risk outside our control | Confirm the customer's patch level. The add-on adds no unauthenticated endpoints. |

---

## 11. Version compatibility considerations

| Area | What varies by version | Evidence | Conf. |
|---|---|---|---|
| Release numbering | The format is `major.minor.maintenance.CPS` (e.g. 12.1.2.22). CPS (Critical Patch Sets) arrive about monthly; features and UI arrive in maintenance releases. Windchill+ gets CPS-level feature changes. | KB CS134275, https://www.ptc.com/en/support/article/CS134275 ; ReleaseId Javadoc | M |
| Support lifecycle | 12.0 standard support ended 30 Jun 2024 (extended to 30 Jun 2025). End dates for 12.1.2, 13.0.2 and 13.1.x are NOT VERIFIED; see the PTC Product Release Calendar (KB CS81144). | https://community.ptc.com/t5/Windchill/Windchill-12-0-support-end-date/td-p/982252 | M |
| Java | Windchill 12 was certified on Java 11 (KB CS363056). The Windchill 13.0.1 "Changing the JDK" page shows Corretto 17 paths. Java 21 for 13.1.x is NOT VERIFIED. **This determines our bridge's compile target.** | https://www.ptc.com/en/support/article/CS363056 ; https://support.ptc.com/help/windchill/r13.0.1.0/en/Windchill_Help_Center/WCUpdateExistingIntallConfig/WCUpdInstall_ChangingJDKs.html | M |
| Libraries | 12.1 and 13.0 removed XStream and the `javax.ws.rs` dependencies, breaking customizations | PTC Community thread | M |
| Deprecations | 13.1.2 publishes lists of deprecated APIs | https://support.ptc.com/help/windchill/r13.1.2.0/en/Windchill_Help_Center/deprecated_apis/methods_3.html | M |
| WRS | A separate module (WRS 1.x/2.x, mapped per KB CS318837) until 12.1.2.11; bundled afterwards. Domain versions (v1…v6+) come with deprecations; pin them. | Section 6.2 | M |
| UI | Classic JCA plus the **Next Gen UI** from 13.1.2. The 12.1.2 "Managing Custom Actions…" change. | Sections 5.1 and 5.9 | M |
| REST from Java | 13.1.2 adds `WRSCaller` for calling WRS from customizations | Section 5.6 | M |
| Authentication | Entra ID as CAS and IdP for 12.0.2.2 and later; OAuth delegated authorization; M2M client credentials | Section 6.3 | M |
| Windchill+ | CCD deployment, a 100 MB package limit, "Fit for SaaS" intake scanning, allowed and disallowed customization lists, **REST-only integrations**, no access-control bypass | https://support.ptc.com/help/windchill/plus/r13.1.2.0/en/Windchill_Help_Center/customization/AutomatedBuildDeploy_Plus_Azure_CCD_wncplus_CustConstraints.html ; https://support.ptc.com/help/windchill/plus/r12.1.2.0/en/Windchill_Help_Center/customization/AutomatedBuildDeploy_Security_Guardrails_wncplus.html | M |
| PTC AI plugins | AI plugins are supported on 12.1.2.22, 13.0.2.10 and 13.1.3.0, and on SaaS | Section 1.2 | M |

**Rule for this project:** every implementation decision is recorded against the exact release and CPS, and re-validated on each Windchill upgrade. Our own supported-API usage list (section 7.1) becomes the upgrade checklist.

---

## 12. Open questions: information we need from you

### Strategy
- **Q1.** Are you aware of PTC's **Windchill AI Assistant** (April 2026)? Is it licensed or being evaluated? Should our capability complement it, compete with it, or be reconsidered?
- **Q2.** Is fully local inference (Ollama, no cloud) a hard requirement (data residency, export control), or a preference?

### Version and deployment
- **Q-VER-1.** The exact Windchill release and CPS (output of `windchill version`, or the REST function `PTC/GetWindchillVersion()`).
- **Q-VER-2.** Deployment: on-prem (own data center or IaaS), PTC-managed cloud, or **Windchill+ SaaS**?
- **Q-VER-3.** Installed modules: PDMLink, ProjectLink, MPMLink? Is **WVS publishing** of Office documents to PDF configured?
- **Q-VER-4.** Do users work in the classic UI, the Next Gen UI, or both? Which browsers?
- **Q-VER-5.** Database (Oracle or SQL Server) and whether content is vaulted or stored as BLOBs. This matters for performance, not for correctness.

### Authentication and security
- **Q-SEC-1.** Authentication setup: web-server/LDAP, AD, SAML SSO, PingFederate, Entra ID? Is **OAuth for WRS** configured?
- **Q-SEC-2.** Are **security labels**, export control (ITAR/EAR) or **agreements** in use? May such documents be AI-processed at all?
- **Q-SEC-3.** Data classification rules for AI processing, and retention requirements for derived data (summaries, extracted text).
- **Q-SEC-4.** Audit requirements: must AI accesses appear in Windchill audit reports?
- **Q-SEC-5.** Network zoning: can the Method Server make outbound HTTPS calls to an internal AI host? Where would the GPU host sit?

### Windchill access for the team
- **Q-ENV-1.** Is there a **dev/test Windchill** we can use, with admin access to install customizations and restart the Method Server?
- **Q-ENV-2.** Is WRS reachable (`/Windchill/servlet/odata/`)? Can we open the **API catalog** and `$metadata`?
- **Q-ENV-3.** Existing customizations: the current `custom-actions.xml` and `custom-actionModels.xml`, `site.xconf` changes, `ext.*` code, and other integrations (e.g. ThingWorx Navigate). Your change-control and deployment process.
- **Q-ENV-4.** Test users: we need at least three.
  - a user with Read + Download;
  - a user with **Read but no Download**;
  - a user with no access (and, if labels are used, one without the clearance).

### Documents and AI
- **Q-DOC-1.** Typical documents: native PDF, scanned PDF, or Office? Page counts, file sizes, languages. Do some include drawings or tables?
- **Q-DOC-2.** Where are the PDFs: primary content, attachments, or representations? Which document subtypes are in scope?
- **Q-DOC-3.** Can you provide 10–20 **non-sensitive sample documents** for offline evaluation, with a few expert-written reference summaries?
- **Q-AI-1.** Ollama host hardware (GPU model, VRAM, RAM), Ollama version, and the currently used model.
- **Q-AI-2.** Model licensing constraints: an approved-model list, and whether legal review is needed.
- **Q-AI-3.** Expected concurrency and latency tolerance, i.e. how long users will wait for a summary.

### The existing proof of concept
- **Q-POC-1.** The **screenshots** and ideally the **source code** of the PoC.
- **Q-POC-2.** How the PoC obtains content and under which identity (the section 9.8 questions), and where each part runs.

---

## 13. Recommended proof-of-concept plan

Each phase has an exit criterion. No production code is written until Phase 0 is complete and you approve.

### Phase 0: Confirm the environment (no code)
- Collect the answers to section 12.
- On the target release, **verify the load-bearing facts at High confidence**:
  - the local Javadoc: `ContentHelper`, `ContentServerHelper.findContentStream`, `AccessControlHelper`, `AccessPermission.DOWNLOAD`, `ReferenceFactory`;
  - the Customization Guide chapters on actions, action models (the incremental syntax), filters and deployment;
  - `jcaDebug` on a WTDocument info page (the action model name);
  - `DocMgmt/$metadata` and the API catalog;
  - KB CS344061, CS372037, CS400695 and CS318837.
- **Exit:** a verified fact sheet for our release, and a decision between P1 and P2.

### Phase 1: Three read-only spikes, in parallel (throwaway code, dev environment only)
1. **Windchill content and permission spike.** Read-only; no customization installed. As each of the three test users:
   - fetch a known WTDocument's metadata, latest iteration and primary content through WRS (Basic/SSO, and OAuth if available);
   - download the content;
   - record exactly what Windchill returns for **Read-without-Download** and **no-access** users.

   This checks the most security-critical assumptions (section 6.6 and R4).
2. **Minimal action spike** (dev Windchill only): a "Hello" action on the WTDocument action model, added incrementally. It opens a popup showing the resolved OID, number, revision.iteration, content-item list, and the `hasAccess(READ)` / `hasAccess(DOWNLOAD)` results for the current user. It validates registration, placement, OID resolution and the access check without any AI.
3. **Offline AI spike** (no Windchill), on the sample documents:
   - page-aware extraction (pdfplumber or pypdf, and Docling);
   - OCR detection;
   - Ollama structured output with the section 9.5 schema;
   - citation verification;
   - a comparison of 2–3 models on quality, latency and memory.
- **Exit:** evidence for every NOT VERIFIED item on the critical path, a chosen extraction stack and model, and measured latency.

### Phase 2: MVP "AI Summarize" (production-quality code, after approval)
- **Windchill side:** the action, a validation filter (subtype, checked-in, file content, pilot group), the AI Bridge (sections 9.2 and 9.4) and the result popup.
- **Gateway side:** the job API, extraction, OCR, map-reduce summarization with schema and validation, citation verification, cache, audit and hardening (sections 8.6 and 8.7).
- **Tests:**
  - unit tests;
  - integration tests on the dev Windchill;
  - the **negative security test suite** (mandatory);
  - load tests at the expected concurrency.
- **Exit:** the security test suite passes, and quality metrics on the evaluation set meet the agreed thresholds.

### Phase 3: Pilot
- A limited user group and monitoring (latency, failures, user feedback on accuracy).
- Documentation for administrators: deployment, configuration and upgrade checklist.

### Later (each one is additive; see section 9.7)
Key points and executive summary, then requirements, specifications and risks, then Ask AI (per-document RAG), then revision comparison, then other object types, then an info-page tab or Next Gen UI, then the P2 external app if needed.

### Recommended next step
Two things, in this order:
1. **Answer the section 12 questions**, especially Q1, Q-VER-1/2, Q-SEC-1/2, Q-ENV-1/4 and Q-POC-1.
2. **Approve Phase 1.** The offline AI spike can start as soon as we have non-sensitive sample PDFs. The two Windchill spikes need a dev Windchill environment and the three test users.

---

## Appendix A: Main sources by topic

URLs are listed as they appeared in search results; locale variants such as `/es/`, `/it/` and `/fr/` were seen for some pages. **All PTC URLs should be opened and confirmed for the target release.**

- **PTC Help Center roots:**
  - https://support.ptc.com/help/windchill/r13.1.2.0/en/
  - https://support.ptc.com/help/windchill/r12.1.2.0/en/
  - Windchill+: https://support.ptc.com/help/windchill/plus/r13.1.2.0/en/Windchill_Help_Center.html
  - WRS: https://support.ptc.com/help/windchill_rest_services/r2.7/en/
  - AI plugins: https://support.ptc.com/help/windchill/ai_plugin/en/
- **Javadoc:**
  - Official, local: `<WT_HOME>/codebase/wt/clients/library/api/index.html` (KB CS17101, https://www.ptc.com/en/support/article/CS17101).
  - Mirror used for this research: https://github.com/srinivasmd/Windchill_13_1_2_JavaDocs.github.io (unofficial).
- **Customization rules:**
  - https://www.ptc.com/en/support/customer-support-guide/guidelines_legal-windchill-solutions/supported-and-nonsupported-usage-of-the-api
  - https://www.ptc.com/en/support/customer-support-guide/guidelines_legal-windchill-solutions/requirements-for-windchill-customization-support
- **Security:** the pages cited in section 8. OWASP Top 10 for LLM Applications 2025: https://github.com/OWASP/www-project-top-10-for-large-language-model-applications/tree/main/2_0_vulns
- **Ollama:**
  - https://github.com/ollama/ollama (docs/api.md, docs/capabilities/structured-outputs.mdx, docs/context-length.mdx, docs/faq.mdx, envconfig/config.go, llm/llama_server.go)
  - https://github.com/ollama/ollama/releases/tag/v0.5.0
  - https://github.com/advisories/GHSA-f6mr-38g8-39rg
- **llama.cpp grammar limits:** https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md
- **Extraction and OCR:**
  - https://github.com/jsvine/pdfplumber
  - https://github.com/py-pdf/pypdf
  - https://github.com/docling-project/docling
  - https://github.com/apache/tika
  - https://github.com/apache/pdfbox
  - https://github.com/pymupdf/PyMuPDF (AGPL)
  - https://github.com/ocrmypdf/OCRmyPDF
  - https://github.com/tesseract-ocr/tesseract
  - https://github.com/PaddlePaddle/PaddleOCR
- **Retrieval (later phases):**
  - https://github.com/pgvector/pgvector
  - https://github.com/qdrant/qdrant
  - https://github.com/FlagOpen/FlagEmbedding
  - https://github.com/QwenLM/Qwen3-Embedding
- **Validation and evaluation:**
  - https://github.com/instructor-ai/instructor
  - https://github.com/explodinggradients/ragas
  - https://github.com/princeton-nlp/ALCE
- **Diffing:**
  - https://github.com/python/cpython/blob/main/Doc/library/difflib.rst
  - https://github.com/google/diff-match-patch (archived)
