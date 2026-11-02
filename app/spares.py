"""Yedek cihaz havuzu: arızalanan cihaz yerine verilen yedeğin takibi.
'yedek' durumundaki cihazlar havuzdur; verilince ödünç kaydı açılır, geri gelince kapanır."""
import json

from . import assets as A, db
from .textnorm import fold

SPARE_STATUS = "yedek"


def pool(locations=None) -> dict:
    c = db.conn()
    # Havuzdaki (yedek durumunda, sahada olmayan) cihazlar
    avail = [A.get(r[0]) for r in c.execute(
        "SELECT id FROM assets WHERE archived=0 AND status=? AND id NOT IN "
        "(SELECT asset_id FROM spare_loans WHERE back_at IS NULL)", (SPARE_STATUS,))]
    # Sahada dönen yedekler
    out_rows = c.execute(
        "SELECT l.*, a.asset_code, json_extract(a.data,'$.brand_model') brand_model, "
        "ra.asset_code replacing_code FROM spare_loans l JOIN assets a ON a.id=l.asset_id "
        "LEFT JOIN assets ra ON ra.id=l.replacing_asset_id WHERE l.back_at IS NULL ORDER BY l.out_at DESC")
    on_loan = [dict(r) for r in out_rows]
    if locations is not None:
        ls = {fold(x) for x in locations}
        on_loan = [x for x in on_loan if fold(x.get("to_unit") or "") in ls]
    return {"available": avail, "on_loan": on_loan,
            "available_count": len(avail), "on_loan_count": len(on_loan)}


def mark_spare(asset_ids, user):
    for aid in asset_ids:
        A.update(aid, {"status": SPARE_STATUS}, user, action="yedek")
    return {"ok": True}


def give(asset_id, user, to_unit=None, to_person=None, replacing_asset_id=None, ticket_id=None, note=None) -> dict:
    c = db.conn()
    a = A.get(asset_id)
    if not a:
        raise ValueError("Yedek cihaz bulunamadı")
    if c.execute("SELECT 1 FROM spare_loans WHERE asset_id=? AND back_at IS NULL", (asset_id,)).fetchone():
        raise ValueError("Bu yedek zaten sahada")
    lid = c.execute("INSERT INTO spare_loans(asset_id,out_at,out_by,to_unit,to_person,replacing_asset_id,ticket_id,note)"
                    " VALUES(?,?,?,?,?,?,?,?)", (asset_id, db.now(), user, to_unit, to_person, replacing_asset_id,
                                                 ticket_id, note)).lastrowid
    A.update(asset_id, {"status": "aktif", "location_name": to_unit} if to_unit else {"status": "aktif"}, user, action="yedek_verildi")
    A.add_event(asset_id, user, "yedek_verildi", f"{to_unit or ''} {to_person or ''}".strip() +
                (f" — yerine: {A.get(replacing_asset_id)['asset_code']}" if replacing_asset_id else ""))
    if replacing_asset_id:
        A.add_event(replacing_asset_id, user, "yedek_takildi", f"Yerine {a['asset_code']} verildi")
    return {"loan_id": lid}


def take_back(asset_id, user, note=None) -> dict:
    c = db.conn()
    r = c.execute("SELECT id FROM spare_loans WHERE asset_id=? AND back_at IS NULL ORDER BY id DESC LIMIT 1", (asset_id,)).fetchone()
    if not r:
        raise ValueError("Bu cihaz için açık yedek kaydı yok")
    c.execute("UPDATE spare_loans SET back_at=?, back_by=?, note=COALESCE(note,'')||? WHERE id=?",
              (db.now(), user, f"\niade: {note}" if note else "", r[0]))
    A.update(asset_id, {"status": SPARE_STATUS}, user, action="yedek_iade")
    A.add_event(asset_id, user, "yedek_iade", "Havuza döndü")
    return {"ok": True}


def history(asset_id):
    return [dict(r) for r in db.conn().execute(
        "SELECT l.*, ra.asset_code replacing_code FROM spare_loans l LEFT JOIN assets ra ON ra.id=l.replacing_asset_id "
        "WHERE l.asset_id=? ORDER BY l.id DESC", (asset_id,))]
