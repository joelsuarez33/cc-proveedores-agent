"""Excel -> Postgres/Supabase via COPY. Se corre en cada refresh, no en runtime.

Uso:
    python load_to_supabase.py --src cc_anonimizado.xlsx --sheet Sheet1
Requiere SUPABASE_DB_URL en el .env (Connection string > Session pooler del dashboard).
"""
import argparse
import io
import os
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv

load_dotenv()

COLUMN_MAP = {
    "Acreedor": "proveedor_id",
    "Clave de referencia": "clave_referencia",
    "Referencia": "referencia",
    "Nº documento": "documento",
    "Clave referencia 1": "clave_referencia_1",
    "Vía de pago": "via_pago",
    "Bloqueo de pago": "bloqueo_pago",
    "Demora tras vencimiento neto": "dias_vencida",
    "Importe en moneda doc.": "importe_documento",
    "Moneda del documento": "moneda_documento",
    "Importe en moneda local": "importe_local",
    "Moneda local": "moneda_local",
    "Fecha de documento": "fecha_documento",
    "Fe.contabilización": "fecha_contabilizacion",
    "Vencimiento neto": "fecha_vencimiento",
    "Fecha compensación": "fecha_compensacion",
    "Doc.compensación": "documento_compensacion",
    "Clase de documento": "clase_documento",
    "Cta.contrapartida": "cuenta_contrapartida",
}
# "Nombre del usuario" queda deliberadamente fuera: es el operador SAP, no aporta.

REQUIRED = {
    "Acreedor", "Nº documento", "Importe en moneda doc.", "Moneda del documento",
    "Importe en moneda local", "Moneda local", "Vencimiento neto", "Fecha compensación",
}
DATE_COLS = ["fecha_documento", "fecha_contabilizacion", "fecha_vencimiento", "fecha_compensacion"]
NUM_COLS = ["importe_documento", "importe_local"]
# Columnas que son códigos, no números. Excel las trae como float y quedan
# con ".0" pegado ("9975101.0"). Van forzadas a texto y limpiadas.
TEXT_COLS = [
    "documento", "documento_compensacion", "clave_referencia",
    "clave_referencia_1", "cuenta_contrapartida", "referencia",
]

# Se leen como string desde el arranque: un código de 14+ dígitos leído como
# float64 pierde precisión antes de que lleguemos a limpiarlo.
DTYPE_TEXTO = {
    "Acreedor": "string",
    "Nº documento": "string",
    "Doc.compensación": "string",
    "Clave de referencia": "string",
    "Clave referencia 1": "string",
    "Cta.contrapartida": "string",
    "Referencia": "string",
}


def clean_export_artifacts(df: pd.DataFrame) -> pd.DataFrame:
    """Los ALV de SAP no salen tabulares.

    Dos artefactos distintos producen `proveedor_id` vacío y hay que tratarlos
    al revés uno del otro:

    1. Fila de subtotal / total: sin acreedor, sin documento, sin fechas, pero
       con importe. Es la suma del grupo anterior. Cargarla duplica el saldo.
    2. Repetición suprimida: cuando el layout agrupa por acreedor, SAP imprime
       el número solo en la primera fila del grupo. Las siguientes son partidas
       reales y hay que propagarles el acreedor, no descartarlas.

    Se distinguen por si la fila tiene datos de documento.
    """
    vacio = df["proveedor_id"].isna()
    if not vacio.any():
        return df

    tiene_documento = pd.Series(False, index=df.index)
    for col in ("documento", "fecha_documento", "fecha_vencimiento", "referencia"):
        if col in df.columns:
            tiene_documento |= df[col].notna()

    a_rellenar = vacio & tiene_documento
    if a_rellenar.any():
        # Solo sobre las filas que califican. Un ffill sobre la columna entera
        # también le pega el acreedor anterior a las filas de subtotal, que
        # entonces sobreviven al descarte y duplican el saldo del grupo.
        relleno = df["proveedor_id"].ffill()
        df.loc[a_rellenar, "proveedor_id"] = relleno.loc[a_rellenar]
        print(f"  {int(a_rellenar.sum())} filas con acreedor suprimido -> propagado")

    sobrantes = df["proveedor_id"].isna()
    if sobrantes.any():
        importe = pd.to_numeric(df.loc[sobrantes, "importe_local"], errors="coerce")
        print(
            f"  {int(sobrantes.sum())} filas de subtotal/total descartadas "
            f"(suman {importe.sum():,.2f} en moneda local)"
        )
        df = df.loc[~sobrantes].copy()

    return df


def build_frame(src: Path, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(
        src,
        sheet_name=sheet,
        dtype=DTYPE_TEXTO,
    )
    df.columns = df.columns.astype(str).str.strip()

    missing = REQUIRED - set(df.columns)
    if missing:
        raise SystemExit(f"Faltan columnas en el Excel: {sorted(missing)}")

    available = {s: t for s, t in COLUMN_MAP.items() if s in df.columns}
    df = df[list(available)].rename(columns=available)

    # Normalizar SIN zfill todavía: zfill sobre vacío produce '0000000000',
    # un acreedor fantasma.
    df["proveedor_id"] = (
        df["proveedor_id"].astype("string").str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .replace("", pd.NA)
    )

    df = clean_export_artifacts(df)
    df["proveedor_id"] = df["proveedor_id"].str.zfill(10)

    for col in TEXT_COLS:
        if col in df.columns:
            df[col] = (
                df[col].astype("string").str.strip()
                .str.replace(r"\.0$", "", regex=True)
            )
    for col in NUM_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").round(2)
    if "dias_vencida" in df.columns:
        df["dias_vencida"] = pd.to_numeric(df["dias_vencida"], errors="coerce").astype("Int64")
    for col in DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    # Control de carga: comparar contra la fila de total del Excel.
    print(f"  {len(df)} partidas, {df['proveedor_id'].nunique()} acreedores")
    for moneda, grupo in df.dropna(subset=["moneda_local"]).groupby("moneda_local"):
        print(f"  total {moneda}: {grupo['importe_local'].sum():,.2f}")

    if df["proveedor_id"].isna().any():
        raise SystemExit("Quedaron filas sin acreedor. Revisar el layout del Excel.")

    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, type=Path)
    ap.add_argument("--sheet", default="Sheet1")
    ap.add_argument("--table", default="cc.partidas",
                    help="Tabla destino. Debe existir (correr 01_schema.sql primero).")
    ap.add_argument("--truncate", action="store_true", default=True,
                    help="Full refresh: vacía la tabla antes de cargar.")
    args = ap.parse_args()

    dsn = os.environ["SUPABASE_DB_URL"]
    df = build_frame(args.src, args.sheet)
    cols = list(df.columns)

    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="")
    buf.seek(0)

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        # Falla ruidosamente si la tabla no existe, en vez de crear una con
        # tipos inferidos encima de un proyecto que ya tiene cosas adentro.
        cur.execute("select to_regclass(%s);", (args.table,))
        if cur.fetchone()[0] is None:
            raise SystemExit(f"La tabla {args.table} no existe. Corré 01_schema.sql primero.")

        if args.truncate:
            cur.execute(f"truncate table {args.table} restart identity;")
        copy_sql = (
            f"copy {args.table} ({', '.join(cols)}) "
            "from stdin with (format csv, null '')"
        )
        with cur.copy(copy_sql) as cp:
            cp.write(buf.read())
        conn.commit()
        cur.execute(f"select count(*) from {args.table};")
        print(f"{cur.fetchone()[0]} filas en {args.table}")


if __name__ == "__main__":
    main()