import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';

import { FileUploadComponent } from './file-upload.component';

describe('FileUploadComponent', () => {
  it('reads the chosen text file and emits its content', (done) => {
    TestBed.configureTestingModule({ imports: [FileUploadComponent], providers: [provideNoopAnimations()] });
    const fixture = TestBed.createComponent(FileUploadComponent);
    fixture.detectChanges();
    fixture.componentInstance.loaded.subscribe((f) => {
      expect(f.name).toBe('analitica.csv');
      expect(f.content).toContain('Glucosa;92');
      expect(fixture.componentInstance.fileName()).toBe('analitica.csv');
      done();
    });
    const input: HTMLInputElement = fixture.nativeElement.querySelector('input[type=file]');
    const file = new File(['Marcador;Valor\nGlucosa;92\n'], 'analitica.csv', { type: 'text/csv' });
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    input.dispatchEvent(new Event('change'));
  });
});
