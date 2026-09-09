class ClientNotFoundError(Exception):
    def __init__(self, client_code: str):
        super().__init__(f"client not found: {client_code}")
        self.client_code = client_code
