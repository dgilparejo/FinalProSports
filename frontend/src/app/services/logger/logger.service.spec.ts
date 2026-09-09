import { TestBed } from '@angular/core/testing';

import { LoggerService } from './logger.service';

describe('LoggerService', () => {
  it('keeps the last error as a signal and clears it', () => {
    const logger = TestBed.inject(LoggerService);
    spyOn(console, 'error');
    logger.error('algo falló');
    expect(logger.lastError()).toBe('algo falló');
    logger.clearError();
    expect(logger.lastError()).toBeNull();
  });
});
