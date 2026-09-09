/** Constants of the `app-confirm-modal` design-system wrapper; the component extends this class. */
export class ConfirmModalConstants {
  static readonly WIDTH = '420px';
  /** Material's own cap is 80vw, which on a 360 px phone leaves a 288 px dialog; the content deserves the screen. */
  static readonly MAX_WIDTH = '95vw';
  static readonly CONFIRM_KEY = 'common.confirm';
  static readonly CANCEL_KEY = 'common.cancel';
}
