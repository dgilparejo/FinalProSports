import { Injectable, signal } from '@angular/core';

/** Minimal own logger (replaces @w2m/npm-logger): console in development plus the last user-facing error as a signal for the shell. */
@Injectable({ providedIn: 'root' })
export class LoggerService {
  readonly lastError = signal<string | null>(null);

  info(message: string, ...data: unknown[]): void {
    console.info(`[fps] ${message}`, ...data);
  }

  warn(message: string, ...data: unknown[]): void {
    console.warn(`[fps] ${message}`, ...data);
  }

  error(message: string, ...data: unknown[]): void {
    console.error(`[fps] ${message}`, ...data);
    this.lastError.set(message);
  }

  clearError(): void {
    this.lastError.set(null);
  }
}
