class FoodAlreadyExistsError(Exception):
    """A catalogue food with that canonical name (or one of its synonyms) already exists (S5)."""

    def __init__(self, canonical_name: str, existing_id: int | None = None):
        super().__init__(f"food already in the catalogue: {canonical_name}" + (f" (id {existing_id})" if existing_id else ""))
        self.canonical_name, self.existing_id = canonical_name, existing_id
