import { Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class AppModeService {
  readonly mode = environment.mode;

  isLocal(): boolean {
    return this.mode === 'local';
  }

  isCloud(): boolean {
    return this.mode === 'cloud';
  }
}
