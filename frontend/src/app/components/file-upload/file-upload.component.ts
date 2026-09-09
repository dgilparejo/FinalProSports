import { Component, input, output, signal } from '@angular/core';

import { FileUploadConstants } from '@models/components/file-upload';

import { ButtonComponent } from '../button/button.component';

export interface UploadedFile {
  name: string;
  content: string;
}

/** Reads a local text file (CSV / JSON) in the browser and emits its content; the backend never receives multipart. */
@Component({
  selector: 'app-file-upload',
  imports: [ButtonComponent],
  template: `
    <label class="upload">
      <input type="file" [accept]="accept()" (change)="onFile($event)" hidden #file />
      <app-button [variant]="variant()" [icon]="'upload_file'" (clicked)="file.click()">{{ label() }}</app-button>
      @if (fileName()) {
        <span class="muted small">{{ fileName() }}</span>
      }
      @if (error()) {
        <span class="tone-danger small">{{ error() }}</span>
      }
    </label>
  `,
  styles: `
    :host {
      display: inline-block;
    }
    .upload {
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }
  `,
})
export class FileUploadComponent extends FileUploadConstants {
  readonly label = input('Importar fichero');
  readonly accept = input<string>(FileUploadConstants.ACCEPT_TEXT);
  readonly variant = input<'primary' | 'secondary' | 'ghost'>('secondary');
  readonly loaded = output<UploadedFile>();
  readonly fileName = signal<string | null>(null);
  readonly error = signal<string | null>(null);

  onFile(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.error.set(null);
    if (file.size > FileUploadConstants.MAX_BYTES) {
      this.error.set('fichero demasiado grande');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      this.fileName.set(file.name);
      this.loaded.emit({ name: file.name, content: String(reader.result ?? '') });
    };
    reader.readAsText(file);
    (event.target as HTMLInputElement).value = '';
  }
}
