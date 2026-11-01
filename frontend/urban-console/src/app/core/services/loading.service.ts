import { Injectable, signal, computed } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class LoadingService {
  private activeRequests = signal<number>(0);
  private explicitLoading = signal<boolean>(false);
  private loadingMessage = signal<string>('Loading municipal data...');

  /** Reactive boolean whether global loader is active */
  readonly isLoading = computed(() => this.activeRequests() > 0 || this.explicitLoading());

  /** Reactive message displayed in the loader */
  readonly message = computed(() => this.loadingMessage());

  /** Set display message without incrementing active request counter */
  setMessage(message: string): void {
    this.loadingMessage.set(message);
  }

  /** Increment HTTP or background async request counter */
  show(message?: string): void {
    if (message) {
      this.loadingMessage.set(message);
    }
    this.activeRequests.update((count) => count + 1);
  }

  /** Decrement request counter */
  hide(): void {
    this.activeRequests.update((count) => Math.max(0, count - 1));
    if (this.activeRequests() === 0 && !this.explicitLoading()) {
      this.loadingMessage.set('Loading municipal data...');
    }
  }

  /** Explicit manual lock for components */
  setLoading(state: boolean, message?: string): void {
    if (message) {
      this.loadingMessage.set(message);
    }
    this.explicitLoading.set(state);
    if (!state && this.activeRequests() === 0) {
      this.loadingMessage.set('Loading municipal data...');
    }
  }

  /** Reset all loading states */
  reset(): void {
    this.activeRequests.set(0);
    this.explicitLoading.set(false);
    this.loadingMessage.set('Loading municipal data...');
  }
}
