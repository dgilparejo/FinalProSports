/** Constants of the `app-input` design-system wrapper; the component extends this class. */
export class InputConstants {
  static readonly TYPES = ['text', 'number', 'email', 'tel', 'date'] as const;
  static readonly DEFAULT_TYPE = 'text';
  static readonly NUMBER_STEP = 'any';
}
