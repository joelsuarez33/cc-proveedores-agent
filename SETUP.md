# Puesta en marcha

## Instalación

Windows (PowerShell):

    py -3.12 -m venv .venv
    .venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install -r requirements.txt

Linux / macOS:

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    pip install -r requirements.txt

Requiere Python 3.10 o superior. Verificar con `python --version`.

## Configuración

    copy .env.example .env      # Windows
    cp .env.example .env        # Linux/macOS

Completar los valores. Ver la tabla de orígenes en el propio `.env.example`.

## Orden de ejecución

1. SQL Editor de Supabase: `01_schema.sql`, después `02_rpc.sql`.
2. `python load_to_supabase.py --src cc_anonimizado.xlsx --sheet Sheet1`
3. SQL Editor: `03_verificacion.sql` (todos los chequeos deben pasar).
4. `python agent.py`

Opcional: `04_keepalive.sql` si el proyecto es plan Free y queda inactivo.

## Eval

    python eval_tool_calls.py                          # proveedor por defecto
    set LLM_PROVIDER=deepseek && python eval_tool_calls.py    # Windows
    LLM_PROVIDER=deepseek python eval_tool_calls.py           # Linux/macOS
