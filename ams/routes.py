from __future__ import annotations

import time
from typing import Any

from flask import Flask, flash, redirect, render_template, request, url_for

from .academics import calc_ips_ipk, numeric_to_letter
from .auth import authenticate, change_credentials, current_user, ensure_seed, login_user, logout_user
from .db import load_db, next_id, save_db, update_db
from .decorators import login_required, role_required


def _by_id(items: list[dict[str, Any]], item_id: int) -> dict[str, Any] | None:
    return next((x for x in items if x.get("id") == item_id), None)


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


def register_routes(app: Flask) -> None:
    ensure_seed()

    @app.context_processor
    def inject_globals():
        db = load_db()
        return {
            "me": current_user(),
            "settings": db.get("settings", {}),
        }

    @app.get("/")
    def home():
        if current_user():
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            u = authenticate(
                request.form.get("username", "").strip(),
                request.form.get("password", ""),
            )
            if not u:
                flash("Login gagal. Cek username/password.", "error")
                return render_template("auth/login.html")
            login_user(u)
            return redirect(request.args.get("next") or url_for("dashboard"))
        return render_template("auth/login.html")

    @app.get("/logout")
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        u = current_user() or {}
        role = u.get("role")
        if role == "admin":
            return redirect(url_for("admin_dashboard"))
        if role == "dosen":
            return redirect(url_for("dosen_dashboard"))
        if role == "mahasiswa":
            return redirect(url_for("mahasiswa_dashboard"))
        return redirect(url_for("login"))

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        me = current_user()
        if not me:
            return redirect(url_for("login"))
        if request.method == "POST":
            new_username = request.form.get("username", "").strip()
            new_password = request.form.get("password", "")
            ok, msg = change_credentials(
                me["id"],
                new_username=new_username if new_username and new_username != me.get("username") else None,
                new_password=new_password if new_password else None,
            )
            flash(msg, "success" if ok else "error")
            return redirect(url_for("profile"))
        return render_template("profile.html")

    # ---------------------------
    # Admin
    # ---------------------------
    @app.get("/admin")
    @role_required(["admin"])
    def admin_dashboard():
        db = load_db()
        return render_template(
            "admin/dashboard.html",
            stats={
                "users": len(db.get("users", [])),
                "dosen": len(db.get("dosen", [])),
                "mahasiswa": len(db.get("mahasiswa", [])),
                "matakuliah": len(db.get("matakuliah", [])),
                "offering": len(db.get("offering", [])),
            },
            settings=db.get("settings", {}),
        )

    @app.get("/admin/users")
    @role_required(["admin"])
    def admin_users():
        db = load_db()
        return render_template("admin/users.html", users=db.get("users", []))

    @app.route("/admin/dosen", methods=["GET", "POST"])
    @role_required(["admin"])
    def admin_dosen():
        db = load_db()
        dosen = db.get("dosen", [])
        users = db.get("users", [])

        if request.method == "POST":
            action = request.form.get("action") or "update"
            dosen_id = int(request.form.get("dosen_id") or 0)
            nama = request.form.get("nama", "").strip()
            nidn = request.form.get("nidn", "").strip()
            prodi = request.form.get("prodi", "").strip()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            if not (dosen_id and nama and nidn and username):
                flash("Lengkapi data dosen (nama, NIDN, username).", "error")
                return redirect(url_for("admin_dosen", edit=dosen_id or None))

            def mut(db2: dict[str, Any]):
                dlist = db2.get("dosen", [])
                d = _by_id(dlist, dosen_id)
                if not d:
                    raise ValueError("Dosen tidak ditemukan.")
                d["nama"] = nama
                d["nidn"] = nidn
                d["prodi"] = prodi
                db2["dosen"] = dlist

                ulist = db2.get("users", [])
                u = next((x for x in ulist if x.get("role") == "dosen" and (x.get("ref") or {}).get("id") == dosen_id), None)
                if not u:
                    raise ValueError("User dosen tidak ditemukan.")
                if any(x.get("username") == username and x.get("id") != u.get("id") for x in ulist):
                    raise ValueError("Username sudah dipakai.")
                u["username"] = username
                if password:
                    from werkzeug.security import generate_password_hash

                    u["password_hash"] = generate_password_hash(password)
                u["updated_at"] = int(time.time())
                db2["users"] = ulist

            try:
                update_db(mut)
            except ValueError as e:
                flash(str(e), "error")
                return redirect(url_for("admin_dosen", edit=dosen_id))
            flash("Data dosen diperbarui.", "success")
            return redirect(url_for("admin_dosen"))

        edit = None
        edit_user = None
        edit_id = request.args.get("edit")
        if edit_id:
            try:
                did = int(edit_id)
                edit = _by_id(dosen, did)
                edit_user = next((u for u in users if u.get("role") == "dosen" and (u.get("ref") or {}).get("id") == did), None)
            except ValueError:
                pass

        return render_template("admin/dosen.html", dosen=dosen, users=users, edit=edit, edit_user=edit_user)

    @app.post("/admin/dosen/<int:dosen_id>/delete")
    @role_required(["admin"])
    def admin_dosen_delete(dosen_id: int):
        def mut(db2: dict[str, Any]):
            if any(o.get("dosen_id") == dosen_id for o in db2.get("offering", [])):
                raise ValueError("Tidak bisa hapus: dosen masih menjadi pengampu offering.")
            if any(b.get("dosen_id") == dosen_id for b in db2.get("bimbingan", [])):
                raise ValueError("Tidak bisa hapus: dosen masih punya bimbingan.")

            db2["dosen"] = [d for d in db2.get("dosen", []) if d.get("id") != dosen_id]
            db2["users"] = [u for u in db2.get("users", []) if not (u.get("role") == "dosen" and (u.get("ref") or {}).get("id") == dosen_id)]

        try:
            update_db(mut)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin_dosen"))
        flash("Dosen dihapus.", "success")
        return redirect(url_for("admin_dosen"))

    @app.route("/admin/mahasiswa", methods=["GET", "POST"])
    @role_required(["admin"])
    def admin_mahasiswa():
        db = load_db()
        mahasiswa = db.get("mahasiswa", [])
        jurusan = db.get("jurusan", [])
        dosen = db.get("dosen", [])
        users = db.get("users", [])

        if request.method == "POST":
            mahasiswa_id = int(request.form.get("mahasiswa_id") or 0)
            nama = request.form.get("nama", "").strip()
            nim = request.form.get("nim", "").strip()
            jurusan_id = int(request.form.get("jurusan_id") or 0)
            semester = int(request.form.get("semester") or 1)
            dosen_wali_id = int(request.form.get("dosen_wali_id") or 0)
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            if not (mahasiswa_id and nama and nim and jurusan_id and username):
                flash("Lengkapi data mahasiswa.", "error")
                return redirect(url_for("admin_mahasiswa", edit=mahasiswa_id or None))

            def mut(db2: dict[str, Any]):
                mlist = db2.get("mahasiswa", [])
                m = _by_id(mlist, mahasiswa_id)
                if not m:
                    raise ValueError("Mahasiswa tidak ditemukan.")
                m["nama"] = nama
                m["nim"] = nim
                m["jurusan_id"] = jurusan_id
                m["semester"] = semester
                m["dosen_wali_id"] = dosen_wali_id or None
                db2["mahasiswa"] = mlist

                # sync bimbingan record (simple: ensure one mapping if dosen_wali_id set)
                b = db2.get("bimbingan", [])
                b = [x for x in b if x.get("mahasiswa_id") != mahasiswa_id]
                if dosen_wali_id:
                    b.append({"id": next_id(b), "dosen_id": dosen_wali_id, "mahasiswa_id": mahasiswa_id, "created_at": int(time.time())})
                db2["bimbingan"] = b

                ulist = db2.get("users", [])
                u = next((x for x in ulist if x.get("role") == "mahasiswa" and (x.get("ref") or {}).get("id") == mahasiswa_id), None)
                if not u:
                    raise ValueError("User mahasiswa tidak ditemukan.")
                if any(x.get("username") == username and x.get("id") != u.get("id") for x in ulist):
                    raise ValueError("Username sudah dipakai.")
                u["username"] = username
                if password:
                    from werkzeug.security import generate_password_hash

                    u["password_hash"] = generate_password_hash(password)
                u["updated_at"] = int(time.time())
                db2["users"] = ulist

            try:
                update_db(mut)
            except ValueError as e:
                flash(str(e), "error")
                return redirect(url_for("admin_mahasiswa", edit=mahasiswa_id))
            flash("Data mahasiswa diperbarui.", "success")
            return redirect(url_for("admin_mahasiswa"))

        edit = None
        edit_user = None
        edit_id = request.args.get("edit")
        if edit_id:
            try:
                mid = int(edit_id)
                edit = _by_id(mahasiswa, mid)
                edit_user = next((u for u in users if u.get("role") == "mahasiswa" and (u.get("ref") or {}).get("id") == mid), None)
            except ValueError:
                pass

        return render_template(
            "admin/mahasiswa.html",
            mahasiswa=mahasiswa,
            jurusan=jurusan,
            dosen=dosen,
            edit=edit,
            edit_user=edit_user,
        )

    @app.post("/admin/mahasiswa/<int:mahasiswa_id>/delete")
    @role_required(["admin"])
    def admin_mahasiswa_delete(mahasiswa_id: int):
        def mut(db2: dict[str, Any]):
            if any(e.get("mahasiswa_id") == mahasiswa_id for e in db2.get("enrollments", [])):
                raise ValueError("Tidak bisa hapus: mahasiswa masih punya enrollments.")
            if any(k.get("mahasiswa_id") == mahasiswa_id for k in db2.get("krs", [])):
                raise ValueError("Tidak bisa hapus: mahasiswa masih punya KRS.")
            db2["mahasiswa"] = [m for m in db2.get("mahasiswa", []) if m.get("id") != mahasiswa_id]
            db2["bimbingan"] = [b for b in db2.get("bimbingan", []) if b.get("mahasiswa_id") != mahasiswa_id]
            db2["users"] = [u for u in db2.get("users", []) if not (u.get("role") == "mahasiswa" and (u.get("ref") or {}).get("id") == mahasiswa_id)]

        try:
            update_db(mut)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin_mahasiswa"))
        flash("Mahasiswa dihapus.", "success")
        return redirect(url_for("admin_mahasiswa"))

    @app.route("/admin/jurusan", methods=["GET", "POST"])
    @role_required(["admin"])
    def admin_jurusan():
        if request.method == "POST":
            action = request.form.get("action") or "create"
            kode = request.form.get("kode", "").strip()
            nama = request.form.get("nama", "").strip()
            if not kode or not nama:
                flash("Lengkapi kode & nama jurusan.", "error")
                return redirect(url_for("admin_jurusan"))

            def mut(db: dict[str, Any]):
                items = db.get("jurusan", [])
                if action == "update":
                    jid = int(request.form.get("id") or 0)
                    j = _by_id(items, jid)
                    if not j:
                        raise ValueError("Jurusan tidak ditemukan.")
                    j["kode"] = kode
                    j["nama"] = nama
                else:
                    items.append({"id": next_id(items), "kode": kode, "nama": nama})
                db["jurusan"] = items

            try:
                update_db(mut)
            except ValueError as e:
                flash(str(e), "error")
                return redirect(url_for("admin_jurusan"))
            flash("Jurusan disimpan.", "success")
            return redirect(url_for("admin_jurusan"))

        db = load_db()
        edit_id = request.args.get("edit")
        edit = None
        if edit_id:
            try:
                edit = _by_id(db.get("jurusan", []), int(edit_id))
            except ValueError:
                edit = None
        return render_template("admin/jurusan.html", jurusan=db.get("jurusan", []), edit=edit)

    @app.post("/admin/jurusan/<int:jurusan_id>/delete")
    @role_required(["admin"])
    def admin_jurusan_delete(jurusan_id: int):
        def mut(db2: dict[str, Any]):
            if any(m.get("jurusan_id") == jurusan_id for m in db2.get("mahasiswa", [])):
                raise ValueError("Tidak bisa hapus: jurusan dipakai oleh mahasiswa.")
            if any(mk.get("jurusan_id") == jurusan_id for mk in db2.get("matakuliah", [])):
                raise ValueError("Tidak bisa hapus: jurusan dipakai oleh mata kuliah.")
            db2["jurusan"] = [j for j in db2.get("jurusan", []) if j.get("id") != jurusan_id]

        try:
            update_db(mut)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin_jurusan"))
        flash("Jurusan dihapus.", "success")
        return redirect(url_for("admin_jurusan"))

    @app.route("/admin/create-dosen", methods=["GET", "POST"])
    @role_required(["admin"])
    def admin_create_dosen():
        db = load_db()
        jurusan = db.get("jurusan", [])
        if request.method == "POST":
            nama = request.form.get("nama", "").strip()
            nidn = request.form.get("nidn", "").strip()
            prodi = request.form.get("prodi", "").strip()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip() or "dosen123"
            if not (nama and nidn and username):
                flash("Nama, NIDN, dan username wajib.", "error")
                return redirect(url_for("admin_create_dosen"))

            def mut(db2: dict[str, Any]):
                if any(u.get("username") == username for u in db2.get("users", [])):
                    raise ValueError("Username sudah dipakai.")
                dosen_list = db2.get("dosen", [])
                dosen_id = next_id(dosen_list)
                dosen_list.append(
                    {"id": dosen_id, "nama": nama, "nidn": nidn, "prodi": prodi}
                )
                db2["dosen"] = dosen_list
                users = db2.get("users", [])
                from werkzeug.security import generate_password_hash

                users.append(
                    {
                        "id": next_id(users),
                        "username": username,
                        "password_hash": generate_password_hash(password),
                        "role": "dosen",
                        "ref": {"type": "dosen", "id": dosen_id},
                        "created_at": int(time.time()),
                        "updated_at": int(time.time()),
                    }
                )
                db2["users"] = users

            try:
                update_db(mut)
            except ValueError as e:
                flash(str(e), "error")
                return redirect(url_for("admin_create_dosen"))
            flash("Dosen dibuat. Akun otomatis aktif.", "success")
            return redirect(url_for("admin_users"))

        return render_template("admin/create_dosen.html", jurusan=jurusan)

    @app.route("/admin/create-mahasiswa", methods=["GET", "POST"])
    @role_required(["admin"])
    def admin_create_mahasiswa():
        db = load_db()
        jurusan = db.get("jurusan", [])
        dosen = db.get("dosen", [])
        if request.method == "POST":
            nama = request.form.get("nama", "").strip()
            nim = request.form.get("nim", "").strip()
            jurusan_id = int(request.form.get("jurusan_id") or 0)
            semester = int(request.form.get("semester") or 1)
            dosen_wali_id = int(request.form.get("dosen_wali_id") or 0)
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip() or "mhs123"
            if not (nama and nim and username and jurusan_id):
                flash("Nama, NIM, Jurusan, dan username wajib.", "error")
                return redirect(url_for("admin_create_mahasiswa"))

            def mut(db2: dict[str, Any]):
                if any(u.get("username") == username for u in db2.get("users", [])):
                    raise ValueError("Username sudah dipakai.")
                m_list = db2.get("mahasiswa", [])
                m_id = next_id(m_list)
                m_list.append(
                    {
                        "id": m_id,
                        "nama": nama,
                        "nim": nim,
                        "jurusan_id": jurusan_id,
                        "semester": semester,
                        "dosen_wali_id": dosen_wali_id or None,
                    }
                )
                db2["mahasiswa"] = m_list

                if dosen_wali_id:
                    b = db2.get("bimbingan", [])
                    b.append({"id": next_id(b), "dosen_id": dosen_wali_id, "mahasiswa_id": m_id})
                    db2["bimbingan"] = b

                users = db2.get("users", [])
                from werkzeug.security import generate_password_hash

                users.append(
                    {
                        "id": next_id(users),
                        "username": username,
                        "password_hash": generate_password_hash(password),
                        "role": "mahasiswa",
                        "ref": {"type": "mahasiswa", "id": m_id},
                        "created_at": int(time.time()),
                        "updated_at": int(time.time()),
                    }
                )
                db2["users"] = users

            try:
                update_db(mut)
            except ValueError as e:
                flash(str(e), "error")
                return redirect(url_for("admin_create_mahasiswa"))

            flash("Mahasiswa dibuat. Akun otomatis aktif.", "success")
            return redirect(url_for("admin_users"))

        return render_template(
            "admin/create_mahasiswa.html", jurusan=jurusan, dosen=dosen
        )

    @app.route("/admin/matakuliah", methods=["GET", "POST"])
    @role_required(["admin"])
    def admin_matakuliah():
        db = load_db()
        jurusan = db.get("jurusan", [])
        if request.method == "POST":
            action = request.form.get("action") or "create"
            kode = request.form.get("kode", "").strip()
            nama = request.form.get("nama", "").strip()
            sks = int(request.form.get("sks") or 0)
            jurusan_id = int(request.form.get("jurusan_id") or 0)
            semester_rekom = int(request.form.get("semester_rekom") or 0)
            term = request.form.get("term", "").strip()  # ganjil/genap
            if not (kode and nama and sks and jurusan_id and semester_rekom and term):
                flash("Lengkapi data mata kuliah.", "error")
                return redirect(url_for("admin_matakuliah"))

            def mut(db2: dict[str, Any]):
                items = db2.get("matakuliah", [])
                if action == "update":
                    mid = int(request.form.get("id") or 0)
                    mk0 = _by_id(items, mid)
                    if not mk0:
                        raise ValueError("Mata kuliah tidak ditemukan.")
                    mk0.update(
                        {
                            "kode": kode,
                            "nama": nama,
                            "sks": sks,
                            "jurusan_id": jurusan_id,
                            "semester_rekom": semester_rekom,
                            "term": term,
                        }
                    )
                else:
                    items.append(
                        {
                            "id": next_id(items),
                            "kode": kode,
                            "nama": nama,
                            "sks": sks,
                            "jurusan_id": jurusan_id,
                            "semester_rekom": semester_rekom,
                            "term": term,
                        }
                    )
                db2["matakuliah"] = items

            try:
                update_db(mut)
            except ValueError as e:
                flash(str(e), "error")
                return redirect(url_for("admin_matakuliah"))
            flash("Mata kuliah disimpan.", "success")
            return redirect(url_for("admin_matakuliah"))

        edit_id = request.args.get("edit")
        edit = None
        if edit_id:
            try:
                edit = _by_id(db.get("matakuliah", []), int(edit_id))
            except ValueError:
                edit = None
        return render_template(
            "admin/matakuliah.html",
            jurusan=jurusan,
            matakuliah=db.get("matakuliah", []),
            edit=edit,
        )

    @app.post("/admin/matakuliah/<int:matakuliah_id>/delete")
    @role_required(["admin"])
    def admin_matakuliah_delete(matakuliah_id: int):
        def mut(db2: dict[str, Any]):
            if any(o.get("matakuliah_id") == matakuliah_id for o in db2.get("offering", [])):
                raise ValueError("Tidak bisa hapus: mata kuliah sudah punya offering.")
            db2["matakuliah"] = [m for m in db2.get("matakuliah", []) if m.get("id") != matakuliah_id]

        try:
            update_db(mut)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin_matakuliah"))
        flash("Mata kuliah dihapus.", "success")
        return redirect(url_for("admin_matakuliah"))

    @app.route("/admin/offering", methods=["GET", "POST"])
    @role_required(["admin"])
    def admin_offering():
        db = load_db()
        mk = db.get("matakuliah", [])
        dosen = db.get("dosen", [])
        settings = db.get("settings", {})
        if request.method == "POST":
            matakuliah_id = int(request.form.get("matakuliah_id") or 0)
            dosen_id = int(request.form.get("dosen_id") or 0)
            kelas = request.form.get("kelas", "").strip()
            year = request.form.get("year", "").strip() or settings.get("active_year")
            term = request.form.get("term", "").strip() or settings.get("active_term")
            if not (matakuliah_id and dosen_id and year and term):
                flash("Lengkapi data penawaran MK.", "error")
                return redirect(url_for("admin_offering"))

            def mut(db2: dict[str, Any]):
                items = db2.get("offering", [])
                items.append(
                    {
                        "id": next_id(items),
                        "matakuliah_id": matakuliah_id,
                        "dosen_id": dosen_id,
                        "kelas": kelas or None,
                        "year": year,
                        "term": term,
                        "created_at": int(time.time()),
                    }
                )
                db2["offering"] = items

            update_db(mut)
            flash("Offering dibuat.", "success")
            return redirect(url_for("admin_offering"))

        return render_template(
            "admin/offering.html",
            matakuliah=mk,
            dosen=dosen,
            offering=db.get("offering", []),
        )

    @app.post("/admin/offering/<int:offering_id>/delete")
    @role_required(["admin"])
    def admin_offering_delete(offering_id: int):
        def mut(db2: dict[str, Any]):
            if any(e.get("offering_id") == offering_id for e in db2.get("enrollments", [])):
                raise ValueError("Tidak bisa hapus: offering sudah punya enrollments.")
            db2["offering"] = [o for o in db2.get("offering", []) if o.get("id") != offering_id]

        try:
            update_db(mut)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin_offering"))
        flash("Offering dihapus.", "success")
        return redirect(url_for("admin_offering"))

    @app.post("/admin/offering/<int:offering_id>/update-dosen")
    @role_required(["admin"])
    def admin_offering_update_dosen(offering_id: int):
        dosen_id = int(request.form.get("dosen_id") or 0)
        if not dosen_id:
            flash("Pilih dosen.", "error")
            return redirect(url_for("admin_offering"))

        def mut(db2: dict[str, Any]):
            olist = db2.get("offering", [])
            o = _by_id(olist, offering_id)
            if not o:
                raise ValueError("Offering tidak ditemukan.")
            o["dosen_id"] = dosen_id
            o["updated_at"] = int(time.time())
            db2["offering"] = olist

        try:
            update_db(mut)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin_offering"))
        flash("Dosen pengampu diperbarui.", "success")
        return redirect(url_for("admin_offering"))

    @app.route("/admin/settings", methods=["GET", "POST"])
    @role_required(["admin"])
    def admin_settings():
        if request.method == "POST":
            year = request.form.get("active_year", "").strip()
            term = request.form.get("active_term", "").strip()
            krs_open = request.form.get("krs_open") == "on"
            kuliah_open = request.form.get("kuliah_open") == "on"
            nilai_open = request.form.get("nilai_open") == "on"

            def mut(db2: dict[str, Any]):
                db2["settings"] = {
                    "active_year": year or db2.get("settings", {}).get("active_year", "2025/2026"),
                    "active_term": term or db2.get("settings", {}).get("active_term", "ganjil"),
                    "krs_open": bool(krs_open),
                    "kuliah_open": bool(kuliah_open),
                    "nilai_open": bool(nilai_open),
                }

            update_db(mut)
            flash("Pengaturan disimpan.", "success")
            return redirect(url_for("admin_settings"))

        db = load_db()
        return render_template("admin/settings.html", settings=db.get("settings", {}))

    @app.post("/admin/toggle-krs")
    @role_required(["admin"])
    def admin_toggle_krs():
        def mut(db2: dict[str, Any]):
            s = db2.get("settings", {}) or {}
            s["krs_open"] = not bool(s.get("krs_open"))
            db2["settings"] = s

        db = update_db(mut)
        flash("Periode KRS dibuka." if db.get("settings", {}).get("krs_open") else "Periode KRS ditutup.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/toggle-kuliah")
    @role_required(["admin"])
    def admin_toggle_kuliah():
        def mut(db2: dict[str, Any]):
            s = db2.get("settings", {}) or {}
            s["kuliah_open"] = not bool(s.get("kuliah_open"))
            db2["settings"] = s

        db = update_db(mut)
        flash("Periode Kuliah dibuka." if db.get("settings", {}).get("kuliah_open") else "Periode Kuliah ditutup.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/toggle-nilai")
    @role_required(["admin"])
    def admin_toggle_nilai():
        def mut(db2: dict[str, Any]):
            s = db2.get("settings", {}) or {}
            s["nilai_open"] = not bool(s.get("nilai_open"))
            db2["settings"] = s

        db = update_db(mut)
        flash("Periode Input Nilai dibuka." if db.get("settings", {}).get("nilai_open") else "Periode Input Nilai ditutup.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/bimbingan", methods=["GET", "POST"])
    @role_required(["admin"])
    def admin_bimbingan():
        db = load_db()
        dosen = db.get("dosen", [])
        mahasiswa = db.get("mahasiswa", [])
        bimbingan = db.get("bimbingan", [])

        if request.method == "POST":
            dosen_id = int(request.form.get("dosen_id") or 0)
            mahasiswa_id = int(request.form.get("mahasiswa_id") or 0)
            if not (dosen_id and mahasiswa_id):
                flash("Pilih dosen dan mahasiswa.", "error")
                return redirect(url_for("admin_bimbingan"))

            def mut(db2: dict[str, Any]):
                b2 = db2.get("bimbingan", [])
                if any(
                    x.get("dosen_id") == dosen_id and x.get("mahasiswa_id") == mahasiswa_id
                    for x in b2
                ):
                    raise ValueError("Bimbingan sudah ada.")
                b2.append(
                    {
                        "id": next_id(b2),
                        "dosen_id": dosen_id,
                        "mahasiswa_id": mahasiswa_id,
                        "created_at": int(time.time()),
                    }
                )
                db2["bimbingan"] = b2
                # set dosen wali on mahasiswa
                m_list = db2.get("mahasiswa", [])
                m = _by_id(m_list, mahasiswa_id)
                if m:
                    m["dosen_wali_id"] = dosen_id
                db2["mahasiswa"] = m_list

            try:
                update_db(mut)
            except ValueError as e:
                flash(str(e), "error")
                return redirect(url_for("admin_bimbingan"))
            flash("Bimbingan ditambahkan.", "success")
            return redirect(url_for("admin_bimbingan"))

        return render_template(
            "admin/bimbingan.html",
            dosen=dosen,
            mahasiswa=mahasiswa,
            bimbingan=bimbingan,
            dosen_by_id={d["id"]: d for d in dosen},
            mahasiswa_by_id={m["id"]: m for m in mahasiswa},
        )

    @app.post("/admin/bimbingan/<int:bimbingan_id>/delete")
    @role_required(["admin"])
    def admin_bimbingan_delete(bimbingan_id: int):
        def mut(db2: dict[str, Any]):
            b2 = db2.get("bimbingan", [])
            b = _by_id(b2, bimbingan_id)
            if not b:
                raise ValueError("Bimbingan tidak ditemukan.")
            dosen_id = b.get("dosen_id")
            mahasiswa_id = b.get("mahasiswa_id")
            db2["bimbingan"] = [x for x in b2 if x.get("id") != bimbingan_id]
            # clear dosen_wali_id if it matches and no other wali mapping exists
            if not any(x.get("mahasiswa_id") == mahasiswa_id for x in db2.get("bimbingan", [])):
                m_list = db2.get("mahasiswa", [])
                m = _by_id(m_list, int(mahasiswa_id))
                if m and m.get("dosen_wali_id") == dosen_id:
                    m["dosen_wali_id"] = None
                db2["mahasiswa"] = m_list

        try:
            update_db(mut)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin_bimbingan"))
        flash("Bimbingan dihapus.", "success")
        return redirect(url_for("admin_bimbingan"))

    @app.route("/admin/offering/<int:offering_id>", methods=["GET", "POST"])
    @role_required(["admin"])
    def admin_offering_detail(offering_id: int):
        db = load_db()
        offering = _by_id(db.get("offering", []), offering_id)
        if not offering:
            flash("Offering tidak ditemukan.", "error")
            return redirect(url_for("admin_offering"))

        mk = _by_id(db.get("matakuliah", []), int(offering.get("matakuliah_id")))
        enrollments = [_ensure_enrollment_schema(e.copy()) for e in db.get("enrollments", []) if e.get("offering_id") == offering_id]
        mahasiswa = db.get("mahasiswa", [])
        mahasiswa_by_id = {m["id"]: m for m in mahasiswa}

        if request.method == "POST":
            action = request.form.get("action")
            if action == "add_student":
                mahasiswa_id = int(request.form.get("mahasiswa_id") or 0)
                if not mahasiswa_id:
                    flash("Pilih mahasiswa.", "error")
                    return redirect(url_for("admin_offering_detail", offering_id=offering_id))

                def mut(db2: dict[str, Any]):
                    ens = db2.get("enrollments", [])
                    if any(
                        e.get("offering_id") == offering_id and e.get("mahasiswa_id") == mahasiswa_id
                        for e in ens
                    ):
                        raise ValueError("Mahasiswa sudah terdaftar di offering ini.")
                    ens.append(
                        {
                            "id": next_id(ens),
                            "offering_id": offering_id,
                            "mahasiswa_id": mahasiswa_id,
                            "attendance": [None] * 16,
                            "nilai_tugas_mandiri": None,
                            "nilai_tugas_terstruktur": None,
                            "nilai_uts": None,
                            "nilai_uas": None,
                            "komposisi": {"tugas_mandiri": 10, "tugas_terstruktur": 20, "uts": 30, "uas": 40},
                            "grade": {"numeric": None, "letter": None},
                            "created_at": int(time.time()),
                            "updated_at": int(time.time()),
                            "updated_by": (current_user() or {}).get("id"),
                        }
                    )
                    db2["enrollments"] = ens

                try:
                    update_db(mut)
                except ValueError as e:
                    flash(str(e), "error")
                    return redirect(url_for("admin_offering_detail", offering_id=offering_id))
                flash("Mahasiswa ditambahkan ke kelas.", "success")
                return redirect(url_for("admin_offering_detail", offering_id=offering_id))

            if action == "save_grades":
                admin_id = (current_user() or {}).get("id")

                def mut(db2: dict[str, Any]):
                    ens = db2.get("enrollments", [])
                    for e in ens:
                        if e.get("offering_id") != offering_id:
                            continue
                        mid = e.get("mahasiswa_id")
                        raw = request.form.get(f"numeric_{mid}", "").strip()
                        if raw == "":
                            e["grade"] = {"numeric": None, "letter": None}
                            e["updated_at"] = int(time.time())
                            e["updated_by"] = admin_id
                            continue
                        try:
                            num = int(raw)
                        except ValueError:
                            continue
                        num = max(0, min(100, num))
                        e["grade"] = {"numeric": num, "letter": numeric_to_letter(num)}
                        e["updated_at"] = int(time.time())
                        e["updated_by"] = admin_id
                    db2["enrollments"] = ens

                update_db(mut)
                flash("Nilai tersimpan (oleh admin).", "success")
                return redirect(url_for("admin_offering_detail", offering_id=offering_id))

        return render_template(
            "admin/offering_detail.html",
            offering=offering,
            mk=mk,
            enrollments=enrollments,
            mahasiswa=mahasiswa,
            mahasiswa_by_id=mahasiswa_by_id,
        )

    # ---------------------------
    # Dosen
    # ---------------------------
    @app.get("/dosen")
    @role_required(["dosen"])
    def dosen_dashboard():
        db = load_db()
        me = current_user() or {}
        dosen_id = (me.get("ref") or {}).get("id")
        my_off = [o for o in db.get("offering", []) if o.get("dosen_id") == dosen_id]
        mk_by_id = {m["id"]: m for m in db.get("matakuliah", [])}
        return render_template(
            "dosen/dashboard.html",
            my_offerings=my_off,
            mk_by_id=mk_by_id,
        )

    @app.get("/dosen/matakuliah")
    @role_required(["dosen"])
    def dosen_matakuliah():
        db = load_db()
        me = current_user() or {}
        dosen_id = (me.get("ref") or {}).get("id")
        my_off = [o for o in db.get("offering", []) if o.get("dosen_id") == dosen_id]
        mk_by_id = {m["id"]: m for m in db.get("matakuliah", [])}
        return render_template("dosen/matakuliah.html", offerings=my_off, mk_by_id=mk_by_id)

    @app.route("/dosen/matakuliah/<int:offering_id>", methods=["GET", "POST"])
    @role_required(["dosen"])
    def dosen_mk_detail(offering_id: int):
        db = load_db()
        settings = db.get("settings", {})
        me = current_user() or {}
        dosen_id = (me.get("ref") or {}).get("id")
        offering = _by_id(db.get("offering", []), offering_id)
        if not offering or offering.get("dosen_id") != dosen_id:
            flash("Offering tidak ditemukan.", "error")
            return redirect(url_for("dosen_matakuliah"))

        mk = _by_id(db.get("matakuliah", []), int(offering.get("matakuliah_id")))
        enrollments = [_ensure_enrollment_schema(e.copy()) for e in db.get("enrollments", []) if e.get("offering_id") == offering_id]
        mahasiswa_by_id = {m["id"]: m for m in db.get("mahasiswa", [])}
        selected_meeting = int(request.args.get("meeting") or 1)
        selected_meeting = max(1, min(16, selected_meeting))

        if request.method == "POST":
            action = request.form.get("action")
            if action == "save_attendance":
                if not settings.get("kuliah_open"):
                    flash("Periode Kuliah belum dibuka.", "error")
                    return redirect(url_for("dosen_mk_detail", offering_id=offering_id, meeting=selected_meeting))
                meeting = int(request.form.get("meeting") or 1)
                meeting = max(1, min(16, meeting))
                present_ids = set(int(x) for x in request.form.getlist("present"))

                def mut(db2: dict[str, Any]):
                    ens = db2.get("enrollments", [])
                    for e in ens:
                        if e.get("offering_id") != offering_id:
                            continue
                        att = e.get("attendance") or [None] * 16
                        if len(att) < 16:
                            att = (att + [None] * 16)[:16]
                        att[meeting - 1] = True if e.get("mahasiswa_id") in present_ids else False
                        e["attendance"] = att
                        e["updated_at"] = int(time.time())
                        e["updated_by"] = me.get("id")
                    db2["enrollments"] = ens

                update_db(mut)
                flash("Presensi tersimpan.", "success")
                return redirect(url_for("dosen_mk_detail", offering_id=offering_id, meeting=meeting))

            if action == "save_tugas":
                if not settings.get("kuliah_open"):
                    flash("Periode Kuliah belum dibuka.", "error")
                    return redirect(url_for("dosen_mk_detail", offering_id=offering_id, meeting=selected_meeting))

                def mut(db2: dict[str, Any]):
                    ens = db2.get("enrollments", [])
                    for e in ens:
                        if e.get("offering_id") != offering_id:
                            continue
                        mid = e.get("mahasiswa_id")
                        tm_raw = request.form.get(f"tugas_mandiri_{mid}", "").strip()
                        tt_raw = request.form.get(f"tugas_terstruktur_{mid}", "").strip()
                        try:
                            if tm_raw:
                                e["nilai_tugas_mandiri"] = max(0, min(100, int(tm_raw)))
                            if tt_raw:
                                e["nilai_tugas_terstruktur"] = max(0, min(100, int(tt_raw)))
                            e["updated_at"] = int(time.time())
                            e["updated_by"] = me.get("id")
                        except ValueError:
                            continue
                    db2["enrollments"] = ens

                update_db(mut)
                flash("Nilai tugas tersimpan.", "success")
                return redirect(url_for("dosen_mk_detail", offering_id=offering_id, meeting=selected_meeting))

            if action == "save_uts_uas":
                if not settings.get("nilai_open"):
                    flash("Periode Input Nilai belum dibuka.", "error")
                    return redirect(url_for("dosen_mk_detail", offering_id=offering_id, meeting=selected_meeting))

                def mut(db2: dict[str, Any]):
                    ens = db2.get("enrollments", [])
                    for e in ens:
                        if e.get("offering_id") != offering_id:
                            continue
                        mid = e.get("mahasiswa_id")
                        uts_raw = request.form.get(f"uts_{mid}", "").strip()
                        uas_raw = request.form.get(f"uas_{mid}", "").strip()
                        komp_tm = int(request.form.get(f"komp_tm_{mid}", "10") or 10)
                        komp_tt = int(request.form.get(f"komp_tt_{mid}", "20") or 20)
                        komp_uts = int(request.form.get(f"komp_uts_{mid}", "30") or 30)
                        komp_uas = int(request.form.get(f"komp_uas_{mid}", "40") or 40)

                        try:
                            if uts_raw:
                                e["nilai_uts"] = max(0, min(100, int(uts_raw)))
                            if uas_raw:
                                e["nilai_uas"] = max(0, min(100, int(uas_raw)))

                            e["komposisi"] = {
                                "tugas_mandiri": max(0, min(100, komp_tm)),
                                "tugas_terstruktur": max(0, min(100, komp_tt)),
                                "uts": max(0, min(100, komp_uts)),
                                "uas": max(0, min(100, komp_uas)),
                            }

                            # Calculate final grade
                            tm = e.get("nilai_tugas_mandiri") or 0
                            tt = e.get("nilai_tugas_terstruktur") or 0
                            uts = e.get("nilai_uts") or 0
                            uas = e.get("nilai_uas") or 0
                            komp = e["komposisi"]
                            total = (tm * komp["tugas_mandiri"] + tt * komp["tugas_terstruktur"] + uts * komp["uts"] + uas * komp["uas"]) / 100.0
                            e["grade"] = {"numeric": round(total, 2), "letter": numeric_to_letter(int(round(total)))}
                            e["updated_at"] = int(time.time())
                            e["updated_by"] = me.get("id")
                        except ValueError:
                            continue
                    db2["enrollments"] = ens

                update_db(mut)
                flash("Nilai UTS/UAS tersimpan. Nilai akhir otomatis dihitung.", "success")
                return redirect(url_for("dosen_mk_detail", offering_id=offering_id, meeting=selected_meeting))

        return render_template(
            "dosen/mk_detail.html",
            offering=offering,
            mk=mk,
            enrollments=enrollments,
            mahasiswa_by_id=mahasiswa_by_id,
            selected_meeting=selected_meeting,
            settings=settings,
        )

    @app.get("/dosen/matakuliah/<int:offering_id>/rekap")
    @role_required(["dosen"])
    def dosen_mk_rekap(offering_id: int):
        db = load_db()
        me = current_user() or {}
        dosen_id = (me.get("ref") or {}).get("id")
        offering = _by_id(db.get("offering", []), offering_id)
        if not offering or offering.get("dosen_id") != dosen_id:
            flash("Offering tidak ditemukan.", "error")
            return redirect(url_for("dosen_matakuliah"))

        mk = _by_id(db.get("matakuliah", []), int(offering.get("matakuliah_id")))
        enrollments = [_ensure_enrollment_schema(e.copy()) for e in db.get("enrollments", []) if e.get("offering_id") == offering_id]
        mahasiswa_by_id = {m["id"]: m for m in db.get("mahasiswa", [])}

        rows: list[dict[str, Any]] = []
        meeting_present = [0] * 16
        for e in enrollments:
            att = (e.get("attendance") or [None] * 16)
            if len(att) < 16:
                att = (att + [None] * 16)[:16]
            hadir = sum(1 for x in att if x is True)
            for i, x in enumerate(att[:16]):
                if x is True:
                    meeting_present[i] += 1
            m = mahasiswa_by_id.get(e.get("mahasiswa_id")) or {}
            rows.append(
                {
                    "nama": m.get("nama") or e.get("mahasiswa_id"),
                    "nim": m.get("nim") or "-",
                    "hadir": hadir,
                    "persen": round((hadir / 16.0) * 100.0, 1),
                    "attendance": att[:16],
                }
            )

        return render_template(
            "dosen/mk_rekap.html",
            offering=offering,
            mk=mk,
            rows=rows,
            meeting_present=meeting_present,
            total_students=len(enrollments),
        )

    @app.route("/dosen/bimbingan", methods=["GET", "POST"])
    @role_required(["dosen"])
    def dosen_bimbingan():
        db = load_db()
        settings = db.get("settings", {})
        me = current_user() or {}
        dosen_id = (me.get("ref") or {}).get("id")
        bimbingan = [b for b in db.get("bimbingan", []) if b.get("dosen_id") == dosen_id]
        mahasiswa_by_id = {m["id"]: m for m in db.get("mahasiswa", [])}

        # Get KRS yang masih dalam periode KRS (pending atau approved yang bisa di-cancel)
        all_krs = [
            k
            for k in db.get("krs", [])
            if any(b.get("mahasiswa_id") == k.get("mahasiswa_id") for b in bimbingan)
            and k.get("year") == settings.get("active_year")
            and k.get("term") == settings.get("active_term")
        ]
        pending_krs = [k for k in all_krs if k.get("status") == "pending"]
        approved_krs = [k for k in all_krs if k.get("status") == "approved"]

        if request.method == "POST":
            action = request.form.get("action")
            krs_id = int(request.form.get("krs_id") or 0)

            if not settings.get("krs_open"):
                flash("Periode KRS sudah ditutup.", "error")
                return redirect(url_for("dosen_bimbingan"))

            def mut(db2: dict[str, Any]):
                krs_list = db2.get("krs", [])
                k = _by_id(krs_list, krs_id)
                if not k:
                    raise ValueError("KRS tidak ditemukan.")

                if action == "approve":
                    k["status"] = "approved"
                    k["approved_by"] = me.get("id")
                    k["approved_at"] = int(time.time())

                    # generate enrollments for each offering
                    ens = db2.get("enrollments", [])
                    for off_id in k.get("items", []):
                        if any(
                            e.get("offering_id") == off_id and e.get("mahasiswa_id") == k.get("mahasiswa_id")
                            for e in ens
                        ):
                            continue
                        ens.append(
                            {
                                "id": next_id(ens),
                                "offering_id": off_id,
                                "mahasiswa_id": k.get("mahasiswa_id"),
                                "attendance": [None] * 16,
                                "nilai_tugas_mandiri": None,
                                "nilai_tugas_terstruktur": None,
                                "nilai_uts": None,
                                "nilai_uas": None,
                                "komposisi": {"tugas_mandiri": 10, "tugas_terstruktur": 20, "uts": 30, "uas": 40},
                                "grade": {"numeric": None, "letter": None},
                                "created_at": int(time.time()),
                                "updated_at": int(time.time()),
                                "updated_by": me.get("id"),
                            }
                        )
                    db2["enrollments"] = ens

                elif action == "reject":
                    k["status"] = "rejected"
                    k["approved_by"] = me.get("id")
                    k["approved_at"] = int(time.time())

                elif action == "cancel":
                    if k.get("status") != "approved":
                        raise ValueError("Hanya KRS yang sudah approved bisa dibatalkan.")
                    k["status"] = "pending"
                    k["approved_by"] = None
                    k["approved_at"] = None
                    # Remove enrollments
                    ens = db2.get("enrollments", [])
                    db2["enrollments"] = [
                        e
                        for e in ens
                        if not (
                            e.get("mahasiswa_id") == k.get("mahasiswa_id")
                            and e.get("offering_id") in k.get("items", [])
                        )
                    ]

            try:
                update_db(mut)
            except ValueError as e:
                flash(str(e), "error")
                return redirect(url_for("dosen_bimbingan"))
            flash(f"KRS {'disetujui' if action == 'approve' else 'ditolak' if action == 'reject' else 'dibatalkan'}.", "success")
            return redirect(url_for("dosen_bimbingan"))

        return render_template(
            "dosen/bimbingan.html",
            bimbingan=bimbingan,
            mahasiswa_by_id=mahasiswa_by_id,
            pending_krs=pending_krs,
            approved_krs=approved_krs,
            settings=settings,
        )

    # ---------------------------
    # Mahasiswa
    # ---------------------------
    @app.get("/mahasiswa")
    @role_required(["mahasiswa"])
    def mahasiswa_dashboard():
        db = load_db()
        me = current_user() or {}
        m_id = (me.get("ref") or {}).get("id")
        m = _by_id(db.get("mahasiswa", []), int(m_id))
        summary = calc_ips_ipk(db, mahasiswa_id=int(m_id))
        return render_template("mahasiswa/dashboard.html", mahasiswa=m, summary=summary)

    @app.route("/mahasiswa/krs", methods=["GET", "POST"])
    @role_required(["mahasiswa"])
    def mahasiswa_krs():
        db = load_db()
        settings = db.get("settings", {})
        me = current_user() or {}
        m_id = int((me.get("ref") or {}).get("id"))
        m = _by_id(db.get("mahasiswa", []), m_id) or {}

        # determine available offerings for student's jurusan + term
        mk_by_id = {x["id"]: x for x in db.get("matakuliah", [])}
        offerings = [
            o
            for o in db.get("offering", [])
            if o.get("year") == settings.get("active_year")
            and o.get("term") == settings.get("active_term")
            and (mk_by_id.get(o.get("matakuliah_id"), {}).get("jurusan_id") == m.get("jurusan_id"))
            and (mk_by_id.get(o.get("matakuliah_id"), {}).get("semester_rekom") == m.get("semester"))
            and (mk_by_id.get(o.get("matakuliah_id"), {}).get("term") == settings.get("active_term"))
        ]

        # find current KRS (active period)
        krs_list = [
            k
            for k in db.get("krs", [])
            if k.get("mahasiswa_id") == m_id
            and k.get("year") == settings.get("active_year")
            and k.get("term") == settings.get("active_term")
        ]
        current_krs = krs_list[0] if krs_list else None

        if request.method == "POST":
            if not settings.get("krs_open"):
                flash("Periode KRS sedang ditutup.", "error")
                return redirect(url_for("mahasiswa_krs"))

            chosen = [int(x) for x in request.form.getlist("offering_id")]
            if not chosen:
                flash("Pilih minimal 1 mata kuliah.", "error")
                return redirect(url_for("mahasiswa_krs"))

            allowed_ids = {o["id"] for o in offerings}
            chosen = [x for x in chosen if x in allowed_ids]
            if not chosen:
                flash("Pilihan tidak valid.", "error")
                return redirect(url_for("mahasiswa_krs"))

            def mut(db2: dict[str, Any]):
                krs2 = db2.get("krs", [])
                existing = next(
                    (
                        k
                        for k in krs2
                        if k.get("mahasiswa_id") == m_id
                        and k.get("year") == settings.get("active_year")
                        and k.get("term") == settings.get("active_term")
                    ),
                    None,
                )
                if existing and existing.get("status") == "approved":
                    raise ValueError("KRS sudah disetujui, tidak bisa diubah.")
                if existing:
                    existing["items"] = chosen
                    existing["status"] = "pending"
                    existing["updated_at"] = int(time.time())
                else:
                    krs2.append(
                        {
                            "id": next_id(krs2),
                            "mahasiswa_id": m_id,
                            "year": settings.get("active_year"),
                            "term": settings.get("active_term"),
                            "items": chosen,
                            "status": "pending",
                            "created_at": int(time.time()),
                            "updated_at": int(time.time()),
                            "approved_by": None,
                            "approved_at": None,
                        }
                    )
                db2["krs"] = krs2

            try:
                update_db(mut)
            except ValueError as e:
                flash(str(e), "error")
                return redirect(url_for("mahasiswa_krs"))

            flash("KRS terkirim. Menunggu persetujuan dosen wali.", "success")
            return redirect(url_for("mahasiswa_krs"))

        return render_template(
            "mahasiswa/krs.html",
            mahasiswa=m,
            offerings=offerings,
            mk_by_id=mk_by_id,
            dosen_by_id={d["id"]: d for d in db.get("dosen", [])},
            current_krs=current_krs,
        )

    @app.post("/mahasiswa/krs/cancel")
    @role_required(["mahasiswa"])
    def mahasiswa_krs_cancel():
        db = load_db()
        settings = db.get("settings", {})
        if not settings.get("krs_open"):
            flash("Periode KRS sedang ditutup.", "error")
            return redirect(url_for("mahasiswa_krs"))
        me = current_user() or {}
        m_id = int((me.get("ref") or {}).get("id"))
        year = settings.get("active_year")
        term = settings.get("active_term")

        def mut(db2: dict[str, Any]):
            krs2 = db2.get("krs", [])
            kept = []
            removed = False
            for k in krs2:
                if (
                    k.get("mahasiswa_id") == m_id
                    and k.get("year") == year
                    and k.get("term") == term
                    and k.get("status") != "approved"
                ):
                    removed = True
                    continue
                kept.append(k)
            db2["krs"] = kept
            if not removed:
                raise ValueError("Tidak ada KRS yang bisa dibatalkan.")

        try:
            update_db(mut)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("mahasiswa_krs"))

        flash("KRS dibatalkan.", "success")
        return redirect(url_for("mahasiswa_krs"))

    @app.get("/mahasiswa/nilai")
    @role_required(["mahasiswa"])
    def mahasiswa_nilai():
        db = load_db()
        settings = db.get("settings", {})
        me = current_user() or {}
        m_id = int((me.get("ref") or {}).get("id"))
        ens = [_ensure_enrollment_schema(e.copy()) for e in db.get("enrollments", []) if e.get("mahasiswa_id") == m_id]

        offerings = {o["id"]: o for o in db.get("offering", [])}
        mk = {m["id"]: m for m in db.get("matakuliah", [])}
        dosen = {d["id"]: d for d in db.get("dosen", [])}

        def row(enr: dict[str, Any]) -> dict[str, Any]:
            off = offerings.get(enr.get("offering_id")) or {}
            mk0 = mk.get(off.get("matakuliah_id")) or {}
            d0 = dosen.get(off.get("dosen_id")) or {}
            grade = enr.get("grade") or {}
            num = grade.get("numeric")
            letter = grade.get("letter") or (numeric_to_letter(int(num)) if num is not None else None)
            att = enr.get("attendance") or []
            hadir = len([x for x in att if x is True])
            komp = enr.get("komposisi") or {"tugas_mandiri": 10, "tugas_terstruktur": 20, "uts": 30, "uas": 40}
            return {
                "year": off.get("year"),
                "term": off.get("term"),
                "kode": mk0.get("kode"),
                "nama": mk0.get("nama"),
                "sks": mk0.get("sks"),
                "dosen": d0.get("nama"),
                "nilai": num,
                "huruf": letter,
                "hadir": f"{hadir}/16",
                "nilai_tugas_mandiri": enr.get("nilai_tugas_mandiri"),
                "nilai_tugas_terstruktur": enr.get("nilai_tugas_terstruktur"),
                "nilai_uts": enr.get("nilai_uts"),
                "nilai_uas": enr.get("nilai_uas"),
                "komposisi": komp,
                "attendance": att[:16],
            }

        rows = [row(e) for e in ens]
        return render_template(
            "mahasiswa/nilai.html",
            settings=settings,
            rows=rows,
        )

