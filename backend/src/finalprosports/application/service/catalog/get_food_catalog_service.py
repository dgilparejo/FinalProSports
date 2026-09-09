from finalprosports.application.port.outbound.persistence.catalog.food_catalog_output_port import FoodCatalogOutputPort
from finalprosports.domain.model import Food


class GetFoodCatalogService:
    def __init__(self, catalog: FoodCatalogOutputPort):
        self._catalog = catalog

    def get_catalog(self, professional_id: str) -> tuple[Food, ...]:
        return self._catalog.all(professional_id)
