import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "db.json"

def migrate():
    if not DB_PATH.exists():
        print("DB not found.")
        return

    data = json.loads(DB_PATH.read_text(encoding="utf-8"))
    
    # 1. Update Offerings (Schedule & Status)
    for o in data.get("offering", []):
        if "day" not in o: o["day"] = "Senin"
        if "start_time" not in o: o["start_time"] = "08:00"
        if "end_time" not in o: o["end_time"] = "10:00"
        if "room" not in o: o["room"] = "R.101"
        if "status" not in o: o["status"] = "active" # Default active for existing
        if "reject_reason" not in o: o["reject_reason"] = None

    # 2. Update Dosen & Mahasiswa (Profile)
    for d in data.get("dosen", []):
        if "email" not in d: d["email"] = ""
        if "phone" not in d: d["phone"] = ""
        if "address" not in d: d["address"] = ""
        if "photo_url" not in d: d["photo_url"] = ""
    
    for m in data.get("mahasiswa", []):
        if "email" not in m: m["email"] = ""
        if "phone" not in m: m["phone"] = ""
        if "address" not in m: m["address"] = ""
        if "photo_url" not in m: m["photo_url"] = ""

    # 3. Add Assessments tables if not exist
    if "assessments" not in data:
        data["assessments"] = []
    
    if "assessment_grades" not in data:
        data["assessment_grades"] = []

    # Backup
    backup_path = str(DB_PATH) + ".bak"
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(DB_PATH.read_text(encoding="utf-8"))
    
    # Save
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
