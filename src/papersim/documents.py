"""PDF document indexing and source-addressable evidence validation."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import re
from typing import Any, Iterable

from .contracts import ContractError
from .store import sha256


_LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\u00ad": "",
    "\u2212": "-",
}
_GLYPHS = {
    "ð": "(",
    "Þ": ")",
    "\x03": "=",
    "\x04": "-",
    "\x05": ")",
    "\x02": "=",
    "\ufb01": "fi",
    "\ufb02": "fl",
}


def normalize_text(value: str) -> str:
    for source, target in {**_LIGATURES, **_GLYPHS}.items():
        value = value.replace(source, target)
    value = value.replace("\r", " ").replace("\n", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _pymupdf():
    try:
        import pymupdf
    except ImportError as exc:
        raise ContractError("PDF extraction requires the optional 'extraction' dependencies") from exc
    return pymupdf


@dataclass(frozen=True)
class PdfLine:
    page: int
    text: str
    bbox: tuple[float, float, float, float]
    block: int
    line: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EquationRegion:
    number: int
    page: int
    bbox: tuple[float, float, float, float]
    raw_text: str
    image: str = ""
    confidence: str = "detected"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRef:
    label: str
    artifact_sha256: str
    page: int
    bbox: tuple[float, float, float, float]
    quote: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class PdfDocument:
    """Index a PDF without modifying it."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise ContractError(f"PDF does not exist: {self.path}")
        self.sha256 = sha256(self.path)
        self._document = _pymupdf().open(self.path)

    @property
    def page_count(self) -> int:
        return int(self._document.page_count)

    def close(self) -> None:
        self._document.close()

    def page_text(self, page: int) -> str:
        self._check_page(page)
        return self._document[page - 1].get_text("text")

    def lines(self, page: int | None = None) -> list[PdfLine]:
        pages = range(1, self.page_count + 1) if page is None else [page]
        result: list[PdfLine] = []
        for page_number in pages:
            self._check_page(page_number)
            data = self._document[page_number - 1].get_text("dict")
            for block_index, block in enumerate(data.get("blocks", [])):
                for line_index, line in enumerate(block.get("lines", [])):
                    text = "".join(str(span.get("text") or "") for span in line.get("spans", [])).strip()
                    if not text:
                        continue
                    bbox = tuple(float(value) for value in line["bbox"])
                    result.append(PdfLine(page_number, text, bbox, block_index, line_index))
        return result

    def equation_regions(self) -> list[EquationRegion]:
        regions: list[EquationRegion] = []
        for page_number in range(1, self.page_count + 1):
            data = self._document[page_number - 1].get_text("dict")
            for block in data.get("blocks", []):
                block_lines: list[PdfLine] = []
                for line_index, line in enumerate(block.get("lines", [])):
                    text = "".join(str(span.get("text") or "") for span in line.get("spans", [])).strip()
                    if text:
                        block_lines.append(
                            PdfLine(
                                page_number,
                                text,
                                tuple(float(value) for value in line["bbox"]),
                                -1,
                                line_index,
                            )
                        )
                for index, line in enumerate(block_lines):
                    number = self._equation_number(line.text)
                    if number is None:
                        continue
                    selected = [line]
                    cursor = index - 1
                    while cursor >= 0 and len(selected) < 6:
                        previous = block_lines[cursor]
                        vertical_gap = selected[0].bbox[1] - previous.bbox[3]
                        if vertical_gap > 24 or len(previous.text) > 120:
                            break
                        selected.insert(0, previous)
                        cursor -= 1
                    bbox = (
                        min(item.bbox[0] for item in selected),
                        min(item.bbox[1] for item in selected),
                        max(item.bbox[2] for item in selected),
                        max(item.bbox[3] for item in selected),
                    )
                    regions.append(
                        EquationRegion(
                            number=number,
                            page=page_number,
                            bbox=bbox,
                            raw_text="\n".join(item.text for item in selected),
                        )
                    )
        deduplicated: dict[tuple[int, int], EquationRegion] = {}
        for region in regions:
            key = (region.page, region.number)
            if key not in deduplicated or len(region.raw_text) > len(deduplicated[key].raw_text):
                deduplicated[key] = region
        return sorted(deduplicated.values(), key=lambda item: (item.page, item.number))

    def render_equation_regions(self, output_dir: str | Path) -> list[EquationRegion]:
        output = Path(output_dir).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
        rendered: list[EquationRegion] = []
        for region in self.equation_regions():
            page = self._document[region.page - 1]
            clip = _pymupdf().Rect(*region.bbox)
            clip.x0 = max(0.0, clip.x0 - 4)
            clip.y0 = max(0.0, clip.y0 - 4)
            clip.x1 = min(page.rect.x1, clip.x1 + 4)
            clip.y1 = min(page.rect.y1, clip.y1 + 4)
            filename = f"page_{region.page:03d}_eq_{region.number:03d}.png"
            pixmap = page.get_pixmap(matrix=_pymupdf().Matrix(4, 4), clip=clip, alpha=False)
            pixmap.save(output / filename)
            rendered.append(
                EquationRegion(
                    number=region.number,
                    page=region.page,
                    bbox=region.bbox,
                    raw_text=region.raw_text,
                    image=filename,
                )
            )
        return rendered

    def validate_evidence(self, refs: Iterable[EvidenceRef]) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        for ref in refs:
            self._check_page(ref.page)
            page = self._document[ref.page - 1]
            page_rect = page.rect
            x0, y0, x1, y1 = ref.bbox
            valid_bbox = 0 <= x0 < x1 <= page_rect.x1 + 1e-6 and 0 <= y0 < y1 <= page_rect.y1 + 1e-6
            quote = normalize_text(ref.quote)
            page_text = normalize_text(page.get_text("text"))
            quote_found = bool(quote) and quote in page_text
            if not quote_found:
                for region in self.equation_regions():
                    if region.page == ref.page and normalize_text(region.raw_text) == quote:
                        quote_found = True
                        break
            passed = ref.artifact_sha256 == self.sha256 and valid_bbox and quote_found
            findings.append(
                {
                    "label": ref.label,
                    "passed": passed,
                    "sha256_match": ref.artifact_sha256 == self.sha256,
                    "bbox_valid": valid_bbox,
                    "quote_found": quote_found,
                    "page": ref.page,
                    "bbox": list(ref.bbox),
                }
            )
        return {"passed": all(item["passed"] for item in findings), "findings": findings}

    @staticmethod
    def _equation_number(text: str) -> int | None:
        value = normalize_text(text)
        match = re.fullmatch(r"[\(\[](\d{1,2})[\)\]]", value)
        return int(match.group(1)) if match else None

    def _check_page(self, page: int) -> None:
        if page < 1 or page > self.page_count:
            raise ContractError(f"PDF page out of range: {page}; page_count={self.page_count}")
