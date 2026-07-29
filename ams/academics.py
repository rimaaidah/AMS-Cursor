from __future__ import annotations

from typing import Any


def _ensure_enrollment_schema(enr: dict[str, Any]) -> dict[str, Any]:
    """Ensure enrollment has all required fields for 3-period system."""
    if "nilai_tugas_mandiri" not in enr:
        enr["nilai_tugas_mandiri"] = None
    if "nilai_tugas_terstruktur" not in enr:
        enr["nilai_tugas_terstruktur"] = None
    if "nilai_uts" not in enr:
        enr["nilai_uts"] = None
    if "nilai_uas" not in enr:
        enr["nilai_uas"] = None
    if "komposisi" not in enr:
        enr["komposisi"] = {"tugas_mandiri": 10, "tugas_terstruktur": 20, "uts": 30, "uas": 40}
    return enr


GRADE_POINTS = {
    "A": 4.0,
    "AB": 3.5,
    "B": 3.0,
    "BC": 2.5,
    "C": 2.0,
    "D": 1.0,
    "E": 0.0,
}


def numeric_to_letter(n: int | None) -> str | None:
    if n is None:
        return None
    if n >= 85:
        return "A"
    if n >= 80:
        return "AB"
    if n >= 70:
        return "B"
    if n >= 65:
        return "BC"
    if n >= 55:
        return "C"
    if n >= 45:
        return "D"
    return "E"


def grade_point(letter: str | None) -> float | None:
    if not letter:
        return None
    return GRADE_POINTS.get(letter)


def calc_ips_ipk(
    db: dict[str, Any], *, mahasiswa_id: int
) -> dict[str, Any]:
    """
    Compute IPS (per-term) and cumulative IPK from enrollments.
    We group by (year, term) based on offering's year/term.
    """
    offerings = {o["id"]: o for o in db.get("offering", [])}
    matakuliah = {m["id"]: m for m in db.get("matakuliah", [])}
    enrollments = [_ensure_enrollment_schema(e.copy()) for e in db.get("enrollments", []) if e.get("mahasiswa_id") == mahasiswa_id]

    per: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for e in enrollments:
        off = offerings.get(e.get("offering_id"))
        if not off:
            continue
        key = (off.get("year", "-"), off.get("term", "-"))
        per.setdefault(key, []).append(e)

    def mk_sks(enr: dict[str, Any]) -> int:
        off = offerings.get(enr.get("offering_id")) or {}
        mk = matakuliah.get(off.get("matakuliah_id")) or {}
        return int(mk.get("sks") or 0)

    def enr_points(enr: dict[str, Any]) -> float | None:
        g = enr.get("grade") or {}
        letter = g.get("letter")
        if not letter:
            num = g.get("numeric")
            letter = numeric_to_letter(int(num)) if num is not None else None
        return grade_point(letter)

    ips_list: list[dict[str, Any]] = []
    total_qp = 0.0
    total_sks = 0

    for (year, term), enrs in sorted(per.items()):
        term_qp = 0.0
        term_sks = 0
        for enr in enrs:
            sks = mk_sks(enr)
            gp = enr_points(enr)
            if sks <= 0 or gp is None:
                continue
            term_qp += gp * sks
            term_sks += sks
        ips = (term_qp / term_sks) if term_sks else 0.0
        ips_list.append({"year": year, "term": term, "ips": round(ips, 2), "sks": term_sks})

        total_qp += term_qp
        total_sks += term_sks

    ipk = (total_qp / total_sks) if total_sks else 0.0
    return {"ips": ips_list, "ipk": round(ipk, 2), "total_sks": total_sks}

