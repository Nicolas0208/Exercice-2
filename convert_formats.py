import os
import pandas as pd

FOLDER = r"C:\Ex2\outputs\etape1_extraction"

files = os.listdir(FOLDER)
xlsx_years = {f.replace("openalex_", "").replace(".xlsx", "") for f in files if f.endswith(".xlsx")}
csv_years  = {f.replace("openalex_", "").replace(".csv",  "") for f in files if f.endswith(".csv")}

# XLSX → CSV
for year in sorted(xlsx_years - csv_years):
    src = os.path.join(FOLDER, f"openalex_{year}.xlsx")
    dst = os.path.join(FOLDER, f"openalex_{year}.csv")
    print(f"[XLSX->CSV] {year}...")
    df = pd.read_excel(src)
    df.to_csv(dst, index=False, encoding="utf-8-sig")
    print(f"  Créé : {dst}")

# CSV → XLSX
for year in sorted(csv_years - xlsx_years):
    src = os.path.join(FOLDER, f"openalex_{year}.csv")
    dst = os.path.join(FOLDER, f"openalex_{year}.xlsx")
    print(f"[CSV->XLSX] {year}...")
    df = pd.read_csv(src, encoding="utf-8-sig", low_memory=False)
    df.to_excel(dst, index=False)
    print(f"  Créé : {dst}")

# Vérification finale
print("\n=== Vérification ===")
files_after = os.listdir(FOLDER)
xlsx_after = {f.replace("openalex_", "").replace(".xlsx", "") for f in files_after if f.endswith(".xlsx")}
csv_after  = {f.replace("openalex_", "").replace(".csv",  "") for f in files_after if f.endswith(".csv")}
all_years  = xlsx_after | csv_after

for year in sorted(all_years):
    has_xlsx = year in xlsx_after
    has_csv  = year in csv_after
    status   = "OK" if has_xlsx and has_csv else "MANQUANT"
    print(f"  {year} : xlsx={'oui' if has_xlsx else 'non'}  csv={'oui' if has_csv else 'non'}  [{status}]")
