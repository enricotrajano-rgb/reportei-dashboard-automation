import argparse
import csv
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from main import ReporteiClient


SCRIPT_DIR = Path(__file__).resolve().parent

# Edite estes valores para rodar pelo botao Run sem precisar passar argumentos.
DEFAULT_START_DATE = "01/08/2026"
DEFAULT_END_DATE = "26/08/2026"   
DEFAULT_PROJECT_NAMES = ""
DEFAULT_EXCLUDE_PROJECTS = "Agro Agenda"
DEFAULT_NETWORKS = "facebook,instagram_business,linkedin,tiktok,youtube"
DEFAULT_OUTPUT = str(Path.home() / "Downloads" / "reportei_dashboard_base.csv")
DEFAULT_SAVE_CSV = False
DEFAULT_GOOGLE_SPREADSHEET_ID = "11hFk76IZe1AnCD3lsq6N95hclSZjIdgrkbmI0GWVCrI"
DEFAULT_GOOGLE_WORKSHEET_NAME = "Base"
DEFAULT_GOOGLE_SERVICE_ACCOUNT_FILE = r"c:\Users\Enrico.Trajano\Downloads\clear-rock-498913-e3-70c12ea73e76.json"
DEFAULT_CACHE_DIR = ".reportei_cache"
DEFAULT_CACHE_TTL_HOURS = 24
DEFAULT_MODE = "update_values"
DEFAULT_PERIOD = ""
REPORTING_TIMEZONE = ZoneInfo("America/Sao_Paulo")
DEFAULT_TOP_SLOW_BLOCKS = 10
DEFAULT_RUN_HISTORY = str(SCRIPT_DIR / "reportei_dashboard_run_history.csv")
DEFAULT_BLOCK_HISTORY = str(SCRIPT_DIR / "reportei_dashboard_block_history.csv")
DEFAULT_ESTIMATE_HISTORY_LIMIT = 8
# False = busca dados completos por dia quando a rede ainda nao tem serie diaria confiavel.
# True = modo ultra rapido; pula metricas daily-only e pode deixar N/D.
DEFAULT_SKIP_DAILY_ONLY = False
DEFAULT_LIVE_WRITE = True
FAST_MODE_KEEP_DAILY_FIELDS = {"Publicacoes"}

NETWORKS = {
    "facebook": "Facebook",
    "instagram_business": "Instagram",
    "youtube": "YouTube",
    "linkedin": "LinkedIn",
    "tiktok": "TikTok",
}

NETWORK_ORDER = [
    "facebook",
    "instagram_business",
    "linkedin",
    "tiktok",
    "youtube",
]

# Algumas linhas da Base representam mais de uma integracao da mesma rede.
# Nesses casos, as metricas das contas listadas sao somadas na mesma linha.
COMBINED_NETWORK_INTEGRATIONS = {
    ("bom dia mercado", "instagram_business"): (
        "picpaybdm",
        "bom_dia_mercado",
    ),
}

RETRY_ATTEMPTS = 4
RETRY_DELAY_SECONDS = 3
RATE_LIMIT_DELAY_SECONDS = 20
GOOGLE_WRITE_RETRY_ATTEMPTS = 4
GOOGLE_WRITE_RETRY_DELAY_SECONDS = 5
GOOGLE_VALUES_BATCH_SIZE = 100
GOOGLE_SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
OUTPUT_FIELDNAMES = [
    "Produto",
    "Redes",
    "Data",
    "Seguidores",
    "Visualizacoes",
    "Publicacoes",
    "Engajamento",
]
METRIC_FIELDNAMES = OUTPUT_FIELDNAMES[3:]


DASHBOARD_SUMMARY_FIELDS = {
    "Seguidores": {
        "facebook": {"reference_key": "fb:follows_over_time"},
        "instagram_business": {"reference_key": "ig:followers_count_chart"},
        "youtube": {"reference_key": "youtube:subscriber_count"},
        "linkedin": {"reference_key": "li:followers_total"},
        "tiktok": {"reference_key": "tiktok:follows"},
    },
    "Visualizacoes": {
        "facebook": {"reference_key": "fb:page_media_views_organic"},
        "instagram_business": {"reference_key": "ig:organic_views_insights"},
        "youtube": {"reference_key": "youtube:views"},
        "linkedin": {"reference_key": "li:impressions"},
        "tiktok": {"reference_key": "tiktok:views"},
    },
    "Publicacoes": {
        "facebook": {"reference_key": "fb:page_posts_count"},
        "instagram_business": {"sum_of": ["ig:media_count", "ig:stories_count"]},
        "youtube": {"note": "N/D"},
        "linkedin": {"reference_key": "li:posts_total"},
        "tiktok": {"reference_key": "tiktok:video_count"},
    },
    "Engajamento": {
        "facebook": {"reference_key": "fb:page_post_engagements"},
        "instagram_business": {
            "sum_of": [
                "ig:post_total_interactions_count",
                "ig:reels_interactions",
                "ig:stories_total_interactions",
                "ig:ad_total_interactions_insights",
            ]
        },
        "youtube": {"sum_of": ["youtube:likes", "youtube:comments", "youtube:shares"]},
        "linkedin": {"reference_key": "li:engagement"},
        "tiktok": {"sum_of": ["tiktok:likes", "tiktok:comments", "tiktok:share"]},
    },
}


FACEBOOK_PERIOD_DAILY_FIELDS = {
    "Seguidores": "fb:follows_over_time",
    "Visualizacoes": "fb:page_media_views_organic",
    "Engajamento": "fb:page_post_engagements",
}

INSTAGRAM_PERIOD_DAILY_FIELDS = {
    "Seguidores": "ig:followers_count_chart",
}

REQUEST_METRIC_OVERRIDES = {
    "fb:page_posts_count": {
        "component": "number_v1",
        "metrics": ["page_posts_count"],
        "type": ["total_posts_count"],
    },
}


def get_client():
    load_dotenv()
    token = os.getenv("REPORTEI_TOKEN")
    return ReporteiClient(token, timeout=90)


def normalize_date(date_text):
    for date_format in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_text, date_format).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(
        f'Data invalida "{date_text}". Use o formato DD/MM/YYYY ou YYYY-MM-DD.'
    )


def format_number(value):
    if value is None:
        return "N/D"
    if isinstance(value, str):
        return value
    if isinstance(value, float):
        if value.is_integer():
            value = int(value)
        else:
            formatted = f"{value:,.2f}"
            return formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    return str(value)


def list_projects(client):
    response = client.list_projects(per_page=100)
    return response.get("data", [])


def filter_projects(projects, project_names_csv):
    if not project_names_csv:
        return sorted(projects, key=lambda project: project["name"].strip().lower())

    requested_names = [
        item.strip()
        for item in project_names_csv.split(",")
        if item.strip()
    ]
    requested_names_lower = {name.lower() for name in requested_names}
    filtered_projects = [
        project
        for project in projects
        if project["name"].strip().lower() in requested_names_lower
    ]
    found_names_lower = {
        project["name"].strip().lower()
        for project in filtered_projects
    }
    missing_names = [
        name
        for name in requested_names
        if name.lower() not in found_names_lower
    ]
    if missing_names:
        raise ValueError(
            "Projeto(s) nao encontrado(s): " + ", ".join(missing_names)
        )
    return sorted(
        filtered_projects,
        key=lambda project: project["name"].strip().lower(),
    )


def get_integrations_by_slug(client, project_id):
    response = client.list_integrations(project_id=project_id, per_page=100)
    integrations = response.get("data", [])
    return {integration["slug"]: integration for integration in integrations}


def get_metric_definitions_map(client, integration_slug):
    response = client.list_metrics(integration_slug=integration_slug, per_page=100)
    metrics = response.get("data", [])
    return {metric["reference_key"]: metric for metric in metrics}


def prepare_metric_definition_for_request(metric_definition):
    prepared = {
        key: value
        for key, value in metric_definition.items()
        if value not in (None, [], {})
    }
    override = REQUEST_METRIC_OVERRIDES.get(prepared.get("reference_key"))
    if override:
        prepared.update(override)
    if isinstance(prepared.get("type"), str):
        prepared["type"] = [prepared["type"]]
    return prepared


def build_parser():
    parser = argparse.ArgumentParser(
        description="Gera uma base diaria otimizada para Looker Studio."
    )
    parser.add_argument(
        "--start",
        default=os.getenv("REPORTEI_DASHBOARD_START", DEFAULT_START_DATE),
        help="DD/MM/YYYY ou YYYY-MM-DD",
    )
    parser.add_argument(
        "--end",
        default=os.getenv("REPORTEI_DASHBOARD_END", DEFAULT_END_DATE),
        help="DD/MM/YYYY ou YYYY-MM-DD",
    )
    parser.add_argument(
        "--period",
        choices=[
            "current_month_until_yesterday",
            "previous_month",
            "last_7_days",
            "last_30_days",
        ],
        default=os.getenv("REPORTEI_DASHBOARD_PERIOD", DEFAULT_PERIOD),
        help=(
            "Periodo automatico. current_month_until_yesterday usa dia 1 do mes "
            "atual ate ontem; no dia 1, usa o mes anterior completo."
        ),
    )
    parser.add_argument(
        "--project-names",
        default=os.getenv("REPORTEI_DASHBOARD_PROJECT_NAMES", DEFAULT_PROJECT_NAMES),
        help="Projetos separados por virgula. Vazio = todos.",
    )
    parser.add_argument(
        "--exclude-projects",
        default=os.getenv("REPORTEI_DASHBOARD_EXCLUDE_PROJECTS", DEFAULT_EXCLUDE_PROJECTS),
        help="Projetos para excluir, separados por virgula.",
    )
    parser.add_argument(
        "--networks",
        default=os.getenv("REPORTEI_DASHBOARD_NETWORKS", DEFAULT_NETWORKS),
        help="Slugs separados por virgula. Vazio = todas.",
    )
    parser.add_argument(
        "--output",
        default=os.getenv("REPORTEI_DASHBOARD_OUTPUT", DEFAULT_OUTPUT),
        help="Caminho do CSV, usado somente com --save-csv ou --csv-only.",
    )
    parser.add_argument(
        "--google-sheet-id",
        default=os.getenv("GOOGLE_SPREADSHEET_ID", DEFAULT_GOOGLE_SPREADSHEET_ID),
        help="ID da Google Sheet que sera atualizada.",
    )
    parser.add_argument(
        "--worksheet",
        default=os.getenv("GOOGLE_WORKSHEET_NAME", DEFAULT_GOOGLE_WORKSHEET_NAME),
        help="Nome da aba da Google Sheet.",
    )
    parser.add_argument(
        "--service-account-file",
        default=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", DEFAULT_GOOGLE_SERVICE_ACCOUNT_FILE),
        help="Caminho do JSON da service account do Google.",
    )
    parser.add_argument(
        "--csv-only",
        action="store_true",
        help="Gera somente CSV, mesmo que uma Google Sheet esteja configurada.",
    )
    parser.add_argument(
        "--mode",
        choices=["update_values", "replace", "fill_missing", "refresh_existing"],
        default=os.getenv("REPORTEI_DASHBOARD_MODE", DEFAULT_MODE),
        help=(
            "update_values atualiza apenas metricas em linhas existentes; replace recria "
            "o recorte; fill_missing busca apenas linhas existentes incompletas; "
            "refresh_existing atualiza o recorte preservando linhas fora dele."
        ),
    )
    parser.add_argument(
        "--save-csv",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_SAVE_CSV,
        help="Tambem salva um CSV local alem de atualizar a Google Sheet.",
    )
    parser.add_argument(
        "--live-write",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_LIVE_WRITE,
        help="Atualiza a Google Sheet em blocos durante a execucao.",
    )
    parser.add_argument(
        "--skip-daily-only",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_SKIP_DAILY_ONLY,
        help="Nao consulta metricas que so vieram corretamente por dia. Mais rapido, mas pode deixar campos em branco.",
    )
    parser.add_argument(
        "--cache-dir",
        default=os.getenv("REPORTEI_DASHBOARD_CACHE_DIR", DEFAULT_CACHE_DIR),
        help="Pasta para cache de projetos, integracoes e catalogo de metricas.",
    )
    parser.add_argument(
        "--cache-ttl-hours",
        type=float,
        default=float(os.getenv("REPORTEI_DASHBOARD_CACHE_TTL_HOURS", DEFAULT_CACHE_TTL_HOURS)),
        help="Validade do cache em horas.",
    )
    parser.add_argument(
        "--use-cache",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Usa cache persistente para dados quase estaveis.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignora cache existente e regrava com dados novos.",
    )
    parser.add_argument(
        "--top-slow-blocks",
        type=int,
        default=int(os.getenv("REPORTEI_DASHBOARD_TOP_SLOW_BLOCKS", DEFAULT_TOP_SLOW_BLOCKS)),
        help="Quantidade de blocos mais lentos mostrados no final.",
    )
    parser.add_argument(
        "--run-history",
        default=os.getenv("REPORTEI_DASHBOARD_RUN_HISTORY", DEFAULT_RUN_HISTORY),
        help="CSV local que registra historico de tempo das execucoes.",
    )
    parser.add_argument(
        "--block-history",
        default=os.getenv("REPORTEI_DASHBOARD_BLOCK_HISTORY", DEFAULT_BLOCK_HISTORY),
        help="CSV local que registra historico por bloco Produto/Rede.",
    )
    parser.add_argument(
        "--estimate-history-limit",
        type=int,
        default=int(os.getenv("REPORTEI_DASHBOARD_ESTIMATE_HISTORY_LIMIT", DEFAULT_ESTIMATE_HISTORY_LIMIT)),
        help="Quantidade maxima de execucoes historicas usadas na estimativa inicial.",
    )
    parser.add_argument(
        "--repair-date-column",
        action="store_true",
        help="Converte seriais numericos da coluna Data (C) para texto dd/mm/aaaa e sai.",
    )
    return parser


def iter_days(start_iso, end_iso):
    current = datetime.strptime(start_iso, "%Y-%m-%d")
    end_dt = datetime.strptime(end_iso, "%Y-%m-%d")
    while current <= end_dt:
        yield current
        current += timedelta(days=1)


def date_label(day_dt):
    return day_dt.strftime("%d/%m/%Y")


def resolve_period_dates(period, start_text, end_text, today=None):
    if not period:
        return normalize_date(start_text), normalize_date(end_text)

    # O runner do GitHub usa UTC; o período da planilha deve seguir o calendário
    # local de São Paulo para sempre fechar em ontem local.
    today = today or datetime.now(REPORTING_TIMEZONE)
    today = datetime(today.year, today.month, today.day)
    yesterday = today - timedelta(days=1)

    if period == "current_month_until_yesterday":
        if today.day == 1:
            end_dt = yesterday
            start_dt = datetime(end_dt.year, end_dt.month, 1)
        else:
            start_dt = datetime(today.year, today.month, 1)
            end_dt = yesterday
    elif period == "previous_month":
        first_current_month = datetime(today.year, today.month, 1)
        end_dt = first_current_month - timedelta(days=1)
        start_dt = datetime(end_dt.year, end_dt.month, 1)
    elif period == "last_7_days":
        end_dt = yesterday
        start_dt = end_dt - timedelta(days=6)
    elif period == "last_30_days":
        end_dt = yesterday
        start_dt = end_dt - timedelta(days=29)
    else:
        raise ValueError(f"Periodo automatico invalido: {period}")

    return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")


def date_label_from_sheet_serial(value):
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        serial = float(text.replace(",", "."))
    except ValueError:
        return text
    if not 30000 <= serial <= 70000:
        return text
    day_dt = datetime(1899, 12, 30) + timedelta(days=int(serial))
    return date_label(day_dt)


def normalize_sheet_date_value(value):
    text = str(value or "").strip()
    for date_format in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return date_label(datetime.strptime(text, date_format))
        except ValueError:
            continue
    return date_label_from_sheet_serial(text)


def format_duration(seconds):
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def print_slow_blocks(block_stats, limit):
    if not block_stats or limit <= 0:
        return
    slow_blocks = sorted(
        block_stats,
        key=lambda item: item["Segundos"],
        reverse=True,
    )[:limit]
    print("Blocos mais lentos:")
    for index, item in enumerate(slow_blocks, start=1):
        extra = ""
        if item.get("Redes") == "Instagram":
            extra = (
                f" | periodo={format_duration(item.get('InstagramPeriodoSegundos', 0))}"
                f" | diario={format_duration(item.get('InstagramDiarioSegundos', 0))}"
            )
        print(
            f"{index}. {item['Produto']} | {item['Redes']} | "
            f"{format_duration(item['Segundos'])} | "
            f"linhas={item['Linhas']} | puladas={item['Puladas']}"
            f"{extra}"
        )


def read_csv_rows(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def median_value(values):
    ordered = sorted(values)
    count = len(ordered)
    midpoint = count // 2
    if count % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


def estimate_rows_count(projects, networks_csv, start_iso, end_iso, existing_rows=None):
    days_count = sum(1 for _ in iter_days(start_iso, end_iso))
    networks = ordered_networks(networks_csv)
    if existing_rows:
        requested_keys = set()
        project_names = {project["name"].strip().lower() for project in projects}
        network_names = {NETWORKS.get(slug, slug).strip().lower() for slug in networks}
        date_labels = {date_label(day_dt) for day_dt in iter_days(start_iso, end_iso)}
        for row in existing_rows:
            if (
                str(row.get("Produto", "")).strip().lower() in project_names
                and str(row.get("Redes", "")).strip().lower() in network_names
                and row.get("Data") in date_labels
            ):
                requested_keys.add(row_key(row))
        if requested_keys:
            return len(requested_keys), days_count
    return len(projects) * len(networks) * days_count, days_count


def estimate_run_duration(history_path, args, estimated_rows, history_limit):
    history_rows = read_csv_rows(history_path)
    if not history_rows:
        return None

    candidates = [
        row for row in history_rows
        if row.get("mode") == args.mode
        and row.get("networks") == args.networks
        and row.get("skip_daily_only") == str(args.skip_daily_only)
        and safe_float(row.get("rows_fetched")) > 0
        and safe_float(row.get("elapsed_seconds")) > 0
    ]
    if not candidates:
        candidates = [
            row for row in history_rows
            if safe_float(row.get("rows_fetched")) > 0
            and safe_float(row.get("elapsed_seconds")) > 0
        ]
    candidates = candidates[-max(history_limit, 1):]
    if not candidates:
        return None

    seconds_per_row = [
        safe_float(row.get("elapsed_seconds")) / safe_float(row.get("rows_fetched"))
        for row in candidates
        if safe_float(row.get("rows_fetched")) > 0
    ]
    if not seconds_per_row:
        return None

    original_samples = len(seconds_per_row)
    if len(seconds_per_row) >= 4:
        median_seconds_per_row = median_value(seconds_per_row)
        outlier_limit = max(median_seconds_per_row * 4, median_seconds_per_row + 10)
        filtered_seconds_per_row = [
            value for value in seconds_per_row
            if value <= outlier_limit
        ]
        if len(filtered_seconds_per_row) >= 3:
            seconds_per_row = filtered_seconds_per_row

    avg_seconds_per_row = sum(seconds_per_row) / len(seconds_per_row)
    low_seconds = min(seconds_per_row) * estimated_rows
    high_seconds = max(seconds_per_row) * estimated_rows
    avg_seconds = avg_seconds_per_row * estimated_rows
    return {
        "samples": len(seconds_per_row),
        "low_seconds": low_seconds,
        "avg_seconds": avg_seconds,
        "high_seconds": high_seconds,
        "outliers_ignored": original_samples - len(seconds_per_row),
    }


def print_run_estimate(args, projects, start_iso, end_iso, existing_rows):
    estimated_rows, days_count = estimate_rows_count(
        projects,
        args.networks,
        start_iso,
        end_iso,
        existing_rows=existing_rows,
    )
    networks_count = len(ordered_networks(args.networks))
    estimate = estimate_run_duration(
        args.run_history,
        args,
        estimated_rows,
        args.estimate_history_limit,
    )
    print("Estimativa da execucao:")
    print(f"Periodo: {date_label(datetime.strptime(start_iso, '%Y-%m-%d'))} - {date_label(datetime.strptime(end_iso, '%Y-%m-%d'))}")
    print(f"Dias: {days_count}")
    print(f"Projetos: {len(projects)}")
    print(f"Redes solicitadas: {networks_count}")
    print(f"Linhas previstas: {estimated_rows}")
    if estimate:
        print(
            "Tempo estimado: "
            f"{format_duration(estimate['low_seconds'])} - {format_duration(estimate['high_seconds'])} "
            f"(media {format_duration(estimate['avg_seconds'])}, "
            f"{estimate['samples']} execucoes historicas"
            f"{', ' + str(estimate['outliers_ignored']) + ' outlier(s) ignorado(s)' if estimate.get('outliers_ignored') else ''})"
        )
    else:
        print("Tempo estimado: sem historico suficiente.")


def append_run_history(history_path, args, start_iso, end_iso, started_at, elapsed, projects_count, rows_count, final_rows_count, block_stats):
    if not history_path:
        return None
    path = Path(history_path)
    slowest = max(block_stats, key=lambda item: item["Segundos"]) if block_stats else {}
    row = {
        "executed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "start": date_label(datetime.strptime(start_iso, "%Y-%m-%d")),
        "end": date_label(datetime.strptime(end_iso, "%Y-%m-%d")),
        "mode": args.mode,
        "networks": args.networks,
        "project_names": args.project_names,
        "exclude_projects": args.exclude_projects,
        "skip_daily_only": args.skip_daily_only,
        "projects_count": projects_count,
        "rows_fetched": rows_count,
        "rows_final": final_rows_count,
        "elapsed_seconds": int(elapsed),
        "elapsed_label": format_duration(elapsed),
        "slowest_product": slowest.get("Produto", ""),
        "slowest_network": slowest.get("Redes", ""),
        "slowest_seconds": int(slowest.get("Segundos", 0)),
        "slowest_label": format_duration(slowest.get("Segundos", 0)) if slowest else "",
    }
    file_exists = path.exists()
    if str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(row.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
    return path


def append_block_history(block_history_path, args, start_iso, end_iso, block_stats):
    if not block_history_path or not block_stats:
        return None
    path = Path(block_history_path)
    if str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "executed_at",
        "start",
        "end",
        "mode",
        "produto",
        "rede",
        "linhas",
        "puladas",
        "segundos",
        "tempo",
        "instagram_period_seconds",
        "instagram_daily_seconds",
        "erro",
    ]
    executed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for item in block_stats:
            writer.writerow({
                "executed_at": executed_at,
                "start": date_label(datetime.strptime(start_iso, "%Y-%m-%d")),
                "end": date_label(datetime.strptime(end_iso, "%Y-%m-%d")),
                "mode": args.mode,
                "produto": item.get("Produto", ""),
                "rede": item.get("Redes", ""),
                "linhas": item.get("Linhas", 0),
                "puladas": item.get("Puladas", 0),
                "segundos": int(item.get("Segundos", 0)),
                "tempo": format_duration(item.get("Segundos", 0)),
                "instagram_period_seconds": int(item.get("InstagramPeriodoSegundos", 0)),
                "instagram_daily_seconds": int(item.get("InstagramDiarioSegundos", 0)),
                "erro": item.get("Erro", ""),
            })
    return path


def parse_csv_values(raw_value):
    return [item.strip() for item in str(raw_value or "").split(",") if item.strip()]


def ordered_networks(networks_csv):
    requested = parse_csv_values(networks_csv) or list(NETWORK_ORDER)
    ordered = [slug for slug in NETWORK_ORDER if slug in requested]
    ordered.extend(slug for slug in requested if slug not in ordered)
    return ordered


def apply_exclusions(projects, exclude_projects_csv):
    excluded = {item.lower() for item in parse_csv_values(exclude_projects_csv)}
    if not excluded:
        return projects
    return [
        project
        for project in projects
        if project.get("name", "").strip().lower() not in excluded
    ]


def make_cache_config(args):
    return {
        "enabled": args.use_cache,
        "refresh": args.refresh_cache,
        "ttl_seconds": max(args.cache_ttl_hours, 0) * 3600,
        "dir": Path(args.cache_dir),
    }


def cache_file_path(cache_config, key):
    safe_key = "".join(char if char.isalnum() or char in "._-" else "_" for char in key)
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


def cached_list_projects(client, cache_config):
    return cached_call(cache_config, "projects", lambda: list_projects(client))


def cached_get_integrations_by_slug(client, project_id, cache_config):
    return cached_call(
        cache_config,
        f"integrations_{project_id}",
        lambda: get_integrations_by_slug(client, project_id),
    )


def get_integrations_grouped_by_slug(client, project_id):
    response = client.list_integrations(project_id=project_id, per_page=100)
    grouped = {}
    for integration in response.get("data", []):
        network_slug = str(integration.get("slug", "")).strip()
        if network_slug:
            grouped.setdefault(network_slug, []).append(integration)
    return grouped


def cached_get_integrations_grouped_by_slug(client, project_id, cache_config):
    return cached_call(
        cache_config,
        f"integrations_grouped_v1_{project_id}",
        lambda: get_integrations_grouped_by_slug(client, project_id),
    )


def normalized_integration_name(value):
    return str(value or "").strip().casefold()


def select_integrations_for_export(
    project,
    network_slug,
    integrations_by_slug,
    grouped_integrations=None,
):
    project_name = normalized_integration_name(project.get("name"))
    required_names = COMBINED_NETWORK_INTEGRATIONS.get((project_name, network_slug))
    if not required_names:
        integration = integrations_by_slug.get(network_slug)
        return [integration] if integration else []

    available = (grouped_integrations or {}).get(network_slug, [])
    available_by_name = {
        normalized_integration_name(integration.get("name")): integration
        for integration in available
    }
    selected = [
        available_by_name[name]
        for name in required_names
        if name in available_by_name
    ]
    missing_names = [name for name in required_names if name not in available_by_name]
    if missing_names:
        raise ValueError(
            "Integracao(oes) obrigatoria(s) ausente(s): " + ", ".join(missing_names)
        )
    return selected


def cached_get_metric_definitions_map(client, network_slug, cache_config):
    return cached_call(
        cache_config,
        f"metrics_{network_slug}",
        lambda: get_metric_definitions_map(client, network_slug),
    )


def format_dashboard_value(value):
    if value == "N/D" or value is None:
        return ""
    return format_number(value)


def request_metrics_with_backoff(client, start, end, integration_id, metrics):
    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return client.get_metrics_data(
                start=start,
                end=end,
                integration_id=integration_id,
                metrics=metrics,
            )
        except Exception as exc:
            last_error = exc
            message = str(exc)
            if attempt >= RETRY_ATTEMPTS:
                break
            if "429" in message or "Too many requests" in message:
                time.sleep(RATE_LIMIT_DELAY_SECONDS * attempt)
            else:
                time.sleep(RETRY_DELAY_SECONDS * attempt)
    raise last_error


def fetch_metrics_batch(client, integration_id, metric_definitions, start, end):
    if not metric_definitions:
        return {}
    prepared = [prepare_metric_definition_for_request(item) for item in metric_definitions]
    response = request_metrics_with_backoff(client, start, end, integration_id, prepared)
    data = response.get("data", {})
    results = {}
    for metric_definition in prepared:
        metric_id = metric_definition["id"]
        payload = data.get(metric_id, {})
        results[metric_definition["reference_key"]] = {
            "reference_key": metric_definition["reference_key"],
            "value": extract_numeric_value(payload),
            "raw": {"data": {metric_id: payload}},
        }
    return results


def extract_numeric_value(payload):
    if isinstance(payload, (int, float)):
        return payload
    if isinstance(payload, str):
        normalized = payload.strip().replace(".", "").replace(",", ".")
        try:
            numeric = float(normalized)
        except ValueError:
            return None
        return int(numeric) if numeric.is_integer() else numeric
    if isinstance(payload, dict):
        for key in ["value", "values", "total", "count", "views", "reach", "impressions"]:
            value = payload.get(key)
            if isinstance(value, (int, float)):
                return value
            if isinstance(value, str):
                return extract_numeric_value(value)
        for value in payload.values():
            extracted = extract_numeric_value(value)
            if extracted is not None:
                return extracted
    if isinstance(payload, list):
        for item in payload:
            extracted = extract_numeric_value(item)
            if extracted is not None:
                return extracted
    return None


def metric_definitions_for_field(metric_map, field_config):
    if "note" in field_config:
        return []
    if "reference_key" in field_config:
        metric = metric_map.get(field_config["reference_key"])
        return [metric] if metric else []
    return [metric_map[key] for key in field_config["sum_of"] if key in metric_map]


def fetch_daily_network_fields(client, integration_id, metric_map, network_slug, day_iso):
    metric_definitions = []
    seen_reference_keys = set()
    for field_name in DASHBOARD_SUMMARY_FIELDS:
        field_config = DASHBOARD_SUMMARY_FIELDS[field_name].get(network_slug)
        if not field_config or "note" in field_config:
            continue
        for metric_definition in metric_definitions_for_field(metric_map, field_config):
            reference_key = metric_definition["reference_key"]
            if reference_key in seen_reference_keys:
                continue
            seen_reference_keys.add(reference_key)
            metric_definitions.append(metric_definition)

    batch = fetch_metrics_batch(
        client,
        integration_id,
        metric_definitions,
        day_iso,
        day_iso,
    )
    return {
        field_name: resolve_field_value_from_batch(batch, network_slug, field_name)
        for field_name in DASHBOARD_SUMMARY_FIELDS
    }


def resolve_field_value_from_batch(batch, network_slug, field_name):
    field_config = DASHBOARD_SUMMARY_FIELDS[field_name].get(network_slug)
    if not field_config:
        return "N/D"
    if "note" in field_config:
        return field_config["note"]
    if "reference_key" in field_config:
        value = batch.get(field_config["reference_key"], {}).get("value")
        return value if value is not None else "N/D"

    total = 0
    for reference_key in field_config["sum_of"]:
        value = batch.get(reference_key, {}).get("value")
        if not isinstance(value, (int, float)):
            return "N/D"
        total += value
    return total


def fetch_missing_daily_fields(client, integration_id, metric_map, network_slug, day_iso, field_names):
    metric_definitions = []
    seen_reference_keys = set()
    for field_name in field_names:
        field_config = DASHBOARD_SUMMARY_FIELDS[field_name].get(network_slug)
        if not field_config or "note" in field_config:
            continue
        for metric_definition in metric_definitions_for_field(metric_map, field_config):
            reference_key = metric_definition["reference_key"]
            if reference_key in seen_reference_keys:
                continue
            seen_reference_keys.add(reference_key)
            metric_definitions.append(metric_definition)

    batch = fetch_metrics_batch(
        client,
        integration_id,
        metric_definitions,
        day_iso,
        day_iso,
    )
    return {
        field_name: resolve_field_value_from_batch(batch, network_slug, field_name)
        for field_name in field_names
    }


def fetch_period_daily_values(client, integration_id, metric_map, start_iso, end_iso, period_fields):
    definitions = [
        metric_map[reference_key]
        for reference_key in period_fields.values()
        if reference_key in metric_map
    ]
    period_batch = fetch_metrics_batch(client, integration_id, definitions, start_iso, end_iso)
    daily_values = {}
    for field_name, reference_key in period_fields.items():
        result = period_batch.get(reference_key)
        daily_values[field_name] = extract_daily_series(result, start_iso)
    return daily_values


def sum_integration_values(values):
    if not values or any(not isinstance(value, (int, float)) for value in values):
        return "N/D"
    return sum(values)


def combine_integration_fields(field_sets, field_names):
    return {
        field_name: sum_integration_values([
            fields.get(field_name, "N/D")
            for fields in field_sets
        ])
        for field_name in field_names
    }


def fetch_daily_network_fields_for_integrations(
    client,
    integrations,
    metric_map,
    network_slug,
    day_iso,
):
    field_sets = [
        fetch_daily_network_fields(
            client,
            integration["id"],
            metric_map,
            network_slug,
            day_iso,
        )
        for integration in integrations
    ]
    return combine_integration_fields(field_sets, DASHBOARD_SUMMARY_FIELDS)


def fetch_missing_daily_fields_for_integrations(
    client,
    integrations,
    metric_map,
    network_slug,
    day_iso,
    field_names,
):
    field_sets = [
        fetch_missing_daily_fields(
            client,
            integration["id"],
            metric_map,
            network_slug,
            day_iso,
            field_names,
        )
        for integration in integrations
    ]
    return combine_integration_fields(field_sets, field_names)


def fetch_period_daily_values_for_integrations(
    client,
    integrations,
    metric_map,
    start_iso,
    end_iso,
    period_fields,
):
    values_by_integration = [
        fetch_period_daily_values(
            client,
            integration["id"],
            metric_map,
            start_iso,
            end_iso,
            period_fields,
        )
        for integration in integrations
    ]
    combined = {field_name: {} for field_name in period_fields}
    if not values_by_integration:
        return combined

    for field_name in period_fields:
        common_dates = set(values_by_integration[0].get(field_name, {}))
        for integration_values in values_by_integration[1:]:
            common_dates.intersection_update(integration_values.get(field_name, {}))
        for day_iso in common_dates:
            values = [
                integration_values[field_name][day_iso]
                for integration_values in values_by_integration
            ]
            total = sum_integration_values(values)
            if total != "N/D":
                combined[field_name][day_iso] = total
    return combined


def normalize_series_date_label(label):
    text = str(label or "").strip()
    if not text:
        return None
    candidates = [text[:10], text]
    for candidate in candidates:
        for date_format in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(candidate, date_format).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def extract_daily_series(result, start_iso):
    values_by_date = {}
    if not result:
        return values_by_date
    payloads = (result.get("raw") or {}).get("data") or {}
    if not payloads:
        return values_by_date
    payload = next(iter(payloads.values()))

    labels = payload.get("labels") if isinstance(payload, dict) else None
    values = payload.get("values") if isinstance(payload, dict) else None
    if isinstance(labels, list) and isinstance(values, list):
        series = next((item for item in values if isinstance(item, dict) and isinstance(item.get("data"), list)), None)
        if series:
            for index, label in enumerate(labels):
                date_text = normalize_series_date_label(label)
                if (
                    date_text
                    and index < len(series["data"])
                    and isinstance(series["data"][index], (int, float))
                ):
                    values_by_date[date_text] = series["data"][index]
            return values_by_date
        if all(isinstance(item, (int, float)) for item in values):
            for index, label in enumerate(labels):
                date_text = normalize_series_date_label(label)
                if date_text and index < len(values):
                    values_by_date[date_text] = values[index]
            return values_by_date

    trend_data = (payload.get("trend") or {}).get("data") if isinstance(payload, dict) else None
    if isinstance(trend_data, list):
        start_dt = datetime.strptime(start_iso, "%Y-%m-%d")
        for index, value in enumerate(trend_data):
            if isinstance(value, (int, float)):
                day_iso = (start_dt + timedelta(days=index)).strftime("%Y-%m-%d")
                values_by_date[day_iso] = value
    return values_by_date


def make_row_key(product_name, network_name, date_text):
    return (
        str(product_name or "").strip().lower(),
        str(network_name or "").strip().lower(),
        str(date_text or "").strip(),
    )


def network_slug_from_name(network_name):
    normalized = str(network_name or "").strip().lower()
    for slug, display_name in NETWORKS.items():
        if normalized in {slug.lower(), display_name.lower()}:
            return slug
    return normalized


def row_key(row):
    return make_row_key(row.get("Produto"), row.get("Redes"), row.get("Data"))


def is_complete_row(row):
    network_slug = network_slug_from_name(row.get("Redes"))
    for field_name in METRIC_FIELDNAMES:
        field_config = DASHBOARD_SUMMARY_FIELDS[field_name].get(network_slug, {})
        if "note" in field_config:
            continue
        if not str(row.get(field_name, "")).strip():
            return False
    return True


def build_target_key(project, network_slug, day_dt):
    return make_row_key(
        project["name"],
        NETWORKS.get(network_slug, network_slug),
        date_label(day_dt),
    )


def build_rows(
    projects,
    client,
    start_iso,
    end_iso,
    networks_csv,
    skip_daily_only=False,
    on_block_rows=None,
    cache_config=None,
    skip_row_keys=None,
    include_row_keys=None,
):
    rows = []
    block_stats = []
    target_keys = set()
    total_skipped_rows = 0
    cache_config = cache_config or {"enabled": False, "refresh": False}
    skip_row_keys = skip_row_keys or set()
    include_row_keys = set(include_row_keys) if include_row_keys is not None else None
    networks = ordered_networks(networks_csv)
    metric_maps = {}
    for network_slug in networks:
        metric_maps[network_slug] = cached_get_metric_definitions_map(
            client,
            network_slug,
            cache_config,
        )

    work_items = []
    for project in projects:
        integrations_by_slug = cached_get_integrations_by_slug(
            client,
            project["id"],
            cache_config,
        )
        grouped_integrations = None
        for network_slug in networks:
            combined_key = (
                normalized_integration_name(project.get("name")),
                network_slug,
            )
            selection_error = ""
            if combined_key in COMBINED_NETWORK_INTEGRATIONS:
                grouped_integrations = (
                    grouped_integrations
                    or cached_get_integrations_grouped_by_slug(
                        client,
                        project["id"],
                        cache_config,
                    )
                )
            try:
                selected_integrations = select_integrations_for_export(
                    project,
                    network_slug,
                    integrations_by_slug,
                    grouped_integrations,
                )
            except ValueError as exc:
                selected_integrations = []
                selection_error = str(exc)

            if not selected_integrations:
                block_days = list(iter_days(start_iso, end_iso))
                block_target_keys = [
                    build_target_key(project, network_slug, day_dt)
                    for day_dt in block_days
                ]
                relevant_keys = block_target_keys
                if include_row_keys is not None:
                    relevant_keys = [
                        key for key in block_target_keys
                        if key in include_row_keys
                    ]
                if relevant_keys:
                    message = selection_error or "Integracao ausente na Reportei"
                    print(
                        f"{message}: {project['name']} | "
                        f"{NETWORKS.get(network_slug, network_slug)} | "
                        f"{len(relevant_keys)} linha(s) existentes nao atualizadas."
                    )
                    block_stats.append({
                        "Produto": project["name"],
                        "Redes": NETWORKS.get(network_slug, network_slug),
                        "Linhas": 0,
                        "Puladas": len(relevant_keys),
                        "Segundos": 0,
                        "InstagramPeriodoSegundos": 0,
                        "InstagramDiarioSegundos": 0,
                        "Erro": message,
                    })
                    total_skipped_rows += len(relevant_keys)
                continue
            work_items.append({
                "project": project,
                "network_slug": network_slug,
                "integrations": selected_integrations,
            })

    total_steps = len(work_items)
    for current_step, work_item in enumerate(work_items, start=1):
        project = work_item["project"]
        network_slug = work_item["network_slug"]
        integrations = work_item["integrations"]

        progress_message = (
            f"[{current_step}/{total_steps}] "
            f"{project['name']} | {NETWORKS.get(network_slug, network_slug)}"
        )
        if len(integrations) > 1:
            integration_names = ", ".join(
                str(integration.get("name", integration.get("id", "")))
                for integration in integrations
            )
            progress_message += f" | contas combinadas: {integration_names}"
        print(progress_message)

        block_started_at = time.time()
        block_skipped_rows = 0
        instagram_period_seconds = 0
        instagram_daily_seconds = 0
        block_days = list(iter_days(start_iso, end_iso))
        block_target_keys = [
            build_target_key(project, network_slug, day_dt)
            for day_dt in block_days
        ]
        target_keys.update(block_target_keys)
        if include_row_keys is not None and not any(key in include_row_keys for key in block_target_keys):
            block_stats.append({
                "Produto": project["name"],
                "Redes": NETWORKS.get(network_slug, network_slug),
                "Linhas": 0,
                "Puladas": len(block_target_keys),
                "Segundos": time.time() - block_started_at,
            })
            total_skipped_rows += len(block_target_keys)
            continue
        if block_target_keys and all(key in skip_row_keys for key in block_target_keys):
            block_skipped_rows = len(block_target_keys)
            total_skipped_rows += block_skipped_rows
            block_stats.append({
                "Produto": project["name"],
                "Redes": NETWORKS.get(network_slug, network_slug),
                "Linhas": 0,
                "Puladas": block_skipped_rows,
                "Segundos": time.time() - block_started_at,
            })
            continue

        metric_map = metric_maps[network_slug]
        period_values = {}
        block_rows = []
        try:
            if network_slug == "facebook":
                period_values = fetch_period_daily_values_for_integrations(
                    client,
                    integrations,
                    metric_map,
                    start_iso,
                    end_iso,
                    FACEBOOK_PERIOD_DAILY_FIELDS,
                )
            elif network_slug == "instagram_business":
                instagram_period_started_at = time.time()
                period_values = fetch_period_daily_values_for_integrations(
                    client,
                    integrations,
                    metric_map,
                    start_iso,
                    end_iso,
                    INSTAGRAM_PERIOD_DAILY_FIELDS,
                )
                instagram_period_seconds = time.time() - instagram_period_started_at

            for day_dt in block_days:
                day_iso = day_dt.strftime("%Y-%m-%d")
                key = build_target_key(project, network_slug, day_dt)
                if include_row_keys is not None and key not in include_row_keys:
                    block_skipped_rows += 1
                    total_skipped_rows += 1
                    continue
                if key in skip_row_keys:
                    block_skipped_rows += 1
                    total_skipped_rows += 1
                    continue

                fields = {}
                for field_name, values_by_day in period_values.items():
                    value = values_by_day.get(day_iso)
                    if value is not None:
                        fields[field_name] = value

                missing_field_names = [
                    field_name
                    for field_name in DASHBOARD_SUMMARY_FIELDS
                    if field_name not in fields
                ]
                if network_slug == "facebook" and missing_field_names:
                    if skip_daily_only:
                        daily_fields_to_fetch = [
                            field_name
                            for field_name in missing_field_names
                            if field_name in FAST_MODE_KEEP_DAILY_FIELDS
                        ]
                        if daily_fields_to_fetch:
                            fields.update(fetch_missing_daily_fields_for_integrations(
                                client,
                                integrations,
                                metric_map,
                                network_slug,
                                day_iso,
                                daily_fields_to_fetch,
                            ))
                        fields.update({
                            field_name: "N/D"
                            for field_name in missing_field_names
                            if field_name not in fields
                        })
                    else:
                        fields.update(fetch_missing_daily_fields_for_integrations(
                            client,
                            integrations,
                            metric_map,
                            network_slug,
                            day_iso,
                            missing_field_names,
                        ))
                elif missing_field_names:
                    daily_started_at = time.time() if network_slug == "instagram_business" else None
                    if skip_daily_only:
                        daily_fields_to_fetch = [
                            field_name
                            for field_name in missing_field_names
                            if field_name in FAST_MODE_KEEP_DAILY_FIELDS
                        ]
                        if daily_fields_to_fetch:
                            fields.update(fetch_missing_daily_fields_for_integrations(
                                client,
                                integrations,
                                metric_map,
                                network_slug,
                                day_iso,
                                daily_fields_to_fetch,
                            ))
                        fields.update({
                            field_name: "N/D"
                            for field_name in missing_field_names
                            if field_name not in fields
                        })
                    else:
                        fields.update(fetch_daily_network_fields_for_integrations(
                            client,
                            integrations,
                            metric_map,
                            network_slug,
                            day_iso,
                        ))
                    if daily_started_at is not None:
                        instagram_daily_seconds += time.time() - daily_started_at

                block_rows.append({
                    "Produto": project["name"],
                    "Redes": NETWORKS.get(network_slug, network_slug),
                    "Data": date_label(day_dt),
                    "Seguidores": format_dashboard_value(fields["Seguidores"]),
                    "Visualizacoes": format_dashboard_value(fields["Visualizacoes"]),
                    "Publicacoes": format_dashboard_value(fields["Publicacoes"]),
                    "Engajamento": format_dashboard_value(fields["Engajamento"]),
                })
        except Exception as exc:
            error_message = str(exc).replace("\n", " ")[:500]
            print(
                "Bloco ignorado por erro na API: "
                f"{project['name']} | {NETWORKS.get(network_slug, network_slug)} | "
                f"{error_message}"
            )
            block_stats.append({
                "Produto": project["name"],
                "Redes": NETWORKS.get(network_slug, network_slug),
                "Linhas": len(block_rows),
                "Puladas": len(block_target_keys) - len(block_rows),
                "Segundos": time.time() - block_started_at,
                "InstagramPeriodoSegundos": instagram_period_seconds,
                "InstagramDiarioSegundos": instagram_daily_seconds,
                "Erro": error_message,
            })
            if block_rows:
                rows.extend(block_rows)
                if on_block_rows:
                    on_block_rows(block_rows)
            continue
        rows.extend(block_rows)
        if on_block_rows:
            on_block_rows(block_rows)
        block_stats.append({
            "Produto": project["name"],
            "Redes": NETWORKS.get(network_slug, network_slug),
            "Linhas": len(block_rows),
            "Puladas": block_skipped_rows,
            "Segundos": time.time() - block_started_at,
            "InstagramPeriodoSegundos": instagram_period_seconds,
            "InstagramDiarioSegundos": instagram_daily_seconds,
            "Erro": "",
        })
    if total_skipped_rows:
        print(f"Linhas puladas por incremental: {total_skipped_rows}")
    return rows, block_stats, target_keys


def write_csv(output_path, rows):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def normalize_sheet_cell(value):
    if value == "N/D":
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and all(char.isdigit() or char in ".," for char in stripped):
            normalized = stripped.replace(".", "").replace(",", ".")
            try:
                numeric = float(normalized)
            except ValueError:
                return value
            return int(numeric) if numeric.is_integer() else numeric
    return value


def rows_to_sheet_values(rows):
    values = [OUTPUT_FIELDNAMES]
    for row in rows:
        values.append([
            normalize_sheet_cell(row.get(field_name, ""))
            for field_name in OUTPUT_FIELDNAMES
        ])
    return values


def chunked(items, size):
    for index in range(0, len(items), size):
        yield items[index:index + size]


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


def sheet_values_to_rows(values):
    rows = []
    for sheet_index, values_row in enumerate(values[1:], start=2):
        row = {}
        for index, field_name in enumerate(OUTPUT_FIELDNAMES):
            value = values_row[index] if index < len(values_row) else ""
            if field_name == "Data":
                value = normalize_sheet_date_value(value)
            row[field_name] = value
        if any(str(value).strip() for value in row.values()):
            row["_sheet_row"] = sheet_index
            rows.append(row)
    return rows


def read_google_sheet_rows(spreadsheets, spreadsheet_id, worksheet_name):
    response = spreadsheets.values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{worksheet_name}!A:G",
    ).execute()
    values = response.get("values", [])
    if not values:
        return []
    return sheet_values_to_rows(values)


def repair_google_sheet_date_column(spreadsheets, spreadsheet_id, worksheet_name):
    response = spreadsheets.values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{worksheet_name}!C2:C",
        valueRenderOption="UNFORMATTED_VALUE",
        dateTimeRenderOption="SERIAL_NUMBER",
    ).execute()
    values = response.get("values", [])
    updates = []
    for offset, values_row in enumerate(values, start=2):
        current_value = values_row[0] if values_row else ""
        repaired_value = normalize_sheet_date_value(current_value)
        if repaired_value and repaired_value != str(current_value).strip():
            updates.append({
                "range": f"{worksheet_name}!C{offset}:C{offset}",
                "values": [[repaired_value]],
            })

    total_batches = (len(updates) + GOOGLE_VALUES_BATCH_SIZE - 1) // GOOGLE_VALUES_BATCH_SIZE
    for batch_index, batch_data in enumerate(chunked(updates, GOOGLE_VALUES_BATCH_SIZE), start=1):
        execute_google_request_with_backoff(
            lambda batch_data=batch_data: spreadsheets.values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "valueInputOption": "RAW",
                    "data": batch_data,
                },
            ),
            f"Reparo coluna Data lote {batch_index}/{total_batches}",
        )
    return len(updates)


def merge_incremental_rows(existing_rows, new_rows, target_keys, mode):
    if mode == "replace":
        return new_rows

    new_keys = {row_key(row) for row in new_rows}
    if mode == "fill_missing":
        rows_to_keep = [
            row for row in existing_rows
            if row_key(row) not in new_keys
        ]
    elif mode == "refresh_existing":
        rows_to_keep = [
            row for row in existing_rows
            if row_key(row) not in target_keys
        ]
    else:
        raise ValueError(f"Modo incremental invalido: {mode}")
    return rows_to_keep + new_rows


def existing_row_index_by_key(existing_rows):
    return {
        row_key(row): row
        for row in existing_rows
        if row.get("_sheet_row")
    }


def strip_internal_fields(row):
    return {
        field_name: row.get(field_name, "")
        for field_name in OUTPUT_FIELDNAMES
    }


def rows_without_internal_fields(rows):
    return [strip_internal_fields(row) for row in rows]


def parse_row_date(row):
    text = str(row.get("Data", "")).strip()
    for date_format in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            continue
    return datetime.max


def network_sort_index(network_name):
    by_name = {
        NETWORKS.get(slug, slug).lower(): index
        for index, slug in enumerate(NETWORK_ORDER)
    }
    return by_name.get(str(network_name or "").strip().lower(), len(NETWORK_ORDER))


def sort_rows(rows):
    return sorted(
        rows_without_internal_fields(rows),
        key=lambda row: (
            str(row.get("Produto", "")).strip().lower(),
            network_sort_index(row.get("Redes")),
            parse_row_date(row),
        ),
    )


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


def ensure_google_worksheet(spreadsheets, spreadsheet_id, worksheet_name, min_rows=1000):
    metadata = spreadsheets.get(spreadsheetId=spreadsheet_id).execute()
    worksheet_id = None
    for sheet in metadata.get("sheets", []):
        if sheet["properties"]["title"] == worksheet_name:
            worksheet_id = sheet["properties"]["sheetId"]
            break
    worksheet_exists = worksheet_id is not None
    if not worksheet_exists:
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
        worksheet_id = create_response["replies"][0]["addSheet"]["properties"]["sheetId"]
    return worksheet_id


def clear_google_sheet_values(spreadsheets, spreadsheet_id, worksheet_name):
    range_name = f"{worksheet_name}!A2:G"
    spreadsheets.values().clear(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        body={},
    ).execute()


def reset_google_sheet_format_(spreadsheets, spreadsheet_id, worksheet_id):
    spreadsheets.batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": worksheet_id,
                            "startRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": len(OUTPUT_FIELDNAMES),
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {"bold": False},
                                "numberFormat": {
                                    "type": "TEXT",
                                    "pattern": "@",
                                },
                            }
                        },
                        "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.numberFormat",
                    }
                }
            ]
        },
    ).execute()


def write_google_sheet_header(spreadsheets, spreadsheet_id, worksheet_name):
    spreadsheets.values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{worksheet_name}!A1",
        valueInputOption="RAW",
        body={"values": [OUTPUT_FIELDNAMES]},
    ).execute()


def append_google_sheet_rows(spreadsheets, spreadsheet_id, worksheet_name, rows):
    if not rows:
        return
    values = [
        [normalize_sheet_cell(row.get(field_name, "")) for field_name in OUTPUT_FIELDNAMES]
        for row in rows
    ]
    spreadsheets.values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{worksheet_name}!A:G",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": values},
    ).execute()


def update_existing_google_sheet_metric_rows(spreadsheets, spreadsheet_id, worksheet_name, existing_rows, rows):
    if not rows:
        return {
            "updated": 0,
            "missing": 0,
        }

    existing_by_key = existing_row_index_by_key(existing_rows)
    data = []
    missing = 0
    for row in rows:
        existing_row = existing_by_key.get(row_key(row))
        if not existing_row:
            missing += 1
            continue
        sheet_row = existing_row["_sheet_row"]
        data.append({
            "range": f"{worksheet_name}!D{sheet_row}:G{sheet_row}",
            "values": [[
                normalize_sheet_cell(row.get(field_name, ""))
                for field_name in METRIC_FIELDNAMES
            ]],
        })

    updated = 0
    total_batches = (len(data) + GOOGLE_VALUES_BATCH_SIZE - 1) // GOOGLE_VALUES_BATCH_SIZE
    for batch_index, batch_data in enumerate(chunked(data, GOOGLE_VALUES_BATCH_SIZE), start=1):
        execute_google_request_with_backoff(
            lambda batch_data=batch_data: spreadsheets.values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "valueInputOption": "RAW",
                    "data": batch_data,
                },
            ),
            f"Atualizacao Google Sheets D:G lote {batch_index}/{total_batches}",
        )
        updated += len(batch_data)
        if total_batches > 1:
            print(f"Google Sheets D:G: lote {batch_index}/{total_batches} atualizado.")
    return {
        "updated": updated,
        "missing": missing,
    }


def write_google_sheet(spreadsheet_id, worksheet_name, service_account_file, rows):
    spreadsheets = create_google_sheets_client(service_account_file)
    worksheet_id = ensure_google_worksheet(
        spreadsheets,
        spreadsheet_id,
        worksheet_name,
        min_rows=len(rows) + 1,
    )
    clear_google_sheet_values(spreadsheets, spreadsheet_id, worksheet_name)
    reset_google_sheet_format_(spreadsheets, spreadsheet_id, worksheet_id)
    spreadsheets.values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{worksheet_name}!A1",
        valueInputOption="RAW",
        body={"values": rows_to_sheet_values(rows)},
    ).execute()
    format_google_sheet_(spreadsheets, spreadsheet_id, worksheet_id, len(rows) + 1)


def prepare_live_google_sheet(spreadsheet_id, worksheet_name, service_account_file):
    spreadsheets = create_google_sheets_client(service_account_file)
    worksheet_id = ensure_google_worksheet(spreadsheets, spreadsheet_id, worksheet_name)
    clear_google_sheet_values(spreadsheets, spreadsheet_id, worksheet_name)
    reset_google_sheet_format_(spreadsheets, spreadsheet_id, worksheet_id)
    write_google_sheet_header(spreadsheets, spreadsheet_id, worksheet_name)
    format_google_sheet_(spreadsheets, spreadsheet_id, worksheet_id, 2)
    return {
        "spreadsheets": spreadsheets,
        "spreadsheet_id": spreadsheet_id,
        "worksheet_name": worksheet_name,
        "worksheet_id": worksheet_id,
        "written_rows": 0,
    }


def append_live_google_sheet(live_writer, rows):
    append_google_sheet_rows(
        live_writer["spreadsheets"],
        live_writer["spreadsheet_id"],
        live_writer["worksheet_name"],
        rows,
    )
    live_writer["written_rows"] += len(rows)
    format_google_sheet_(
        live_writer["spreadsheets"],
        live_writer["spreadsheet_id"],
        live_writer["worksheet_id"],
        live_writer["written_rows"] + 1,
    )


def format_google_sheet_(spreadsheets, spreadsheet_id, worksheet_id, row_count, format_date_column=True):
    requests = [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": worksheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": max(row_count, 2),
                            "startColumnIndex": 0,
                            "endColumnIndex": len(OUTPUT_FIELDNAMES),
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {"bold": False}
                            }
                        },
                        "fields": "userEnteredFormat.textFormat.bold",
                    }
                },
    ]
    if format_date_column:
        requests.append(
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
                                "textFormat": {"bold": True}
                            }
                        },
                        "fields": "userEnteredFormat.textFormat.bold",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": worksheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": max(row_count, 2),
                            "startColumnIndex": 2,
                            "endColumnIndex": 3,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "TEXT",
                                    "pattern": "@",
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                }
        )
    requests.extend([
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": worksheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": max(row_count, 2),
                            "startColumnIndex": 3,
                            "endColumnIndex": 7,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "NUMBER",
                                    "pattern": "#,##0",
                                }
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
    ])
    spreadsheets.batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": requests
        },
    ).execute()


def main():
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()

    start_iso, end_iso = resolve_period_dates(args.period, args.start, args.end)
    if datetime.strptime(start_iso, "%Y-%m-%d") > datetime.strptime(end_iso, "%Y-%m-%d"):
        raise SystemExit("A data inicial nao pode ser maior que a data final.")
    if args.period:
        print(
            f"Periodo automatico {args.period}: "
            f"{date_label(datetime.strptime(start_iso, '%Y-%m-%d'))} - "
            f"{date_label(datetime.strptime(end_iso, '%Y-%m-%d'))}"
        )

    should_write_google_sheet = bool(args.google_sheet_id and not args.csv_only)
    should_write_csv = args.csv_only or args.save_csv
    if args.mode != "replace" and not should_write_google_sheet:
        raise SystemExit("Modo incremental precisa de Google Sheet configurada.")

    if args.repair_date_column:
        if not should_write_google_sheet:
            raise SystemExit("Reparo de datas precisa de Google Sheet configurada.")
        spreadsheets = create_google_sheets_client(args.service_account_file)
        ensure_google_worksheet(spreadsheets, args.google_sheet_id, args.worksheet)
        repaired_count = repair_google_sheet_date_column(
            spreadsheets,
            args.google_sheet_id,
            args.worksheet,
        )
        print(f"Datas reparadas na coluna C: {repaired_count}")
        return

    client = get_client()
    cache_config = make_cache_config(args)
    projects = filter_projects(cached_list_projects(client, cache_config), args.project_names)
    projects = apply_exclusions(projects, args.exclude_projects)
    if not projects:
        raise SystemExit("Nenhum projeto encontrado para exportacao.")

    started_at = time.time()
    live_writer = None
    existing_rows = []
    skip_row_keys = set()
    include_row_keys = None
    update_result = None
    worksheet_id = None

    if args.mode == "refresh_existing" and args.live_write:
        print("Live write desativado no refresh_existing para preservar merge seguro.")
        args.live_write = False

    if args.mode != "replace":
        spreadsheets = create_google_sheets_client(args.service_account_file)
        worksheet_id = ensure_google_worksheet(spreadsheets, args.google_sheet_id, args.worksheet)
        existing_rows = read_google_sheet_rows(
            spreadsheets,
            args.google_sheet_id,
            args.worksheet,
        )
        existing_keys = {row_key(row) for row in existing_rows}
        if args.mode in {"update_values", "fill_missing"}:
            include_row_keys = existing_keys
        if args.mode == "fill_missing":
            skip_row_keys = {
                row_key(row)
                for row in existing_rows
                if is_complete_row(row)
            }
        print(f"Linhas existentes na Google Sheet: {len(existing_rows)}")

    print_run_estimate(args, projects, start_iso, end_iso, existing_rows)

    if should_write_google_sheet and args.live_write and args.mode == "replace":
        live_writer = prepare_live_google_sheet(
            args.google_sheet_id,
            args.worksheet,
            args.service_account_file,
        )

    live_update_totals = {
        "updated": 0,
        "missing": 0,
    }

    def handle_block_rows(block_rows):
        if not block_rows:
            return
        if live_writer:
            append_live_google_sheet(live_writer, block_rows)
            return
        if args.mode in {"update_values", "fill_missing"} and args.live_write:
            result = update_existing_google_sheet_metric_rows(
                spreadsheets,
                args.google_sheet_id,
                args.worksheet,
                existing_rows,
                block_rows,
            )
            live_update_totals["updated"] += result["updated"]
            live_update_totals["missing"] += result["missing"]
            print(
                f"Google Sheet atualizada em tempo real: "
                f"{result['updated']} linha(s) neste bloco."
            )

    rows, block_stats, target_keys = build_rows(
        projects,
        client,
        start_iso,
        end_iso,
        args.networks,
        skip_daily_only=args.skip_daily_only,
        cache_config=cache_config,
        skip_row_keys=skip_row_keys,
        include_row_keys=include_row_keys,
        on_block_rows=handle_block_rows if args.live_write else None,
    )
    final_rows = rows_without_internal_fields(rows)
    if args.mode in {"fill_missing", "update_values"}:
        if args.live_write:
            update_result = live_update_totals
        else:
            update_result = update_existing_google_sheet_metric_rows(
                spreadsheets,
                args.google_sheet_id,
                args.worksheet,
                existing_rows,
                rows,
            )
        format_google_sheet_(
            spreadsheets,
            args.google_sheet_id,
            worksheet_id,
            max(len(existing_rows) + 1, 2),
            format_date_column=False,
        )
    elif args.mode == "refresh_existing":
        final_rows = sort_rows(
            merge_incremental_rows(existing_rows, rows, target_keys, args.mode)
        )

    output_path = Path(args.output)
    if should_write_csv:
        write_csv(output_path, final_rows)
    if should_write_google_sheet and not args.live_write and args.mode in {"replace", "refresh_existing"}:
        write_google_sheet(
            args.google_sheet_id,
            args.worksheet,
            args.service_account_file,
            final_rows,
        )

    elapsed = time.time() - started_at
    final_rows_count = len(final_rows)
    if args.mode in {"update_values", "fill_missing"} and existing_rows:
        final_rows_count = len(existing_rows)
    history_path = append_run_history(
        args.run_history,
        args,
        start_iso,
        end_iso,
        started_at,
        elapsed,
        len(projects),
        len(rows),
        final_rows_count,
        block_stats,
    )
    block_history_path = append_block_history(
        args.block_history,
        args,
        start_iso,
        end_iso,
        block_stats,
    )
    print(f"Projetos: {len(projects)}")
    print(f"Linhas buscadas: {len(rows)}")
    if update_result:
        print(f"Linhas atualizadas na Google Sheet: {update_result['updated']}")
        if update_result["missing"]:
            print(f"Linhas sem correspondencia na Google Sheet: {update_result['missing']}")
    elif args.mode != "replace":
        print(f"Linhas finais na base: {len(final_rows)}")
    print(f"Tempo total: {format_duration(elapsed)}")
    print_slow_blocks(block_stats, args.top_slow_blocks)
    if should_write_csv:
        print(f"CSV: {output_path.resolve()}")
    if should_write_google_sheet:
        print(f"Google Sheet atualizada: {args.google_sheet_id} / {args.worksheet}")
    if history_path:
        print(f"Historico atualizado: {history_path.resolve()}")
    if block_history_path:
        print(f"Historico por bloco atualizado: {block_history_path.resolve()}")


if __name__ == "__main__":
    main()

