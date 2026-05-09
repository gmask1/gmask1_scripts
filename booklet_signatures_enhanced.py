#!/usr/bin/env python3
"""
Combine one or more PDFs and split them into bookbinding signatures.

This script supports two layout modes:

1) reading-order
   Keeps pages in normal reading order within each signature. Use this when
   your PDF viewer or printer driver can handle booklet printing.

2) imposed
   Rearranges each signature into landscape sheet sides, two book pages per PDF
   page, ready for plain duplex printing without booklet mode. In this mode the
   output PDF pages are already imposed for folding into signatures.

Examples:
    python booklet_signatures.py \
        --inputs chapter1.pdf chapter2.pdf \
        --output-folder ./out \
        --sheets-per-signature 4 \
        --output-mode per-signature \
        --tail-mode short \
        --layout-mode reading-order

    python booklet_signatures.py \
        --inputs chapter1.pdf chapter2.pdf \
        --output-folder ./out \
        --sheets-per-signature 4 \
        --output-mode per-signature \
        --tail-mode pad \
        --layout-mode imposed

    python booklet_signatures.py \
        --inputs chapter1.pdf chapter2.pdf \
        --output-folder ./out \
        --sheets-per-signature 4 \
        --output-mode per-signature \
        --tail-mode short \
        --layout-mode reading-order \
        --final-blank-placement front

    python booklet_signatures.py \
        --inputs chapter1.pdf chapter2.pdf \
        --output-folder ./out \
        --sheets-per-signature 4 \
        --output-mode per-signature \
        --tail-mode short \
        --layout-mode reading-order \
        --final-blank-placement infront

Notes about imposed mode:
    - It assumes each source PDF page is one finished book page.
    - It creates landscape sheet-side pages sized at 2 x page width by 1 x page
      height, placing two source pages side-by-side.
    - Print with normal duplex printing (typically flip on the short edge) and
      DO NOT enable booklet mode.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from pypdf import PageObject, PdfReader, PdfWriter, Transformation


@dataclass
class SourceDocument:
    path: Path
    reader: PdfReader
    page_count: int


@dataclass
class BookPage:
    page: PageObject
    source_path: Path
    source_page_number: int  # 1-based within source PDF
    book_page_number: int    # 1-based within combined book


@dataclass
class SignaturePlan:
    index: int
    real_pages: int
    total_pages: int
    blank_pages: int
    start_book_page: int
    end_book_page: int

    @property
    def sheets(self) -> int:
        return self.total_pages // 4


class BookletError(Exception):
    pass


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append PDFs and split them into signature-sized PDFs for bookbinding.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="Input PDF files, in the order they should appear in the final book.",
    )
    parser.add_argument(
        "--output-folder",
        required=True,
        help="Folder where the output PDF(s) and plan file will be written.",
    )
    parser.add_argument(
        "--sheets-per-signature",
        type=int,
        default=4,
        help="Physical sheets in a full signature. Each sheet holds 4 book pages total.",
    )
    parser.add_argument(
        "--output-mode",
        choices=("per-signature", "single"),
        default="per-signature",
        help="Write one PDF per signature, or one combined PDF containing all signatures.",
    )
    parser.add_argument(
        "--tail-mode",
        choices=("short", "pad"),
        default="short",
        help=(
            "How to handle an incomplete final signature: 'short' makes the last signature shorter "
            "(still rounded up to a whole sheet / multiple of 4 pages), 'pad' fills the final signature "
            "with blanks to the full signature size."
        ),
    )
    parser.add_argument(
        "--final-blank-placement",
        choices=("back", "front", "infront"),
        default="back",
        help=(
            "For an incomplete final signature, place any required blank pages at the 'back' "
            "(current behavior), at the 'front' before all final-signature content, or 'infront' "
            "of only the final real page so the back-cover page remains at the back of the book."
        ),
    )
    parser.add_argument(
        "--layout-mode",
        choices=("reading-order", "imposed"),
        default="reading-order",
        help=(
            "'reading-order' keeps pages in normal order for printer/viewer booklet mode; "
            "'imposed' rearranges pages onto landscape sheet sides for plain duplex printing without booklet mode."
        ),
    )
    parser.add_argument(
        "--base-name",
        default="book",
        help="Base filename for the generated output files.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow existing output files to be overwritten.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write PDFs; only print the signature plan and write the plan text file.",
    )
    return parser.parse_args(argv)


def ensure_pdf_path(path_text: str) -> Path:
    path = Path(path_text).expanduser().resolve()
    if not path.exists():
        raise BookletError(f"Input file not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise BookletError(f"Input file is not a PDF: {path}")
    return path


def load_sources(input_paths: Sequence[str]) -> list[SourceDocument]:
    sources: list[SourceDocument] = []
    for raw_path in input_paths:
        path = ensure_pdf_path(raw_path)
        try:
            reader = PdfReader(str(path))
        except Exception as exc:  # pragma: no cover - defensive
            raise BookletError(f"Could not read PDF '{path}': {exc}") from exc
        page_count = len(reader.pages)
        if page_count == 0:
            raise BookletError(f"Input PDF has no pages: {path}")
        sources.append(SourceDocument(path=path, reader=reader, page_count=page_count))
    return sources


def build_book_pages(sources: Sequence[SourceDocument]) -> tuple[list[BookPage], float, float, list[str]]:
    book_pages: list[BookPage] = []
    warnings: list[str] = []
    base_width: float | None = None
    base_height: float | None = None
    first_size_source: str | None = None

    book_page_number = 1
    for source in sources:
        for page_index, page in enumerate(source.reader.pages, start=1):
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            if base_width is None or base_height is None:
                base_width = width
                base_height = height
                first_size_source = f"{source.path.name} page {page_index}"
            else:
                if abs(width - base_width) > 0.5 or abs(height - base_height) > 0.5:
                    warnings.append(
                        "Page size mismatch detected: "
                        f"{source.path.name} page {page_index} is {width:.2f} x {height:.2f} pt, "
                        f"but the first page ({first_size_source}) is {base_width:.2f} x {base_height:.2f} pt. "
                        "The script will continue, but inserted blank pages will use the first page size, "
                        "and imposed mode will use the first page size as the sheet layout basis."
                    )
            book_pages.append(
                BookPage(
                    page=page,
                    source_path=source.path,
                    source_page_number=page_index,
                    book_page_number=book_page_number,
                )
            )
            book_page_number += 1

    assert base_width is not None and base_height is not None
    return book_pages, base_width, base_height, warnings


def build_signature_plan(total_book_pages: int, sheets_per_signature: int, tail_mode: str) -> list[SignaturePlan]:
    if sheets_per_signature <= 0:
        raise BookletError("--sheets-per-signature must be greater than zero.")

    full_signature_pages = sheets_per_signature * 4
    if total_book_pages <= 0:
        raise BookletError("There are no book pages to process.")

    plans: list[SignaturePlan] = []
    remaining = total_book_pages
    cursor = 1
    index = 1

    while remaining > 0:
        if remaining >= full_signature_pages:
            real_pages = full_signature_pages
            total_pages = full_signature_pages
        else:
            real_pages = remaining
            if tail_mode == "pad":
                total_pages = full_signature_pages
            elif tail_mode == "short":
                total_pages = math.ceil(real_pages / 4) * 4
            else:  # pragma: no cover - argparse should prevent this
                raise BookletError(f"Unsupported tail mode: {tail_mode}")

        plans.append(
            SignaturePlan(
                index=index,
                real_pages=real_pages,
                total_pages=total_pages,
                blank_pages=total_pages - real_pages,
                start_book_page=cursor,
                end_book_page=cursor + real_pages - 1,
            )
        )
        cursor += real_pages
        remaining -= real_pages
        index += 1

    return plans


def signature_book_pages(book_pages: Sequence[BookPage], plan: SignaturePlan) -> list[BookPage]:
    start_index = plan.start_book_page - 1
    end_index = plan.end_book_page
    return list(book_pages[start_index:end_index])


def make_writer_with_metadata(
    base_name: str,
    sources: Sequence[SourceDocument],
    plan_label: str,
    layout_mode: str,
) -> PdfWriter:
    writer = PdfWriter()
    source_names = ", ".join(source.path.name for source in sources)
    writer.add_metadata(
        {
            "/Title": f"{base_name} - {plan_label}",
            "/Author": "ChatGPT generated booklet_signatures.py",
            "/Subject": f"Bookbinding signatures prepared from appended source PDFs ({layout_mode})",
            "/Keywords": "bookbinding, booklet, signatures, pdf",
            "/Creator": "booklet_signatures.py",
            "/Producer": "pypdf",
            "/Source": source_names,
            "/ModDate": datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%SZ"),
        }
    )
    return writer


def get_blank_placement_for_plan(
    plan: SignaturePlan,
    total_plan_count: int,
    final_blank_placement: str,
) -> str:
    if plan.blank_pages > 0 and plan.index == total_plan_count:
        return final_blank_placement
    return "back"



def add_reading_order_signature_to_writer(
    writer: PdfWriter,
    signature_pages: Sequence[BookPage],
    blanks_to_add: int,
    blank_width: float,
    blank_height: float,
    blank_placement: str,
) -> None:
    if blank_placement == "front":
        for _ in range(blanks_to_add):
            writer.add_blank_page(width=blank_width, height=blank_height)
        for book_page in signature_pages:
            writer.add_page(book_page.page)
    elif blank_placement == "back":
        for book_page in signature_pages:
            writer.add_page(book_page.page)
        for _ in range(blanks_to_add):
            writer.add_blank_page(width=blank_width, height=blank_height)
    elif blank_placement == "infront":
        if signature_pages:
            for book_page in signature_pages[:-1]:
                writer.add_page(book_page.page)
            for _ in range(blanks_to_add):
                writer.add_blank_page(width=blank_width, height=blank_height)
            writer.add_page(signature_pages[-1].page)
        else:
            for _ in range(blanks_to_add):
                writer.add_blank_page(width=blank_width, height=blank_height)
    else:  # pragma: no cover - defensive
        raise BookletError(f"Unsupported blank placement: {blank_placement}")



def build_signature_slots(
    signature_pages: Sequence[BookPage],
    blanks_to_add: int,
    blank_placement: str,
) -> list[BookPage | None]:
    content_slots: list[BookPage | None] = list(signature_pages)
    blank_slots: list[BookPage | None] = [None] * blanks_to_add

    if blank_placement == "front":
        return blank_slots + content_slots
    if blank_placement == "back":
        return content_slots + blank_slots
    if blank_placement == "infront":
        if content_slots:
            return content_slots[:-1] + blank_slots + [content_slots[-1]]
        return blank_slots
    raise BookletError(f"Unsupported blank placement: {blank_placement}")



def add_two_up_sheet_side(
    writer: PdfWriter,
    left_page: BookPage | None,
    right_page: BookPage | None,
    page_width: float,
    page_height: float,
) -> None:
    sheet_width = page_width * 2
    sheet_height = page_height
    sheet = PageObject.create_blank_page(width=sheet_width, height=sheet_height)

    if left_page is not None:
        sheet.merge_transformed_page(
            left_page.page,
            Transformation().translate(tx=0, ty=0),
        )
    if right_page is not None:
        sheet.merge_transformed_page(
            right_page.page,
            Transformation().translate(tx=page_width, ty=0),
        )

    writer.add_page(sheet)



def add_imposed_signature_to_writer(
    writer: PdfWriter,
    signature_pages: Sequence[BookPage],
    blanks_to_add: int,
    blank_width: float,
    blank_height: float,
    blank_placement: str,
) -> None:
    slots = build_signature_slots(signature_pages, blanks_to_add, blank_placement)
    total_pages = len(slots)
    if total_pages % 4 != 0:
        raise BookletError("Imposed layout requires signatures whose total page count is a multiple of 4.")

    for sheet_index in range(total_pages // 4):
        left_front = total_pages - (2 * sheet_index)
        right_front = 1 + (2 * sheet_index)
        left_back = 2 + (2 * sheet_index)
        right_back = total_pages - (2 * sheet_index + 1)

        add_two_up_sheet_side(
            writer,
            left_page=slots[left_front - 1],
            right_page=slots[right_front - 1],
            page_width=blank_width,
            page_height=blank_height,
        )
        add_two_up_sheet_side(
            writer,
            left_page=slots[left_back - 1],
            right_page=slots[right_back - 1],
            page_width=blank_width,
            page_height=blank_height,
        )



def check_output_path(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise BookletError(
            f"Output file already exists: {path}\n"
            "Use --overwrite to allow replacement, or choose a different output folder/base name."
        )



def write_pdf(path: Path, writer: PdfWriter) -> None:
    with path.open("wb") as handle:
        writer.write(handle)



def slot_label(slot_number: int, plan: SignaturePlan, blank_placement: str) -> str:
    if blank_placement == "front":
        if slot_number <= plan.blank_pages:
            return "blank"
        content_slot = slot_number - plan.blank_pages
        if content_slot <= plan.real_pages:
            return str(plan.start_book_page + content_slot - 1)
        return "blank"

    if blank_placement == "back":
        if slot_number <= plan.real_pages:
            return str(plan.start_book_page + slot_number - 1)
        return "blank"

    if blank_placement == "infront":
        if plan.real_pages <= 0:
            return "blank"
        if slot_number <= max(plan.real_pages - 1, 0):
            return str(plan.start_book_page + slot_number - 1)
        if slot_number <= (plan.real_pages - 1) + plan.blank_pages:
            return "blank"
        if slot_number == plan.total_pages:
            return str(plan.end_book_page)
        return "blank"

    raise BookletError(f"Unsupported blank placement: {blank_placement}")



def build_plan_text(
    sources: Sequence[SourceDocument],
    plans: Sequence[SignaturePlan],
    output_mode: str,
    tail_mode: str,
    sheets_per_signature: int,
    layout_mode: str,
    final_blank_placement: str,
    warnings: Sequence[str],
) -> str:
    lines: list[str] = []
    lines.append("Booklet signature plan")
    lines.append("=" * 80)
    lines.append(f"Created: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("Inputs")
    lines.append("-" * 80)
    for source in sources:
        lines.append(f"- {source.path} ({source.page_count} pages)")
    lines.append("")
    lines.append("Settings")
    lines.append("-" * 80)
    lines.append(f"Output mode            : {output_mode}")
    lines.append(f"Tail mode              : {tail_mode}")
    lines.append(f"Final blank placement  : {final_blank_placement}")
    lines.append(f"Layout mode            : {layout_mode}")
    lines.append(f"Sheets per signature   : {sheets_per_signature}")
    lines.append(f"Book pages per full sig: {sheets_per_signature * 4}")
    lines.append(f"Signature count        : {len(plans)}")
    lines.append(f"Total input book pages : {sum(source.page_count for source in sources)}")
    if layout_mode == "reading-order":
        total_output_pdf_pages = sum(plan.total_pages for plan in plans)
    else:
        total_output_pdf_pages = sum(plan.total_pages // 2 for plan in plans)
    lines.append(f"Total output PDF pages : {total_output_pdf_pages}")
    lines.append("")
    lines.append("Signatures")
    lines.append("-" * 80)
    for plan in plans:
        blank_placement = get_blank_placement_for_plan(plan, len(plans), final_blank_placement)
        detail = (
            f"Signature {plan.index:02d}: book pages {plan.start_book_page}-{plan.end_book_page} "
            f"| real={plan.real_pages} | total={plan.total_pages} | sheets={plan.sheets}"
        )
        if plan.blank_pages:
            detail += f" | blanks={plan.blank_pages} ({blank_placement})"
        lines.append(detail)

        if layout_mode == "imposed":
            for sheet_index in range(plan.sheets):
                left_front = plan.total_pages - (2 * sheet_index)
                right_front = 1 + (2 * sheet_index)
                left_back = 2 + (2 * sheet_index)
                right_back = plan.total_pages - (2 * sheet_index + 1)
                lines.append(
                    f"  Sheet {sheet_index + 1:02d} front: "
                    f"{slot_label(left_front, plan, blank_placement)} | {slot_label(right_front, plan, blank_placement)}"
                )
                lines.append(
                    f"  Sheet {sheet_index + 1:02d} back : "
                    f"{slot_label(left_back, plan, blank_placement)} | {slot_label(right_back, plan, blank_placement)}"
                )

    if warnings:
        lines.append("")
        lines.append("Warnings")
        lines.append("-" * 80)
        for warning in warnings:
            lines.append(f"- {warning}")
    lines.append("")
    lines.append("Note")
    lines.append("-" * 80)
    if layout_mode == "reading-order":
        lines.append(
            "These output PDFs are kept in normal reading order inside each signature. "
            "Use this mode when your PDF viewer or printer handles booklet printing."
        )
        if final_blank_placement == "front":
            lines.append(
                "When the final signature is incomplete, required blanks are placed before the final content so "
                "the last source PDF page remains the last page of the signature."
            )
        elif final_blank_placement == "infront":
            lines.append(
                "When the final signature is incomplete, required blanks are placed immediately before only the "
                "final real page of the final signature. This is useful when the last source PDF page is a back cover."
            )
        if output_mode == "single":
            lines.append(
                "If your printer's booklet mode treats the entire file as one booklet, print the single PDF by "
                "signature-sized page ranges rather than all at once."
            )
    else:
        lines.append(
            "These output PDFs are already imposed as landscape sheet sides, two book pages per PDF page. "
            "Print with plain duplex printing and do not enable booklet mode."
        )
        if final_blank_placement == "front":
            lines.append(
                "When the final signature is incomplete, required blanks are placed at the front of the logical "
                "signature before imposition so the final source PDF page remains the last page of the signature."
            )
        elif final_blank_placement == "infront":
            lines.append(
                "When the final signature is incomplete, required blanks are placed immediately before only the "
                "final real page of the logical signature before imposition. This is useful when the last source PDF "
                "page is a back cover."
            )
        lines.append(
            "Typical duplex setting is flip on the short edge, but confirm with a small test print because some "
            "printers and drivers label duplex orientation differently."
        )
    return "\n".join(lines) + "\n"



def write_plan_file(path: Path, text: str, overwrite: bool) -> None:
    check_output_path(path, overwrite)
    path.write_text(text, encoding="utf-8")



def print_console_summary(
    plans: Sequence[SignaturePlan],
    total_input_pages: int,
    layout_mode: str,
    final_blank_placement: str,
) -> None:
    print()
    print(f"Total input pages : {total_input_pages}")
    print(f"Signature count   : {len(plans)}")
    print(f"Layout mode       : {layout_mode}")
    print(f"Final blank place : {final_blank_placement}")
    print()
    for plan in plans:
        blank_placement = get_blank_placement_for_plan(plan, len(plans), final_blank_placement)
        if layout_mode == "reading-order":
            output_pdf_pages = plan.total_pages
        else:
            output_pdf_pages = plan.total_pages // 2
        line = (
            f"Signature {plan.index:02d}: pages {plan.start_book_page}-{plan.end_book_page}, "
            f"real={plan.real_pages}, total={plan.total_pages}, sheets={plan.sheets}, "
            f"output_pdf_pages={output_pdf_pages}"
        )
        if plan.blank_pages:
            line += f", blanks={plan.blank_pages} ({blank_placement})"
        print(line)
    print()



def add_signature_to_writer(
    *,
    writer: PdfWriter,
    signature_pages: Sequence[BookPage],
    blanks_to_add: int,
    blank_width: float,
    blank_height: float,
    layout_mode: str,
    blank_placement: str,
) -> None:
    if layout_mode == "reading-order":
        add_reading_order_signature_to_writer(
            writer,
            signature_pages=signature_pages,
            blanks_to_add=blanks_to_add,
            blank_width=blank_width,
            blank_height=blank_height,
            blank_placement=blank_placement,
        )
    elif layout_mode == "imposed":
        add_imposed_signature_to_writer(
            writer,
            signature_pages=signature_pages,
            blanks_to_add=blanks_to_add,
            blank_width=blank_width,
            blank_height=blank_height,
            blank_placement=blank_placement,
        )
    else:  # pragma: no cover - argparse should prevent this
        raise BookletError(f"Unsupported layout mode: {layout_mode}")



def generate_outputs(
    *,
    sources: Sequence[SourceDocument],
    book_pages: Sequence[BookPage],
    plans: Sequence[SignaturePlan],
    blank_width: float,
    blank_height: float,
    output_folder: Path,
    base_name: str,
    output_mode: str,
    layout_mode: str,
    final_blank_placement: str,
    overwrite: bool,
) -> list[Path]:
    generated: list[Path] = []

    layout_suffix = "reading_order" if layout_mode == "reading-order" else "imposed"

    if output_mode == "per-signature":
        for plan in plans:
            label = f"signature {plan.index:02d} ({layout_mode})"
            writer = make_writer_with_metadata(
                base_name=base_name,
                sources=sources,
                plan_label=label,
                layout_mode=layout_mode,
            )
            sig_pages = signature_book_pages(book_pages, plan)
            blank_placement = get_blank_placement_for_plan(plan, len(plans), final_blank_placement)
            add_signature_to_writer(
                writer=writer,
                signature_pages=sig_pages,
                blanks_to_add=plan.blank_pages,
                blank_width=blank_width,
                blank_height=blank_height,
                layout_mode=layout_mode,
                blank_placement=blank_placement,
            )
            out_path = output_folder / f"{base_name}_sig{plan.index:02d}_{layout_suffix}.pdf"
            check_output_path(out_path, overwrite)
            write_pdf(out_path, writer)
            generated.append(out_path)
    elif output_mode == "single":
        writer = make_writer_with_metadata(
            base_name=base_name,
            sources=sources,
            plan_label=f"all signatures ({layout_mode})",
            layout_mode=layout_mode,
        )
        for plan in plans:
            sig_pages = signature_book_pages(book_pages, plan)
            blank_placement = get_blank_placement_for_plan(plan, len(plans), final_blank_placement)
            add_signature_to_writer(
                writer=writer,
                signature_pages=sig_pages,
                blanks_to_add=plan.blank_pages,
                blank_width=blank_width,
                blank_height=blank_height,
                layout_mode=layout_mode,
                blank_placement=blank_placement,
            )
        out_path = output_folder / f"{base_name}_all_signatures_{layout_suffix}.pdf"
        check_output_path(out_path, overwrite)
        write_pdf(out_path, writer)
        generated.append(out_path)
    else:  # pragma: no cover - argparse should prevent this
        raise BookletError(f"Unsupported output mode: {output_mode}")

    return generated



def main(argv: Sequence[str]) -> int:
    try:
        args = parse_args(argv)
        output_folder = Path(args.output_folder).expanduser().resolve()
        output_folder.mkdir(parents=True, exist_ok=True)

        sources = load_sources(args.inputs)
        book_pages, blank_width, blank_height, warnings = build_book_pages(sources)
        plans = build_signature_plan(
            total_book_pages=len(book_pages),
            sheets_per_signature=args.sheets_per_signature,
            tail_mode=args.tail_mode,
        )

        plan_text = build_plan_text(
            sources=sources,
            plans=plans,
            output_mode=args.output_mode,
            tail_mode=args.tail_mode,
            sheets_per_signature=args.sheets_per_signature,
            layout_mode=args.layout_mode,
            final_blank_placement=args.final_blank_placement,
            warnings=warnings,
        )

        plan_path = output_folder / f"{args.base_name}_signature_plan.txt"
        write_plan_file(plan_path, plan_text, overwrite=args.overwrite)
        print_console_summary(
            plans,
            total_input_pages=len(book_pages),
            layout_mode=args.layout_mode,
            final_blank_placement=args.final_blank_placement,
        )

        if warnings:
            print("Warnings:")
            for warning in warnings:
                print(f"- {warning}")
            print()

        if args.dry_run:
            print(f"Dry run complete. Plan file written to: {plan_path}")
            return 0

        generated_paths = generate_outputs(
            sources=sources,
            book_pages=book_pages,
            plans=plans,
            blank_width=blank_width,
            blank_height=blank_height,
            output_folder=output_folder,
            base_name=args.base_name,
            output_mode=args.output_mode,
            layout_mode=args.layout_mode,
            final_blank_placement=args.final_blank_placement,
            overwrite=args.overwrite,
        )

        print("Generated files:")
        for path in generated_paths:
            print(f"- {path}")
        print(f"- {plan_path}")
        return 0

    except BookletError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
