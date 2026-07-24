import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { TranslateService } from '@ngx-translate/core';
import { ThemeService } from './core/services/theme.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet],
  template: '<router-outlet />'
})
export class AppComponent {
  private theme = inject(ThemeService);

  constructor(private translate: TranslateService) {
  this.translate.setDefaultLang('fr');
  this.translate.use('fr');
  this.theme.init();
}
}
