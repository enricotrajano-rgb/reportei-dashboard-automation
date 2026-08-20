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
DEFAULT_TOP_PER_PRODUCT_NETWORK = 5
DEFAULT_CACHE_DIR = ".reportei_cache"
DEFAULT_CACHE_TTL_HOURS = 24

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
    "Curtidas",
    "Comentarios",
    "Compartilhamentos",
    "Salvos",
    "Reposts",
]
SHEET_COLUMN_RANGE = "A:J"
NUMERIC_FIELDNAMES = {
    "Visualizacoes",
    "Curtidas",
    "Comentarios",
    "Compartilhamentos",
    "Salvos",
    "Reposts",
}
RANKING_ENGAGEMENT_FIELDNAMES = [
    "Curtidas",
    "Comentarios",
    "Compartilhamentos",
    "Salvos",
    "Reposts",
]

NETWORKS = {
    "facebook": "Facebook",
    "instagram_business": "Instagram",
}
NETWORK_ORDER = ["facebook", "instagram_business"]

# Facebook entrega reacoes totais por post, nao curtidas puras.
# Instagram aceita reposts por post quando a metrica e enviada no request da datatable.
POST_TABLES = {
    "facebook": [
        {
            "reference_key": "fb:page_posts",
            "metrics": [
                "type",
                "total_reach",
                "total_reactions",
                "comments",
                "shares",
                "created_at",
            ],
            "visualizacoes": "total_reach",
            "curtidas": "total_reactions",
            "comentarios": "comments",
            "compartilhamentos": "shares",
            "data": "created_at",
        }
    ],
    "instagram_business": [
        {
            "reference_key": "ig:media_datatable",
            "metrics": [
                "type",
                "reach",
                "views",
                "likes",
                "comments",
                "shares",
                "saved",
                "reposts",
                "created_at",
            ],
            "visualizacoes": "views",
            "curtidas": "likes",
            "comentarios": "comments",
            "compartilhamentos": "shares",
            "salvos": "saved",
            "reposts": "reposts",
            "data": "created_at",
        },
        {
            "reference_key": "ig:reels_datatable",
            "metrics": [
                "reach",
                "views",
                "likes",
                "comments",
                "shares",
                "saved",
                "reposts",
                "created_at",
            ],
            "visualizacoes": "views",
            "curtidas": "likes",
            "comentarios": "comments",
            "compartilhamentos": "shares",
            "salvos": "saved",
            "reposts": "reposts",
            "data": "created_at",
        },
    ],
}


def build_parser():
    parser = argparse.ArgumentParser(
        description="Gera a base de top posts para Looker Studio."
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
        choices=[
            "",
            "current_month_until_yesterday",
            "previous_month",
            "last_7_days",
            "last_30_days",
        ],
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
        default=int(
            os.getenv(
                "REPORTEI_TOP_POSTS_PER_PRODUCT_NETWORK",
                DEFAULT_TOP_PER_PRODUCT_NETWORK,
            )
        ),
        help="Quantidade maxima por Produto + Rede. 0 = sem limite.",
    )
    parser.add_argument(
        "--output",
        default=os.getenv("REPORTEI_TOP_POSTS_OUTPUT", DEFAULT_OUTPUT),
        help="Caminho do CSV.",
    )
    parser.add_argument(
        "--save-csv",
        action=argparse.BooleanOptionalAction,
        default=os.getenv("REPORTEI_TOP_POSTS_SAVE_CSV", str(DEFAULT_SAVE_CSV)).lower()
        == "true",
        help="Tambem salva CSV local.",
    )
    parser.add_argument(
        "--spreadsheet-id",
        default=os.getenv("GOOGLE_SPREADSHEET_ID", DEFAULT_GOOGLE_SPREADSHEET_ID),
        help="ID da Google Sheet.",
    )
    parser.add_argument(
        "--worksheet-name",
        default=os.getenv(
            "REPORTEI_TOP_POSTS_WORKSHEET_NAME",
            os.getenv("GOOGLE_TOP_POSTS_WORKSHEET_NAME", DEFAULT_GOOGLE_WORKSHEET_NAME),
        ),
        help="Nome da aba de destino.",
    )
    parser.add_argument(
        "--service-account-file",
        default=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", DEFAULT_GOOGLE_SERVICE_ACCOUNT_FILE),
        help="Arquivo JSON da service account.",
    )
    parser.add_argument("--no-google", action="store_true", help="Nao atualiza Google Sheets.")
    parser.add_argument(
        "--repair-existing-types",
        action="store_true",
        default=os.getenv("REPORTEI_TOP_POSTS_REPAIR_EXISTING_TYPES", "false").lower()
        == "true",
        help="Converte linhas existentes da aba para data/numeros reais.",
    )
    parser.add_argument(
        "--repair-types-only",
        action="store_true",
        help="Apenas repara os tipos da aba existente, sem consultar a API.",
    )
    parser.add_argument(
        "--cache-dir",
        default=os.getenv("REPORTEI_CACHE_DIR", DEFAULT_CACHE_DIR),
        help="Mantido por compatibilidade; este script nao usa cache local.",
    )
    parser.add_argument(
        "--cache-ttl-hours",
        type=int,
        default=int(os.getenv("REPORTEI_CACHE_TTL_HOURS", DEFAULT_CACHE_TTL_HOURS)),
        help="Mantido por compatibilidade.",
    )
    parser.add_argument(
        "--use-cache",
        action=argparse.BooleanOptionalAction,
        default=os.getenv("REPORTEI_USE_CACHE", "true").lower() != "false",
        help="Mantido por compatibilidade.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Mantido por compatibilidade.",
    )
    return parser


def parse_csv_values(raw_value):
    return [item.strip() for item in str(raw_value or "").split(",") if item.strip()]


def ordered_networks(networks_csv):
    requested = parse_csv_values(networks_csv) or list(NETWORK_ORDER)
    ordered = [slug for slug in NETWORK_ORDER if slug in requested]
    ordered.extend(slug for slug in requested if slug not in ordered)
    return ordered


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
                wait_seconds = RATE_LIMIT_DELAY_SECONDS * attempt
            else:
                wait_seconds = RETRY_DELAY_SECONDS * attempt
            print(f"{label}: tentativa {attempt + 1}/{RETRY_ATTEMPTS} em {wait_seconds}s.")
            time.sleep(wait_seconds)
    raise last_error


def get_client():
    load_dotenv(SCRIPT_DIR / ".env")
    token = os.getenv("REPORTEI_TOKEN")
    return ReporteiClient(token, timeout=90)


def list_all_pages(loader, label, per_page=100):
    items = []
    page = 1
    while True:
        response = request_with_backoff(
            lambda page=page: loader(page, per_page),
            f"{label} pagina {page}",
        )
        data = response.get("data", [])
        items.extend(data)
        if len(data) < per_page:
            break
        page += 1
    return items


def list_projects(client):
    return list_all_pages(
        lambda page, per_page: client.list_projects(page=page, per_page=per_page),
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
    integrations = list_all_pages(
        lambda page, per_page: client.list_integrations(
            page=page,
            per_page=per_page,
            project_id=project_id,
        ),
        f"Integracoes projeto {project_id}",
    )
    return {
        integration.get("slug"): integration
        for integration in integrations
        if integration.get("slug")
    }


def get_metric_definitions_map(client, network_slug):
    metrics = list_all_pages(
        lambda page, per_page: client.list_metrics(
            network_slug,
            page=page,
            per_page=per_page,
        ),
        f"Metricas {network_slug}",
    )
    return {
        metric.get("reference_key"): metric
        for metric in metrics
        if metric.get("reference_key")
    }


def prepare_metric_definition_for_request(metric_definition, table_config):
    prepared = {
        key: value
        for key, value in metric_definition.items()
        if value not in (None, [], {})
    }
    if table_config.get("metrics"):
        prepared["metrics"] = table_config["metrics"]
    if isinstance(prepared.get("type"), str):
        prepared["type"] = [prepared["type"]]
    return prepared


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
    if isinstance(value, (int, float)):
        base_date = datetime(1899, 12, 30).date()
        return base_date + timedelta(days=int(value))
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


def table_metric_value(raw_row, metric_definition, table_config, config_key):
    metric_name = table_config.get(config_key)
    if not metric_name:
        return 0
    return row_metric_value(raw_row, metric_definition, metric_name)


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


def iter_date_chunks(start_iso, end_iso, chunk_days=7):
    start_date = datetime.strptime(start_iso, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_iso, "%Y-%m-%d").date()
    current = start_date
    while current <= end_date:
        chunk_end = min(current + timedelta(days=chunk_days - 1), end_date)
        yield current.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")
        current = chunk_end + timedelta(days=1)


def fetch_post_table_by_chunks(
    client,
    integration_id,
    prepared_metric,
    start_iso,
    end_iso,
    original_error,
):
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


def fetch_post_table(client, integration_id, prepared_metric, start_iso, end_iso):
    try:
        response = request_with_backoff(
            lambda: client.get_metrics_data(
                start=start_iso,
                end=end_iso,
                integration_id=integration_id,
                metrics=[prepared_metric],
            ),
            prepared_metric.get("reference_key", "Tabela de posts"),
        )
        payload = response.get("data", {}).get(prepared_metric["id"], {})
        return extract_rows_from_datatable(payload)
    except Exception as exc:
        print(
            f"{prepared_metric.get('reference_key', 'Tabela de posts')}: "
            "consulta completa falhou; tentando por semanas."
        )
        return fetch_post_table_by_chunks(
            client,
            integration_id,
            prepared_metric,
            start_iso,
            end_iso,
            exc,
        )


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

    return {
        "Data": post_date_value(raw_row, metric_definition, table_config),
        "Produto": project_name,
        "Rede": NETWORKS.get(network_slug, network_slug),
        "Link": link,
        "Visualizacoes": format_metric(visualizacoes),
        "Curtidas": format_metric(
            table_metric_value(raw_row, metric_definition, table_config, "curtidas")
        ),
        "Comentarios": format_metric(
            table_metric_value(raw_row, metric_definition, table_config, "comentarios")
        ),
        "Compartilhamentos": format_metric(
            table_metric_value(
                raw_row,
                metric_definition,
                table_config,
                "compartilhamentos",
            )
        ),
        "Salvos": format_metric(
            table_metric_value(raw_row, metric_definition, table_config, "salvos")
        ),
        "Reposts": format_metric(
            table_metric_value(raw_row, metric_definition, table_config, "reposts")
        ),
    }


def row_engagement_total(row):
    return sum(to_number(row.get(field_name)) for field_name in RANKING_ENGAGEMENT_FIELDNAMES)


def sort_key_for_ranking(row):
    return (
        -to_number(row["Visualizacoes"]),
        -row_engagement_total(row),
        row["Data"],
        row["Link"].lower(),
    )


def apply_top_per_product_network(rows, top_per_product_network):
    if not top_per_product_network or top_per_product_network <= 0:
        return rows

    grouped = {}
    for row in rows:
        key = (row["Produto"].strip().lower(), row["Rede"].strip().lower())
        grouped.setdefault(key, []).append(row)

    limited_rows = []
    for group_rows in grouped.values():
        limited_rows.extend(
            sorted(group_rows, key=sort_key_for_ranking)[:top_per_product_network]
        )
    return limited_rows


def build_rows(client, projects, networks, start_iso, end_iso, top_per_product_network):
    metric_maps = {
        network_slug: get_metric_definitions_map(client, network_slug)
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
        integrations = get_integrations_by_slug(client, project["id"])
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

                request_metric_definition = prepare_metric_definition_for_request(
                    metric_definition,
                    table_config,
                )
                print(f"{label}: buscando {reference_key}.")
                try:
                    raw_rows = fetch_post_table(
                        client,
                        integration["id"],
                        request_metric_definition,
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
                        request_metric_definition,
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
                    if not existing or to_number(row["Visualizacoes"]) > to_number(
                        existing["Visualizacoes"]
                    ):
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
        writer.writerows(output_row(row) for row in rows)


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


def sheet_values_to_rows(values):
    rows = []
    for row_number, values_row in enumerate(values[1:], start=2):
        row = {}
        for index, field_name in enumerate(OUTPUT_FIELDNAMES):
            value = values_row[index] if index < len(values_row) else ""
            row[field_name] = value
        if any(str(value).strip() for value in row.values()):
            row["_row_number"] = row_number
            rows.append(row)
    return rows


def read_google_sheet_rows(spreadsheets, spreadsheet_id, worksheet_name):
    response = spreadsheets.values().get(
        spreadsheetId=spreadsheet_id,
        range=sheet_range(worksheet_name, SHEET_COLUMN_RANGE),
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
    return sorted(rows, key=row_sort_tuple)


def row_to_sheet_values(row):
    return [sheet_cell_value(row, field_name) for field_name in OUTPUT_FIELDNAMES]


def sheet_cell_value(row, field_name):
    value = row.get(field_name, "")
    if field_name == "Data":
        row_date = parse_sheet_date(value)
        if row_date is None:
            return value
        return (row_date - datetime(1899, 12, 30).date()).days
    if field_name in NUMERIC_FIELDNAMES:
        return to_number(value)
    return value


def output_row(row):
    return {field_name: row.get(field_name, "") for field_name in OUTPUT_FIELDNAMES}


def remove_internal_fields(row):
    return output_row(row)


def group_contiguous_numbers(numbers):
    groups = []
    sorted_numbers = sorted(numbers)
    if not sorted_numbers:
        return groups
    start = previous = sorted_numbers[0]
    for number in sorted_numbers[1:]:
        if number == previous + 1:
            previous = number
            continue
        groups.append((start, previous))
        start = previous = number
    groups.append((start, previous))
    return groups


def find_insert_row_number(rows_to_keep, new_rows):
    if not new_rows:
        return None
    first_new_key = row_sort_tuple(sort_sheet_rows(new_rows)[0])
    rows_before = sum(1 for row in rows_to_keep if row_sort_tuple(row) < first_new_key)
    return 2 + rows_before


def row_sort_tuple(row):
    return (
        parse_sheet_date(row.get("Data")) or datetime.max.date(),
        str(row.get("Produto", "")).lower(),
        str(row.get("Rede", "")).lower(),
        -to_number(row.get("Visualizacoes")),
        -row_engagement_total(row),
        str(row.get("Link", "")).lower(),
    )


def write_google_sheet_header(spreadsheets, spreadsheet_id, worksheet_name):
    execute_google_request_with_backoff(
        lambda: spreadsheets.values().update(
            spreadsheetId=spreadsheet_id,
            range=sheet_range(worksheet_name, "A1:J1"),
            valueInputOption="USER_ENTERED",
            body={"values": [OUTPUT_FIELDNAMES]},
        ),
        "Cabecalho Google Sheets",
    )


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
                    "startColumnIndex": 0,
                    "endColumnIndex": 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {"type": "DATE", "pattern": "dd/mm/yyyy"}
                    }
                },
                "fields": "userEnteredFormat.numberFormat",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": worksheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": max(row_count, 2),
                    "startColumnIndex": 4,
                    "endColumnIndex": len(OUTPUT_FIELDNAMES),
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


def delete_period_rows(spreadsheets, spreadsheet_id, worksheet_id, existing_rows, start_iso, end_iso):
    period_row_numbers = [
        row["_row_number"]
        for row in existing_rows
        if row.get("_row_number") and row_in_period(row, start_iso, end_iso)
    ]
    groups = group_contiguous_numbers(period_row_numbers)
    if not groups:
        return 0

    requests = []
    for start_row, end_row in reversed(groups):
        requests.append(
            {
                "deleteDimension": {
                    "range": {
                        "sheetId": worksheet_id,
                        "dimension": "ROWS",
                        "startIndex": start_row - 1,
                        "endIndex": end_row,
                    }
                }
            }
        )
    execute_google_request_with_backoff(
        lambda: spreadsheets.batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ),
        "Remocao de linhas do periodo no Google Sheets",
    )
    return len(period_row_numbers)


def insert_period_rows(spreadsheets, spreadsheet_id, worksheet_id, worksheet_name, insert_row_number, rows):
    if not rows:
        return

    row_count = len(rows)
    insert_index = max(insert_row_number - 1, 1)
    execute_google_request_with_backoff(
        lambda: spreadsheets.batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "insertDimension": {
                            "range": {
                                "sheetId": worksheet_id,
                                "dimension": "ROWS",
                                "startIndex": insert_index,
                                "endIndex": insert_index + row_count,
                            },
                            "inheritFromBefore": insert_index > 1,
                        }
                    }
                ]
            },
        ),
        "Insercao de linhas do periodo no Google Sheets",
    )
    execute_google_request_with_backoff(
        lambda: spreadsheets.values().update(
            spreadsheetId=spreadsheet_id,
            range=sheet_range(
                worksheet_name,
                f"A{insert_row_number}:J{insert_row_number + row_count - 1}",
            ),
            valueInputOption="USER_ENTERED",
            body={"values": [row_to_sheet_values(row) for row in rows]},
        ),
        "Escrita do periodo no Google Sheets",
    )


def repair_existing_sheet_types(spreadsheets, spreadsheet_id, worksheet_name):
    all_rows = read_google_sheet_rows(spreadsheets, spreadsheet_id, worksheet_name)
    if not all_rows:
        return 0
    execute_google_request_with_backoff(
        lambda: spreadsheets.values().update(
            spreadsheetId=spreadsheet_id,
            range=sheet_range(worksheet_name, f"A2:J{len(all_rows) + 1}"),
            valueInputOption="USER_ENTERED",
            body={
                "values": [row_to_sheet_values(remove_internal_fields(row)) for row in all_rows]
            },
        ),
        "Reparo de tipos existentes no Google Sheets",
    )
    return len(all_rows)


def write_google_sheet(
    spreadsheet_id,
    worksheet_name,
    service_account_file,
    rows,
    start_iso,
    end_iso,
    repair_existing_types=False,
):
    spreadsheets = create_google_sheets_client(service_account_file)
    worksheet_id = ensure_google_worksheet(
        spreadsheets,
        spreadsheet_id,
        worksheet_name,
        min_rows=len(rows) + 1,
    )
    write_google_sheet_header(spreadsheets, spreadsheet_id, worksheet_name)
    existing_rows = read_google_sheet_rows(spreadsheets, spreadsheet_id, worksheet_name)
    rows_to_keep = [row for row in existing_rows if not row_in_period(row, start_iso, end_iso)]
    new_rows = sort_sheet_rows([remove_internal_fields(row) for row in rows])
    insert_row_number = find_insert_row_number(rows_to_keep, new_rows)
    replaced_count = delete_period_rows(
        spreadsheets,
        spreadsheet_id,
        worksheet_id,
        existing_rows,
        start_iso,
        end_iso,
    )
    if insert_row_number is not None:
        insert_period_rows(
            spreadsheets,
            spreadsheet_id,
            worksheet_id,
            worksheet_name,
            insert_row_number,
            new_rows,
        )
    final_count = len(rows_to_keep) + len(new_rows)
    repaired_count = 0
    if repair_existing_types:
        repaired_count = repair_existing_sheet_types(
            spreadsheets,
            spreadsheet_id,
            worksheet_name,
        )
    format_google_sheet(spreadsheets, spreadsheet_id, worksheet_id, final_count + 1)
    return {
        "existing": len(existing_rows),
        "replaced": replaced_count,
        "written": len(rows),
        "final": final_count,
        "repaired": repaired_count,
    }


def repair_types_only(spreadsheet_id, worksheet_name, service_account_file):
    spreadsheets = create_google_sheets_client(service_account_file)
    worksheet_id = ensure_google_worksheet(spreadsheets, spreadsheet_id, worksheet_name)
    write_google_sheet_header(spreadsheets, spreadsheet_id, worksheet_name)
    repaired_count = repair_existing_sheet_types(spreadsheets, spreadsheet_id, worksheet_name)
    format_google_sheet(spreadsheets, spreadsheet_id, worksheet_id, repaired_count + 1)
    return repaired_count


def main():
    started_at = time.time()
    args = build_parser().parse_args()
    start_iso, end_iso = resolve_period_dates(args.period, args.start, args.end)
    networks = ordered_networks(args.networks)

    if args.repair_types_only:
        repaired_count = repair_types_only(
            args.spreadsheet_id,
            args.worksheet_name,
            args.service_account_file,
        )
        print(f"Google Sheet reparada: {args.spreadsheet_id} / {args.worksheet_name}")
        print(f"Tipos reparados: {repaired_count} linha(s).")
        print(f"Tempo total: {int(time.time() - started_at)}s")
        return

    client = get_client()
    projects = filter_projects(list_projects(client), args.project_names, args.exclude_projects)
    print(f"Periodo: {start_iso} ate {end_iso}")
    print(f"Projetos: {len(projects)}")
    print(f"Redes: {', '.join(NETWORKS.get(slug, slug) for slug in networks)}")

    rows = build_rows(
        client,
        projects,
        networks,
        start_iso,
        end_iso,
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
            repair_existing_types=args.repair_existing_types,
        )
        print(f"Google Sheet atualizada: {args.spreadsheet_id} / {args.worksheet_name}")
        print(
            "Historico preservado: "
            f"{write_result['final']} linha(s) finais; "
            f"{write_result['replaced']} linha(s) substituida(s) no periodo."
        )
        if write_result["repaired"]:
            print(
                "Tipos reparados: "
                f"{write_result['repaired']} linha(s) existentes convertida(s) "
                "para data/numeros reais."
            )

    print(f"Linhas finais: {len(rows)}")
    print(f"Tempo total: {int(time.time() - started_at)}s")


if __name__ == "__main__":
    main()
