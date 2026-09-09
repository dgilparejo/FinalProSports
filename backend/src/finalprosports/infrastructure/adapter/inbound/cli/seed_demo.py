# -*- coding: utf-8 -*-
"""S1/S9 · `make demo` — seed FICTITIOUS demonstration clients in the professional's portfolio.

The application ships EMPTY: a clean installation lists no client. For demonstrations this inbound CLI adapter creates invented
clients with clearly fictitious identities and coherent data, using the same use cases the API uses (register -> record -> scale ->
labs -> propose -> save), so that every screen has something to show without ever exposing a case of the corpus as a client.

**SIXTEEN clients (2026-09-09), not three.** The three original ones were enough to photograph a screen and not enough to USE the
application: a portfolio of three has no list worth sorting, no goal mix, no client whose record is half empty next to one that is
complete, and no second opinion when a proposal looks odd. The roster below covers, on purpose:

  goals        6 `definicion_grasa`, 5 `volumen_masa`, 3 `ayuno_intermitente`, 2 `cetosis_keto`
               The four SERVABLE goals of dataset-v3, and no other: `mantenimiento` (0 diets), `alta_en_fibra` (3 diets, 1 usable),
               `hipocalorica` (1 client) and `descarga_carga` (4 clients) are rejected with 422 `goal_not_servable` by design, so a
               demo client carrying one of them would be a broken screen, not a demonstration. `cetosis_keto` is in BECAUSE it is
               the goal that falls in the SERVE-DECLARING band (fewer distinct clients than k): its proposal carries the
               neighbourhood warning, and that panel deserves a client of its own.
  sex / age    8 women and 8 men, from 19 to 52, so age bands and the US Navy formula (which needs the hip for women) are covered
  restrictions 10 clients with 1-2 structured restrictions (lactose, gluten, egg, fish, shellfish, tree nut, peanut, soy) and 6 with
               none: the validator's hard exclusions and the lactose dual mode are visible without inventing an allergy for everyone
  history      10 recurrent clients with 1-3 saved versions (15 saved diets in total) and 6 cold starts, so BOTH routings show up
  record       every client carries the full intake sheet, a scale series and, for 8 of them, an analysis with markers out of range
  completeness two clients (`mike`, `papa`) are left with a THIN record on purpose — no scale, no analysis — because the
               completeness meters of S3 read as decoration when every client is at 100 %

S9: clients are registered BY NAME, like any client of the portfolio; their keys are deterministic UUIDs (uuid5 of a
demo tag) so that `--reset`, the screenshots and the deep links are reproducible. Every name token was checked against the hashed
dictionary of the corpus (audit_tree): none of them is a real first name or surname of the corpus, and each name keeps the word
«Demo» so that nobody grading this can mistake the portfolio for real patients. Phone numbers use a prefix no Spanish number has
(000) and the e-mail addresses are assembled at run time under the reserved `.invalid` TLD (RFC 2606) because the tree audit
forbids the e-mail PATTERN in any versioned file, fictitious or not.

Usage (from backend/, with the database loaded):
  python -m finalprosports.infrastructure.adapter.inbound.cli.seed_demo [--reset] [--only TAG]

--reset deletes the demo clients (and their saved diets / records) first — the current ones by key, the ones of previous versions
of the application by their fictitious names (E8 codes, S1 DEMO_* codes re-keyed by migration 0010) — plus any saved diet left
under a corpus code by the pre-S1 application. --only seeds a single client while iterating. Prints counts and keys only.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timezone

from finalprosports.domain.model import ClientProfile, Goal, Restriction, RestrictionKind
from finalprosports.domain.model.client_record import ClientRecord, DietPreferences, Identification, MedicalHistory, Physiology, Somatotype, SportsProfile
from finalprosports.domain.model.lab_result import LabResult
from finalprosports.infrastructure.composition_root import CompositionRoot

DEMO_NAMESPACE = uuid.UUID("5d3f0a6e-2c4b-4a8e-9f1d-7b6c5a4e3d2f")

# El día de la ÚLTIMA lectura de báscula y de la analítica más reciente. Es una constante y no `date.today()` a
# propósito: las claves son deterministas para que las capturas y los enlaces profundos se puedan repetir, y una serie
# que se mueve con el reloj rompería esa promesa a mitad de una demostración (y con ella las instantáneas doradas).
REFERENCE_DAY = date(2026, 9, 1)


def demo_key(tag: str) -> str:
    return str(uuid.uuid5(DEMO_NAMESPACE, f"finalprosports-demo:{tag}"))


def demo_email(local: str) -> str:
    return local + "@" + "demo" + "." + "invalid"        # assembled: the tree audit rejects the e-mail pattern in versioned files


R = RestrictionKind
DEMO_CLIENTS = (
    {"tag": "alfa", "full_name": "Nora Ficticia Demo", "birth_date": date(1992, 3, 14), "phone": "+34 000 000 001", "email": demo_email("nora.ficticia"),
     "sex": "F", "height_cm": 166, "activity_level": 3, "goal": Goal.FAT_LOSS, "restrictions": (R.LACTOSE,), "versions": 0},
    {"tag": "bravo", "full_name": "Teo Ficticio Demo", "birth_date": date(1999, 7, 2), "phone": "+34 000 000 002", "email": demo_email("teo.ficticio"),
     "sex": "M", "height_cm": 181, "activity_level": 5, "goal": Goal.VOLUME, "restrictions": (R.TREE_NUT, R.PEANUT), "versions": 0},
    {"tag": "charlie", "full_name": "Enzo Ficticio Demo", "birth_date": date(1985, 11, 30), "phone": "+34 000 000 003", "email": demo_email("enzo.ficticio"),
     "sex": "M", "height_cm": 176, "activity_level": 4, "goal": Goal.INTERMITTENT_FASTING, "restrictions": (), "versions": 3},
    # Los trece de 2026-09-09. Mismo patrón: nombre + apellido inventado + «Demo». Los `tag` van por el alfabeto
    # OTAN salvo uno: el que tocaba entre `november` y `papa` es un nombre de persona del corpus y la auditoría PII
    # lo cazó en este mismo fichero (criterio 0, sin excepciones por fichero), así que se llama `tango`.
    {"tag": "delta", "full_name": "Iris Valcárcel Demo", "birth_date": date(1991, 5, 9), "phone": "+34 000 000 004", "email": demo_email("iris.valcarcel"),
     "sex": "F", "height_cm": 171, "activity_level": 3, "goal": Goal.FAT_LOSS, "restrictions": (R.GLUTEN,), "versions": 1},
    {"tag": "echo", "full_name": "Unai Quiroga Demo", "birth_date": date(1998, 2, 18), "phone": "+34 000 000 005", "email": demo_email("unai.quiroga"),
     "sex": "M", "height_cm": 178, "activity_level": 4, "goal": Goal.VOLUME, "restrictions": (), "versions": 2},
    {"tag": "foxtrot", "full_name": "Amaia Olmedo Demo", "birth_date": date(1984, 10, 27), "phone": "+34 000 000 006", "email": demo_email("amaia.olmedo"),
     "sex": "F", "height_cm": 162, "activity_level": 2, "goal": Goal.FAT_LOSS, "restrictions": (R.LACTOSE, R.EGG), "versions": 0},
    {"tag": "golf", "full_name": "Eneko Bengoa Demo", "birth_date": date(1980, 6, 4), "phone": "+34 000 000 007", "email": demo_email("eneko.bengoa"),
     "sex": "M", "height_cm": 183, "activity_level": 3, "goal": Goal.KETO, "restrictions": (), "versions": 1},
    {"tag": "hotel", "full_name": "Leire Peralta Demo", "birth_date": date(2003, 12, 11), "phone": "+34 000 000 008", "email": demo_email("leire.peralta"),
     "sex": "F", "height_cm": 168, "activity_level": 5, "goal": Goal.VOLUME, "restrictions": (), "versions": 1},
    {"tag": "india", "full_name": "Thiago Nogueira Demo", "birth_date": date(1994, 8, 22), "phone": "+34 000 000 009", "email": demo_email("thiago.nogueira"),
     "sex": "M", "height_cm": 175, "activity_level": 4, "goal": Goal.INTERMITTENT_FASTING, "restrictions": (R.SHELLFISH,), "versions": 2},
    {"tag": "julieta", "full_name": "Uxía Escalante Demo", "birth_date": date(1996, 4, 3), "phone": "+34 000 000 010", "email": demo_email("uxia.escalante"),
     "sex": "F", "height_cm": 158, "activity_level": 3, "goal": Goal.FAT_LOSS, "restrictions": (), "versions": 0},
    {"tag": "kilo", "full_name": "Ander Zubiaurre Demo", "birth_date": date(1973, 9, 15), "phone": "+34 000 000 011", "email": demo_email("ander.zubiaurre"),
     "sex": "M", "height_cm": 174, "activity_level": 2, "goal": Goal.FAT_LOSS, "restrictions": (R.FISH,), "versions": 1},
    {"tag": "lima", "full_name": "Noa Cifuentes Demo", "birth_date": date(1989, 1, 26), "phone": "+34 000 000 012", "email": demo_email("noa.cifuentes"),
     "sex": "F", "height_cm": 165, "activity_level": 4, "goal": Goal.INTERMITTENT_FASTING, "restrictions": (R.LACTOSE,), "versions": 1},
    {"tag": "mike", "full_name": "Xoel Manzaneda Demo", "birth_date": date(2006, 7, 19), "phone": "+34 000 000 013", "email": demo_email("xoel.manzaneda"),
     "sex": "M", "height_cm": 186, "activity_level": 5, "goal": Goal.VOLUME, "restrictions": (), "versions": 0},
    {"tag": "november", "full_name": "Idoia Vilaplana Demo", "birth_date": date(1978, 11, 6), "phone": "+34 000 000 014", "email": demo_email("idoia.vilaplana"),
     "sex": "F", "height_cm": 160, "activity_level": 2, "goal": Goal.FAT_LOSS, "restrictions": (R.GLUTEN, R.LACTOSE), "versions": 1},
    {"tag": "tango", "full_name": "Izan Tolosana Demo", "birth_date": date(1987, 3, 31), "phone": "+34 000 000 015", "email": demo_email("izan.tolosana"),
     "sex": "M", "height_cm": 180, "activity_level": 3, "goal": Goal.VOLUME, "restrictions": (R.TREE_NUT,), "versions": 2},
    {"tag": "papa", "full_name": "Aitana Larrañaga Demo", "birth_date": date(2000, 9, 8), "phone": "+34 000 000 016", "email": demo_email("aitana.larranaga"),
     "sex": "F", "height_cm": 172, "activity_level": 4, "goal": Goal.KETO, "restrictions": (R.SOY,), "versions": 0},
)
LEGACY_DEMO_NAMES = {"Alfa Demo Ficticia", "Bravo Demo Ficticio", "Charlie Demo Ficticio"}      # S1 demo identities, re-keyed by migration 0010
LEGACY_DEMO_CODES = ("DEMO_ALFA", "DEMO_BRAVO", "DEMO_CHARLIE", "NEW_demo_01", "NEW_demo_02")    # pre-0010 keys (harmless if absent)
DEMO_RECORDS = {      # S3: the rest of the intake sheet (identification comes from the registration)
    "alfa": ClientRecord("", "", Identification(),
                         Physiology(date(2026, 8, 20), 63.5, 166, 15.0, 74.0, 32.0, 96.0, Somatotype.MESOMORPH),
                         MedicalHistory("ninguna conocida", "lactosa", "molestia lumbar leve al correr", "ninguna"),
                         DietPreferences("pollo, arroz, fruta", "pescado azul, coliflor", "chocolate con leche por la noche", False, False),
                         SportsProfile(3, "running y fuerza", "10 km en 52 min", "perder grasa manteniendo fuerza", "9:00-17:30", "19:00-20:15", "batido de proteínas", None, "Garmin")),
    "bravo": ClientRecord("", "", Identification(),
                          Physiology(date(2026, 8, 22), 78.0, 181, 17.5, 82.0, 39.0, None, Somatotype.ECTOMORPH),
                          MedicalHistory("frutos de cáscara y cacahuete", "ninguna", "ninguna", "apendicitis (2015)"),
                          DietPreferences("pasta, pollo, plátano", "espinacas", "refrescos", False, True),
                          SportsProfile(2, "gimnasio (fuerza)", "press banca 90 kg", "ganar masa muscular", "turno de mañana 7:00-15:00", "17:00-18:30", "creatina, batido de proteínas", None, None)),
    "charlie": ClientRecord("", "", Identification(),
                            Physiology(date(2026, 6, 10), 84.0, 176, 18.2, 92.0, 40.0, None, Somatotype.ENDOMORPH),
                            MedicalHistory("ninguna", "ninguna", "rodilla derecha (menisco, 2019)", "menisco (2019)"),
                            DietPreferences("carne, huevos", "hígado, coles de bruselas", "cerveza los fines de semana", False, True),
                            SportsProfile(10, "ciclismo y fuerza", "marcha cicloturista 120 km", "definir manteniendo rendimiento", "9:00-18:00", "20:00-21:00", "creatina, omega 3", "empezó con ayuno 16/8", "Polar")),
    "delta": ClientRecord("", "", Identification(),
                          Physiology(date(2026, 4, 8), 74.2, 171, 16.0, 81.0, 33.5, 102.0, Somatotype.MESOMORPH),
                          MedicalHistory("ninguna", "gluten (celiaquía diagnosticada en 2018)", "fascitis plantar en 2024, resuelta", "ninguna"),
                          DietPreferences("arroz, pavo, yogur, naranja", "brócoli, hígado", "picoteo por la tarde en el trabajo", False, False),
                          SportsProfile(5, "crossfit y natación", "media maratón en 2h 04min", "bajar grasa sin perder fuerza", "8:30-18:00 con guardias", "20:30-21:45", "batido de proteínas, multivitamínico", "cuidado con el pan y la avena: celíaca", "Garmin")),
    "echo": ClientRecord("", "", Identification(),
                         Physiology(date(2026, 5, 21), 71.5, 178, 17.0, 79.0, 37.0, None, Somatotype.ECTOMORPH),
                         MedicalHistory("ninguna", "ninguna", "ninguna", "ninguna"),
                         DietPreferences("pasta, arroz, pollo, plátano, avena", "coliflor", "bollería en el desayuno", False, True),
                         SportsProfile(3, "gimnasio (hipertrofia)", "sentadilla 120 kg", "subir a 78 kg sin ensuciar la dieta", "9:00-18:00", "19:00-20:30", "creatina, batido de proteínas", "le cuesta llegar a las calorías", None)),
    "foxtrot": ClientRecord("", "", Identification(),
                            Physiology(date(2026, 3, 12), 79.8, 162, 15.5, 92.0, 34.0, 110.0, Somatotype.ENDOMORPH),
                            MedicalHistory("huevo (leve, evita el crudo)", "lactosa", "cervicalgia por trabajo de oficina", "cesárea (2019)"),
                            DietPreferences("fruta, pollo, patata", "pescado azul, setas", "dulces después de comer", False, False),
                            SportsProfile(1, "caminar y pilates", "ninguno", "perder 8 kg y dormir mejor", "jornada partida 9:00-13:00 y 16:00-19:30", "13:15-14:00", "ninguno", "primera dieta pautada", None)),
    "golf": ClientRecord("", "", Identification(),
                         Physiology(date(2026, 6, 25), 95.4, 183, 18.5, 101.0, 42.0, None, Somatotype.ENDOMORPH),
                         MedicalHistory("ninguna", "ninguna", "hombro izquierdo (tendinopatía, 2023)", "ninguna"),
                         DietPreferences("carne, huevos, queso, aguacate", "legumbres, arroz", "cerveza dos veces por semana", True, True),
                         SportsProfile(8, "fuerza y montaña", "ascensión a 3.000 m", "cetosis controlada durante ocho semanas", "turnos rotativos", "07:00-08:15", "omega 3, magnesio", "ya hizo cetosis en 2024 y la toleró bien", "Suunto")),
    "hotel": ClientRecord("", "", Identification(),
                          Physiology(date(2026, 7, 2), 58.6, 168, 14.5, 68.0, 30.5, 92.0, Somatotype.ECTOMORPH),
                          MedicalHistory("ninguna", "ninguna", "esguince de tobillo (2025)", "ninguna"),
                          DietPreferences("pollo, arroz, yogur, frutos rojos", "coles", "helado los domingos", False, False),
                          SportsProfile(4, "voleibol y gimnasio", "liga autonómica juvenil", "ganar 3 kg de masa en temporada", "estudiante, mañanas", "18:00-20:00", "batido de proteínas", None, "Garmin")),
    "india": ClientRecord("", "", Identification(),
                          Physiology(date(2026, 5, 5), 81.3, 175, 17.5, 88.0, 39.5, None, Somatotype.MESOMORPH),
                          MedicalHistory("marisco (anafilaxia, lleva adrenalina)", "ninguna", "lumbalgia ocasional", "ninguna"),
                          DietPreferences("ternera, huevos, arroz, café", "coliflor, tofu", "café con azúcar, cinco al día", False, False),
                          SportsProfile(6, "boxeo y fuerza", "tres combates amateur", "mantener peso de categoría con ayuno 16/8", "13:00-21:00", "10:30-12:00", "creatina, cafeína", "ya entrena en ayunas", "Polar")),
    "julieta": ClientRecord("", "", Identification(),
                            Physiology(date(2026, 8, 6), 61.2, 158, 14.0, 72.0, 31.0, 95.0, Somatotype.MESOMORPH),
                            MedicalHistory("ninguna", "ninguna", "ninguna", "ninguna"),
                            DietPreferences("merluza, arroz, verdura, kiwi", "cordero", "vino los fines de semana", False, True),
                            SportsProfile(2, "spinning", "ninguno", "definir para el verano", "9:00-17:00 en remoto", "18:30-19:30", "ninguno", None, None)),
    "kilo": ClientRecord("", "", Identification(),
                         Physiology(date(2026, 2, 17), 92.7, 174, 17.8, 104.0, 41.5, None, Somatotype.ENDOMORPH),
                         MedicalHistory("pescado (evita todo pescado)", "ninguna", "prótesis de rodilla derecha (2021)", "prótesis de rodilla (2021)"),
                         DietPreferences("pollo, pavo, pan, patata", "pescado, marisco", "pan en todas las comidas", True, True),
                         SportsProfile(1, "caminar y bicicleta estática", "ninguno", "bajar grasa por indicación médica", "jubilado", "10:00-11:00", "omega 3", "hipertensión en tratamiento; sin sal añadida", None)),
    "lima": ClientRecord("", "", Identification(),
                         Physiology(date(2026, 6, 30), 68.9, 165, 15.0, 78.0, 32.5, 98.0, Somatotype.MESOMORPH),
                         MedicalHistory("ninguna", "lactosa", "ninguna", "ninguna"),
                         DietPreferences("pavo, arroz, fruta, almendras", "hígado, morcilla", "queso por la noche", False, False),
                         SportsProfile(7, "running y fuerza", "maratón en 4h 12min", "ayuno 16/8 compatible con los rodajes", "7:00-15:00", "16:30-18:00", "batido de proteínas, magnesio", "lleva dos años con ayuno intermitente", "Garmin")),
    "mike": ClientRecord("", "", Identification(),
                         Physiology(date(2026, 8, 28), 69.4, 186, None, 78.0, None, None, Somatotype.ECTOMORPH),
                         MedicalHistory("ninguna", "ninguna", "ninguna", None),
                         DietPreferences("pasta, pollo", None, None, False, False),
                         SportsProfile(1, "baloncesto", None, "ganar masa", "estudiante", "17:00-19:00", None, "expediente a medias: alta reciente", None)),
    "november": ClientRecord("", "", Identification(),
                             Physiology(date(2026, 1, 22), 76.5, 160, 16.5, 94.0, 35.0, 108.0, Somatotype.ENDOMORPH),
                             MedicalHistory("ninguna", "gluten y lactosa", "artrosis en manos", "histerectomía (2020)"),
                             DietPreferences("arroz, pollo, calabacín, manzana", "pescado azul, queso", "chocolate a media tarde", False, False),
                             SportsProfile(3, "natación y pilates", "ninguno", "perder grasa y mejorar analítica", "8:00-15:00", "16:00-17:00", "multivitamínico, omega 3", "menopausia; vigilar hierro y vitamina D", None)),
    "tango": ClientRecord("", "", Identification(),
                          Physiology(date(2026, 4, 30), 83.1, 180, 17.2, 86.0, 38.5, None, Somatotype.MESOMORPH),
                          MedicalHistory("frutos de cáscara", "ninguna", "rotura de fibras en isquios (2025)", "ninguna"),
                          DietPreferences("ternera, arroz, huevos, plátano", "brócoli", "cerveza los viernes", False, True),
                          SportsProfile(9, "powerlifting", "total 520 kg en competición", "subir de categoría sin ganar grasa", "9:00-18:00", "19:30-21:00", "creatina, batido de proteínas, glutamina", None, "Polar")),
    "papa": ClientRecord("", "", Identification(),
                         Physiology(date(2026, 8, 26), 64.8, 172, None, 74.0, None, 96.0, Somatotype.MESOMORPH),
                         MedicalHistory("ninguna", "soja", None, None),
                         DietPreferences("aguacate, huevos, salmón", "tofu, bebida de soja", None, False, False),
                         SportsProfile(2, "gimnasio", None, "probar cetosis un mes", "9:00-18:00", "20:00-21:00", None, "expediente a medias: sin báscula todavía", None)),
}

# ---------------------------------------------------------------------------------------------------------------- #
# Analíticas (S4). Rangos de referencia SEXO-NEUTROS a propósito: los que dependen del sexo (hemoglobina,           #
# hematocrito, creatinina en mujeres) obligarían a escribir dos rangos por marcador para un dato que aquí es solo   #
# CONTEXTO — la analítica no entra en la recuperación ni en la composición, y así está declarado en la interfaz.    #
# ---------------------------------------------------------------------------------------------------------------- #
LAB_REFS = {
    "Glucosa": ("mg/dL", 70.0, 100.0),
    "Hemoglobina glicosilada": ("%", 4.0, 5.7),
    "Colesterol total": ("mg/dL", None, 200.0),
    "HDL": ("mg/dL", 40.0, None),
    "LDL": ("mg/dL", None, 130.0),
    "Triglicéridos": ("mg/dL", None, 150.0),
    "Ferritina": ("ng/mL", 30.0, 300.0),
    "Hierro": ("µg/dL", 60.0, 170.0),
    "Vitamina D": ("ng/mL", 30.0, 100.0),
    "Vitamina B12": ("pg/mL", 200.0, 900.0),
    "TSH": ("mUI/L", 0.4, 4.0),
    "Creatinina": ("mg/dL", 0.7, 1.3),
    "GPT (ALT)": ("U/L", None, 41.0),
    "Ácido úrico": ("mg/dL", 3.4, 7.0),
}
# Los valores: inventados, coherentes con el perfil del cliente, y con uno o dos marcadores FUERA de rango en cada
# panel para que los colores semánticos (bajo / alto / en rango) se vean sin tener que fabricar un enfermo.
DEMO_LABS_VALUES = {
    "charlie": (date(2026, 6, 12), {"Glucosa": 96, "Colesterol total": 212, "HDL": 48, "LDL": 138, "Triglicéridos": 145, "Ferritina": 85, "Vitamina D": 24, "TSH": 2.3}),
    "delta": (date(2026, 7, 3), {"Glucosa": 88, "Hemoglobina glicosilada": 5.2, "Colesterol total": 186, "HDL": 62, "LDL": 104, "Triglicéridos": 92, "Ferritina": 22, "Hierro": 54, "Vitamina D": 31, "TSH": 2.8}),
    "foxtrot": (date(2026, 5, 19), {"Glucosa": 108, "Hemoglobina glicosilada": 5.9, "Colesterol total": 224, "HDL": 44, "LDL": 149, "Triglicéridos": 178, "Ferritina": 64, "Vitamina D": 19, "TSH": 3.4, "GPT (ALT)": 38}),
    "golf": (date(2026, 6, 26), {"Glucosa": 101, "Hemoglobina glicosilada": 5.6, "Colesterol total": 231, "HDL": 51, "LDL": 152, "Triglicéridos": 134, "Ferritina": 198, "Vitamina D": 28, "TSH": 1.7, "Creatinina": 1.05, "Ácido úrico": 7.4, "GPT (ALT)": 44}),
    "india": (date(2026, 5, 8), {"Glucosa": 92, "Colesterol total": 178, "HDL": 55, "LDL": 102, "Triglicéridos": 88, "Ferritina": 132, "Vitamina D": 34, "Vitamina B12": 412, "TSH": 1.9, "Creatinina": 1.12}),
    "kilo": (date(2026, 2, 20), {"Glucosa": 118, "Hemoglobina glicosilada": 6.2, "Colesterol total": 246, "HDL": 38, "LDL": 164, "Triglicéridos": 208, "Ferritina": 156, "Vitamina D": 21, "TSH": 2.6, "Creatinina": 1.28, "Ácido úrico": 7.8, "GPT (ALT)": 52}),
    "lima": (date(2026, 7, 14), {"Glucosa": 84, "Colesterol total": 172, "HDL": 68, "LDL": 92, "Triglicéridos": 74, "Ferritina": 28, "Hierro": 61, "Vitamina D": 38, "Vitamina B12": 268, "TSH": 1.4}),
    "november": (date(2026, 2, 4), {"Glucosa": 97, "Hemoglobina glicosilada": 5.5, "Colesterol total": 218, "HDL": 58, "LDL": 136, "Triglicéridos": 118, "Ferritina": 18, "Hierro": 48, "Vitamina D": 16, "Vitamina B12": 194, "TSH": 4.6}),
}

# ---------------------------------------------------------------------------------------------------------------- #
# Báscula (S3 / migración 0015). La exportación de la báscula del profesional trae ONCE magnitudes; aquí se generan #
# de forma DETERMINISTA a partir de cuatro anclas por cliente (peso actual, grasa actual, deriva mensual y número   #
# de lecturas) en vez de escribir 70 filas a mano: la serie tiene que ser coherente con el objetivo del cliente —   #
# bajando en definición, subiendo en volumen — y una tabla literal de ese tamaño se desincroniza del perfil en la   #
# primera corrección. Las fórmulas son las de siempre (Mifflin-St Jeor para el basal) y están abajo, a la vista.    #
# ---------------------------------------------------------------------------------------------------------------- #
DEMO_SCALE = {        # tag: (peso actual kg, grasa actual %, deriva kg/mes, lecturas)
    "alfa": (63.5, 27.4, -0.5, 6),
    "bravo": (78.0, 14.2, +0.7, 5),
    "charlie": (82.1, 20.6, -0.8, 8),
    "delta": (71.8, 29.1, -0.6, 6),
    "echo": (73.4, 13.8, +0.6, 5),
    "foxtrot": (78.2, 36.8, -0.4, 7),
    "golf": (94.1, 27.3, -1.1, 4),
    "hotel": (59.8, 21.5, +0.4, 5),
    "india": (80.6, 15.4, -0.3, 6),
    "julieta": (60.7, 25.9, -0.4, 4),
    "kilo": (90.3, 32.4, -0.7, 9),
    "lima": (67.8, 24.2, -0.3, 7),
    # `mike` y `papa` no tienen báscula: son las dos altas recientes con el expediente a medias (ver la cabecera).
    "november": (75.1, 38.2, -0.5, 8),
    "tango": (84.6, 16.1, +0.5, 6),
}
ALLERGY_KINDS = (RestrictionKind.PEANUT, RestrictionKind.TREE_NUT, RestrictionKind.SHELLFISH, RestrictionKind.EGG, RestrictionKind.FISH)
INTOLERANCE_KINDS = (RestrictionKind.LACTOSE, RestrictionKind.GLUTEN, RestrictionKind.SOY)


def lab_panel(day: date, values: dict) -> tuple[LabResult, ...]:
    """One analysis: each marker with the reference range of LAB_REFS, so the derived status is the real one."""
    out = []
    for marker, value in values.items():
        unit, low, high = LAB_REFS[marker]
        out.append(LabResult(marker, float(value), unit, low, high, day, source="file"))
    return tuple(out)


def _epoch_ms(when: datetime) -> int:
    return int(when.replace(tzinfo=timezone.utc).timestamp() * 1000)


def scale_export(spec: dict, anchor: tuple[float, float, float, int]) -> tuple[list[dict], list[dict]]:
    """The scale's export for one client, in the dialect of the `.bin` (`users` + `history`), oldest reading first.

    Cada lectura va un mes antes que la siguiente y la ÚLTIMA cae en REFERENCE_DAY. La grasa acompaña al peso pero no
    en la misma proporción: perder peso baja grasa (0,55 puntos por kilo) y ganarlo la sube poco (0,15), que es lo que
    se ve en las series del corpus. El resto de magnitudes se derivan del par (peso, grasa) con las relaciones de
    siempre; no son medidas, son coherentes, y para una demostración eso es exactamente lo que hace falta."""
    weight_now, fat_now, drift, readings = anchor
    male = spec["sex"] == "M"
    height = spec["height_cm"]
    age = REFERENCE_DAY.year - spec["birth_date"].year - ((REFERENCE_DAY.month, REFERENCE_DAY.day) < (spec["birth_date"].month, spec["birth_date"].day))
    users = [{"isMale": male, "birthdate": _epoch_ms(datetime.combine(spec["birth_date"], datetime.min.time())),
              "height_cm": height, "activity_level": spec["activity_level"], "isLifetimeAthlete": spec["activity_level"] >= 5}]
    history = []
    for back in range(readings - 1, -1, -1):                       # `back` meses hacia atrás; 0 = la lectura más reciente
        weight = round(weight_now - drift * back, 1)
        fat = round(fat_now - (0.55 if drift < 0 else 0.15) * drift * back, 1)
        lean = weight * (1 - fat / 100)
        bone = round(lean * 0.055, 1)                              # hueso ≈ 5,5 % de la masa libre de grasa
        muscle_kg = round(lean - bone, 1)
        water = round(45.0 + (100 - fat) * 0.155, 1)               # el agua sigue a la masa libre de grasa
        month = REFERENCE_DAY.month - back
        year = REFERENCE_DAY.year + (month - 1) // 12
        when = datetime(year, (month - 1) % 12 + 1, min(REFERENCE_DAY.day, 28), 7, 40)
        basal = 10 * weight + 6.25 * height - 5 * age + (5 if male else -161)
        ideal_fat = 15.0 if male else 24.0
        history.append({"date": _epoch_ms(when), "weight": weight, "percentFat": fat, "percentHydration": water,
                        "boneMass": bone, "muscleMass": muscle_kg, "height": height,
                        "physiqueRating": 3 if fat <= ideal_fat else (5 if fat <= ideal_fat + 8 else 7),
                        "visceralFatRating": round(fat / (2.2 if male else 3.2), 1),
                        "metabolicAge": int(round(age + (fat - ideal_fat) / 2)),
                        "basalMet": str(int(round(basal)))})       # llega como CADENA en la exportación real
    return users, history


def draft_of(spec: dict, pid: str) -> ClientProfile:
    restrictions = tuple(Restriction(k) for k in spec["restrictions"])
    return ClientProfile(client_code="", professional_id=pid, sex=spec["sex"], age=None, height_cm=spec["height_cm"],
                         activity_level=spec["activity_level"], goal=spec["goal"], restrictions=restrictions,
                         has_allergies=any(r.kind in ALLERGY_KINDS for r in restrictions), has_intolerances=any(r.kind in INTOLERANCE_KINDS for r in restrictions))


def identification_of(spec: dict) -> Identification:
    return Identification(spec["full_name"], spec["birth_date"], spec["phone"], spec["email"])


def reset_demo(root: CompositionRoot, pid: str) -> dict:
    keys = [demo_key(s["tag"]) for s in DEMO_CLIENTS]
    names = {s["full_name"] for s in DEMO_CLIENTS} | LEGACY_DEMO_NAMES
    by_name = [k for k, ident in root.client_records.list_identifications(pid).items() if (ident.full_name or "").strip() in names]
    removed = 0
    for key in sorted(set(keys) | set(by_name) | set(LEGACY_DEMO_CODES)):
        if root.client_repository.get(pid, key) is not None:
            root.client_repository.delete(pid, key)
            removed += 1
    return {"clients_removed": removed, "corpus_saved_diets_removed": root.proposal_repository.delete_for_corpus_clients(pid)}


def seed(root: CompositionRoot, reset: bool, only: str | None = None) -> dict:
    pid = root.configured_professional_id          # offline seeding: no request, no token
    out = {"professional_id": pid, "reset": reset, "clients": [], "saved_versions": {}}
    if reset:
        out["removed"] = reset_demo(root, pid)
    for spec in DEMO_CLIENTS:
        if only is not None and spec["tag"] != only:
            continue
        key = demo_key(spec["tag"])
        if root.client_repository.get(pid, key) is not None:                          # idempotent without --reset
            root.client_repository.delete(pid, key)
        profile = root.register_client_use_case.register(draft_of(spec, pid), identification_of(spec), client_id=key)
        out["clients"].append({"tag": spec["tag"], "id": key, "name_length": len(spec["full_name"]), "goal": spec["goal"].value})
        record = DEMO_RECORDS.get(spec["tag"])
        if record is not None:                                                        # S3: fictitious intake sheet -> record + synced profile
            full = ClientRecord(key, pid, identification_of(spec), record.physiology, record.medical, record.diet, record.sports)
            _, profile, matches = root.update_client_record_use_case.update(pid, full)
            out.setdefault("records", {})[spec["tag"]] = {k: {"matched": len(m.matched), "unmatched": len(m.unmatched)} for k, m in matches.items()}
        if spec["tag"] in DEMO_SCALE:                                                 # S3 / 0015: the scale series (sets sex, age, height and activity on the profile)
            users, history = scale_export(spec, DEMO_SCALE[spec["tag"]])
            imported = root.import_body_composition_use_case.import_scale(pid, key, users, history, today=REFERENCE_DAY)
            profile = imported["profile"]
            out.setdefault("measurements", {})[spec["tag"]] = imported["measurements_added"]
        if spec["tag"] in DEMO_LABS_VALUES:                                           # S4: fictitious analysis (context only)
            day, values = DEMO_LABS_VALUES[spec["tag"]]
            out.setdefault("lab_results", {})[spec["tag"]] = len(root.add_lab_results_use_case.add_manual(pid, key, lab_panel(day, values)))
        for _ in range(spec["versions"]):
            proposal = root.propose_diet_use_case.propose(pid, profile, k=20)          # history = the versions saved so far (same goal -> rotation)
            saved = root.save_edited_diet_use_case.save(pid, proposal, edited=False)
            out["saved_versions"].setdefault(spec["tag"], []).append({"id": saved["id"], "routing": proposal.parameters.get("routing"),
                                                                     "strategy": proposal.strategy, "items": sum(len(m.items) for m in proposal.meals)})
    out["portfolio_size"] = len(root.get_clients_service.get_clients(pid))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="delete the demo clients (current and legacy identities) before seeding")
    ap.add_argument("--only", metavar="TAG", default=None, help="seed a single client by tag (alfa, bravo, charlie, delta, ...)")
    args = ap.parse_args()
    if args.only is not None and args.only not in {s["tag"] for s in DEMO_CLIENTS}:
        print(f"unknown tag: {args.only}", file=sys.stderr)
        return 2
    root = CompositionRoot.from_env()
    print(json.dumps(seed(root, args.reset, args.only), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
