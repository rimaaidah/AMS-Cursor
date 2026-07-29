# AMS-Cursor (Academic Management System)

Sistem Informasi Akademik berbasis **HTML5 + CSS + JavaScript + Python (Flask)** dengan penyimpanan data berbasis **JSON (non-SQL)**.

## Cara menjalankan (Windows)

```bat
cd "%USERPROFILE%\\Downloads\\AMS-Cursor"
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
python seed_demo.py
python app.py
```

Buka di browser:

- `http://127.0.0.1:5000`

## Akun demo (seed)

- **Admin**: `admin` / `admin`
- **Dosen** (opsional via `seed_demo.py`): `dosen1` / `dosen123`
- **Mahasiswa** (opsional via `seed_demo.py`): `mhs1` / `mhs123`

Catatan: admin dapat membuat akun dosen & mahasiswa dari menu Admin.

