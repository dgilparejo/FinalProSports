class ClientCodeReservedError(Exception):
    """The code belongs to the case base (corpus): the application may never register or edit a client under it (S1)."""

    def __init__(self, client_code: str):
        super().__init__(f"client code reserved for the case base: {client_code}")
        self.client_code = client_code
