"""Generate the synthetic SOP sample PDFs served by the mock Windchill provider.

DEVELOPMENT ONLY. The documents describe a fictitious company ("Northwind
Industrial"); all content, names and people are invented. Document metadata (number,
name, revision, iteration, state) is read from ``samples/catalog.json`` so that the
PDFs always match the mock catalog.

Usage (from the repository root):

    uv run --project apps/api python scripts/generate_samples.py   # -> samples/
    uv run --project apps/api python scripts/generate_samples.py --out DIR

Output is deterministic: rerunning the script with the same library versions produces
byte-identical PDFs (fixed metadata, ReportLab ``invariant`` mode, no random data).

SOP-00056 page 3 is an image-only page (text rendered into a PNG, no text layer) that
simulates a scanned page; the extractor must flag it as needing OCR. SOP-00123
deliberately contains gaps that an AI reviewer should flag: a vague filter instruction
that conflicts with the 500-hour replacement interval, a work instruction (WI-2210)
that is referenced but missing from the References section, and a spindle runout check
without a tolerance.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "samples" / "catalog.json"
DEFAULT_OUT_DIR = REPO_ROOT / "samples"

COMPANY = "Northwind Industrial"
SYNTHETIC_NOTICE = (
    "Synthetic sample \u2013 development only. Fictitious company, people and content."
)
CONTROLLED_NOTICE = (
    "Controlled document. Printed copies are uncontrolled \u2013 verify the current "
    "revision before use."
)
DRAFT_BANNER = "DRAFT \u2013 IN WORK \u2013 NOT APPROVED FOR PRODUCTION USE"

SECTION_TITLES = (
    "Purpose",
    "Scope",
    "References",
    "Responsibilities",
    "Safety / PPE",
    "Tools & Materials",
    "Procedure",
    "Inspection & Acceptance Criteria",
    "Records",
    "Revision History",
)

# --- Content model --------------------------------------------------------------------


@dataclass(frozen=True)
class Para:
    text: str


@dataclass(frozen=True)
class SubHeading:
    text: str


@dataclass(frozen=True)
class Steps:
    """Numbered steps ``{prefix}.{n}`` starting at ``start``."""

    prefix: str
    items: tuple[str, ...]
    start: int = 1


@dataclass(frozen=True)
class Bullets:
    items: tuple[str, ...]


@dataclass(frozen=True)
class Roles:
    """Bold term followed by its description (responsibilities, definitions)."""

    items: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Notice:
    kind: str  # "WARNING" | "CAUTION" | "NOTE"
    text: str


@dataclass(frozen=True)
class DataTable:
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    widths: tuple[float, ...]  # fractions of the frame width
    caption: str | None = None


@dataclass(frozen=True)
class ScannedPage:
    """A full page rendered as an image without a text layer (simulated scan)."""

    blocks: tuple[Para | SubHeading | Steps, ...]


Block = Para | SubHeading | Steps | Bullets | Roles | Notice | DataTable | ScannedPage


@dataclass(frozen=True)
class Section:
    title: str
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class SopContent:
    number: str
    subtitle: str
    effective_date: str
    owner: str
    approver: str
    applies_to: str
    sections: tuple[Section, ...]
    draft: bool = False
    # Physical page number the ScannedPage must land on (verified after the build).
    scanned_page: int | None = None


@dataclass(frozen=True)
class SopMetadata:
    """The subset of catalog metadata printed in the PDF."""

    number: str
    name: str
    revision: str
    iteration: str
    state: str

    @property
    def version(self) -> str:
        return f"{self.revision}.{self.iteration}"


def section(title: str, *blocks: Block) -> Section:
    return Section(title, blocks)


def steps(prefix: str, *items: str, start: int = 1) -> Steps:
    return Steps(prefix, items, start)


def bullets(*items: str) -> Bullets:
    return Bullets(items)


def roles(*items: tuple[str, str]) -> Roles:
    return Roles(items)


def scanned_page(*blocks: Para | SubHeading | Steps) -> ScannedPage:
    return ScannedPage(blocks)


def revision_history(*rows: tuple[str, str, str, str]) -> DataTable:
    return DataTable(
        header=("Rev.", "Date", "Author", "Description of change"),
        rows=rows,
        widths=(0.08, 0.13, 0.13, 0.66),
    )


def references(*rows: tuple[str, str]) -> DataTable:
    return DataTable(header=("Document", "Title"), rows=rows, widths=(0.2, 0.8))


def specification_table(*rows: tuple[str, str]) -> DataTable:
    return DataTable(header=("Item", "Specification"), rows=rows, widths=(0.3, 0.7))


# --- SOP content ----------------------------------------------------------------------

SOP_00123 = SopContent(
    number="SOP-00123",
    subtitle="Monthly Preventive Maintenance of CNC Vertical Machining Centers",
    effective_date="2026-03-21",
    owner="J. Alvarez, Maintenance Engineering",
    approver="K. Lindqvist, Maintenance Manager (2026-03-14)",
    applies_to=("Greenfield Plant \u2013 Machining Cells 1\u20133, machines VMC-01 to VMC-06"),
    sections=(
        section(
            "Purpose",
            Para(
                "This procedure defines the monthly preventive maintenance (PM) of CNC "
                "vertical machining centers (VMCs). Its objectives are to keep the "
                "machines within their specified operating conditions, to detect wear "
                "before it causes scrap or unplanned downtime, and to ensure that "
                "maintenance work is performed safely and recorded consistently."
            ),
        ),
        section(
            "Scope",
            steps(
                "2",
                "This SOP applies to all VMC-850 series vertical machining centers in "
                "Machining Cells 1\u20133 at the Greenfield Plant (asset numbers "
                "VMC-01 to VMC-06).",
                "It covers the monthly PM tasks listed in Table 1 and the "
                "interval-based tasks that fall due during a monthly PM, such as the "
                "replacement of the hydraulic return filter.",
                "Daily operator checks are covered by WI-2205 Daily Machine Checks "
                "\u2013 VMC. Annual geometric verification (laser calibration and "
                "ballbar testing) is performed by an external calibration provider and "
                "is outside the scope of this SOP.",
                "Corrective maintenance (breakdown repair) is outside the scope of "
                "this SOP and is performed under corrective work orders in the "
                "computerized maintenance management system (CMMS).",
            ),
        ),
        section(
            "References",
            references(
                ("SOP-00087", "Lockout/Tagout (LOTO) Procedure"),
                ("SOP-00056", "Coolant Concentration Control"),
                ("WI-2205", "Daily Machine Checks \u2013 VMC"),
                ("F-123-01", "Monthly PM Checklist \u2013 VMC (form)"),
                (
                    "MM-VMC850",
                    (
                        "OEM Operation and Maintenance Manual, VMC-850 series, Chapter "
                        "6 Periodic Maintenance"
                    ),
                ),
                ("EHS-014", "Personal Protective Equipment Standard"),
                (
                    "ISO 3448",
                    "Industrial liquid lubricants \u2013 ISO viscosity classification",
                ),
            ),
        ),
        section(
            "Responsibilities",
            roles(
                (
                    "Maintenance Technician",
                    (
                        "Performs the PM tasks in this SOP as an authorized employee "
                        "under SOP-00087, records all readings on F-123-01 and in the "
                        "CMMS, and reports any out-of-tolerance condition to the "
                        "Maintenance Supervisor before the machine is released."
                    ),
                ),
                (
                    "Maintenance Supervisor",
                    (
                        "Schedules PM work orders, ensures that technicians are "
                        "trained on this SOP, reviews and signs completed checklists "
                        "and approves the return to production when a nonconformity "
                        "was found."
                    ),
                ),
                (
                    "Machine Operator (affected employee)",
                    (
                        "Completes the current cycle, removes the workpiece when "
                        "instructed and does not attempt to operate the machine while "
                        "it is locked out."
                    ),
                ),
                (
                    "Cell Lead",
                    (
                        "Releases the machine for maintenance according to the PM "
                        "schedule and confirms that the machine is ready for "
                        "production after PM."
                    ),
                ),
                (
                    "Maintenance Engineering (document owner)",
                    (
                        "Maintains this SOP, reviews PM results quarterly for trends "
                        "and adjusts task intervals where the data supports it."
                    ),
                ),
            ),
        ),
        section(
            "Safety / PPE",
            Notice(
                "WARNING",
                "Hazardous energy. The VMC contains electrical energy (400 V AC), "
                "hydraulic energy (up to 65 bar, with a charged accumulator), "
                "pneumatic energy (6 bar) and stored mechanical energy (drawbar spring "
                'pack, Z-axis counterbalance). Tasks marked "Yes" in the LOTO column '
                "of Table 1 shall only be performed after the machine has been "
                "isolated in accordance with SOP-00087.",
            ),
            steps(
                "5",
                "The machine shall be locked out and tagged out in accordance with "
                "SOP-00087 before any guard is removed or any work is performed inside "
                "the machine enclosure or the electrical cabinet.",
                "Hydraulic pressure shall be relieved and the accumulator bled down to "
                "0 bar, as confirmed on gauge PG-1, before any hydraulic line, fitting "
                "or filter housing is opened.",
                "Safety glasses with side shields and safety shoes (S3) are required "
                "for all tasks in this SOP. Cut-resistant gloves (EN 388 level C or "
                "higher) must be worn when handling tools, chips and filter elements; "
                "nitrile gloves must be worn when handling hydraulic oil, way oil or "
                "coolant.",
                "Hearing protection must be worn in areas posted as hearing protection "
                "zones (above 85 dB(A)).",
                "Compressed air shall not be used to blow chips out of the machine or "
                "to clean clothing or skin.",
                "Oil and coolant spills must be cleaned up immediately with absorbent "
                "pads and disposed of as oily waste.",
                "Work inside the machine enclosure should be performed by one person "
                "at a time; a second person may assist from outside the enclosure.",
                "Only electrically qualified persons may open the electrical cabinet.",
            ),
        ),
        section(
            "Tools & Materials",
            specification_table(
                (
                    "Hydraulic oil",
                    "ISO VG 46 anti-wear hydraulic oil (HLP 46), stock no. LUB-046",
                ),
                ("Way lubricant", "ISO VG 68 slideway oil, stock no. LUB-068"),
                (
                    "Hydraulic return filter element",
                    "10 \u00b5m nominal, OEM part no. HF-850-10",
                ),
                ("Torque wrench", "20\u2013100 N\u00b7m, within calibration date"),
                (
                    "Drawbar force gauge",
                    "0\u201330 kN with BT40 adapter, within calibration date",
                ),
                ("Belt tension meter", "Frequency (sonic) type, 10\u2013600 Hz"),
                ("Dial test indicator", "0.001 mm resolution, with magnetic base"),
                ("Test mandrel", "BT40, 300 mm, ground"),
                (
                    "Refractometer",
                    "Handheld, 0\u201318 % Brix, used as described in SOP-00056",
                ),
                (
                    "Consumables",
                    "Lint-free cloths, absorbent pads, oily-waste container",
                ),
                (
                    "Lockout devices",
                    "Personal lock, tag and hasp in accordance with SOP-00087",
                ),
            ),
        ),
        section(
            "Procedure",
            Para(
                "Table 1 lists the tasks performed during the monthly PM. Record every "
                "reading on F-123-01 at the time it is taken; do not record values "
                "from memory."
            ),
            DataTable(
                caption="Table 1 \u2013 Monthly PM tasks and intervals",
                header=("No.", "Task", "Interval", "LOTO", "Step"),
                rows=(
                    (
                        "1",
                        "Hydraulic pressure and oil temperature",
                        "Monthly",
                        "No",
                        "7.2.1, 7.2.2",
                    ),
                    ("2", "Hydraulic oil level", "Monthly", "No", "7.2.3"),
                    (
                        "3",
                        "Way-lube tank level and lube cycle",
                        "Monthly",
                        "No",
                        "7.2.4",
                    ),
                    (
                        "4",
                        "Coolant concentration",
                        "Monthly (weekly per SOP-00056)",
                        "No",
                        "7.2.5",
                    ),
                    ("5", "Spindle drawbar force", "Monthly", "No", "7.2.6"),
                    ("6", "Spindle runout", "Monthly", "No", "7.2.7"),
                    (
                        "7",
                        "Pneumatic supply and water separator",
                        "Monthly",
                        "No",
                        "7.2.8",
                    ),
                    (
                        "8",
                        "Hydraulic return filter replacement",
                        "Every 500 operating hours",
                        "Yes",
                        "7.4.2",
                    ),
                    ("9", "Spindle drive belt tension", "Quarterly", "Yes", "7.4.3"),
                    ("10", "Way covers and wipers", "Monthly", "Yes", "7.4.4"),
                    ("11", "Coolant tank screens", "Monthly", "Yes", "7.4.5"),
                    ("12", "Guards and guard fasteners", "Monthly", "Yes", "7.4.7"),
                    (
                        "13",
                        "Hydraulic oil change",
                        "4,000 operating hours or 12 months",
                        "Yes",
                        "MM-VMC850",
                    ),
                ),
                widths=(0.06, 0.37, 0.35, 0.07, 0.15),
            ),
            SubHeading("7.1 Preparation"),
            steps(
                "7.1",
                "Obtain the PM work order from the CMMS and a blank Monthly PM "
                "Checklist F-123-01. Enter the asset number, the date and the work "
                "order number.",
                "Agree the maintenance start time with the Cell Lead. The operator "
                "shall complete the current cycle, remove the workpiece and return the "
                "machine to its home position.",
                "Record the spindle run hours and the hydraulic pump operating hours "
                "from the maintenance screen of the CNC control on F-123-01.",
                "Confirm that the torque wrench and the drawbar force gauge carry a "
                "valid calibration label. Instruments with an expired calibration must "
                "not be used.",
            ),
            SubHeading("7.2 Running checks (before isolation)"),
            Notice(
                "NOTE",
                "The checks in 7.2 are performed with the machine powered and the "
                "hydraulic unit running. Keep the doors closed, except where a step "
                "requires access to the spindle in setup mode.",
            ),
            steps(
                "7.2",
                "Hydraulic pressure: With the hydraulic unit running for at least 30 "
                "minutes, read the system pressure on gauge PG-1 at the hydraulic "
                "power unit. The pressure shall be 55\u201365 bar. If the pressure is "
                "outside this range, adjust the pressure-reducing valve in accordance "
                "with MM-VMC850, section 6.4. If the pressure cannot be brought within "
                "range, the machine shall not be returned to production and a "
                "corrective work order shall be raised.",
                "Hydraulic oil temperature: Read the oil temperature on the tank "
                "thermometer. The temperature shall be 40\u201360 \u00b0C. A "
                "temperature above 60 \u00b0C indicates a fault in the oil cooler or "
                "its fan and must be reported to the Maintenance Supervisor.",
                "Hydraulic oil level: The oil level shall be between the MIN and MAX "
                "marks of the sight glass. Top up only with ISO VG 46 hydraulic oil "
                "(LUB-046). Oils of different grades or brands must not be mixed.",
                "Way lubrication: Check the way-lube tank level. The level shall be "
                "above the 1/3 mark (at least 1.0 L in the 3.0 L tank). Top up with "
                "ISO VG 68 slideway oil (LUB-068). Trigger a manual lubrication cycle "
                "from the control and verify that oil reaches the X, Y and Z axis "
                "distribution blocks.",
                "Coolant concentration: Take a coolant sample and measure the "
                "concentration with the refractometer in accordance with SOP-00056. "
                "The concentration shall be 6\u20138 %. If it is outside this range, "
                "correct it as described in SOP-00056 and record the corrected value.",
                "Spindle drawbar force: Select setup mode, open the door and clamp the "
                "drawbar force gauge in the spindle using the tool release button. "
                "Take three readings and record the lowest. The clamping force shall "
                "be at least 12 kN (nominal 14 kN). If any reading is below 12 kN, the "
                'spindle shall be tagged "Do Not Operate" and the Maintenance '
                "Supervisor informed; the drawbar spring pack must be replaced before "
                "the machine is used.",
                "Spindle runout: Clamp the test mandrel in the spindle and press the "
                "emergency stop. With the dial test indicator on the machine table, "
                "verify the spindle runout at the spindle nose and at 300 mm from the "
                "spindle nose while rotating the spindle slowly by hand. Record both "
                "readings on F-123-01.",
                "Pneumatic supply: The air pressure at the machine regulator shall be "
                "5.5\u20136.5 bar. Drain the water separator and check that the filter "
                "bowl is free of oil and water.",
            ),
            SubHeading("7.3 Isolation"),
            steps(
                "7.3",
                "Move the axes to the maintenance position (Z axis fully up, table "
                "centered), stop the spindle and switch off the hydraulic unit.",
                "Isolate and lock out all energy sources in accordance with SOP-00087 "
                "and the energy control procedure posted on the machine (main "
                "disconnect Q1, pneumatic supply valve V-1).",
                "Open the accumulator bleed valve and verify that gauge PG-1 reads 0 bar.",
                "Verify zero energy by attempting to start the machine from the "
                "control panel (try-out) as required by SOP-00087. Return all controls "
                "to the off position.",
            ),
            SubHeading("7.4 Maintenance with the machine isolated"),
            steps(
                "7.4",
                "Remove the rear access guard and the hydraulic unit cover. Place the "
                "fasteners in a parts tray.",
                "Hydraulic return filter: The hydraulic return filter element shall be "
                "replaced every 500 operating hours of the hydraulic pump, or earlier "
                "if the clogging indicator shows red. Compare the pump hours recorded "
                "in 7.1.3 with the last replacement recorded in the CMMS. Lubricate "
                "the seal of the new element with clean hydraulic oil and record the "
                "pump hours at replacement.",
                "Spindle drive belt (quarterly): Measure the belt tension at mid-span "
                "with the belt tension meter. The belt frequency shall be 88\u201396 "
                "Hz. If adjustment is required, tension the belt in accordance with "
                "WI-2210 Spindle Belt Tensioning and repeat the measurement.",
                "Way covers and wipers: Inspect the telescopic way covers and the "
                "wipers of all axes for damage, chips and coolant ingress. Replace "
                "damaged wipers; report damaged way covers to the Maintenance "
                "Supervisor.",
                "Coolant tank: Remove chips from the coolant tank screens and the chip "
                "conveyor tray. Check the coolant level and top up with premix in "
                "accordance with SOP-00056.",
                "Filters: Inspect filters regularly, including the coolant, hydraulic "
                "and electrical cabinet air filters, and replace them when they are "
                "dirty.",
                "Guards: Refit all guards and covers. Tighten the M10 guard fasteners "
                "to 45 N\u00b7m with the calibrated torque wrench. Inspect the "
                "polycarbonate viewing window of the door for cracks, crazing or "
                "clouding; a damaged window shall be replaced before the machine is "
                "released.",
                "Electrical cabinet (electrically qualified persons only): Check the "
                "door seals for damage and confirm that no coolant or chips have "
                "entered the cabinet.",
            ),
            SubHeading("7.5 Return to service"),
            steps(
                "7.5",
                "Remove all tools and materials from the machine. Account for every "
                "tool used before the doors are closed.",
                "Remove the locks and tags in accordance with SOP-00087 and inform the "
                "operator and the Cell Lead that the machine is being restarted.",
                "Start the hydraulic unit and run the spindle warm-up program O9000 "
                "(10 minutes). Verify that no alarms are active and that the "
                "electrical cabinet cooling unit is running.",
                "After 15 minutes of operation, verify again that the hydraulic "
                "pressure is 55\u201365 bar and that there are no leaks at the filter "
                "housing or at any fitting that was disturbed.",
                "Complete F-123-01, close the work order in the CMMS and hand the "
                "checklist to the Maintenance Supervisor for review.",
            ),
        ),
        section(
            "Inspection & Acceptance Criteria",
            steps(
                "8",
                "The machine may be returned to production only when all criteria in "
                "Table 2 are met, or when the Maintenance Supervisor has approved a "
                "documented deviation in the CMMS.",
            ),
            DataTable(
                caption="Table 2 \u2013 Acceptance criteria",
                header=("Parameter", "Acceptance criterion", "If not met"),
                rows=(
                    (
                        "Hydraulic system pressure",
                        "55\u201365 bar at PG-1",
                        "Adjust per MM-VMC850 6.4",
                    ),
                    (
                        "Hydraulic oil temperature",
                        "40\u201360 \u00b0C after 30 min",
                        "Report; check oil cooler",
                    ),
                    (
                        "Hydraulic oil level",
                        "Between MIN and MAX",
                        "Top up with ISO VG 46",
                    ),
                    (
                        "Way-lube tank level",
                        "Above 1/3 mark (min. 1.0 L)",
                        "Top up with ISO VG 68",
                    ),
                    ("Coolant concentration", "6\u20138 %", "Correct per SOP-00056"),
                    (
                        "Drawbar clamping force",
                        "Min. 12 kN (nominal 14 kN)",
                        "Tag out; replace spring pack",
                    ),
                    ("Spindle belt tension", "88\u201396 Hz", "Adjust per WI-2210"),
                    ("Pneumatic supply", "5.5\u20136.5 bar", "Adjust regulator"),
                    ("Guard fasteners", "45 N\u00b7m", "Re-torque"),
                    (
                        "Leaks after restart",
                        "None visible after 15 min",
                        "Repair before release",
                    ),
                ),
                widths=(0.33, 0.33, 0.34),
            ),
            steps(
                "8",
                "Every out-of-tolerance reading must be recorded as a nonconformity in "
                "the CMMS with the measured value, the corrective action taken and the "
                "value after correction.",
                "The Maintenance Supervisor shall review and sign the completed "
                "checklist within 2 working days.",
                start=2,
            ),
        ),
        section(
            "Records",
            steps(
                "9",
                "This SOP generates the following records: the completed Monthly PM "
                "Checklist F-123-01 signed by the technician and the Maintenance "
                "Supervisor, the PM work order in the CMMS including all readings, and "
                "the filter replacement entries with the pump operating hours.",
                "Records shall be retained for 3 years from the date of the PM. Paper "
                "checklists are scanned into the CMMS within 5 working days; the paper "
                "original may then be discarded.",
                "Nonconformity and deviation records are retained with the work order.",
            ),
        ),
        section(
            "Revision History",
            revision_history(
                ("A.1", "2025-10-06", "J. Alvarez", "Initial draft for review."),
                (
                    "A.2",
                    "2026-01-19",
                    "J. Alvarez",
                    "Review comments incorporated; drawbar force check added.",
                ),
                (
                    "A.3",
                    "2026-03-14",
                    "J. Alvarez",
                    (
                        "Hydraulic pressure range changed to 55\u201365 bar; filter "
                        "replacement interval set to 500 operating hours. Released."
                    ),
                ),
            ),
        ),
    ),
)

SOP_00087 = SopContent(
    number="SOP-00087",
    subtitle="Control of Hazardous Energy During Servicing and Maintenance",
    effective_date="2026-02-02",
    owner="M. Chen, Environment, Health & Safety",
    approver="A. Brennan, Plant Manager (2026-01-22)",
    applies_to="Greenfield Plant \u2013 all production and facility equipment",
    sections=(
        section(
            "Purpose",
            Para(
                "This procedure establishes the minimum requirements for the control "
                "of hazardous energy at Northwind Industrial. It ensures that machines "
                "and equipment are stopped, isolated from all energy sources and "
                "locked out before any employee performs servicing or maintenance "
                "where the unexpected energization, start-up or release of stored "
                "energy could cause injury."
            ),
        ),
        section(
            "Scope",
            steps(
                "2",
                "This procedure applies to all employees and contractors who service, "
                "maintain, clean, adjust, set up or repair machines and equipment at "
                "the Greenfield Plant, and to employees who work in areas where such "
                "work is performed.",
                "It applies to all forms of hazardous energy, including electrical, "
                "hydraulic, pneumatic, mechanical, thermal, chemical and gravitational "
                "energy.",
                "Normal production operations are excluded unless a guard or safety "
                "device must be removed or bypassed, or a person must place any part "
                "of the body in the point of operation or another danger zone.",
                "Work on cord-and-plug connected equipment is excluded when the plug "
                "is removed and remains under the exclusive control of the person "
                "performing the work.",
                "Definitions:",
            ),
            roles(
                (
                    "Authorized employee",
                    (
                        "A person trained and designated to lock out equipment in "
                        "order to perform servicing or maintenance on it."
                    ),
                ),
                (
                    "Affected employee",
                    (
                        "A person who operates or uses the equipment being locked out, "
                        "or who works in the area where the servicing is performed."
                    ),
                ),
                (
                    "Energy control procedure (ECP)",
                    (
                        "The equipment-specific, written sequence for isolating and "
                        "verifying all energy sources of a machine, posted at the "
                        "machine."
                    ),
                ),
                (
                    "Zero energy state",
                    (
                        "The condition in which all energy sources are isolated and "
                        "all stored or residual energy has been released or restrained."
                    ),
                ),
            ),
        ),
        section(
            "References",
            references(
                ("29 CFR 1910.147", "The control of hazardous energy (lockout/tagout)"),
                (
                    "ISO 14118",
                    "Safety of machinery \u2013 Prevention of unexpected start-up",
                ),
                ("EHS-002", "Contractor Safety Management"),
                ("EHS-014", "Personal Protective Equipment Standard"),
                ("F-087-01", "Energy Control Procedure (ECP) template"),
                ("F-087-02", "Group Lockout Log"),
                ("F-087-03", "Annual Periodic Inspection Record"),
                ("F-087-04", "Lock Removal in Absence of the Authorized Employee"),
            ),
        ),
        section(
            "Responsibilities",
            roles(
                (
                    "Authorized employee",
                    (
                        "Applies personal locks and tags, verifies zero energy before "
                        "starting work and removes only their own locks."
                    ),
                ),
                (
                    "Affected employee",
                    (
                        "Recognizes lockout devices, never attempts to remove or "
                        "bypass them and does not restart locked-out equipment."
                    ),
                ),
                (
                    "Supervisor",
                    (
                        "Ensures that servicing is performed under this procedure, "
                        "that ECPs are available at the machines and that only "
                        "trained, authorized employees perform lockout."
                    ),
                ),
                (
                    "Lockout coordinator",
                    (
                        "The single authorized employee with overall responsibility "
                        "for a group lockout, including the group lock box and the "
                        "Group Lockout Log F-087-02."
                    ),
                ),
                (
                    "EHS Manager (document owner)",
                    (
                        "Maintains this procedure, organizes training and the annual "
                        "periodic inspections, and audits compliance."
                    ),
                ),
            ),
            SubHeading("Training"),
            steps(
                "4",
                "Authorized employees shall complete LOTO training, including a "
                "practical assessment on representative equipment, before performing "
                "lockout for the first time, and refresher training every 3 years.",
                "Affected employees shall receive awareness training on the purpose "
                "and use of this procedure during induction.",
                "Retraining is required whenever job assignments, equipment or ECPs "
                "change in a way that introduces a new hazard, or when a periodic "
                "inspection or an observation shows deviations from this procedure.",
                "Contractors shall follow this procedure or an equivalent procedure "
                "approved by EHS in accordance with EHS-002.",
            ),
        ),
        section(
            "Safety / PPE",
            Notice(
                "WARNING",
                "Never rely on a machine's control circuit (emergency stop, stop "
                "button, interlock or PLC) for energy isolation. Only energy-isolating "
                "devices such as disconnect switches, circuit breakers and manual "
                "valves may be locked out.",
            ),
            steps(
                "5",
                "PPE shall be selected in accordance with the ECP and EHS-014. As a "
                "minimum, safety glasses and safety shoes shall be worn.",
                "The test for absence of voltage shall only be performed by "
                "electrically qualified persons wearing the arc-rated PPE stated on "
                "the equipment's arc-flash label.",
                "Each authorized employee must use their own personal lock and key; "
                "keys shall not be shared.",
                "Tags alone may not be used instead of locks unless the "
                "energy-isolating device cannot accept a lock and EHS has approved the "
                "tagout-only method in the ECP.",
            ),
        ),
        section(
            "Tools & Materials",
            specification_table(
                (
                    "Personal safety padlock",
                    ("Red, keyed different, one key per lock, marked with the owner's name"),
                ),
                (
                    "Danger tag",
                    ('"DANGER \u2013 DO NOT OPERATE", with name, department, date and phone'),
                ),
                ("Lockout hasp", "Steel, for up to 6 locks"),
                (
                    "Valve and breaker lockouts",
                    "Gate valve, ball valve and circuit breaker types",
                ),
                (
                    "Group lock box",
                    "Holds the keys of all isolation locks of a group lockout",
                ),
                (
                    "Voltage tester",
                    (
                        "Two-pole, CAT III 1000 V, proven on a known live source "
                        "before and after use"
                    ),
                ),
                (
                    "Blocking devices",
                    "Mechanical blocks and safety pins rated for the load",
                ),
            ),
        ),
        section(
            "Procedure",
            SubHeading("7.1 Preparation"),
            steps(
                "7.1",
                "Obtain the ECP for the equipment. If no ECP exists or the ECP does "
                "not match the equipment, stop and contact the Supervisor and EHS; "
                "work shall not begin until a valid ECP is available.",
                "Identify every energy source and its isolation point from the ECP, "
                "including stored energy such as hydraulic accumulators, springs, "
                "capacitors, compressed air receivers and raised loads.",
                "Notify all affected employees that the equipment will be shut down "
                "and locked out, and why.",
            ),
            SubHeading("7.2 Shutdown and isolation"),
            steps(
                "7.2",
                "Shut down the equipment using its normal stopping procedure.",
                "Operate every energy-isolating device listed in the ECP, for example "
                "the main disconnect and the pneumatic and hydraulic isolation valves.",
                "Apply a personal lock and a completed danger tag to each "
                "energy-isolating device. Where more than one person works on the "
                "equipment, use a hasp or a group lock box (see 7.5).",
            ),
            SubHeading("7.3 Stored energy"),
            steps(
                "7.3",
                "Hydraulic accumulators shall be bled down through the designated "
                "bleed valve until the gauge reads 0 bar. If the ECP lists no bleed "
                "valve, the accumulator shall be treated as charged and work shall not "
                "begin.",
                "Pneumatic systems shall be vented to atmosphere and the lockable dump "
                "valve locked in the open position.",
                "Suspended or raised parts, such as press rams, spindle heads and "
                "lifting tables, shall be lowered to a safe position or secured with "
                "mechanical blocks or safety pins rated for the load.",
                "Capacitors and variable frequency drives shall be allowed to "
                "discharge for at least the time stated on the drive label (minimum 5 "
                "minutes) before the absence of voltage is tested.",
                "If stored energy can re-accumulate, verification of isolation shall "
                "be continued until the work is completed.",
            ),
            SubHeading("7.4 Verification of zero energy"),
            steps(
                "7.4",
                "Confirm that all persons are clear of the equipment.",
                "Attempt to start the equipment with the normal operating controls "
                "(try-out). The equipment must not start or move.",
                "Test for absence of voltage at the load side of the isolation point "
                "using the live-dead-live method: test the voltage tester on a known "
                "live source, test all phases and each phase to earth, then test the "
                "voltage tester again on the known live source.",
                "Check that all pressure gauges read 0 bar and that no parts can move "
                "under gravity.",
                "Return all operating controls to the off or neutral position. Work "
                "may begin only after zero energy has been verified.",
            ),
            SubHeading("7.5 Group lockout"),
            steps(
                "7.5",
                "The lockout coordinator isolates the equipment, applies isolation "
                "locks to every energy-isolating device and verifies zero energy in "
                "accordance with 7.4.",
                "The keys of the isolation locks are placed in the group lock box. "
                "Each member of the group applies a personal lock to the box before "
                "starting work and removes it when their own work is complete.",
                "The lockout coordinator records all names on the Group Lockout Log "
                "F-087-02 and may remove the isolation locks only after all personal "
                "locks have been removed from the group lock box.",
                "At shift change, the oncoming authorized employees shall apply their "
                "personal locks before the off-going employees remove theirs, so that "
                "lockout protection is continuous.",
            ),
            SubHeading("7.6 Release from lockout"),
            steps(
                "7.6",
                "Check that tools and blocking devices have been removed and that all "
                "guards and safety devices are reinstalled and functional.",
                "Confirm that all persons are clear and notify the affected employees "
                "that the equipment will be re-energized.",
                "Each lock shall be removed only by the authorized employee who applied it.",
                "Remove the locks and tags, restore the energy sources in the order "
                "given in the ECP and perform a functional test of the equipment.",
            ),
            SubHeading("7.7 Removal of a lock in the absence of the authorized employee"),
            steps(
                "7.7",
                "If the authorized employee who applied a lock is not on site and "
                "cannot be reached, the lock may be removed only by the Maintenance "
                "Manager with an EHS representative present.",
                "The removal shall be documented on F-087-04; the employee must be "
                "informed before resuming work.",
            ),
        ),
        section(
            "Inspection & Acceptance Criteria",
            steps(
                "8",
                "Each ECP shall be inspected at least annually by an authorized "
                "employee other than the persons using the procedure being inspected "
                "(annual periodic inspection).",
                "The inspection shall include a review of the responsibilities of each "
                "authorized employee under the ECP and the observation of an actual or "
                "simulated lockout.",
                "The inspection is acceptable only when all of the following are met:",
            ),
            bullets(
                "All energy sources and isolation points in the ECP match the installed equipment.",
                "Every isolation point was locked with a personal lock and a completed tag.",
                "Stored energy was released and zero energy was verified before work began.",
                "The authorized employees could explain the ECP and their responsibilities.",
            ),
            steps(
                "8",
                "Deficiencies shall be corrected within 30 days and the persons "
                "involved retrained. The inspector certifies the inspection on "
                "F-087-03 with the equipment, the date, the employees included and the "
                "inspector's name.",
                start=4,
            ),
        ),
        section(
            "Records",
            steps(
                "9",
                "ECPs are posted at each machine and reviewed whenever the equipment is modified.",
                "Annual periodic inspection records (F-087-03), Group Lockout Logs "
                "(F-087-02) and lock removal records (F-087-04) shall be retained for "
                "3 years.",
                "Training records shall be retained for the duration of employment plus 3 years.",
            ),
        ),
        section(
            "Revision History",
            revision_history(
                ("A.1", "2022-05-10", "M. Chen", "Initial release."),
                (
                    "B.1",
                    "2025-06-30",
                    "M. Chen",
                    ("Revision started: group lockout and shift change requirements added."),
                ),
                (
                    "B.2",
                    "2026-01-22",
                    "M. Chen",
                    ("Accumulator bleed-down verification and form F-087-04 added. Released."),
                ),
            ),
        ),
    ),
)

SOP_00141 = SopContent(
    number="SOP-00141",
    subtitle="Die Change and Setup of 250 t Hydraulic Presses",
    effective_date="Not yet effective (draft)",
    owner="R. Okafor, Production Engineering",
    approver="Pending \u2013 in review",
    applies_to="Greenfield Plant \u2013 Press Shop, presses HP-250-01 and HP-250-02",
    draft=True,
    sections=(
        section(
            "Purpose",
            Para(
                "This procedure describes the setup and die changeover of the 250 t "
                "hydraulic presses in the Press Shop. It ensures that dies are "
                "installed safely, that tonnage and shut height are set correctly for "
                "each die and that the first part is approved before production starts."
            ),
            Notice(
                "NOTE",
                "This document is a draft for review. It must not be used for "
                "production until it has been released.",
            ),
        ),
        section(
            "Scope",
            steps(
                "2",
                "This procedure applies to the 250 t hydraulic presses HP-250-01 and "
                "HP-250-02 and to all dies in the die library that are released for "
                "these presses.",
                "Die maintenance and repair in the tool room are outside the scope of "
                "this procedure.",
            ),
        ),
        section(
            "References",
            references(
                ("SOP-00087", "Lockout/Tagout (LOTO) Procedure"),
                ("DSS", "Die Setup Sheet (one per die, identified by the die number)"),
                ("F-141-01", "Press Changeover Checklist"),
                ("F-141-02", "First-Article Inspection Report"),
                ("MM-HP250", "OEM Operating Manual, 250 t hydraulic press"),
                (
                    "ISO 16092-3",
                    ("Machine tools safety \u2013 Presses \u2013 Part 3: Hydraulic presses"),
                ),
            ),
        ),
        section(
            "Responsibilities",
            roles(
                (
                    "Press setter",
                    (
                        "Performs the changeover as an authorized employee under "
                        "SOP-00087, sets tonnage and shut height from the Die Setup "
                        "Sheet and performs the safety device checks."
                    ),
                ),
                (
                    "Press operator",
                    (
                        "Assists the setter as directed and starts production only "
                        "after release by the setter and Quality."
                    ),
                ),
                (
                    "Quality inspector",
                    ("Performs the first-article inspection and releases or rejects the setup."),
                ),
                (
                    "Production Supervisor",
                    ("Plans changeovers and ensures that only qualified setters perform them."),
                ),
            ),
        ),
        section(
            "Safety / PPE",
            Notice(
                "WARNING",
                "Crushing hazard. Never place any part of the body between the dies "
                "unless the press is locked out in accordance with SOP-00087 and "
                "safety blocks are installed between the ram and the bolster.",
            ),
            steps(
                "5",
                "Die changes shall be performed with the press locked out in "
                "accordance with SOP-00087, except for the steps that require power, "
                "which are performed in inch mode from the two-hand control station.",
                "Safety blocks shall be installed whenever work is performed between the dies.",
                "Dies shall be lifted only with the 2 t overhead crane and certified "
                "lifting equipment; nobody may stand under a suspended load.",
                "Safety glasses, safety shoes (S3), cut-resistant gloves for handling "
                "dies and blanks, and hearing protection must be worn in the Press "
                "Shop.",
                "The light curtain and the two-hand control shall never be bypassed.",
            ),
        ),
        section(
            "Tools & Materials",
            specification_table(
                ("Overhead crane", "2 t, with certified slings and die lifting eyes"),
                ("Die cart", "Rated 2 t, with locking casters"),
                ("Safety blocks", "Rated for the press, yellow, with interlock plug"),
                ("Torque wrench", "50\u2013350 N\u00b7m, within calibration date"),
                ("Light curtain test rod", "30 mm diameter (light curtain resolution)"),
                ("Shut height gauge", "Digital, 0.01 mm resolution"),
            ),
        ),
        section(
            "Procedure",
            SubHeading("7.1 Preparation"),
            steps(
                "7.1",
                "Confirm that the die number on the production order matches the die "
                "and the Die Setup Sheet (DSS).",
                'Check that the die carries a green "Ready for Use" tag from the tool room.',
                "Read the required tonnage, shut height and cushion pressure from the "
                "DSS and enter them on F-141-01.",
                "Target changeover time: TBD (to be agreed with Production).",
            ),
            SubHeading("7.2 Removal of the previous die"),
            steps(
                "7.2",
                "Lower the ram in inch mode until the upper die rests on the lower die.",
                "Release the upper die clamps and raise the ram to the top position.",
                "Lock out the press in accordance with SOP-00087 and install the safety blocks.",
                "Release the lower die clamps, move the die onto the die cart and "
                "return it to the die library.",
            ),
            SubHeading("7.3 Die installation"),
            steps(
                "7.3",
                "Clean the bolster and the ram face; remove slugs and debris.",
                "Place the new die on the bolster with the die cart and locate it with "
                "the locating keys.",
                "Clamp the lower die. Tighten the M16 clamp bolts to 210 N\u00b7m in a "
                "cross pattern.",
                "Remove the safety blocks and the locks in accordance with SOP-00087.",
            ),
            SubHeading("7.4 Shut height and tonnage"),
            steps(
                "7.4",
                "In inch mode, lower the ram onto the upper die, clamp the upper die "
                "to the ram and tighten the clamp bolts to 210 N\u00b7m.",
                "Set the shut height to the value on the DSS. The shut height must be "
                "within the press range of 450\u2013750 mm and within \u00b10.1 mm of "
                "the DSS value.",
                "Set the tonnage limit to the value on the DSS. The tonnage setting "
                "shall not exceed 80 % of the rated press capacity (200 t on a 250 t "
                "press) unless Production Engineering has approved a higher value in "
                "writing.",
                "Set the die cushion pressure to the value on the DSS.",
            ),
            SubHeading("7.5 Safety device checks"),
            steps(
                "7.5",
                "Two-hand control: Verify that the ram does not move when only one "
                "button is pressed, that it moves only when both buttons are pressed "
                "within 0.5 s of each other, and that releasing either button stops "
                "the ram.",
                "Light curtain: With the ram moving down in single-stroke mode, pass "
                "the 30 mm test rod through the protective field at the top, the "
                "middle and the bottom of the field. The ram must stop each time.",
                'If any safety device check fails, the press shall be tagged "Do Not '
                'Operate" and the Production Supervisor and Maintenance informed. '
                "Production must not start.",
                "[Review note: confirm the minimum safety distance of the light "
                "curtain with EHS before release.]",
            ),
            SubHeading("7.6 Trial strokes and first-article inspection"),
            steps(
                "7.6",
                "Make two trial strokes in single-stroke mode and check the parts "
                "visually for splits, wrinkles and burrs.",
                "Submit the first part produced at nominal settings to the Quality "
                "inspector together with F-141-01.",
                "The Quality inspector measures the part in accordance with the "
                "control plan and records the results on F-141-02. Production may "
                "start only after the first article has been approved.",
                "The approved first article shall be tagged and kept at the press "
                "until the end of the shift.",
            ),
        ),
        section(
            "Inspection & Acceptance Criteria",
            DataTable(
                header=("Check", "Acceptance criterion"),
                rows=(
                    ("Die identification", "Die, DSS and production order match"),
                    ("Tonnage setting", "Per DSS; max. 80 % of rated capacity (200 t)"),
                    ("Shut height", "DSS value \u00b10.1 mm; within 450\u2013750 mm"),
                    ("Clamp bolt torque", "210 N\u00b7m (M16)"),
                    ("Two-hand control", "Ram stops when either button is released"),
                    ("Light curtain", "Ram stops at all three test positions"),
                    (
                        "First article",
                        "Conforms to the control plan; approved on F-141-02",
                    ),
                ),
                widths=(0.35, 0.65),
            ),
        ),
        section(
            "Records",
            steps(
                "9",
                "The completed Press Changeover Checklist F-141-01 and the "
                "First-Article Inspection Report F-141-02 are filed with the "
                "production order.",
                "Records shall be retained for 5 years.",
            ),
        ),
        section(
            "Revision History",
            revision_history(("A.1", "2026-09-02", "R. Okafor", "Initial draft for review.")),
        ),
    ),
)

SOP_00056 = SopContent(
    number="SOP-00056",
    subtitle="Monitoring and Correction of Water-Miscible Metalworking Fluids",
    effective_date="2025-11-17",
    owner="S. Patel, Process Engineering",
    approver="K. Lindqvist, Maintenance Manager (2025-11-05)",
    applies_to=("Greenfield Plant \u2013 Machining Cells 1\u20133 and central coolant system CS-1"),
    scanned_page=3,
    sections=(
        section(
            "Purpose",
            Para(
                "This procedure defines how the concentration and condition of "
                "water-miscible metalworking fluid (coolant) are monitored and "
                "corrected. Coolant kept within its specified limits protects tools "
                "and parts from corrosion, maintains surface finish and tool life, and "
                "reduces health risks such as dermatitis and bacterial contamination."
            ),
        ),
        section(
            "Scope",
            steps(
                "2",
                "This procedure applies to all machines in Machining Cells 1\u20133 "
                "with individual coolant sumps and to the central coolant system CS-1.",
                "It covers the semi-synthetic coolant NC-400, the only coolant "
                "approved for these machines. Neat cutting oils and grinding fluids "
                "are outside the scope.",
            ),
        ),
        section(
            "References",
            references(
                ("SOP-00123", "Machine Maintenance SOP"),
                ("SDS NC-400", "Safety Data Sheet, semi-synthetic coolant NC-400"),
                ("TDS NC-400", "Technical Data Sheet, semi-synthetic coolant NC-400"),
                ("EHS-021", "Metalworking Fluid Health Program"),
                ("F-056-01", "Coolant Log"),
            ),
        ),
        section(
            "Responsibilities",
            roles(
                (
                    "Machine operator",
                    (
                        "Checks the coolant level and appearance at the start of each "
                        "shift and reports foam, odor or oil on the surface."
                    ),
                ),
                (
                    "Coolant technician",
                    (
                        "Performs the measurements in this SOP, corrects the coolant "
                        "and records all results on F-056-01."
                    ),
                ),
                (
                    "Maintenance Supervisor",
                    ("Reviews the Coolant Log weekly and arranges sump cleaning when required."),
                ),
                (
                    "EHS",
                    ("Runs the health program in EHS-021 and approves the use of biocides."),
                ),
            ),
        ),
        section(
            "Safety / PPE",
            Notice(
                "CAUTION",
                "Coolant concentrate and biocides irritate the skin and eyes. Read the "
                "SDS before handling. Avoid skin contact with coolant and wash your "
                "hands before eating, drinking or smoking.",
            ),
            steps(
                "5",
                "Nitrile gloves and safety glasses shall be worn when sampling, "
                "measuring or topping up coolant. A face shield must be worn when "
                "handling concentrate or biocide.",
                "Biocides may only be added by trained coolant technicians and only in "
                "the dose approved by EHS.",
                "Coolant spills must be cleaned up immediately; wet floors are a slip hazard.",
            ),
        ),
        section(
            "Tools & Materials",
            specification_table(
                (
                    "Refractometer",
                    "Handheld, 0\u201318 % Brix, automatic temperature compensation",
                ),
                ("Distilled water", "For zeroing the refractometer"),
                (
                    "pH meter",
                    ("Resolution 0.1 pH, calibrated weekly with pH 7.0 and pH 10.0 buffers"),
                ),
                (
                    "Dip slides",
                    "Combined bacteria/fungi slides; incubator at 30 \u00b0C",
                ),
                (
                    "Sample bottles",
                    "Clean, 100 mL, labeled with machine number and date",
                ),
                (
                    "Coolant proportioner",
                    "Set to 7 % premix, supplied with potable water",
                ),
                ("Tramp oil skimmer", "Belt or disk type"),
            ),
        ),
        section(
            "Procedure",
            SubHeading("7.1 Sampling"),
            steps(
                "7.1",
                "Measure every sump weekly and after every recharge. Take samples with "
                "the coolant circulating for at least 15 minutes.",
                "Draw the sample from the return flow near the pump inlet, not from "
                "the surface of the sump. Fill a clean sample bottle and label it.",
            ),
            SubHeading("7.2 Concentration measurement"),
            steps(
                "7.2",
                "Zero the refractometer with distilled water.",
                "Place two or three drops of the sample on the prism, close the cover "
                "and read the Brix value at the boundary line.",
                "Calculate the concentration: concentration (%) = Brix reading \u00d7 "
                "refractometer factor. The refractometer factor of NC-400 is 1.2 (see "
                "TDS NC-400). Example: a reading of 5.8 Brix gives 5.8 \u00d7 1.2 = "
                "7.0 %.",
                "The target concentration is 6\u20138 %. Record the Brix reading and "
                "the calculated concentration on F-056-01.",
            ),
            SubHeading("7.3 Concentration correction"),
            Para(
                "Correct the concentration in accordance with Table 1. Never pour neat "
                "concentrate directly into a sump; always use premix from the "
                "proportioner or add water."
            ),
            DataTable(
                caption="Table 1 \u2013 Correction of concentration",
                header=("Measured concentration", "Action"),
                rows=(
                    (
                        "Below 5.0 %",
                        "Add 10 % premix; re-measure after 1 h; inform the supervisor",
                    ),
                    (
                        "5.0\u20135.9 %",
                        "Add 10 % premix; re-measure at the next weekly check",
                    ),
                    ("6.0\u20138.0 %", "No action; top up with 7 % premix only"),
                    ("8.1\u20139.0 %", "Top up with water only"),
                    (
                        "Above 9.0 %",
                        "Top up with water; check the proportioner setting",
                    ),
                ),
                widths=(0.3, 0.7),
            ),
            scanned_page(
                SubHeading("7.4 pH measurement"),
                steps(
                    "7.4",
                    "Measure the pH of the sample with the calibrated pH meter. The pH "
                    "shall be 8.5-9.2.",
                    "If the pH is below 8.5, add pH buffer in accordance with TDS "
                    "NC-400 and re-measure after 24 h.",
                    "A pH below 8.0 indicates strong bacterial activity: perform a dip "
                    "slide test immediately (7.6) and inform the Maintenance "
                    "Supervisor.",
                ),
                SubHeading("7.5 Tramp oil"),
                steps(
                    "7.5",
                    "Inspect the sump surface for tramp oil (leaked hydraulic oil and "
                    "way oil). Tramp oil shall not exceed 2 % of the sump volume.",
                    "Remove tramp oil with the skimmer. Empty the skimmer collection "
                    "container when it is three-quarters full.",
                    "Repeated high tramp oil indicates a leak: raise a maintenance "
                    "work order to find the source (see SOP-00123).",
                ),
                SubHeading("7.6 Bacteria and fungi (dip slides)"),
                steps(
                    "7.6",
                    "Perform a dip slide test every 2 weeks, and whenever the coolant "
                    "smells or the pH is below 8.0.",
                    "Immerse the dip slide in the sample for 10 s, drain it and "
                    "incubate it at 30 \u00b0C for 48 h.",
                    "Compare the slide with the manufacturer's chart and record the "
                    "result on F-056-01. Bacteria shall be below 100,000 CFU/mL; no "
                    "fungal growth shall be visible.",
                    "At 100,000 CFU/mL or more, or with visible fungal growth, inform "
                    "EHS; biocide may only be added as approved by EHS. At 1,000,000 "
                    "CFU/mL or more, the sump shall be drained, cleaned and recharged.",
                ),
            ),
            SubHeading("7.7 Sump top-up and recharge"),
            steps(
                "7.7",
                "Top up sumps only with 7 % premix from the proportioner.",
                "When a sump is recharged, drain it completely, clean it with the "
                "system cleaner specified in TDS NC-400, rinse it and fill it with 7 % "
                "premix. Measure the concentration after 15 minutes of circulation.",
                "Record every top-up and recharge, with the volume added, on F-056-01.",
            ),
        ),
        section(
            "Inspection & Acceptance Criteria",
            DataTable(
                header=("Parameter", "Acceptance criterion", "Frequency"),
                rows=(
                    ("Concentration", "6\u20138 % (Brix \u00d7 1.2)", "Weekly"),
                    ("pH", "8.5\u20139.2", "Weekly"),
                    ("Tramp oil", "Max. 2 % of sump volume", "Weekly"),
                    ("Bacteria (dip slide)", "Below 100,000 CFU/mL", "Every 2 weeks"),
                    ("Fungi (dip slide)", "No visible growth", "Every 2 weeks"),
                    ("Appearance and odor", "No foam, no rancid odor", "Each shift"),
                ),
                widths=(0.32, 0.43, 0.25),
            ),
            steps(
                "8",
                "Results outside these limits shall be corrected as described in "
                "Section 7 and the corrective action recorded.",
                "A sump that does not meet the criteria after correction must be "
                "reported to the Maintenance Supervisor.",
            ),
        ),
        section(
            "Records",
            steps(
                "9",
                "All measurements, corrections, top-ups and recharges are recorded on "
                "the Coolant Log F-056-01, one log per sump.",
                "Coolant logs shall be retained for 3 years.",
            ),
        ),
        section(
            "Revision History",
            revision_history(
                ("A.1", "2019-03-11", "S. Patel", "Initial release."),
                (
                    "B.1",
                    "2022-08-29",
                    "S. Patel",
                    "pH range and dip slide testing added.",
                ),
                (
                    "C.1",
                    "2025-11-05",
                    "S. Patel",
                    (
                        "Refractometer factor for NC-400 updated to 1.2; tramp oil "
                        "limit reduced to 2 %. Released."
                    ),
                ),
            ),
        ),
    ),
)

CONTENT: dict[str, SopContent] = {c.number: c for c in (SOP_00123, SOP_00087, SOP_00141, SOP_00056)}

# --- Rendering ------------------------------------------------------------------------

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_X = 20 * mm
MARGIN_BOTTOM = 24 * mm
FRAME_WIDTH = PAGE_WIDTH - 2 * MARGIN_X

INK = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#616E7C")
ACCENT = colors.HexColor("#1F3A5F")
RULE = colors.HexColor("#9AA5B1")
GRID = colors.HexColor("#CBD2D9")
HEADER_FILL = colors.HexColor("#E4E7EB")
DRAFT_RED = colors.HexColor("#B42318")
NOTICE_COLORS = {
    "WARNING": (colors.HexColor("#B42318"), colors.HexColor("#FDECEA")),
    "CAUTION": (colors.HexColor("#B54708"), colors.HexColor("#FEF4E6")),
    "NOTE": (colors.HexColor("#1F3A5F"), colors.HexColor("#EAF1F8")),
}

BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK)
STYLES = {
    "body": BODY,
    "label": ParagraphStyle(
        "label", parent=BODY, fontName="Helvetica-Bold", fontSize=9, textColor=MUTED
    ),
    "title": ParagraphStyle(
        "title",
        parent=BODY,
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=24,
        textColor=ACCENT,
    ),
    "subtitle": ParagraphStyle("subtitle", parent=BODY, fontSize=11.5, leading=15, textColor=INK),
    "h1": ParagraphStyle(
        "h1",
        parent=BODY,
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=ACCENT,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=1,
    ),
    "h2": ParagraphStyle(
        "h2",
        parent=BODY,
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        spaceBefore=6,
        spaceAfter=2,
        keepWithNext=1,
    ),
    "step": ParagraphStyle(
        "step",
        parent=BODY,
        leftIndent=11 * mm,
        bulletIndent=0,
        bulletFontName="Helvetica-Bold",
        spaceAfter=3,
    ),
    "bullet": ParagraphStyle(
        "bullet", parent=BODY, leftIndent=16 * mm, bulletIndent=11 * mm, spaceAfter=2
    ),
    "role": ParagraphStyle("role", parent=BODY, spaceAfter=3),
    "cell": ParagraphStyle("cell", parent=BODY, fontSize=8.5, leading=11),
    "cell_head": ParagraphStyle(
        "cell_head", parent=BODY, fontName="Helvetica-Bold", fontSize=8.5, leading=11
    ),
    "caption": ParagraphStyle(
        "caption",
        parent=BODY,
        fontName="Helvetica-Bold",
        fontSize=8.5,
        spaceBefore=4,
        spaceAfter=3,
    ),
}

# Keep numbers and their units on one line (NBSP extracts as a plain space).
_UNITS = (
    r"bar|\u00b0C|%|N\u00b7m|kN|Hz|mm|\u00b5m|mL|L|t|h|s|V|minutes|hours|days|years|"
    r"Brix|CFU/mL|dB\(A\)|operating hours|working days"
)
_NUMBER_UNIT = re.compile(rf"(?<=\d) (?=(?:{_UNITS})(?![\w]))")
_KEEP_TOGETHER = re.compile(r"\b(ISO VG|pH|Table|Section|section) (?=\d)")


def markup(text: str) -> str:
    """Escape plain text for a ReportLab Paragraph and bind numbers to their units."""
    text = _NUMBER_UNIT.sub("\u00a0", text)
    text = _KEEP_TOGETHER.sub(lambda m: m.group(1).replace(" ", "\u00a0") + "\u00a0", text)
    return escape(text)


def _table(block: DataTable) -> list[Flowable]:
    data = [[Paragraph(markup(h), STYLES["cell_head"]) for h in block.header]]
    data += [[Paragraph(markup(cell), STYLES["cell"]) for cell in row] for row in block.rows]
    table = Table(data, colWidths=[w * FRAME_WIDTH for w in block.widths], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_FILL),
                ("GRID", (0, 0), (-1, -1), 0.5, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    flowables: list[Flowable] = []
    if block.caption:
        flowables.append(Paragraph(markup(block.caption), STYLES["caption"]))
    flowables += [table, Spacer(1, 5)]
    return flowables


def _notice(block: Notice) -> list[Flowable]:
    border, fill = NOTICE_COLORS[block.kind]
    label_style = ParagraphStyle(
        f"notice_{block.kind}", parent=BODY, fontName="Helvetica-Bold", textColor=border
    )
    table = Table(
        [[Paragraph(block.kind, label_style), Paragraph(markup(block.text), BODY)]],
        colWidths=[22 * mm, FRAME_WIDTH - 22 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fill),
                ("LINEBEFORE", (0, 0), (0, 0), 2.5, border),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return [table, Spacer(1, 6)]


def _step_numbers(block: Steps) -> list[str]:
    return [f"{block.prefix}.{n}" for n in range(block.start, block.start + len(block.items))]


def _flowables(block: Block, render_scan: Callable[[ScannedPage], Flowable]) -> list[Flowable]:
    match block:
        case Para(text):
            return [Paragraph(markup(text), BODY), Spacer(1, 4)]
        case SubHeading(text):
            return [Paragraph(markup(text), STYLES["h2"])]
        case Steps():
            return [
                Paragraph(markup(item), STYLES["step"], bulletText=number)
                for number, item in zip(_step_numbers(block), block.items, strict=True)
            ]
        case Bullets(items):
            return [
                Paragraph(markup(item), STYLES["bullet"], bulletText="\u2013") for item in items
            ]
        case Roles(items):
            return [
                Paragraph(f"<b>{markup(term)}:</b> {markup(text)}", STYLES["role"])
                for term, text in items
            ]
        case Notice():
            return _notice(block)
        case DataTable():
            return _table(block)
        case ScannedPage():
            return [
                NextPageTemplate("scan"),
                PageBreak(),
                render_scan(block),
                NextPageTemplate("content"),
                PageBreak(),
            ]
    raise TypeError(f"unsupported block: {block!r}")


def _title_block(meta: SopMetadata, content: SopContent) -> list[Flowable]:
    rows = [
        ("Document number", meta.number),
        ("Title", meta.name),
        (
            "Revision",
            f"{meta.version} (revision {meta.revision}, iteration {meta.iteration})",
        ),
        ("Lifecycle state", meta.state),
        ("Effective date", content.effective_date),
        ("Document owner", content.owner),
        ("Approved by", content.approver),
        ("Applies to", content.applies_to),
    ]
    table = Table(
        [
            [
                Paragraph(label, STYLES["cell_head"]),
                Paragraph(markup(value), STYLES["cell"]),
            ]
            for label, value in rows
        ],
        colWidths=[40 * mm, FRAME_WIDTH - 40 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), HEADER_FILL),
                ("GRID", (0, 0), (-1, -1), 0.5, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return [
        Paragraph("STANDARD OPERATING PROCEDURE", STYLES["label"]),
        Spacer(1, 3),
        Paragraph(markup(meta.name), STYLES["title"]),
        Paragraph(markup(content.subtitle), STYLES["subtitle"]),
        Spacer(1, 8),
        table,
        Spacer(1, 6),
    ]


def build_story(
    meta: SopMetadata,
    content: SopContent,
    render_scan: Callable[[ScannedPage], Flowable],
) -> list[Flowable]:
    titles = tuple(section.title for section in content.sections)
    if titles != SECTION_TITLES:
        raise ValueError(f"{content.number}: sections must be {SECTION_TITLES}, got {titles}")
    story = _title_block(meta, content)
    for number, section in enumerate(content.sections, start=1):
        heading = Paragraph(markup(f"{number} {section.title}"), STYLES["h1"])
        body = [f for block in section.blocks for f in _flowables(block, render_scan)]
        if section.title == "Revision History":
            story.append(KeepTogether([heading, *body]))
        else:
            story += [heading, *body]
    return story


class SopDocTemplate(BaseDocTemplate):
    """A4 SOP layout: header and footer on content pages, bare full-page scan pages."""

    def __init__(
        self,
        buffer: io.BytesIO,
        meta: SopMetadata,
        content: SopContent,
        total_pages: int | None,
    ) -> None:
        self.meta = meta
        self.content = content
        self.total_pages = total_pages
        self.scan_pages: list[int] = []
        top = (34 if content.draft else 29) * mm
        super().__init__(
            buffer,
            pagesize=A4,
            leftMargin=MARGIN_X,
            rightMargin=MARGIN_X,
            topMargin=top,
            bottomMargin=MARGIN_BOTTOM,
            title=f"{meta.number} {meta.name}",
            author=f"{COMPANY} (synthetic sample)",
            subject=f"Standard Operating Procedure {meta.version}, {meta.state}",
            creator="Document Intelligence scripts/generate_samples.py",
            keywords=["SOP", meta.number, "synthetic sample", "development only"],
            invariant=1,
        )
        body = Frame(
            MARGIN_X,
            MARGIN_BOTTOM,
            FRAME_WIDTH,
            PAGE_HEIGHT - top - MARGIN_BOTTOM,
            id="body",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        scan = Frame(
            1,
            1,
            PAGE_WIDTH - 2,
            PAGE_HEIGHT - 1,
            id="scan",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates(
            [
                PageTemplate("content", [body], onPage=self._decorate),
                PageTemplate("scan", [scan], onPage=self._record_scan),
            ]
        )

    def page_label(self, page: int) -> str:
        total = self.total_pages if self.total_pages is not None else "?"
        return f"Page {page} of {total}"

    def _record_scan(self, canvas: Canvas, _doc: BaseDocTemplate) -> None:
        self.scan_pages.append(canvas.getPageNumber())

    def _decorate(self, canvas: Canvas, _doc: BaseDocTemplate) -> None:
        meta = self.meta
        right = PAGE_WIDTH - MARGIN_X
        canvas.saveState()
        # Header
        canvas.setFillColor(ACCENT)
        canvas.setFont("Helvetica-Bold", 9.5)
        canvas.drawString(MARGIN_X, PAGE_HEIGHT - 13 * mm, COMPANY.upper())
        canvas.setFillColor(INK)
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(
            right,
            PAGE_HEIGHT - 13 * mm,
            f"{meta.number} | Rev. {meta.version} | {meta.state}",
        )
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(MARGIN_X, PAGE_HEIGHT - 17.5 * mm, meta.name)
        canvas.drawRightString(right, PAGE_HEIGHT - 17.5 * mm, "Standard Operating Procedure")
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN_X, PAGE_HEIGHT - 20 * mm, right, PAGE_HEIGHT - 20 * mm)
        if self.content.draft:
            canvas.setFillColor(DRAFT_RED)
            canvas.setFont("Helvetica-Bold", 10)
            canvas.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 26 * mm, DRAFT_BANNER)
        # Footer
        canvas.line(MARGIN_X, 17 * mm, right, 17 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(MARGIN_X, 12.5 * mm, CONTROLLED_NOTICE)
        canvas.setFillColor(INK)
        canvas.setFont("Helvetica-Bold", 8.5)
        canvas.drawRightString(right, 12.5 * mm, self.page_label(canvas.getPageNumber()))
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.5)
        canvas.drawString(MARGIN_X, 8.5 * mm, SYNTHETIC_NOTICE)
        canvas.restoreState()


# --- Simulated scan -------------------------------------------------------------------

SCAN_DPI = 150
SCAN_SIZE = (round(PAGE_WIDTH / 72 * SCAN_DPI), round(PAGE_HEIGHT / 72 * SCAN_DPI))
# Pillow's bundled font covers ASCII and a little Latin-1 only.
_SCAN_ASCII = str.maketrans({"\u2013": "-", "\u2014": "-", "\u00d7": "x", "\u00b5": "u"})


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: Any, width: float) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and draw.textlength(candidate, font=font) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def render_scan_png(
    blocks: Sequence[Para | SubHeading | Steps], *, header: str, title: str, footer: str
) -> bytes:
    """Render text blocks into a grayscale PNG that looks like a scanned SOP page."""
    width, height = SCAN_SIZE
    margin = 150
    body_font = ImageFont.load_default(size=25)
    small_font = ImageFont.load_default(size=19)
    heading_font = ImageFont.load_default(size=29)
    image = PILImage.new("L", SCAN_SIZE, 250)
    draw = ImageDraw.Draw(image)

    # Header and footer as printed on the paper original.
    draw.text((margin, 90), COMPANY.upper(), font=small_font, fill=40)
    draw.text((width - margin, 90), header, font=small_font, fill=40, anchor="ra")
    draw.text((margin, 120), title, font=small_font, fill=90)
    draw.line((margin, 152, width - margin, 152), fill=120, width=2)
    draw.line((margin, height - 150, width - margin, height - 150), fill=120, width=2)
    draw.text(
        (margin, height - 130),
        CONTROLLED_NOTICE.translate(_SCAN_ASCII),
        font=small_font,
        fill=90,
    )
    draw.text((width - margin, height - 130), footer, font=small_font, fill=40, anchor="ra")
    draw.text(
        (margin, height - 100),
        SYNTHETIC_NOTICE.translate(_SCAN_ASCII),
        font=small_font,
        fill=120,
    )

    y = 200
    indent = 95
    text_width = width - 2 * margin
    for block in blocks:
        match block:
            case SubHeading(text):
                y += 18
                draw.text((margin, y), text.translate(_SCAN_ASCII), font=heading_font, fill=25)
                y += 48
            case Para(text):
                for line in _wrap(draw, text.translate(_SCAN_ASCII), body_font, text_width):
                    draw.text((margin, y), line, font=body_font, fill=30)
                    y += 36
                y += 12
            case Steps():
                for number, item in zip(_step_numbers(block), block.items, strict=True):
                    draw.text((margin, y), number, font=body_font, fill=30)
                    wrapped = _wrap(
                        draw,
                        item.translate(_SCAN_ASCII),
                        body_font,
                        text_width - indent,
                    )
                    for line in wrapped:
                        draw.text((margin + indent, y), line, font=body_font, fill=30)
                        y += 36
                    y += 10
    if y > height - 190:
        raise ValueError("scanned page content does not fit on one page")

    # A slight skew and a darker binding edge make it look like a scan of a paper copy.
    image = image.rotate(0.4, resample=PILImage.Resampling.BICUBIC, fillcolor=225)
    edge = PILImage.linear_gradient("L").rotate(90).resize((40, height))
    image.paste(PILImage.eval(edge, lambda v: 200 + v // 5), (0, 0))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


# --- Build ----------------------------------------------------------------------------


@dataclass(frozen=True)
class BuiltPdf:
    data: bytes
    page_count: int
    scan_pages: tuple[int, ...]


def _render(meta: SopMetadata, content: SopContent, total_pages: int | None) -> BuiltPdf:
    buffer = io.BytesIO()
    doc = SopDocTemplate(buffer, meta, content, total_pages)
    scan_index = 0

    def render_scan(block: ScannedPage) -> Flowable:
        # The scan's page number is only known for certain after the first pass.
        nonlocal scan_index
        scan_index += 1
        page = content.scanned_page if content.scanned_page is not None else scan_index
        png = render_scan_png(
            block.blocks,
            header=f"{meta.number} | Rev. {meta.version} | {meta.state}",
            title=meta.name,
            footer=doc.page_label(page),
        )
        return Image(io.BytesIO(png), width=PAGE_WIDTH - 2, height=PAGE_HEIGHT - 2)

    doc.build(build_story(meta, content, render_scan))
    return BuiltPdf(buffer.getvalue(), doc.page, tuple(doc.scan_pages))


def build_pdf(meta: SopMetadata, content: SopContent) -> BuiltPdf:
    """Build the PDF in two passes so that every page can show "Page X of Y"."""
    first = _render(meta, content, total_pages=None)
    final = _render(meta, content, total_pages=first.page_count)
    if final.page_count != first.page_count:
        raise RuntimeError(f"{meta.number}: page count changed between passes")
    expected_scans = () if content.scanned_page is None else (content.scanned_page,)
    if final.scan_pages != expected_scans:
        raise RuntimeError(
            f"{meta.number}: scanned page landed on {final.scan_pages}, expected "
            f"{expected_scans}; adjust the content before the scanned page"
        )
    return final


def load_catalog(path: Path = CATALOG_PATH) -> list[dict[str, Any]]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    return list(catalog["documents"])


def generate(out_dir: Path, catalog_path: Path = CATALOG_PATH) -> list[tuple[Path, BuiltPdf]]:
    """Generate one PDF per catalog entry into ``out_dir``; return the files written."""
    entries = load_catalog(catalog_path)
    numbers = {entry["metadata"]["number"] for entry in entries}
    if numbers != set(CONTENT):
        raise ValueError(
            f"catalog documents {sorted(numbers)} do not match the sample content {sorted(CONTENT)}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[Path, BuiltPdf]] = []
    for entry in entries:
        m = entry["metadata"]
        meta = SopMetadata(
            number=m["number"],
            name=m["name"],
            revision=m["revision"],
            iteration=m["iteration"],
            state=m["state"],
        )
        built = build_pdf(meta, CONTENT[meta.number])
        target = out_dir / entry["file"]
        target.write_bytes(built.data)
        written.append((target, built))
    return written


def _display(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the synthetic SOP sample PDFs.")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        metavar="DIR",
        help=f"output directory (default: {DEFAULT_OUT_DIR})",
    )
    args = parser.parse_args(argv)
    for path, built in generate(args.out):
        size = f"{built.page_count} pages, {len(built.data):,} bytes"
        print(f"wrote {_display(path)} ({size})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
