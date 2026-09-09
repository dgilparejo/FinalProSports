from enum import StrEnum


class Goal(StrEnum):
    """Normalised goal labels of the corpus (data values in Spanish)."""

    VOLUME = "volumen_masa"
    FAT_LOSS = "definicion_grasa"
    INTERMITTENT_FASTING = "ayuno_intermitente"
    CARB_CYCLING = "descarga_carga"
    KETO = "cetosis_keto"
    HYPOCALORIC = "hipocalorica"
    HIGH_FIBRE = "alta_en_fibra"
    MAINTENANCE = "mantenimiento"
    UNCLASSIFIED = "sin_clasificar"
