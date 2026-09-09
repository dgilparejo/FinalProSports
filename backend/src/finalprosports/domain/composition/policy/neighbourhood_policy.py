"""Cómo se eligen los k casos de entre los candidatos ordenados por similitud, y cuándo un objetivo es servible.

Sin política, se cogen los k primeros, y eso concentra el vecindario porque **varias versiones del
mismo cliente comparten perfil y entran juntas**: así el motor entregaba veinte dietas que venían, de media, de **siete
clientes**, y estaba por debajo de 0,90 de independencia en **las 815 consultas del arnés sin una sola excepción**.
El compositor funciona por mayoría, así que reducir el número de opiniones independientes le quita justamente lo que
lo hace funcionar.

**D3 — un caso por cliente, PUREZA PRIMERO.** Se recorre la lista ordenada por similitud tomando un caso por cliente;
antes de admitir a un cliente de OTRO objetivo se agotan las demás versiones de los clientes del objetivo correcto.
Pierde independencia entre votantes antes que perder el régimen, que es el orden correcto: una dieta de otro objetivo
no es una opinión sobre esta pregunta.

Medido sobre las 815 consultas, contra la selección anterior: **+0,0142 [+0,0097, +0,0189]** en `normalized_key`,
**+0,0139** en familia y **+0,0090** en especie; y de siete clientes efectivos se pasa a **19,5**.

---

**LAS TRES BANDAS.** El corte NO va sobre una fracción, porque con k = 20 satura: D3 rellena con otras versiones de
los mismos clientes y da 0,975 lo mismo con cuarenta clientes que con cuatro. Va sobre el **número absoluto de
clientes distintos del objetivo que existen**, y el corte natural es **k**: por debajo de k clientes, los veinte votos
no pueden ser veinte opiniones ni aunque la selección fuera perfecta.

La distribución del corpus respalda el corte sin ajustarlo — es tri-modal por objetivo: 5 consultas con 1 cliente,
9 con 4, 23 con 13, y todo lo demás con 26 o más. No hay ningún caso ambiguo cerca del umbral.

  SERVIR              >= k clientes distintos del objetivo          778 de 815 (95,5 %)
  SERVIR DECLARANDO   2..k-1 clientes                                23 (2,8 %) -- hoy solo cetosis_keto
  NO SERVIR           < 2 clientes, o pureza < 0,50                  14 (1,7 %) -- descarga_carga (9), hipocalorica (5)

`hipocalorica` tiene UN cliente: los veinte votos son la misma persona, y eso no es un consenso. `descarga_carga`
tiene cuatro, y hay prueba independiente de que ahí no se elige nada — los dos brazos daban diferencia **exactamente
0,0000**, porque entregan el mismo vecindario.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

# Cuántos candidatos hay que pedir para poder seleccionar k con un caso por cliente. Con 8k la selección llegó a los
# veinte huecos en las 815 consultas del arnés; por debajo, en los objetivos numerosos se quedaba corta.
OVERFETCH = 8
MIN_CLIENTS_TO_SERVE_AT_ALL = 2
MIN_PURITY = 0.50


class ServiceBand(StrEnum):
    SERVE = "servir"
    SERVE_DECLARING = "servir_declarando"
    DO_NOT_SERVE = "no_servir"


@dataclass(frozen=True)
class Neighbourhood:
    """Los k casos elegidos y con qué se construyeron. Las dos cifras de abajo son las que ve el profesional."""
    cases: tuple
    goal_diets: int             # cuántos de los k son del objetivo pedido
    goal_clients: int           # de cuántos clientes DISTINTOS del objetivo vienen
    distinct_clients: int       # clientes distintos entre los k, sea cual sea su objetivo
    available_goal_clients: int  # clientes distintos del objetivo que EXISTEN entre los candidatos

    @property
    def purity(self) -> float:
        return self.goal_diets / len(self.cases) if self.cases else 0.0

    @property
    def band(self) -> ServiceBand:
        if self.available_goal_clients < MIN_CLIENTS_TO_SERVE_AT_ALL or self.purity < MIN_PURITY:
            return ServiceBand.DO_NOT_SERVE
        if self.available_goal_clients < len(self.cases):
            return ServiceBand.SERVE_DECLARING
        return ServiceBand.SERVE

    @property
    def warning(self) -> str | None:
        """Lo que el panel de explicabilidad tiene que decir cuando la propuesta se sirve DECLARANDO."""
        if self.band is not ServiceBand.SERVE_DECLARING:
            return None
        return (f"Construida con {self.goal_diets} casos del objetivo, de {self.goal_clients} clientes distintos. "
                f"El corpus solo tiene {self.available_goal_clients} clientes con ese objetivo, así que el consenso "
                f"se apoya en menos personas que casos.")


def select(candidates, goal, k: int) -> Neighbourhood:
    """D3 sobre los candidatos YA ordenados por similitud descendente. No reordena: solo elige."""
    del_objetivo = [c for c in candidates if c.diet.goal == goal]
    otros = [c for c in candidates if c.diet.goal != goal]

    def uno_por_cliente(pool, limit, vistos=None):
        vistos = set() if vistos is None else set(vistos)
        out = []
        for c in pool:
            if c.diet.client_code in vistos:
                continue
            vistos.add(c.diet.client_code)
            out.append(c)
            if len(out) == limit:
                break
        return out, vistos

    elegidos, vistos = uno_por_cliente(del_objetivo, k)
    if len(elegidos) < k:                       # ...y se completa con MÁS versiones de esos mismos clientes
        ya = {id(c) for c in elegidos}
        for c in del_objetivo:
            if id(c) in ya:
                continue
            elegidos.append(c)
            ya.add(id(c))
            if len(elegidos) == k:
                break
    if len(elegidos) < k:                       # ...y SOLO entonces con clientes de otro objetivo
        resto, _ = uno_por_cliente(otros, k - len(elegidos))
        elegidos.extend(resto)
    # El puesto que se entrega es el del vecindario ELEGIDO, no el que tenía en el conjunto de candidatos. Sin esto,
    # el profesional vería «caso 1, caso 2, caso 9, caso 14» y el hueco no significaría nada para él: es un detalle de
    # cuántos candidatos se pidieron, no del parecido. El orden por similitud se conserva.
    elegidos = [replace(c, rank=i + 1) for i, c in enumerate(elegidos)]
    del_obj = [c for c in elegidos if c.diet.goal == goal]
    return Neighbourhood(cases=tuple(elegidos), goal_diets=len(del_obj),
                         goal_clients=len({c.diet.client_code for c in del_obj}),
                         distinct_clients=len({c.diet.client_code for c in elegidos}),
                         available_goal_clients=len({c.diet.client_code for c in del_objetivo}))
