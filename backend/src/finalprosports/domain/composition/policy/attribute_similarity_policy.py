"""Attribute similarity between a query profile and a case (E3.2, strategies 'attributes' and 'hybrid').

Deterministic and interpretable: a weighted sum of per-attribute matches in [0, 1] with EXPLICIT weights. The goal is the
professional's structured input (form field), so matching on it is using data, not leaking it. Unknown attributes score
0.5 (neutral), never 0, so a case is not punished for a missing value. The case side is represented as a ClientProfile
whose `goal` is the DIET's goal (not the client's declared goal) and whose flags are the client's.
"""
from __future__ import annotations

from dataclasses import dataclass

from finalprosports.domain.model import ClientProfile


@dataclass(frozen=True)
class AttributeWeights:
    """Los pesos de la similitud. Los cinco primeros son los originales; los cuatro últimos se añadieron cuando se
    midió que la función miraba SOLO esos cinco números y que todo lo que el expediente había ganado —báscula,
    entrenamientos, deporte, régimen— no entraba en la comparación. Ésa era la causa de que los veinte vecinos
    empataran, de que ponderar por similitud no moviera nada y de que reextraer el corpus no mejorara las propuestas.

    Cobertura medida sobre los 261 clientes con dietas, que es lo que decide cuánto puede aportar cada uno:
    altura 70,9 % · body_type 56,3 % · deporte 32,6 % · método (de la dieta) 27,8 % · horario de entreno 28,0 %.
    El % de grasa US Navy (18,4 %) y el IMC (8,4 %) se quedan fuera: no hay dato suficiente para que pesen.
    """
    goal: float = 0.45
    sex: float = 0.15
    age: float = 0.20
    activity: float = 0.10
    restrictions: float = 0.10
    method: float = 0.0               # régimen estructural de la dieta (ayuno / cetosis / descarga)
    body_type: float = 0.0            # complexión: (barrido de pesos); el rasgo está, el peso no
    height: float = 0.0               # altura
    sport: float = 0.0                # deporte practicado
    # --------------------------------------------------------------- COMPOSICIÓN CORPORAL MEDIDA (báscula, 0015)
    # Siete magnitudes que el profesional registra desde 2016 y que la similitud no veía porque nunca se cargaron en la
    # base de datos. Todas entran a CERO: se activan solo si un barrido sobre una partición por cliente demuestra que
    # mejoran la propuesta. Cobertura con la regla temporal aplicada: 617 de 815 consultas (75,7 %), 55,4-57,3 % de los
    # pares evaluables — por encima de la de `body_type`, que es lo que hasta ahora hacía de proxy del cuerpo.
    weight: float = 0.0
    fat: float = 0.0
    muscle: float = 0.0
    visceral: float = 0.0
    metabolic_age: float = 0.0
    basal_met: float = 0.0
    hydration: float = 0.0
    # GUSTOS POSITIVOS (bloque 8.2a): solapamiento entre los conjuntos de alimentos que dos clientes declaran querer.
    # Entra a CERO como todos: lo activa el barrido o no se activa. Medido que EL los tiene en cuenta (+0,0643
    # [+0,0120, +0,1211] sobre la tasa base, con el control negativo en -0,0612), pero eso dice que importan al
    # ESCRIBIR, no que dos clientes con gustos parecidos reciban dietas parecidas: son dos preguntas distintas.
    likes: float = 0.0
    # ANALITICAS (bloque 3 de la 2a ronda). UN solo peso para el conjunto, no uno por parametro: en 3.1 los dieciséis
    # parámetros probados dan correlaciones entre −0,047 y +0,058 con SIGNOS MEZCLADOS, que es la firma del ruido y no
    # la de una señal. Elegir los dos que salen positivos y pesarlos sería elegir sobre el resultado. Lo que sí se
    # puede preguntar honestamente es si el conjunto aporta, y eso es lo que este peso barre.
    labs: float = 0.0
    # EL 0,10 DE `body_type` ESTÁ EN REVISIÓN Y LO MEDIDO DICE QUE SOBRA (barrido de pesos).
    # Se eligió con un barrido que optimizaba el J TOP-1 —el parecido del primer vecino— y reportaba J 0,3491 -> 0,3820
    # en el apartado con +66 % de separación del vecindario. Esa cifra SE RETIRA: no reproduce, y el script que la
    # produjo no está en el repositorio, así que no se puede auditar su métrica. Rehecho con la partición por cliente
    # (72 desarrollo / 48 apartados, intersección 0), con los DIECISÉIS pesos nombrados explícitamente y midiendo el J
    # de la PROPUESTA COMPLETA, que es lo que se entrega:
    #   bajo D3 (un caso por cliente, pureza primero): 0,2868 con complexión frente a 0,3060 sin ella; sobre el
    #     apartado, quitarla gana +0,0166 PAREADO, IC 95 % [+0,0060, +0,0271];
    #   bajo el motor actual: mismo signo, +0,0027 [-0,0046, +0,0101], no significativo.
    # Ninguno de los once rasgos añadidos (los cuatro del cuestionario y los siete de la báscula) mejora la propuesta,
    # aunque varios sí mejoran el J top-1: ordenar mejor el vecindario no cambia lo que veinte dietas acuerdan por
    # mayoría. El valor sigue a 0,10 porque cambiarlo es una decisión de diseño, no de esta medición.
    # Detalle en la memoria (barrido de pesos) §1.1 y §1.2.
    age_span_years: int = 30          # |Δage| at which the age match reaches 0
    activity_span: int = 5            # |Δactivity| at which the activity match reaches 0
    height_span_cm: int = 25          # |Δaltura| al que la coincidencia llega a 0
    # Anchuras de la báscula: la diferencia a la que dos personas dejan de parecerse en ese rasgo. Se fijan por el
    # RANGO OBSERVADO en el corpus, no por criterio clínico, porque lo que se compara es «cuánto se parecen entre sí
    # los clientes de ESTE profesional», y una anchura mayor que su dispersión haría que todos puntuaran alto.
    weight_span_kg: float = 30.0
    fat_span_pct: float = 15.0
    muscle_span_kg: float = 20.0
    visceral_span: float = 8.0
    metabolic_age_span: float = 20.0
    basal_met_span_kcal: float = 800.0
    hydration_span_pct: float = 10.0

    @property
    def total(self) -> float:
        return (self.goal + self.sex + self.age + self.activity + self.restrictions
                + self.method + self.body_type + self.height + self.sport
                + self.weight + self.fat + self.muscle + self.visceral + self.metabolic_age + self.basal_met
                + self.hydration + self.likes + self.labs)


DEFAULT_WEIGHTS = AttributeWeights()



# ------------------------------------------------------------------------------ rasgos añadidos (medidos, no supuestos)
# Todos degradan igual que los originales: cuando el dato falta en cualquiera de los dos lados devuelven 0.5, el valor
# neutro. NUNCA se imputa un valor: un cliente sin báscula no se compara como si tuviera la complexión media, se compara
# como si ese rasgo no dijera nada, que es lo único honesto cuando el profesional no lo anotó.

_REGIMENES = ("ayuno_intermitente", "cetosis_keto", "descarga_carga")


def _methods_of(p: ClientProfile) -> set[str]:
    """El régimen de un perfil: el de la dieta si lo lleva, y el objetivo cuando el objetivo ES un régimen.

    Un cliente que pide «ayuno intermitente» declara el régimen aunque su perfil no traiga el campo, y sin esto la
    consulta de un cliente nuevo nunca casaría con ningún caso: el campo `methods` vive en la DIETA, no en el cliente.
    """
    m = set(p.methods or ())
    if p.goal is not None and getattr(p.goal, "value", None) in _REGIMENES:
        m.add(p.goal.value)
    return m


def method_match(query: ClientProfile, case: ClientProfile) -> float:
    """El régimen estructural de la dieta. Dos clientes en ayuno se parecen aunque su propósito difiera."""
    query_m, case_m = _methods_of(query), _methods_of(case)
    if not query_m and not case_m:
        return 0.5                                    # ninguno declara régimen: el rasgo no discrimina
    if not query_m or not case_m:
        return 0.3                                    # uno sí y el otro no: se parecen menos, pero no son opuestos
    return 1.0 if query_m & case_m else 0.0


def body_type_match(query: ClientProfile, case: ClientProfile) -> float:
    if not query.body_type or not case.body_type:
        return 0.5
    return 1.0 if query.body_type == case.body_type else 0.0


def height_match(query: ClientProfile, case: ClientProfile, span: int) -> float:
    if query.height_cm is None or case.height_cm is None:
        return 0.5
    return max(0.0, 1.0 - min(abs(query.height_cm - case.height_cm), span) / span)


def sport_match(query: ClientProfile, case: ClientProfile) -> float:
    if not query.sport or not case.sport:
        return 0.5
    a, b = query.sport.strip().lower(), case.sport.strip().lower()
    return 1.0 if a == b else (0.5 if (a in b or b in a) else 0.0)


# Los siete rasgos de la báscula comparten forma: una magnitud numérica cuya coincidencia decae linealmente con la
# diferencia hasta anularse en `span`. `(atributo del perfil, peso, anchura)`; el orden ES el de la tabla del informe.
SCALE_TRAITS = (("weight_kg", "weight", "weight_span_kg"), ("fat_pct", "fat", "fat_span_pct"),
                ("muscle_mass_kg", "muscle", "muscle_span_kg"), ("visceral_fat_rating", "visceral", "visceral_span"),
                ("metabolic_age", "metabolic_age", "metabolic_age_span"), ("basal_met_kcal", "basal_met", "basal_met_span_kcal"),
                ("hydration_pct", "hydration", "hydration_span_pct"))


def numeric_match(a: float | None, b: float | None, span: float) -> float:
    """Coincidencia lineal en [0, 1]. 0.5 cuando falta el dato en cualquiera de los dos lados (nunca se imputa)."""
    if a is None or b is None:
        return 0.5
    return max(0.0, 1.0 - min(abs(float(a) - float(b)), span) / span)


def likes_match(query: ClientProfile, case: ClientProfile) -> float:
    """Jaccard entre los dos conjuntos de gustos positivos. Sin lista en alguno de los dos lados, no es evaluable."""
    a, b = frozenset(query.liked_food_ids or ()), frozenset(case.liked_food_ids or ())
    if not a or not b:
        return 0.5
    return len(a & b) / len(a | b)


def labs_match(query: ClientProfile, case: ClientProfile) -> float:
    """Parecido analítico: media de la coincidencia por parámetro sobre los que los DOS lados tienen medidos.

    Cada parámetro se normaliza por su propio recorrido observado (`lab_spans`), porque un índice que va de 0 a 10 y
    otro que va de 0 a 5.000 no se pueden restar. Sin parámetros compartidos el rasgo no es evaluable.
    """
    a, b = query.lab_values or {}, case.lab_values or {}
    comunes = set(a) & set(b)
    if not comunes:
        return 0.5
    spans = query.lab_spans or {}
    total = 0.0
    for name in comunes:
        span = spans.get(name) or 1.0
        total += max(0.0, 1.0 - min(abs(float(a[name]) - float(b[name])), span) / span)
    return total / len(comunes)


def goal_match(query: ClientProfile, case: ClientProfile) -> float:
    if query.goal is None or case.goal is None:
        return 0.5
    return 1.0 if query.goal == case.goal else 0.0


def sex_match(query: ClientProfile, case: ClientProfile) -> float:
    if query.sex is None or case.sex is None:
        return 0.5
    return 1.0 if query.sex == case.sex else 0.0


def age_match(query: ClientProfile, case: ClientProfile, span: int) -> float:
    if query.age is None or case.age is None:
        return 0.5
    return max(0.0, 1.0 - min(abs(query.age - case.age), span) / span)


def activity_match(query: ClientProfile, case: ClientProfile, span: int) -> float:
    if query.activity_level is None or case.activity_level is None:
        return 0.5
    return max(0.0, 1.0 - min(abs(query.activity_level - case.activity_level), span) / span)


def restriction_compatibility(query: ClientProfile, case: ClientProfile) -> float:
    """1.0 when the query declares no restriction. For each declared flag (allergies, intolerances, medical) the case is fully
    compatible when its client declared the same flag (the professional already prescribed under that restriction) and only
    partially (0.3) otherwise: the diet may contain the restricted foods and will need the restriction policy downstream."""
    pairs = [(query.has_allergies, case.has_allergies), (query.has_intolerances, case.has_intolerances),
             (query.has_medical_restrictions, case.has_medical_restrictions)]
    declared = [c for q, c in pairs if q]
    if not declared:
        return 1.0
    return sum(1.0 if c else 0.3 for c in declared) / len(declared)


def _observable(query: ClientProfile, case: ClientProfile, rasgo: str) -> bool:
    """¿Se puede evaluar este rasgo con lo que hay en los dos perfiles?"""
    if rasgo == "method":
        return bool(_methods_of(query) or _methods_of(case))
    if rasgo == "body_type":
        return bool(query.body_type and case.body_type)
    if rasgo == "height":
        return query.height_cm is not None and case.height_cm is not None
    if rasgo == "sport":
        return bool(query.sport and case.sport)
    if rasgo == "likes":
        return bool(query.liked_food_ids and case.liked_food_ids)
    if rasgo == "labs":
        return bool(set(query.lab_values or {}) & set(case.lab_values or {}))
    if rasgo in {a for a, _, _ in SCALE_TRAITS}:
        return getattr(query, rasgo) is not None and getattr(case, rasgo) is not None
    return True


def attribute_score(query: ClientProfile, case: ClientProfile, w: AttributeWeights = DEFAULT_WEIGHTS) -> float:
    """Coincidencia ponderada en [0, 1].

    Los cinco rasgos originales conservan su 0,5 neutro cuando falta el dato. Los AÑADIDOS se renormalizan: si el
    rasgo no es evaluable —falta en alguno de los dos perfiles— sale del numerador Y del denominador, en lugar de
    aportar medio punto de nada. La diferencia importa: con el 0,5 neutro, dos perfiles IDÉNTICOS sin complexión
    anotada puntuaban 0,95 en vez de 1,0, y un caso idéntico a la consulta tiene que ser 1,0. Excluir es lo honesto
    cuando no hay dato; imputar la media sería inventarlo, y el 0,5 en un rasgo de cobertura baja es casi eso.
    """
    s = (w.goal * goal_match(query, case) + w.sex * sex_match(query, case) + w.age * age_match(query, case, w.age_span_years)
         + w.activity * activity_match(query, case, w.activity_span) + w.restrictions * restriction_compatibility(query, case))
    total = w.goal + w.sex + w.age + w.activity + w.restrictions
    for rasgo, peso, fn in (("method", w.method, method_match), ("body_type", w.body_type, body_type_match),
                            ("sport", w.sport, sport_match), ("likes", w.likes, likes_match),
                            ("labs", w.labs, labs_match)):
        if peso and _observable(query, case, rasgo):
            s += peso * fn(query, case)
            total += peso
    if w.height and _observable(query, case, "height"):
        s += w.height * height_match(query, case, w.height_span_cm)
        total += w.height
    for attr, peso_name, span_name in SCALE_TRAITS:                 # báscula: misma renormalización que los añadidos
        peso = getattr(w, peso_name)
        a, b = getattr(query, attr), getattr(case, attr)
        if peso and a is not None and b is not None:
            s += peso * numeric_match(a, b, getattr(w, span_name))
            total += peso
    return s / total


def hybrid_score(cosine_normalised: float, attributes: float, alpha: float = 0.5) -> float:
    """Mix of the (min-max normalised within the candidate set) cosine similarity and the attribute score."""
    return alpha * cosine_normalised + (1.0 - alpha) * attributes
