import time
from pathlib import Path

from werkzeug.security import generate_password_hash

from ams.db import load_db, next_id, save_db


def ensure_user(db, *, username: str, password: str, role: str, ref: dict):
    users = db.get("users", [])
    u = next((x for x in users if x.get("username") == username), None)
    if u:
        return u
    users.append(
        {
            "id": next_id(users),
            "username": username,
            "password_hash": generate_password_hash(password),
            "role": role,
            "ref": ref,
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
        }
    )
    db["users"] = users
    return users[-1]


def main():
    base_dir = Path(__file__).resolve().parent
    print("Seeding demo data into:", base_dir / "data" / "db.json")

    db = load_db()
    db.setdefault("settings", {})
    db["settings"]["active_year"] = db["settings"].get("active_year") or "2025/2026"
    db["settings"]["active_term"] = db["settings"].get("active_term") or "ganjil"
    db["settings"]["krs_open"] = True

    # Jurusan
    jur = db.get("jurusan", [])
    bca = next((j for j in jur if j.get("kode") == "BCA"), None)
    if not bca:
        bca = {"id": next_id(jur), "kode": "BCA", "nama": "Bachelor of Computer Applications"}
        jur.append(bca)
        db["jurusan"] = jur

    # Dosen
    dosen = db.get("dosen", [])
    d1 = next((d for d in dosen if d.get("nidn") == "D-0001"), None)
    if not d1:
        d1 = {"id": next_id(dosen), "nama": "Dosen Demo", "nidn": "D-0001", "prodi": "BCA"}
        dosen.append(d1)
        db["dosen"] = dosen
    ensure_user(db, username="dosen1", password="dosen123", role="dosen", ref={"type": "dosen", "id": d1["id"]})

    # Mahasiswa
    mhs = db.get("mahasiswa", [])
    m1 = next((m for m in mhs if m.get("nim") == "301240053"), None)
    if not m1:
        m1 = {
            "id": next_id(mhs),
            "nama": "Mahasiswa Demo",
            "nim": "301240053",
            "jurusan_id": bca["id"],
            "semester": 3,
            "dosen_wali_id": d1["id"],
        }
        mhs.append(m1)
        db["mahasiswa"] = mhs
    ensure_user(db, username="mhs1", password="mhs123", role="mahasiswa", ref={"type": "mahasiswa", "id": m1["id"]})

    # Bimbingan
    b = db.get("bimbingan", [])
    if not any(x.get("dosen_id") == d1["id"] and x.get("mahasiswa_id") == m1["id"] for x in b):
        b.append({"id": next_id(b), "dosen_id": d1["id"], "mahasiswa_id": m1["id"], "created_at": int(time.time())})
        db["bimbingan"] = b

    # Mata Kuliah (semester 3 ganjil)
    mk = db.get("matakuliah", [])
    def ensure_mk(kode, nama, sks, term):
        m = next((x for x in mk if x.get("kode") == kode), None)
        if m:
            return m
        m = {
            "id": next_id(mk),
            "kode": kode,
            "nama": nama,
            "sks": sks,
            "jurusan_id": bca["id"],
            "semester_rekom": 3,
            "term": term,
        }
        mk.append(m)
        return m

    mk1 = ensure_mk("STAT101", "Statistical Methods", 3, "ganjil")
    mk2 = ensure_mk("SE201", "Software Engineering", 3, "ganjil")
    mk3 = ensure_mk("PKN101", "Pendidikan Kewarganegaraan", 2, "genap")
    db["matakuliah"] = mk

    # Offering (active term)
    off = db.get("offering", [])
    def ensure_off(matakuliah_id, year, term):
        o = next((x for x in off if x.get("matakuliah_id")==matakuliah_id and x.get("year")==year and x.get("term")==term), None)
        if o:
            return o
        o = {"id": next_id(off), "matakuliah_id": matakuliah_id, "dosen_id": d1["id"], "year": year, "term": term, "created_at": int(time.time())}
        off.append(o)
        return o

    active_year = db["settings"]["active_year"]
    active_term = db["settings"]["active_term"]
    o1 = ensure_off(mk1["id"], active_year, active_term)
    o2 = ensure_off(mk2["id"], active_year, active_term)
    # previous term (to show IPS/IPK)
    o_prev = ensure_off(mk3["id"], "2024/2025", "genap")
    db["offering"] = off

    # KRS pending for active period
    krs = db.get("krs", [])
    k_active = next((k for k in krs if k.get("mahasiswa_id")==m1["id"] and k.get("year")==active_year and k.get("term")==active_term), None)
    if not k_active:
        krs.append({
            "id": next_id(krs),
            "mahasiswa_id": m1["id"],
            "year": active_year,
            "term": active_term,
            "items": [o1["id"], o2["id"]],
            "status": "pending",
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
            "approved_by": None,
            "approved_at": None,
        })
        db["krs"] = krs

    # Enrollment + grade for previous term (to show IPS/IPK)
    ens = db.get("enrollments", [])
    if not any(e.get("offering_id")==o_prev["id"] and e.get("mahasiswa_id")==m1["id"] for e in ens):
        att = [True]*12 + [False]*4
        ens.append({
            "id": next_id(ens),
            "offering_id": o_prev["id"],
            "mahasiswa_id": m1["id"],
            "attendance": att,
            "grade": {"numeric": 86, "letter": "A"},
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
            "updated_by": 1,
        })
        db["enrollments"] = ens

    save_db(db)
    print("Done.")
    print("\nAkun demo tambahan:")
    print("- Dosen : dosen1 / dosen123")
    print("- Mhs   : mhs1 / mhs123")
    print("\nCatatan: KRS mahasiswa demo masih 'pending'—login dosen1 lalu approve di menu Bimbingan & KRS.")


if __name__ == "__main__":
    main()

