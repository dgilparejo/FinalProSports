from finalprosports.application.exception.client.client_not_found_error import ClientNotFoundError
from finalprosports.application.port.outbound.export.diet_exporter_output_port import DietExporterOutputPort
from finalprosports.application.port.outbound.persistence.proposal.proposal_repository_output_port import ProposalRepositoryOutputPort
from finalprosports.application.port.outbound.persistence.client.client_repository_output_port import ClientRepositoryOutputPort
from finalprosports.application.port.outbound.persistence.record.client_record_output_port import ClientRecordOutputPort
from finalprosports.application.port.outbound.persistence.record.lab_result_output_port import LabResultOutputPort
from finalprosports.domain.model.lab_result import latest_per_marker


class ExportDietUseCase:
    def __init__(self, proposals: ProposalRepositoryOutputPort, exporter: DietExporterOutputPort, labs: LabResultOutputPort | None = None,
                 records: ClientRecordOutputPort | None = None, exporters: dict[str, DietExporterOutputPort] | None = None,
                 clients: ClientRepositoryOutputPort | None = None):
        self._proposals, self._exporter, self._labs, self._records = proposals, exporter, labs, records
        self._clients = clients
        self._exporters = exporters or {}
        """One exporter per format the professional can ask for. He writes his diets in LibreOffice Writer, so the .odt is
        not a convenience: it is the document he can still edit, which is what he does today with each client's previous
        version. The PDF is what he hands over. Same `DietDocument` behind both."""

    @property
    def formats(self) -> tuple[str, ...]:
        return tuple(self._exporters) or ("pdf",)

    def export(self, professional_id: str, diet_id: str, fmt: str = "pdf") -> bytes:
        proposal = self._proposals.get(professional_id, diet_id)
        if proposal is None:
            raise ClientNotFoundError(f"saved diet {diet_id}")
        routing = proposal.parameters.get("routing")
        label = {"cold_start": "consenso de casos (cliente nuevo)", "same_goal": "rotación de la versión anterior", "goal_changed": "consenso de casos (cambio de objetivo)"}.get(routing)
        labs = latest_per_marker(self._labs.list(professional_id, proposal.profile.client_code)) if self._labs is not None else ()   # S4: context section of the PDF
        record = self._records.get(professional_id, proposal.profile.client_code) if self._records is not None else None
        name = (record.identification.full_name or "").strip() if record else ""                    # S6/S9: «DIETA <nombre> fecha», as he writes it; never the key
        # S6: «Objetivo:» EN SUS PALABRAS -- pero solo cuando esas palabras describen ESTA dieta.
        #
        # `goals_text` es lo que el cliente dijo que quería en la hoja de entrada y NO cambia nunca: «Ganar masa
        # muscular y tonificar». El objetivo de una DIETA sí cambia. Como el renderizador daba prioridad absoluta al
        # texto libre, todas las dietas de un cliente salían con el mismo objetivo impreso: se generaban una de
        # definición y otra de ayuno y las dos decían «Ganar masa muscular y tonificar».
        #
        # La regla: el texto del cliente se usa cuando el objetivo de la dieta ES el que él declaró; en cuanto la
        # dieta persigue otra cosa, manda el objetivo de la dieta. No se intenta adivinar si el texto «encaja»: se
        # compara el objetivo estructurado, que es un dato, no una interpretación.
        goal_text = (record.sports.goals_text or "").strip() if record else ""
        if goal_text and not self._describes_this_diet(professional_id, proposal):
            goal_text = ""
        exporter = self._exporters.get(fmt, self._exporter)
        return exporter.export(proposal, diet_id, label, lab_results=labs, client_name=name or None, goal_text=goal_text or None)

    def _describes_this_diet(self, professional_id: str, proposal) -> bool:
        """¿El texto libre del expediente habla del objetivo de ESTA dieta?

        Sin repositorio de clientes no se puede saber, y entonces NO se usa el texto: equivocarse imprimiendo el
        objetivo canónico es un documento correcto y aburrido; equivocarse al revés es entregarle al cliente una
        dieta de definición que dice «Ganar masa muscular».
        """
        if self._clients is None:
            return False
        perfil = self._clients.get(professional_id, proposal.profile.client_code)
        return perfil is not None and perfil.goal is not None and perfil.goal == proposal.profile.goal
