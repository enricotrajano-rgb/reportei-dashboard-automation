import argparse
import csv
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from main import ReporteiClient


SCRIPT_DIR = Path(__file__).resolve().parent

DEFAULT_START_DATE = "01/08/2026"
DEFAULT_END_DATE = "05/08/2026"
DEFAULT_PERIOD = ""
DEFAULT_PROJECT_NAMES = ""
DEFAULT_EXCLUDE_PROJECTS = ""
DEFAULT_NETWORKS = "facebook,instagram_business"
DEFAULT_OUTPUT = str(Path.home() / "Downloads" / "reportei_top_posts.csv")
DEFAULT_SAVE_CSV = False
DEFAULT_GOOGLE_SPREADSHEET_ID = "11hFk76IZe1AnCD3lsq6N95hclSZjIdgrkbmI0GWVCrI"
DEFAULT_GOOGLE_WORKSHEET_NAME = "Top Posts"
DEFAULT_GOOGLE_SERVICE_ACCOUNT_FILE = r"c:\Users\Enrico.Trajano\Downloads\clear-rock-498913-e3-70c12ea73e76.json"
DEFAULT_CACHE_DIR = ".reportei_cache"
DEFAULT_CACHE_TTL_HOURS = 24
DEFAULT_TOP_PER_PRODUCT_NETWORK = 5

RETRY_ATTEMPTS = 4
RETRY_DELAY_SECONDS = 3
RATE_LIMIT_DELAY_SECONDS = 20
GOOGLE_WRITE_RETRY_ATTEMPTS = 4
GOOGLE_WRITE_RETRY_DELAY_SECONDS = 5
GOOGLE_SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

OUTPUT_FIELDNAMES = [
    "Data",
    "Produto",
    "Rede",
    "Link",
    "Visualizacoes",
    "Engajamento",
]

NETWORKS = {
    "facebook": "Facebook",
    "instagram_business": "Instagram",
}

NETWORK_ORDER = [
    "facebook",
    "instagram_business",
]

# Facebook: a tabela de posts do Reportei chama total_reach de "Visualizadores".
# Usamos fb:page_posts porque ela traz fotos e reels com link na mesma base.
POST_TABLES = {
    "facebook": [
        {
            "reference_key": "fb:page_posts",
            "visualizacoes": "total_reach",
            "engajamento_sum": ["total_reactions", "comments", "shares"],
            "data": "created_at",
        },
    ],
    "instagram_business": [
        {
            "reference_key": "ig:media_datatable",
            "visualizacoes": "views",
            "engajamento": "total_interactions",
            "data": "created_at",
        },
        {
            "reference_key": "ig:reels_datatable",
            "visualizacoes": "views",
            "engajamento": "total_interactions",
            "data": "created_at",
        },
    ],
}


def build_parser():
    parser = argparse.ArgumentParser(
        description="Gera uma base simples de top posts para Looker Studio."
    )
    parser.add_argument(
        "--start",
        default=os.getenv("REPORTEI_TOP_POSTS_START", DEFAULT_START_DATE),
        help="DD/MM/YYYY ou YYYY-MM-DD",
    )
    parser.add_argument(
        "--end",
        default=os.getenv("REPORTEI_TOP_POSTS_END", DEFAULT_END_DATE),
        help="DD/MM/YYYY ou YYYY-MM-DD",
    )
    parser.add_argument(
        "--period",
        default=os.getenv("REPORTEI_TOP_POSTS_PERIOD", DEFAULT_PERIOD),
        choices=["", "current_month_until_yesterday", "previous_month", "last_7_days", "last_30_days"],
        help="Periodo automatico. Se informado, ignora --start/--end.",
    )
    parser.add_argument(
        "--project-names",
        default=os.getenv("REPORTEI_TOP_POSTS_PROJECT_NAMES", DEFAULT_PROJECT_NAMES),
        help="Lista de produtos separada por virgula. Vazio = todos.",
    )
    parser.add_argument(
        "--exclude-projects",
        default=os.getenv("REPORTEI_TOP_POSTS_EXCLUDE_PROJECTS", DEFAULT_EXCLUDE_PROJECTS),
        help="Lista de produtos a ignorar, separada por virgula.",
    )
    parser.add_argument(
        "--networks",
        default=os.getenv("REPORTEI_TOP_POSTS_NETWORKS", DEFAULT_NETWORKS),
        help="Slugs separados por virgula.",
    )
    parser.add_argument(
        "--top-per-product-network",
        type=int,
        default=int(os.getenv("REPORTEI_TOP_POSTS_PER_PRODUCT_NETWORK", DEFAULT_TOP_PER_PRODUCT_NETWORK)),
        help="Quantidade maxima de posts por combinacao Produto + Rede. 0 = sem limite.",
    )
    parser.add_argument(
        "--output",
        default=os.getenv("REPORTEI_TOP_POSTS_OUTPUT", DEFAULT_OUTPUT),
        help="Caminho do CSV.",
    )
    parser.add_argument(
        "--save-csv",
        action=argparse.BooleanOptionalAction,
        default=os.getenv("REPORTEI_TOP_POSTS_SAVE_CSV", str(DEFAULT_SAVE_CSV)).lower() == "true",
        help="Tambem salva CSV local.",
    )
    parser.add_argument(
        "--spreadsheet-id",
        default=os.getenv("GOOGLE_SPREADSHEET_ID", DEFAULT_GOOGLE_SPREADSHEET_ID),
        help="ID da Google Sheet.",
    )
    parser.add_argument(
        "--worksheet-name",
        default=os.getenv("REPORTEI_TOP_POSTS_WORKSHEET_NAME", os.getenv("GOOGLE_TOP_POSTS_WORKSHEET_NAME", DEFAULT_GOOGLE_WORKSHEET_NAME)),
        help="Nome da aba de destino.",
    )
    parser.add_argument(
        "--service-account-file",
        default=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", DEFAULT_GOOGLE_SERVICE_ACCOUNT_FILE),
        help="Arquivo JSON da service account.",
    )
    parser.add_argument(
        "--no-google",
        action="store_true",
        help="Nao atualiza Google Sheets.",
    )
    parser.add_argument(
        "--cache-dir",
        default=os.getenv("REPORTEI_CACHE_DIR", DEFAULT_CACHE_DIR),
        help="Pasta de cache.",
    )
    parser.add_argument(
        "--cache-ttl-hours",
        type=int,
        default=int(os.getenv("REPORTEI_CACHE_TTL_HOURS", DEFAULT_CACHE_TTL_HOURS)),
        help="Validade do cache em horas.",
    )
    parser.add_argument(
        "--use-cache",
        action=argparse.BooleanOptionalAction,
        default=os.getenv("REPORTEI_USE_CACHE", "true").lower() != "false",
        help="Usa cache persistente para projetos, integracoes e catalogo de metricas.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignora cache existente e regrava com dados novos.",
    )
    return parser


def normalize_date(date_text):
    for date_format in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_text, date_format).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f'Data invalida "{date_text}". Use DD/MM/YYYY ou YYYY-MM-DD.')


def resolve_period_dates(period, start_text, end_text, today=None):
    today = today or datetime.now()
    yesterday = today - timedelta(days=1)
    if not period:
        return normalize_date(start_text), normalize_date(end_text)
    if period == "current_month_until_yesterday":
        start = yesterday.replace(day=1)
        return start.strftime("%Y-%m-%d"), yesterday.strftime("%Y-%m-%d")
    if period == "previous_month":
        first_this_month = today.replace(day=1)
        end = first_this_month - timedelta(days=1)
        start = end.replace(day=1)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    if period == "last_7_days":
        start = yesterday - timedelta(days=6)
        return start.strftime("%Y-%m-%d"), yesterday.strftime("%Y-%m-%d")
    if period == "last_30_days":
        start = yesterday - timedelta(days=29)
        return start.strftime("%Y-%m-%d"), yesterday.strftime("%Y-%m-%d")
    raise ValueError(f"Periodo invalido: {period}")


def parse_csv_values(raw_value):
    return [item.strip() for item in str(raw_value or "").split(",") if item.strip()]


def ordered_networks(networks_csv):
    requested = parse_csv_values(networks_csv) or list(NETWORK_ORDER)
    ordered = [slug for slug in NETWORK_ORDER if slug in requested]
    ordered.extend(slug for slug in requested if slug not in ordered)
    return ordered


def make_cache_config(args):
    return {
        "enabled": args.use_cache,
        "refresh": args.refresh_cache,
        "ttl_seconds": max(args.cache_ttl_hours, 0) * 3600,
        "dir": Path(args.cache_dir),
    }


def cache_file_path(cache_config, key):
    safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", key)
    return cache_config["dir"] / f"{safe_key}.json"


def read_cache(cache_config, key, allow_expired=False):
    if not cache_config["enabled"] or (cache_config["refresh"] and not allow_expired):
        return None
    path = cache_file_path(cache_config, key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    cached_at = payload.get("cached_at")
    if not isinstance(cached_at, (int, float)):
        return None
    if (
        not allow_expired
        and cache_config["ttl_seconds"]
        and time.time() - cached_at > cache_config["ttl_seconds"]
    ):
        return None
    return payload.get("data")


def write_cache(cache_config, key, data):
    if not cache_config["enabled"]:
        return
    path = cache_file_path(cache_config, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "cached_at": time.time(),
        "data": data,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def cached_call(cache_config, key, loader):
    cached = read_cache(cache_config, key)
    if cached is not None:
        return cached
    try:
        data = loader()
    except Exception:
        stale = read_cache(cache_config, key, allow_expired=True)
        if stale is not None:
            print(f"Usando cache expirado para {key} apos falha na API.")
            return stale
        raise
    write_cache(cache_config, key, data)
    return data


def request_with_backoff(loader, label):
    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return loader()
        except Exception as exc:
            last_error = exc
            if attempt >= RETRY_ATTEMPTS:
                break
            message = str(exc)
            if "429" in message or "Too many requests" in message:
                time.sleep(RATE_LIMIT_DELAY_SECONDS * attempt)
            else:
                time.sleep(RETRY_DELAY_SECONDS * attempt)
            print(f"{label}: tentativa {attempt + 1}/{RETRY_ATTEMPTS}.")
    raise last_error


def list_projects(client):
    return request_with_backoff(
        lambda: client.list_projects(per_page=100).get("data", []),
        "Projetos",
    )


def filter_projects(projects, project_names_csv, exclude_projects_csv):
    requested = {item.lower() for item in parse_csv_values(project_names_csv)}
    excluded = {item.lower() for item in parse_csv_values(exclude_projects_csv)}
    filtered = []
    for project in projects:
        name = str(project.get("name", "")).strip()
        normalized = name.lower()
        if requested and normalized not in requested:
            continue
        if normalized in excluded:
            continue
        filtered.append(project)
    return filtered


def get_integrations_by_slug(client, project_id):
    integrations = request_with_backoff(
        lambda: client.list_integrations(project_id=project_id, per_page=100).get("data", []),
        f"Integracoes projeto {project_id}",
    )
    return {
        integration.get("slug"): integration
        for integration in integrations
        if integration.get("slug")
    }


def get_metric_definitions_map(client, network_slug):
    metrics = request_with_backoff(
        lambda: client.list_metrics(network_slug, per_page=100).get("data", []),
        f"Metricas {network_slug}",
    )
    return {
        metric.get("reference_key"): metric
        for metric in metrics
        if metric.get("reference_key")
    }


def prepare_metric_definition_for_request(metric_definition):
    prepared = {
        key: value
        for key, value in metric_definition.items()
        if value not in (None, [], {})
    }
    if isinstance(prepared.get("type"), str):
        prepared["type"] = [prepared["type"]]
    return prepared


def get_client():
    load_dotenv(SCRIPT_DIR / ".env")
    token = os.getenv("REPORTEI_TOKEN")
    return ReporteiClient(token, timeout=90)


def cached_list_projects(client, cache_config):
    return cached_call(cache_config, "projects", lambda: list_projects(client))


def cached_get_integrations_by_slug(client, project_id, cache_config):
    return cached_call(
        cache_config,
        f"integrations_{project_id}",
        lambda: get_integrations_by_slug(client, project_id),
    )


def cached_get_metric_definitions_map(client, network_slug, cache_config):
    return cached_call(
        cache_config,
        f"metrics_{network_slug}",
        lambda: get_metric_definitions_map(client, network_slug),
    )


def to_number(value, default=0):
    if isinstance(value, (int, float)):
        return value
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    normalized = text.replace(".", "").replace(",", ".")
    try:
        number = float(normalized)
    except ValueError:
        return default
    return int(number) if number.is_integer() else number


def format_metric(value):
    number = to_number(value)
    return int(number) if isinstance(number, float) and number.is_integer() else number


def metric_index(metric_definition, metric_name):
    metrics = metric_definition.get("metrics") or []
    try:
        return 1 + metrics.index(metric_name)
    except ValueError:
        return None


def row_metric_value(raw_row, metric_definition, metric_name):
    index = metric_index(metric_definition, metric_name)
    if index is None or index >= len(raw_row):
        return 0
    return to_number(raw_row[index])


def row_raw_metric_value(raw_row, metric_definition, metric_name):
    index = metric_index(metric_definition, metric_name)
    if index is None or index >= len(raw_row):
        return ""
    return raw_row[index]


def format_post_date(value):
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    for date_format in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, date_format).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return text


def parse_sheet_date(value):
    text = str(value or "").strip()
    for date_format in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    return None


def row_dimension(raw_row):
    if not raw_row:
        return {}
    dimension = raw_row[0]
    if isinstance(dimension, dict):
        return dimension
    if isinstance(dimension, str):
        return {"text": dimension}
    return {}


def valid_url(value):
    text = str(value or "").strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return ""


def engagement_value(raw_row, metric_definition, table_config):
    if table_config.get("engajamento"):
        return row_metric_value(raw_row, metric_definition, table_config["engajamento"])
    return sum(
        row_metric_value(raw_row, metric_definition, metric_name)
        for metric_name in table_config.get("engajamento_sum", [])
    )


def post_date_value(raw_row, metric_definition, table_config):
    metric_name = table_config.get("data")
    if not metric_name:
        return ""
    return format_post_date(row_raw_metric_value(raw_row, metric_definition, metric_name))


def extract_rows_from_datatable(payload):
    if isinstance(payload, dict) and isinstance(payload.get("values"), list):
        return payload["values"]
    if isinstance(payload, dict):
        for value in payload.values():
            rows = extract_rows_from_datatable(value)
            if rows:
                return rows
    return []


def fetch_post_table(client, integration_id, metric_definition, start_iso, end_iso):
    prepared = prepare_metric_definition_for_request(metric_definition)
    try:
        response = request_with_backoff(
            lambda: client.get_metrics_data(
                start=start_iso,
                end=end_iso,
                integration_id=integration_id,
                metrics=[prepared],
            ),
            prepared.get("reference_key", "Tabela de posts"),
        )
        payload = response.get("data", {}).get(prepared["id"], {})
        return extract_rows_from_datatable(payload)
    except Exception as exc:
        print(
            f"{prepared.get('reference_key', 'Tabela de posts')}: "
            "consulta completa falhou; tentando por semanas."
        )
        return fetch_post_table_by_chunks(
            client,
            integration_id,
            prepared,
            start_iso,
            end_iso,
            exc,
        )


def iter_date_chunks(start_iso, end_iso, chunk_days=7):
    start_date = datetime.strptime(start_iso, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_iso, "%Y-%m-%d").date()
    current = start_date
    while current <= end_date:
        chunk_end = min(current + timedelta(days=chunk_days - 1), end_date)
        yield current.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")
        current = chunk_end + timedelta(days=1)


def fetch_post_table_by_chunks(client, integration_id, prepared_metric, start_iso, end_iso, original_error):
    rows = []
    for chunk_start, chunk_end in iter_date_chunks(start_iso, end_iso):
        try:
            response = request_with_backoff(
                lambda chunk_start=chunk_start, chunk_end=chunk_end: client.get_metrics_data(
                    start=chunk_start,
                    end=chunk_end,
                    integration_id=integration_id,
                    metrics=[prepared_metric],
                ),
                f"{prepared_metric.get('reference_key', 'Tabela de posts')} {chunk_start}..{chunk_end}",
            )
            payload = response.get("data", {}).get(prepared_metric["id"], {})
            rows.extend(extract_rows_from_datatable(payload))
        except Exception as exc:
            print(
                f"{prepared_metric.get('reference_key', 'Tabela de posts')} "
                f"{chunk_start}..{chunk_end}: falhou; pulando este bloco. "
                f"Erro: {str(exc)[:300]}"
            )
            continue
    if not rows:
        raise original_error
    return rows


def make_post_row(project_name, network_slug, raw_row, metric_definition, table_config):
    dimension = row_dimension(raw_row)
    link = valid_url(dimension.get("url"))
    if not link:
        return None

    visualizacoes = row_metric_value(
        raw_row,
        metric_definition,
        table_config["visualizacoes"],
    )
    if to_number(visualizacoes) <= 0:
        return None

    engajamento = engagement_value(raw_row, metric_definition, table_config)

    return {
        "Data": post_date_value(raw_row, metric_definition, table_config),
        "Produto": project_name,
        "Rede": NETWORKS.get(network_slug, network_slug),
        "Link": link,
        "Visualizacoes": format_metric(visualizacoes),
        "Engajamento": format_metric(engajamento),
    }


def sort_key_for_ranking(row):
    return (
        -to_number(row["Visualizacoes"]),
        -to_number(row["Engajamento"]),
        row["Data"],
        row["Link"].lower(),
    )


def apply_top_per_product_network(rows, top_per_product_network):
    if not top_per_product_network or top_per_product_network <= 0:
        return rows

    grouped = {}
    for row in rows:
        key = (
            row["Produto"].strip().lower(),
            row["Rede"].strip().lower(),
        )
        grouped.setdefault(key, []).append(row)

    limited_rows = []
    for group_rows in grouped.values():
        limited_rows.extend(
            sorted(group_rows, key=sort_key_for_ranking)[:top_per_product_network]
        )
    return limited_rows


def build_rows(client, projects, networks, start_iso, end_iso, cache_config, top_per_product_network):
    metric_maps = {
        network_slug: cached_get_metric_definitions_map(client, network_slug, cache_config)
        for network_slug in networks
        if network_slug in POST_TABLES
    }

    rows_by_key = {}
    total_blocks = sum(
        1
        for project in projects
        for network_slug in networks
        if network_slug in POST_TABLES
    )
    block_index = 0

    for project in projects:
        integrations = cached_get_integrations_by_slug(client, project["id"], cache_config)
        for network_slug in networks:
            if network_slug not in POST_TABLES:
                continue
            block_index += 1
            integration = integrations.get(network_slug)
            label = f"[{block_index}/{total_blocks}] {project['name']} | {NETWORKS.get(network_slug, network_slug)}"
            if not integration:
                print(f"{label}: integracao ausente.")
                continue

            metric_map = metric_maps.get(network_slug, {})
            for table_config in POST_TABLES[network_slug]:
                reference_key = table_config["reference_key"]
                metric_definition = metric_map.get(reference_key)
                if not metric_definition:
                    print(f"{label}: metrica ausente {reference_key}.")
                    continue
                print(f"{label}: buscando {reference_key}.")
                try:
                    raw_rows = fetch_post_table(
                        client,
                        integration["id"],
                        metric_definition,
                        start_iso,
                        end_iso,
                    )
                except Exception as exc:
                    print(
                        f"{label}: falha em {reference_key}; seguindo para o proximo bloco. "
                        f"Erro: {str(exc)[:500]}"
                    )
                    continue
                for raw_row in raw_rows:
                    if not isinstance(raw_row, list):
                        continue
                    row = make_post_row(
                        project["name"],
                        network_slug,
                        raw_row,
                        metric_definition,
                        table_config,
                    )
                    if not row:
                        continue
                    key = (
                        row["Produto"].strip().lower(),
                        row["Rede"].strip().lower(),
                        row["Link"].strip().lower(),
                    )
                    existing = rows_by_key.get(key)
                    if not existing or to_number(row["Visualizacoes"]) > to_number(existing["Visualizacoes"]):
                        rows_by_key[key] = row

    limited_rows = apply_top_per_product_network(
        list(rows_by_key.values()),
        top_per_product_network,
    )
    return sorted(
        limited_rows,
        key=lambda row: (
            row["Produto"].lower(),
            row["Rede"].lower(),
            *sort_key_for_ranking(row),
        ),
    )


def write_csv(output_path, rows):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def create_google_sheets_client(service_account_file):
    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not service_account_file and not service_account_json:
        raise ValueError(
            "Informe --service-account-file, GOOGLE_SERVICE_ACCOUNT_FILE "
            "ou GOOGLE_SERVICE_ACCOUNT_JSON."
        )

    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Dependencias do Google nao instaladas. Rode: pip install -r requirements.txt"
        ) from exc

    if service_account_json:
        credentials = Credentials.from_service_account_info(
            json.loads(service_account_json),
            scopes=GOOGLE_SHEETS_SCOPES,
        )
    else:
        credentials = Credentials.from_service_account_file(
            service_account_file,
            scopes=GOOGLE_SHEETS_SCOPES,
        )
    service = build("sheets", "v4", credentials=credentials)
    return service.spreadsheets()


def execute_google_request_with_backoff(request_factory, action_label):
    last_error = None
    for attempt in range(1, GOOGLE_WRITE_RETRY_ATTEMPTS + 1):
        try:
            return request_factory().execute()
        except Exception as exc:
            last_error = exc
            if attempt >= GOOGLE_WRITE_RETRY_ATTEMPTS:
                break
            print(
                f"{action_label} falhou na tentativa {attempt}/"
                f"{GOOGLE_WRITE_RETRY_ATTEMPTS}; tentando de novo..."
            )
            time.sleep(GOOGLE_WRITE_RETRY_DELAY_SECONDS * attempt)
    raise last_error


def ensure_google_worksheet(spreadsheets, spreadsheet_id, worksheet_name, min_rows=1000):
    metadata = spreadsheets.get(spreadsheetId=spreadsheet_id).execute()
    worksheet_id = None
    for sheet in metadata.get("sheets", []):
        if sheet["properties"]["title"] == worksheet_name:
            worksheet_id = sheet["properties"]["sheetId"]
            break
    if worksheet_id is not None:
        return worksheet_id

    create_response = spreadsheets.batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": worksheet_name,
                            "gridProperties": {
                                "rowCount": max(min_rows, 1000),
                                "columnCount": len(OUTPUT_FIELDNAMES),
                            },
                        }
                    }
                }
            ]
        },
    ).execute()
    return create_response["replies"][0]["addSheet"]["properties"]["sheetId"]


def sheet_range(worksheet_name, cell_range):
    escaped = worksheet_name.replace("'", "''")
    return f"'{escaped}'!{cell_range}"


def clear_google_sheet_values(spreadsheets, spreadsheet_id, worksheet_name):
    spreadsheets.values().clear(
        spreadsheetId=spreadsheet_id,
        range=sheet_range(worksheet_name, "A:F"),
        body={},
    ).execute()


def sheet_values_to_rows(values):
    rows = []
    for values_row in values[1:]:
        row = {}
        for index, field_name in enumerate(OUTPUT_FIELDNAMES):
            row[field_name] = values_row[index] if index < len(values_row) else ""
        if any(str(value).strip() for value in row.values()):
            rows.append(row)
    return rows


def read_google_sheet_rows(spreadsheets, spreadsheet_id, worksheet_name):
    response = spreadsheets.values().get(
        spreadsheetId=spreadsheet_id,
        range=sheet_range(worksheet_name, "A:F"),
    ).execute()
    values = response.get("values", [])
    if not values:
        return []
    return sheet_values_to_rows(values)


def row_in_period(row, start_iso, end_iso):
    row_date = parse_sheet_date(row.get("Data"))
    if row_date is None:
        return False
    start_date = datetime.strptime(start_iso, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_iso, "%Y-%m-%d").date()
    return start_date <= row_date <= end_date


def sort_sheet_rows(rows):
    return sorted(
        rows,
        key=lambda row: (
            parse_sheet_date(row.get("Data")) or datetime.max.date(),
            str(row.get("Produto", "")).lower(),
            str(row.get("Rede", "")).lower(),
            -to_number(row.get("Visualizacoes")),
            -to_number(row.get("Engajamento")),
            str(row.get("Link", "")).lower(),
        ),
    )


def merge_historical_rows(existing_rows, new_rows, start_iso, end_iso):
    rows_to_keep = [
        row
        for row in existing_rows
        if not row_in_period(row, start_iso, end_iso)
    ]
    return sort_sheet_rows(rows_to_keep + new_rows)


def rows_to_sheet_values(rows):
    values = [OUTPUT_FIELDNAMES]
    for row in rows:
        values.append([row.get(field_name, "") for field_name in OUTPUT_FIELDNAMES])
    return values


def format_google_sheet(spreadsheets, spreadsheet_id, worksheet_id, row_count):
    requests = [
        {
            "repeatCell": {
                "range": {
                    "sheetId": worksheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": len(OUTPUT_FIELDNAMES),
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.29, "green": 0.28, "blue": 0.32},
                        "textFormat": {
                            "bold": True,
                            "foregroundColor": {"red": 0.86, "green": 0.9, "blue": 0.98},
                        },
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": worksheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": max(row_count, 2),
                    "startColumnIndex": 4,
                    "endColumnIndex": 6,
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {"type": "NUMBER", "pattern": "#,##0"}
                    }
                },
                "fields": "userEnteredFormat.numberFormat",
            }
        },
        {
            "autoResizeDimensions": {
                "dimensions": {
                    "sheetId": worksheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": len(OUTPUT_FIELDNAMES),
                }
            }
        },
    ]
    execute_google_request_with_backoff(
        lambda: spreadsheets.batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ),
        "Formatacao Google Sheets",
    )


def write_google_sheet(spreadsheet_id, worksheet_name, service_account_file, rows, start_iso, end_iso):
    spreadsheets = create_google_sheets_client(service_account_file)
    worksheet_id = ensure_google_worksheet(
        spreadsheets,
        spreadsheet_id,
        worksheet_name,
        min_rows=len(rows) + 1,
    )
    existing_rows = read_google_sheet_rows(spreadsheets, spreadsheet_id, worksheet_name)
    final_rows = merge_historical_rows(existing_rows, rows, start_iso, end_iso)
    clear_google_sheet_values(spreadsheets, spreadsheet_id, worksheet_name)
    execute_google_request_with_backoff(
        lambda: spreadsheets.values().update(
            spreadsheetId=spreadsheet_id,
            range=sheet_range(worksheet_name, "A1"),
            valueInputOption="RAW",
            body={"values": rows_to_sheet_values(final_rows)},
        ),
        "Escrita Google Sheets",
    )
    format_google_sheet(spreadsheets, spreadsheet_id, worksheet_id, len(final_rows) + 1)
    return {
        "existing": len(existing_rows),
        "replaced": sum(1 for row in existing_rows if row_in_period(row, start_iso, end_iso)),
        "written": len(rows),
        "final": len(final_rows),
    }


def main():
    started_at = time.time()
    args = build_parser().parse_args()
    start_iso, end_iso = resolve_period_dates(args.period, args.start, args.end)
    networks = ordered_networks(args.networks)
    cache_config = make_cache_config(args)
    client = get_client()

    projects = filter_projects(
        cached_list_projects(client, cache_config),
        args.project_names,
        args.exclude_projects,
    )
    print(f"Periodo: {start_iso} ate {end_iso}")
    print(f"Projetos: {len(projects)}")
    print(f"Redes: {', '.join(NETWORKS.get(slug, slug) for slug in networks)}")

    rows = build_rows(
        client,
        projects,
        networks,
        start_iso,
        end_iso,
        cache_config,
        args.top_per_product_network,
    )

    if args.save_csv:
        output_path = Path(args.output)
        write_csv(output_path, rows)
        print(f"CSV salvo: {output_path.resolve()}")

    if not args.no_google:
        write_result = write_google_sheet(
            args.spreadsheet_id,
            args.worksheet_name,
            args.service_account_file,
            rows,
            start_iso,
            end_iso,
        )
        print(f"Google Sheet atualizada: {args.spreadsheet_id} / {args.worksheet_name}")
        print(
            "Historico preservado: "
            f"{write_result['final']} linha(s) finais; "
            f"{write_result['replaced']} linha(s) substituida(s) no periodo."
        )

    print(f"Linhas finais: {len(rows)}")
    print(f"Tempo total: {int(time.time() - started_at)}s")


if __name__ == "__main__":
    main()
