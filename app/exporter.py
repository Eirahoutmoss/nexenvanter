"""Excel dışa aktarma (filtreli liste, boş şablon, içe aktarma raporu)."""
import io

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import assets as A, fields as F

_HFILL = PatternFill("solid", fgColor="0B1F4D")
_HFONT = Font(bold=True, color="FFFFFF")


def _book(headers: list[str], rows, widths=None) -> bytes:
    wb = openpyxl.Workbook(write_only=False)
    ws = wb.active
    ws.title = "Envanter"
    ws.append(headers)
    for i, _ in enumerate(headers, 1):
        c = ws.cell(row=1, column=i)
        c.fill, c.font = _HFILL, _HFONT
        c.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(i, 20)
    for r in rows:
        ws.append(r)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def export_assets(**query) -> bytes:
    flds = F.all_fields()
    headers = [f["label"] for f in flds] + ["Arşivde", "Oluşturma", "Güncelleme", "QR Kimliği"]
    query.update(page=1, size=1000)

    def gen():
        page = 1
        while True:
            res = A.query(**{**query, "page": page})
            for a in res["items"]:
                vals = []
                for f in flds:
                    v = a.get(f["key"]) if f["system"] else a["data"].get(f["key"])
                    vals.append(v)  # metin olarak yazılır: baştaki sıfırlar korunur
                yield vals + ["Evet" if a["archived"] else "", a["created_at"], a["updated_at"], a["public_id"]]
            if page * res["size"] >= res["total"]:
                break
            page += 1
    return _book(headers, gen())


def template() -> bytes:
    return _book([f["label"] for f in F.all_fields()], [])


def report(rows: list[dict]) -> bytes:
    return _book(["Satır", "Barkod", "Sonuç", "Mesaj"],
                 ([r["row"], r["asset_code"], r["result"], r["message"]] for r in rows), {4: 60})
