import argparse
import csv
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from main import ReporteiClient


DEFAULT_OUTPUT = str(Path.home() / "Downloads" / "reportei_metrics_history.csv")
DEFAULT_EXPORT_START_DATE = "01/04/2026"
DEFAULT_EXPORT_END_DATE = "30/04/2026"
DEFAULT_EXPORT_PROJECT_NAMES = "Canal Rural"
DEFAULT_NETWORKS = "facebook,instagram_business,linkedin,tiktok,youtube"
ESTIMATED_SECONDS_PER_PROJECT = 40

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

SUMMARY_FIELDS = {
    "Seguidores": {
        "facebook": {"reference_key": "fb:page_follows"},
        "instagram_business": {"reference_key": "ig:current_followers_count"},
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
        "youtube": {
            "sum_of": [
                "youtube:likes",
                "youtube:comments",
                "youtube:shares",
            ]
        },
        "linkedin": {"reference_key": "li:engagement"},
        "tiktok": {
            "sum_of": [
                "tiktok:likes",
                "tiktok:comments",
                "tiktok:share",
            ]
        },
    },
    "Publicacoes": {
        "facebook": {"reference_key": "fb:page_posts_count"},
        "instagram_business": {
            "sum_of": [
                "ig:media_count",
                "ig:stories_count",
            ]
        },
        "youtube": {"note": "N/D"},
        "linkedin": {"reference_key": "li:posts_total"},
        "tiktok": {"reference_key": "tiktok:video_count"},
    },
}

REQUEST_METRIC_OVERRIDES = {
    "fb:page_posts_count": {
        "component": "number_v1",
        "metrics": ["page_posts_count"],
        "type": ["total_posts_count"],
    },
}
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2


def build_parser():
    parser = argparse.ArgumentParser(
        description="Exporta metricas de todos os projetos da Reportei para CSV."
    )
    parser.add_argument(
        "--start",
        default=DEFAULT_EXPORT_START_DATE,
        help="Data inicial em DD/MM/YYYY ou YYYY-MM-DD",
    )
    parser.add_argument(
        "--end",
        default=DEFAULT_EXPORT_END_DATE,
        help="Data final em DD/MM/YYYY ou YYYY-MM-DD",
    )
    parser.add_argument(
        "--networks",
        default=DEFAULT_NETWORKS,
        help="Slugs das redes separados por virgula.",
    )
    parser.add_argument(
        "--project-names",
        default=DEFAULT_EXPORT_PROJECT_NAMES,
        help="Lista de projetos separados por virgula. Vazio = todos os projetos.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Caminho do CSV historico de saida.",
    )
    return parser


def get_client():
    load_dotenv()
    token = os.getenv("REPORTEI_TOKEN")
    return ReporteiClient(token, timeout=90)


def normalize_date(date_text):
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_text, fmt).strftime("%Y-%m-%d")
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


def format_period_label(start_text, end_text):
    start_iso = normalize_date(start_text)
    end_iso = normalize_date(end_text)
    start_dt = datetime.strptime(start_iso, "%Y-%m-%d")
    end_dt = datetime.strptime(end_iso, "%Y-%m-%d")
    return f"{start_dt.strftime('%d/%m')} - {end_dt.strftime('%d/%m')}"


def truncate_text(text, max_length=180):
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def list_projects(client):
    response = client.list_projects(per_page=100)
    return response.get("data", [])


def filter_projects(projects, project_names_csv):
    if not project_names_csv:
        return sorted(projects, key=lambda project: project["name"].strip().lower())

    requested_names = [
        item.strip() for item in project_names_csv.split(",") if item.strip()
    ]
    requested_names_lower = {name.lower() for name in requested_names}
    filtered_projects = [
        project
        for project in projects
        if project["name"].strip().lower() in requested_names_lower
    ]

    found_names_lower = {
        project["name"].strip().lower() for project in filtered_projects
    }
    missing_names = [
        name for name in requested_names if name.lower() not in found_names_lower
    ]
    if missing_names:
        raise ValueError(
            "Projeto(s) nao encontrado(s): " + ", ".join(missing_names)
        )

    return sorted(
        filtered_projects, key=lambda project: project["name"].strip().lower()
    )


def get_integrations_by_slug(client, project_id):
    response = client.list_integrations(project_id=project_id, per_page=100)
    integrations = response.get("data", [])
    return {item["slug"]: item for item in integrations}


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


def extract_numeric_value(payload):
    if isinstance(payload, (int, float)):
        return payload
    if isinstance(payload, str):
        normalized = payload.strip().replace(".", "").replace(",", ".")
        try:
            numeric_value = float(normalized)
        except ValueError:
            return None
        if numeric_value.is_integer():
            return int(numeric_value)
        return numeric_value
    if isinstance(payload, dict):
        preferred_keys = ["value", "values", "total", "count", "views", "reach", "impressions"]
        for key in preferred_keys:
            value = payload.get(key)
            if isinstance(value, (int, float)):
                return value
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


def request_metrics_with_retry(client, start, end, integration_id, metrics):
    last_exception = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return client.get_metrics_data(
                start=start,
                end=end,
                integration_id=integration_id,
                metrics=metrics,
            )
        except Exception as exc:
            last_exception = exc
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)
    raise last_exception


def fetch_metrics_batch(
    client,
    integration_id,
    metric_definitions,
    start,
    end,
):
    if not metric_definitions:
        return {}

    prepared_metric_definitions = [
        prepare_metric_definition_for_request(metric_definition)
        for metric_definition in metric_definitions
    ]

    def fetch_single_metric(metric_definition):
        response = request_metrics_with_retry(
            client=client,
            start=start,
            end=end,
            integration_id=integration_id,
            metrics=[metric_definition],
        )
        data = response.get("data", {})
        metric_id = metric_definition["id"]
        metric_payload = data.get(metric_id, {})
        return {
            "reference_key": metric_definition["reference_key"],
            "value": extract_numeric_value(metric_payload),
            "raw": {"data": {metric_id: metric_payload}},
        }

    try:
        response = request_metrics_with_retry(
            client=client,
            start=start,
            end=end,
            integration_id=integration_id,
            metrics=prepared_metric_definitions,
        )
        data = response.get("data", {})
        results = {}
        for metric_definition in prepared_metric_definitions:
            metric_id = metric_definition["id"]
            metric_payload = data.get(metric_id, {})
            extracted_value = extract_numeric_value(metric_payload)

            # The batch endpoint can return 200 while skipping one metric.
            # Retry the missing metric individually before accepting N/D.
            if metric_payload in ({}, None) or extracted_value is None:
                try:
                    results[metric_definition["reference_key"]] = fetch_single_metric(
                        metric_definition
                    )
                except Exception as exc:
                    results[metric_definition["reference_key"]] = {
                        "reference_key": metric_definition["reference_key"],
                        "value": "N/D",
                        "raw": {"error": str(exc)},
                    }
                continue

            results[metric_definition["reference_key"]] = {
                "reference_key": metric_definition["reference_key"],
                "value": extracted_value,
                "raw": {"data": {metric_id: metric_payload}},
            }
        return results
    except Exception:
        results = {}
        for metric_definition in prepared_metric_definitions:
            try:
                results[metric_definition["reference_key"]] = fetch_single_metric(
                    metric_definition
                )
            except Exception as exc:
                results[metric_definition["reference_key"]] = {
                    "reference_key": metric_definition["reference_key"],
                    "value": "N/D",
                    "raw": {"error": str(exc)},
                }
        return results


def fetch_summary_field(batch_results, field_config):
    if "note" in field_config:
        return {
            "value": field_config["note"],
            "raw": {"note": field_config["note"]},
            "reference_keys": [],
        }
    if "reference_key" in field_config:
        reference_key = field_config["reference_key"]
        result = batch_results.get(
            reference_key,
            {
                "reference_key": reference_key,
                "value": "N/D",
                "raw": {"error": "metrica nao retornada pela API"},
            },
        )
        return {
            "value": result["value"],
            "raw": result["raw"],
            "reference_keys": [result["reference_key"]],
        }
    if "sum_of" in field_config:
        total = 0
        raw_items = []
        for reference_key in field_config["sum_of"]:
            result = batch_results.get(
                reference_key,
                {
                    "reference_key": reference_key,
                    "value": "N/D",
                    "raw": {"error": "metrica nao retornada pela API"},
                },
            )
            raw_items.append(result)
            if not isinstance(result["value"], (int, float)):
                return {
                    "value": "N/D",
                    "raw": raw_items,
                    "reference_keys": [item["reference_key"] for item in raw_items],
                }
            total += result["value"]
        return {
            "value": total,
            "raw": raw_items,
            "reference_keys": [item["reference_key"] for item in raw_items],
        }
    raise ValueError("Configuracao de metrica invalida.")


def extract_metric_errors(raw_payload):
    errors = []
    if isinstance(raw_payload, dict):
        error_text = raw_payload.get("error")
        if isinstance(error_text, str) and error_text.strip():
            errors.append(error_text.strip())
        for value in raw_payload.values():
            errors.extend(extract_metric_errors(value))
    elif isinstance(raw_payload, list):
        for item in raw_payload:
            errors.extend(extract_metric_errors(item))
    return list(dict.fromkeys(errors))


def collect_project_results(client, project, start, end, networks_csv):
    integrations_by_slug = get_integrations_by_slug(client, project["id"])
    requested_networks = [item.strip() for item in networks_csv.split(",") if item.strip()]
    ordered_networks = [slug for slug in NETWORK_ORDER if slug in requested_networks]
    ordered_networks.extend(slug for slug in requested_networks if slug not in ordered_networks)

    results = []
    for network_slug in ordered_networks:
        integration = integrations_by_slug.get(network_slug)
        if not integration:
            continue

        metric_definitions = get_metric_definitions_map(client, network_slug)
        required_reference_keys = []
        for field_network_map in SUMMARY_FIELDS.values():
            field_config = field_network_map.get(network_slug)
            if not field_config or "note" in field_config:
                continue
            if "reference_key" in field_config:
                required_reference_keys.append(field_config["reference_key"])
            else:
                required_reference_keys.extend(field_config["sum_of"])

        unique_reference_keys = list(dict.fromkeys(required_reference_keys))
        metric_definitions_batch = [
            metric_definitions[reference_key]
            for reference_key in unique_reference_keys
            if reference_key in metric_definitions
        ]

        batch_results = fetch_metrics_batch(
            client=client,
            integration_id=integration["id"],
            metric_definitions=metric_definitions_batch,
            start=start,
            end=end,
        )

        fields = {}
        for field_name, field_network_map in SUMMARY_FIELDS.items():
            field_config = field_network_map.get(network_slug)
            if not field_config:
                continue
            fields[field_name] = fetch_summary_field(batch_results, field_config)
            if fields[field_name]["value"] == "N/D":
                error_messages = extract_metric_errors(fields[field_name]["raw"])
                if error_messages:
                    print(
                        "Aviso: "
                        f'{project["name"]} | {NETWORKS.get(network_slug, network_slug)} | '
                        f"{field_name} ficou N/D. Motivo: "
                        f"{truncate_text(error_messages[0])}"
                    )

        results.append(
            {
                "network_slug": network_slug,
                "network_name": NETWORKS.get(network_slug, network_slug),
                "integration_id": integration["id"],
                "fields": fields,
            }
        )

    return results


def build_rows(projects, client, start_text, end_text, start_iso, end_iso, networks_csv):
    period_label = format_period_label(start_text, end_text)
    rows = []
    for project in projects:
        results = collect_project_results(
            client=client,
            project=project,
            start=start_iso,
            end=end_iso,
            networks_csv=networks_csv,
        )
        for network_result in results:
            row = {
                "Produto": project["name"],
                "Redes": network_result["network_name"],
                "Data": period_label,
            }
            for metric_name in SUMMARY_FIELDS:
                metric_data = network_result["fields"].get(
                    metric_name,
                    {"value": "N/D"},
                )
                row[metric_name] = format_number(metric_data["value"])
            rows.append(row)
    return rows


def read_existing_rows(output_path):
    if not output_path.exists():
        return []
    with output_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))
    if not rows:
        return []

    required_columns = {"Produto", "Redes", "Data"}
    if not required_columns.issubset(rows[0].keys()):
        print(
            "Formato antigo de CSV detectado. "
            "Ignorando linhas antigas para usar o novo layout de exportacao."
        )
        return []

    return rows


def upsert_rows(existing_rows, new_rows):
    merged = {}
    for row in existing_rows:
        key = (
            row["Data"],
            row["Produto"],
            row["Redes"],
        )
        merged[key] = row
    for row in new_rows:
        key = (
            row["Data"],
            row["Produto"],
            row["Redes"],
        )
        merged[key] = row
    return sorted(
        merged.values(),
        key=lambda row: (
            row["Data"],
            row["Produto"].lower(),
            row["Redes"].lower(),
        ),
    )


def write_rows(output_path, rows):
    fieldnames = [
        "Produto",
        "Redes",
        "Data",
        "Seguidores",
        "Visualizacoes",
        "Publicacoes",
        "Engajamento",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def format_duration(seconds):
    minutes, remaining_seconds = divmod(int(seconds), 60)
    if minutes == 0:
        return f"{remaining_seconds}s"
    return f"{minutes}m {remaining_seconds}s"


def main():
    parser = build_parser()
    args = parser.parse_args()

    client = get_client()
    start_iso = normalize_date(args.start)
    end_iso = normalize_date(args.end)
    projects = filter_projects(list_projects(client), args.project_names)

    if not projects:
        raise SystemExit("Nenhum projeto encontrado para exportacao.")

    estimated_total_seconds = len(projects) * ESTIMATED_SECONDS_PER_PROJECT
    print(
        "Tempo estimado para finalizar: "
        f"{format_duration(estimated_total_seconds)} "
        f"para {len(projects)} projeto(s)."
    )

    new_rows = build_rows(
        projects=projects,
        client=client,
        start_text=args.start,
        end_text=args.end,
        start_iso=start_iso,
        end_iso=end_iso,
        networks_csv=args.networks,
    )

    output_path = Path(args.output)
    existing_rows = read_existing_rows(output_path)
    final_rows = upsert_rows(existing_rows, new_rows)
    write_rows(output_path, final_rows)

    print(f"Projetos exportados: {len(projects)}")
    print(f"Linhas desta execucao: {len(new_rows)}")
    print(f"CSV atualizado: {output_path.resolve()}")


if __name__ == "__main__":
    main()
