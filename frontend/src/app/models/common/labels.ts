// Spanish labels of the corpus data values (goals, restrictions, slots). Identifiers in English, values as served by the API.

export interface Option<T = string> {
  value: T;
  label: string;
}

export const GOALS: Option[] = [
  { value: 'volumen_masa', label: 'Volumen / ganancia de masa' },
  { value: 'definicion_grasa', label: 'Definición / pérdida de grasa' },
  { value: 'ayuno_intermitente', label: 'Ayuno intermitente' },
  { value: 'descarga_carga', label: 'Descarga / carga de hidratos' },
  { value: 'cetosis_keto', label: 'Cetosis (keto)' },
  { value: 'hipocalorica', label: 'Hipocalórica' },
  { value: 'alta_en_fibra', label: 'Alta en fibra' },
  { value: 'mantenimiento', label: 'Mantenimiento' },
];

export const RESTRICTIONS: Option[] = [
  { value: 'contains_lactose', label: 'Lactosa' },
  { value: 'contains_gluten', label: 'Gluten' },
  { value: 'contains_soy', label: 'Soja' },
  { value: 'contains_shellfish', label: 'Marisco' },
  { value: 'contains_egg', label: 'Huevo' },
  { value: 'contains_fish', label: 'Pescado' },
  { value: 'is_peanut', label: 'Cacahuete' },
  { value: 'is_tree_nut', label: 'Frutos de cáscara' },
  { value: 'is_alcohol', label: 'Alcohol' },
  { value: 'is_stimulant', label: 'Estimulantes' },
];

export const SLOTS: Option[] = [
  { value: 'DESAYUNO', label: 'Desayuno' },
  { value: 'MEDIA MAÑANA', label: 'Media mañana' },
  { value: 'ALMUERZO', label: 'Almuerzo' },
  { value: 'COMIDA', label: 'Comida' },
  { value: 'MERIENDA', label: 'Merienda' },
  { value: 'ANTES DE ENTRENAR', label: 'Antes de entrenar' },
  { value: 'DESPUES DE ENTRENAR', label: 'Después de entrenar' },
  { value: 'CENA', label: 'Cena' },
  { value: 'RECENA', label: 'Recena' },
  { value: 'BATIDO', label: 'Batido' },
  { value: 'OTHER', label: 'Otras' },
];

export const UNITS: Option[] = [
  { value: 'g', label: 'g' },
  { value: 'ml', label: 'ml' },
  { value: 'unidad', label: 'unidad' },
  { value: 'cucharada', label: 'cucharada' },
  { value: 'cucharadita', label: 'cucharadita' },
  { value: 'lata', label: 'lata' },
  { value: 'loncha', label: 'loncha' },
  { value: 'puñado', label: 'puñado' },
  { value: 'diente', label: 'diente' },
  { value: 'chorrito', label: 'chorrito' },
  { value: 'cazo', label: 'cazo' },
  { value: 'cápsula', label: 'cápsula' },
  { value: '', label: '—' },
];

export const FOOD_GROUPS: Option[] = [
  { value: 'PROTEIN', label: 'Proteína' },
  { value: 'CARB', label: 'Hidratos' },
  { value: 'FAT', label: 'Grasa' },
  { value: 'VEGETABLE', label: 'Verdura' },
  { value: 'FRUIT', label: 'Fruta' },
  { value: 'DAIRY', label: 'Lácteo' },
  { value: 'SUPPLEMENT', label: 'Suplemento' },
  { value: 'BEVERAGE', label: 'Bebida' },
  { value: 'CONDIMENT', label: 'Condimento' },
  { value: 'OTHER', label: 'Otro' },
];

export const FLAG_LABELS: Record<string, string> = {
  is_processed_sugar: 'Azúcar procesado',
  is_soft_drink: 'Refresco / bebida con sabor',
  is_salt: 'Sal',
  is_fasting_compatible: 'Compatible con el ayuno',
  is_alcohol: 'Alcohol',
  is_stimulant: 'Estimulante',
  is_peanut: 'Cacahuete',
  is_tree_nut: 'Frutos de cáscara',
  contains_lactose: 'Contiene lactosa',
  contains_gluten: 'Contiene gluten',
  contains_soy: 'Contiene soja',
  contains_shellfish: 'Contiene marisco',
  contains_egg: 'Contiene huevo',
  contains_fish: 'Contiene pescado',
};
export const RULE_FLAGS = ['is_processed_sugar', 'is_soft_drink', 'is_salt', 'is_fasting_compatible', 'is_alcohol', 'is_stimulant'];
export const ALLERGEN_FLAGS = [
  'is_peanut',
  'is_tree_nut',
  'contains_lactose',
  'contains_gluten',
  'contains_soy',
  'contains_shellfish',
  'contains_egg',
  'contains_fish',
];

export const ROUTING_LABELS: Record<string, string> = {
  cold_start: 'Cliente nuevo: consenso de casos',
  same_goal: 'Mismo objetivo: rotación de la versión anterior',
  goal_changed: 'Cambio de objetivo: consenso del arquetipo',
};

export function goalLabel(value: string | null | undefined): string {
  return GOALS.find((g) => g.value === value)?.label ?? value ?? '—';
}
export function restrictionLabel(value: string): string {
  return RESTRICTIONS.find((r) => r.value === value)?.label ?? value;
}
export function slotLabel(value: string): string {
  return SLOTS.find((s) => s.value === value)?.label ?? value;
}
export function groupLabel(value: string | null | undefined): string {
  return FOOD_GROUPS.find((g) => g.value === value)?.label ?? value ?? '—';
}
export function reasonLabel(reason: string): string {
  if (reason.startsWith('restriction:')) return `restricción declarada (${restrictionLabel(reason.split(':')[1])})`;
  if (reason.startsWith('preference:')) return 'gusto negativo del cliente';
  if (reason.startsWith('rule:')) return `regla del profesional ${reason.split(':')[1]}`;
  return reason;
}
