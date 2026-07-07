import argparse
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


BASE_URL = "https://app.reportei.com/api/v2"


class ReporteiClient:
    def __init__(self, token, base_url=BASE_URL, timeout=30):
        if not token:
            raise ValueError("Token nao encontrado no arquivo .env")

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )

    def _request(self, method, path, params=None, json_body=None):
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = self.session.request(
            method=method,
            url=url,
            params=params,
            json=json_body,
            timeout=self.timeout,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            error_body = response.text
            try:
                error_body = json.dumps(response.json(), ensure_ascii=False)
            except ValueError:
                pass
            raise RuntimeError(
                f"Erro na API Reportei ({response.status_code}) em {path}: {error_body}"
            ) from exc
        return response.json()

    def get_company_settings(self):
        return self._request("GET", "/companies/settings")

    def list_projects(self, page=1, per_page=100, **filters):
        params = {"page": page, "per_page": per_page, **filters}
        return self._request("GET", "/projects", params=params)

    def get_project(self, project_id):
        return self._request("GET", f"/projects/{project_id}")

    def list_integrations(self, page=1, per_page=100, **filters):
        params = {"page": page, "per_page": per_page, **filters}
        return self._request("GET", "/integrations", params=params)

    def get_integration(self, integration_id):
        return self._request("GET", f"/integrations/{integration_id}")

    def list_metrics(self, integration_slug, page=1, per_page=100, **filters):
        params = {
            "integration_slug": integration_slug,
            "page": page,
            "per_page": per_page,
            **filters,
        }
        return self._request("GET", "/metrics", params=params)

    def get_metrics_data(
        self,
        start,
        end,
        integration_id,
        metrics,
        comparison_start=None,
        comparison_end=None,
    ):
        payload = {
            "start": start,
            "end": end,
            "integration_id": integration_id,
            "metrics": metrics,
        }
        if comparison_start:
            payload["comparison_start"] = comparison_start
        if comparison_end:
            payload["comparison_end"] = comparison_end
        return self._request("POST", "/metrics/get-data", json_body=payload)

    def list_templates(self, page=1, per_page=100):
        params = {"page": page, "per_page": per_page}
        return self._request("GET", "/templates", params=params)

    def get_template(self, template_id):
        return self._request("GET", f"/templates/{template_id}")

    def list_reports(self, page=1, per_page=100, **filters):
        params = {"page": page, "per_page": per_page, **filters}
        return self._request("GET", "/reports", params=params)

    def get_report(self, report_id):
        return self._request("GET", f"/reports/{report_id}")

    def create_report(
        self,
        title,
        subtitle,
        start,
        end,
        template_id,
        integration_ids,
        project_id,
        comparison_start=None,
        comparison_end=None,
    ):
        payload = {
            "title": title,
            "subtitle": subtitle,
            "start": start,
            "end": end,
            "template_id": template_id,
            "integration_ids": integration_ids,
            "project_id": project_id,
        }
        if comparison_start:
            payload["comparison_start"] = comparison_start
        if comparison_end:
            payload["comparison_end"] = comparison_end
        return self._request("POST", "/reports", json_body=payload)

    def list_dashboards(self, page=1, per_page=100, **filters):
        params = {"page": page, "per_page": per_page, **filters}
        return self._request("GET", "/dashboards", params=params)

    def get_dashboard(self, dashboard_id):
        return self._request("GET", f"/dashboards/{dashboard_id}")

    def create_dashboard(self, payload):
        return self._request("POST", "/dashboards", json_body=payload)

    def list_webhooks(self, page=1, per_page=100, **filters):
        params = {"page": page, "per_page": per_page, **filters}
        return self._request("GET", "/webhooks", params=params)

    def get_webhook(self, webhook_id):
        return self._request("GET", f"/webhooks/{webhook_id}")

    def create_webhook(self, payload):
        return self._request("POST", "/webhooks", json_body=payload)

    def update_webhook(self, webhook_id, payload):
        return self._request("PUT", f"/webhooks/{webhook_id}", json_body=payload)

    def delete_webhook(self, webhook_id):
        return self._request("DELETE", f"/webhooks/{webhook_id}")

    def list_timeline_events(self, page=1, per_page=100, **filters):
        params = {"page": page, "per_page": per_page, **filters}
        return self._request("GET", "/timeline-events", params=params)

    def get_timeline_event(self, timeline_event_id):
        return self._request("GET", f"/timeline-events/{timeline_event_id}")

    def create_timeline_event(self, payload):
        return self._request("POST", "/timeline-events", json_body=payload)

    def update_timeline_event(self, timeline_event_id, payload):
        return self._request(
            "PUT",
            f"/timeline-events/{timeline_event_id}",
            json_body=payload,
        )

    def delete_timeline_event(self, timeline_event_id):
        return self._request("DELETE", f"/timeline-events/{timeline_event_id}")


def build_parser():
    parser = argparse.ArgumentParser(
        description="CLI para automacoes com a API Reportei V2."
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Formata a saida JSON para leitura humana.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("settings", help="Busca os dados da company autenticada.")

    projects_parser = subparsers.add_parser("projects", help="Lista ou detalha projetos.")
    projects_parser.add_argument("--id", type=int, help="ID de um projeto especifico.")
    projects_parser.add_argument("--page", type=int, default=1)
    projects_parser.add_argument("--per-page", type=int, default=100)
    projects_parser.add_argument("--q")

    integrations_parser = subparsers.add_parser(
        "integrations", help="Lista ou detalha integracoes."
    )
    integrations_parser.add_argument("--id", type=int, help="ID de uma integracao.")
    integrations_parser.add_argument("--project-id", type=int)
    integrations_parser.add_argument("--slug")
    integrations_parser.add_argument("--name")
    integrations_parser.add_argument("--page", type=int, default=1)
    integrations_parser.add_argument("--per-page", type=int, default=100)

    templates_parser = subparsers.add_parser(
        "templates", help="Lista ou detalha templates."
    )
    templates_parser.add_argument("--id", type=int, help="ID de um template.")
    templates_parser.add_argument("--page", type=int, default=1)
    templates_parser.add_argument("--per-page", type=int, default=100)

    reports_parser = subparsers.add_parser("reports", help="Lista ou detalha relatorios.")
    reports_parser.add_argument("--id", type=int, help="ID de um relatorio.")
    reports_parser.add_argument("--project-id", type=int)
    reports_parser.add_argument("--created-at")
    reports_parser.add_argument("--updated-at")
    reports_parser.add_argument("--page", type=int, default=1)
    reports_parser.add_argument("--per-page", type=int, default=100)

    create_report_parser = subparsers.add_parser(
        "create-report", help="Cria um novo relatorio."
    )
    create_report_parser.add_argument("--title", required=True)
    create_report_parser.add_argument("--subtitle", required=True)
    create_report_parser.add_argument("--start", required=True)
    create_report_parser.add_argument("--end", required=True)
    create_report_parser.add_argument("--template-id", type=int, required=True)
    create_report_parser.add_argument("--project-id", type=int, required=True)
    create_report_parser.add_argument(
        "--integration-ids",
        required=True,
        help="Lista separada por virgula. Exemplo: 10,12,13",
    )
    create_report_parser.add_argument("--comparison-start")
    create_report_parser.add_argument("--comparison-end")

    metrics_parser = subparsers.add_parser(
        "metrics", help="Lista metricas disponiveis para um slug."
    )
    metrics_parser.add_argument("--integration-slug", required=True)
    metrics_parser.add_argument("--page", type=int, default=1)
    metrics_parser.add_argument("--per-page", type=int, default=100)

    metrics_data_parser = subparsers.add_parser(
        "metrics-data", help="Consulta valores de metricas."
    )
    metrics_data_parser.add_argument("--integration-id", type=int, required=True)
    metrics_data_parser.add_argument("--start", required=True)
    metrics_data_parser.add_argument("--end", required=True)
    metrics_data_parser.add_argument(
        "--metrics-json",
        help="JSON inline com o array de metricas esperado pela API.",
    )
    metrics_data_parser.add_argument(
        "--metrics-file",
        help="Caminho para um arquivo JSON contendo o array de metricas.",
    )
    metrics_data_parser.add_argument("--comparison-start")
    metrics_data_parser.add_argument("--comparison-end")

    dashboards_parser = subparsers.add_parser(
        "dashboards", help="Lista ou detalha dashboards."
    )
    dashboards_parser.add_argument("--id", type=int, help="ID de um dashboard.")
    dashboards_parser.add_argument("--project-id", type=int)
    dashboards_parser.add_argument("--created-at")
    dashboards_parser.add_argument("--updated-at")
    dashboards_parser.add_argument("--page", type=int, default=1)
    dashboards_parser.add_argument("--per-page", type=int, default=100)

    create_dashboard_parser = subparsers.add_parser(
        "create-dashboard", help="Cria um dashboard com payload JSON."
    )
    create_dashboard_parser.add_argument(
        "--payload-json", help="JSON inline com o payload do dashboard."
    )
    create_dashboard_parser.add_argument(
        "--payload-file", help="Arquivo JSON com o payload do dashboard."
    )

    webhooks_parser = subparsers.add_parser("webhooks", help="Lista ou detalha webhooks.")
    webhooks_parser.add_argument("--id", type=int, help="ID de um webhook.")
    webhooks_parser.add_argument("--project-id", type=int)
    webhooks_parser.add_argument("--event-type")
    webhooks_parser.add_argument("--source")
    webhooks_parser.add_argument("--status")
    webhooks_parser.add_argument("--page", type=int, default=1)
    webhooks_parser.add_argument("--per-page", type=int, default=100)

    create_webhook_parser = subparsers.add_parser(
        "create-webhook", help="Cria um webhook com payload JSON."
    )
    create_webhook_parser.add_argument("--payload-json")
    create_webhook_parser.add_argument("--payload-file")

    update_webhook_parser = subparsers.add_parser(
        "update-webhook", help="Atualiza um webhook com payload JSON."
    )
    update_webhook_parser.add_argument("--id", type=int, required=True)
    update_webhook_parser.add_argument("--payload-json")
    update_webhook_parser.add_argument("--payload-file")

    delete_webhook_parser = subparsers.add_parser(
        "delete-webhook", help="Remove um webhook."
    )
    delete_webhook_parser.add_argument("--id", type=int, required=True)

    timeline_parser = subparsers.add_parser(
        "timeline-events", help="Lista ou detalha eventos da timeline."
    )
    timeline_parser.add_argument("--id", type=int, help="ID de um evento.")
    timeline_parser.add_argument("--project-id", type=int)
    timeline_parser.add_argument("--report-id", type=int)
    timeline_parser.add_argument("--date")
    timeline_parser.add_argument("--page", type=int, default=1)
    timeline_parser.add_argument("--per-page", type=int, default=100)

    create_timeline_parser = subparsers.add_parser(
        "create-timeline-event", help="Cria um evento da timeline com payload JSON."
    )
    create_timeline_parser.add_argument("--payload-json")
    create_timeline_parser.add_argument("--payload-file")

    update_timeline_parser = subparsers.add_parser(
        "update-timeline-event",
        help="Atualiza um evento da timeline com payload JSON.",
    )
    update_timeline_parser.add_argument("--id", type=int, required=True)
    update_timeline_parser.add_argument("--payload-json")
    update_timeline_parser.add_argument("--payload-file")

    delete_timeline_parser = subparsers.add_parser(
        "delete-timeline-event", help="Remove um evento da timeline."
    )
    delete_timeline_parser.add_argument("--id", type=int, required=True)

    automation_parser = subparsers.add_parser(
        "auto-create-report",
        help="Fluxo rapido: escolhe primeiro projeto/template e cria relatorio.",
    )
    automation_parser.add_argument("--project-id", type=int)
    automation_parser.add_argument("--template-id", type=int)
    automation_parser.add_argument("--title", required=True)
    automation_parser.add_argument("--subtitle", required=True)
    automation_parser.add_argument("--start", required=True)
    automation_parser.add_argument("--end", required=True)
    automation_parser.add_argument("--comparison-start")
    automation_parser.add_argument("--comparison-end")

    return parser


def load_json_input(inline_json=None, file_path=None):
    if inline_json and file_path:
        raise ValueError("Use apenas --payload-json ou --payload-file.")
    if not inline_json and not file_path:
        raise ValueError("Informe --payload-json ou --payload-file.")

    if inline_json:
        return json.loads(inline_json)

    content = Path(file_path).read_text(encoding="utf-8")
    return json.loads(content)


def parse_ids(ids_string):
    return [int(item.strip()) for item in ids_string.split(",") if item.strip()]


def print_result(result, pretty=False):
    if pretty:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    print(json.dumps(result, ensure_ascii=False))


def run_command(client, args):
    if args.command == "settings":
        return client.get_company_settings()

    if args.command == "projects":
        if args.id:
            return client.get_project(args.id)
        filters = {}
        if args.q:
            filters["q"] = args.q
        return client.list_projects(page=args.page, per_page=args.per_page, **filters)

    if args.command == "integrations":
        if args.id:
            return client.get_integration(args.id)
        filters = {}
        if args.project_id:
            filters["project_id"] = args.project_id
        if args.slug:
            filters["slug"] = args.slug
        if args.name:
            filters["name"] = args.name
        return client.list_integrations(
            page=args.page,
            per_page=args.per_page,
            **filters,
        )

    if args.command == "templates":
        if args.id:
            return client.get_template(args.id)
        return client.list_templates(page=args.page, per_page=args.per_page)

    if args.command == "reports":
        if args.id:
            return client.get_report(args.id)
        filters = {}
        if args.project_id:
            filters["project_id"] = args.project_id
        if args.created_at:
            filters["created_at"] = args.created_at
        if args.updated_at:
            filters["updated_at"] = args.updated_at
        return client.list_reports(page=args.page, per_page=args.per_page, **filters)

    if args.command == "create-report":
        return client.create_report(
            title=args.title,
            subtitle=args.subtitle,
            start=args.start,
            end=args.end,
            template_id=args.template_id,
            integration_ids=parse_ids(args.integration_ids),
            project_id=args.project_id,
            comparison_start=args.comparison_start,
            comparison_end=args.comparison_end,
        )

    if args.command == "metrics":
        return client.list_metrics(
            integration_slug=args.integration_slug,
            page=args.page,
            per_page=args.per_page,
        )

    if args.command == "metrics-data":
        metrics = load_json_input(args.metrics_json, args.metrics_file)
        return client.get_metrics_data(
            start=args.start,
            end=args.end,
            integration_id=args.integration_id,
            metrics=metrics,
            comparison_start=args.comparison_start,
            comparison_end=args.comparison_end,
        )

    if args.command == "dashboards":
        if args.id:
            return client.get_dashboard(args.id)
        filters = {}
        if args.project_id:
            filters["project_id"] = args.project_id
        if args.created_at:
            filters["created_at"] = args.created_at
        if args.updated_at:
            filters["updated_at"] = args.updated_at
        return client.list_dashboards(page=args.page, per_page=args.per_page, **filters)

    if args.command == "create-dashboard":
        payload = load_json_input(args.payload_json, args.payload_file)
        return client.create_dashboard(payload)

    if args.command == "webhooks":
        if args.id:
            return client.get_webhook(args.id)
        filters = {}
        if args.project_id:
            filters["project_id"] = args.project_id
        if args.event_type:
            filters["event_type"] = args.event_type
        if args.source:
            filters["source"] = args.source
        if args.status:
            filters["status"] = args.status
        return client.list_webhooks(page=args.page, per_page=args.per_page, **filters)

    if args.command == "create-webhook":
        payload = load_json_input(args.payload_json, args.payload_file)
        return client.create_webhook(payload)

    if args.command == "update-webhook":
        payload = load_json_input(args.payload_json, args.payload_file)
        return client.update_webhook(args.id, payload)

    if args.command == "delete-webhook":
        return client.delete_webhook(args.id)

    if args.command == "timeline-events":
        if args.id:
            return client.get_timeline_event(args.id)
        filters = {}
        if args.project_id:
            filters["project_id"] = args.project_id
        if args.report_id:
            filters["report_id"] = args.report_id
        if args.date:
            filters["date"] = args.date
        return client.list_timeline_events(
            page=args.page,
            per_page=args.per_page,
            **filters,
        )

    if args.command == "create-timeline-event":
        payload = load_json_input(args.payload_json, args.payload_file)
        return client.create_timeline_event(payload)

    if args.command == "update-timeline-event":
        payload = load_json_input(args.payload_json, args.payload_file)
        return client.update_timeline_event(args.id, payload)

    if args.command == "delete-timeline-event":
        return client.delete_timeline_event(args.id)

    if args.command == "auto-create-report":
        project_id = args.project_id
        if not project_id:
            projects = client.list_projects(page=1, per_page=1)
            data = projects.get("data", [])
            if not data:
                raise ValueError("Nenhum projeto encontrado para criar o relatorio.")
            project_id = data[0]["id"]

        integrations = client.list_integrations(project_id=project_id, per_page=100)
        integration_ids = [item["id"] for item in integrations.get("data", [])]
        if not integration_ids:
            raise ValueError("Nenhuma integracao encontrada para o projeto informado.")

        template_id = args.template_id
        if not template_id:
            templates = client.list_templates(page=1, per_page=1)
            data = templates.get("data", [])
            if not data:
                raise ValueError("Nenhum template encontrado para criar o relatorio.")
            template_id = data[0]["id"]

        return client.create_report(
            title=args.title,
            subtitle=args.subtitle,
            start=args.start,
            end=args.end,
            template_id=template_id,
            integration_ids=integration_ids,
            project_id=project_id,
            comparison_start=args.comparison_start,
            comparison_end=args.comparison_end,
        )

    raise ValueError(f"Comando nao suportado: {args.command}")


def main():
    load_dotenv()
    token = os.getenv("REPORTEI_TOKEN")
    client = ReporteiClient(token)
    parser = build_parser()
    args = parser.parse_args()

    try:
        result = run_command(client, args)
    except requests.RequestException as exc:
        raise SystemExit(f"Falha de rede ao acessar a API Reportei: {exc}") from exc
    except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc

    print_result(result, pretty=args.pretty)


if __name__ == "__main__":
    main()
