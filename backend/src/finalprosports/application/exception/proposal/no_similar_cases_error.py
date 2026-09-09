class NoSimilarCasesError(Exception):
    def __init__(self, client_code: str):
        super().__init__(f"no similar cases for client {client_code}")
        self.client_code = client_code
