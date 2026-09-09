/** Constants of the `app-button` design-system wrapper; the component extends this class. */
export class ButtonConstants {
  static readonly VARIANTS = ['primary', 'secondary', 'ghost', 'danger', 'icon'] as const;
  static readonly DEFAULT_VARIANT = 'secondary';
  static readonly DEFAULT_TYPE: 'button' | 'submit' = 'button';
}
