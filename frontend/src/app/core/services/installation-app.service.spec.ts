import { TestBed } from '@angular/core/testing';

import { AppModeService } from './app-mode.service';
import { InstallationAppService } from './installation-app.service';

/**
 * Le bouton « Installer l'app » n'existe qu'en cloud, n'apparaît que quand
 * le navigateur propose l'installation, et disparaît une fois l'app installée.
 */
describe('InstallationAppService', () => {
  function creer(mode: 'local' | 'cloud'): InstallationAppService {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [{ provide: AppModeService, useValue: {
        isCloud: () => mode === 'cloud', isLocal: () => mode === 'local',
      } }],
    });
    return TestBed.inject(InstallationAppService);
  }

  function invite(outcome: 'accepted' | 'dismissed') {
    const e = new Event('beforeinstallprompt', { cancelable: true }) as any;
    e.prompt = vi.fn().mockResolvedValue(undefined);
    e.userChoice = Promise.resolve({ outcome });
    return e;
  }

  it("mode local : l'invite du navigateur est ignorée", () => {
    const s = creer('local');
    window.dispatchEvent(invite('accepted'));
    expect(s.disponible()).toBe(false);
  });

  it("mode cloud : l'invite est retenue et le bouton s'affiche", () => {
    const s = creer('cloud');
    const e = invite('accepted');
    window.dispatchEvent(e);
    expect(e.defaultPrevented).toBe(true);
    expect(s.disponible()).toBe(true);
  });

  it("accepter l'installation masque le bouton", async () => {
    const s = creer('cloud');
    const e = invite('accepted');
    window.dispatchEvent(e);
    expect(await s.installer()).toBe(true);
    expect(e.prompt).toHaveBeenCalled();
    expect(s.disponible()).toBe(false);
  });

  it("refuser consomme l'invite (le navigateur en réémettra une)", async () => {
    const s = creer('cloud');
    window.dispatchEvent(invite('dismissed'));
    expect(await s.installer()).toBe(false);
    expect(s.disponible()).toBe(false);
    window.dispatchEvent(invite('accepted'));
    expect(s.disponible()).toBe(true);
  });

  it("l'événement appinstalled masque le bouton", () => {
    const s = creer('cloud');
    window.dispatchEvent(invite('accepted'));
    window.dispatchEvent(new Event('appinstalled'));
    expect(s.disponible()).toBe(false);
  });
});
